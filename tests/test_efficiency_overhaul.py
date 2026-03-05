"""Tests for Phase 1 efficiency overhaul: negative caching, domain stats, adaptive ordering."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import ProviderName
from data.models import (
    EnrichmentType, VerificationStatus, CampaignStatus,
    EnrichmentResult,
)
from providers.base import ProviderResponse
from enrichment.waterfall import WaterfallOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orchestrator(
    provider_responses: dict[ProviderName, ProviderResponse | Exception] | None = None,
    budget_can_spend: bool = True,
    cost_tracker: object | None = None,
    waterfall_order: list[ProviderName] | None = None,
    domain_skip: dict[tuple[str, str], bool] | None = None,
):
    """Build a WaterfallOrchestrator with mocked dependencies."""
    db = AsyncMock()
    db.cache_get = AsyncMock(return_value=None)
    db.cache_set = AsyncMock()
    db.save_enrichment_result = AsyncMock()
    db.save_enrichment_atomic = AsyncMock()
    db.log_action = AsyncMock()
    db.upsert_person = AsyncMock(return_value=MagicMock(id="person-1"))
    db.upsert_company = AsyncMock()
    db.get_person_by_name_domain = AsyncMock(return_value=None)
    db.get_campaign = AsyncMock(return_value=None)
    db.wal_checkpoint = AsyncMock()
    db.record_provider_domain_attempt = AsyncMock()

    # Domain skip logic: configurable per (provider, domain) pair
    if domain_skip:
        async def _should_skip(provider, domain, min_attempts=5):
            return domain_skip.get((provider.lower(), domain.lower()), False)
        db.should_skip_provider_for_domain = AsyncMock(side_effect=_should_skip)
    else:
        db.should_skip_provider_for_domain = AsyncMock(return_value=False)

    providers = {}
    for pname in [ProviderName.APOLLO, ProviderName.ICYPEAS, ProviderName.FINDYMAIL]:
        mock_prov = AsyncMock()
        if provider_responses and pname in provider_responses:
            resp = provider_responses[pname]
            if isinstance(resp, Exception):
                mock_prov.find_email.side_effect = resp
            else:
                mock_prov.find_email.return_value = resp
        else:
            mock_prov.find_email.return_value = ProviderResponse(found=False, credits_used=1.0)
        mock_prov.search_companies.return_value = []
        mock_prov.search_people.return_value = []
        mock_prov.enrich_company.return_value = ProviderResponse(found=False)
        providers[pname] = mock_prov

    pattern_engine = AsyncMock()
    pattern_engine.try_pattern_match = AsyncMock(return_value=None)

    budget = AsyncMock()
    budget.can_spend = AsyncMock(return_value=budget_can_spend)

    circuit_breakers = {
        pname: MagicMock(can_execute=MagicMock(return_value=True),
                         record_success=MagicMock(),
                         record_failure=MagicMock())
        for pname in providers
    }

    rate_limiters = {pname: AsyncMock(acquire=AsyncMock()) for pname in providers}

    orch = WaterfallOrchestrator(
        db=db,
        providers=providers,
        pattern_engine=pattern_engine,
        budget=budget,
        circuit_breakers=circuit_breakers,
        rate_limiters=rate_limiters,
        cost_tracker=cost_tracker,
        waterfall_order=waterfall_order,
    )
    return orch


# ---------------------------------------------------------------------------
# Negative Caching Tests
# ---------------------------------------------------------------------------

class TestNegativeCaching:
    @pytest.mark.asyncio
    async def test_cache_set_called_on_miss(self):
        """When a provider returns found=False, cache_set should be called with found=False."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(found=False, credits_used=1.0),
            ProviderName.ICYPEAS: ProviderResponse(found=False, credits_used=1.0),
            ProviderName.FINDYMAIL: ProviderResponse(found=False, credits_used=1.0),
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        await orch.enrich_single(row)

        # cache_set should have been called with found=False for each provider miss
        cache_set_calls = orch.db.cache_set.call_args_list
        negative_cache_calls = [
            c for c in cache_set_calls
            if c.kwargs.get("found") is False or
            (len(c.args) > 0 and any(isinstance(a, bool) and not a for a in c.args))
        ]
        assert len(negative_cache_calls) >= 1, (
            f"Expected negative cache writes, got cache_set calls: {cache_set_calls}"
        )

    @pytest.mark.asyncio
    async def test_negative_cache_uses_short_ttl(self):
        """Negative cache entries should use a shorter TTL (7 days)."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(found=False, credits_used=1.0),
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        await orch.enrich_single(row)

        # Find cache_set calls with found=False
        for call in orch.db.cache_set.call_args_list:
            if call.kwargs.get("found") is False:
                assert call.kwargs.get("ttl_days") == 7, (
                    f"Expected ttl_days=7 for negative cache, got {call.kwargs}"
                )

    @pytest.mark.asyncio
    async def test_positive_cache_hit_returns_result(self):
        """When cache has a positive hit, it should return immediately."""
        orch = _make_orchestrator()
        orch.db.cache_get = AsyncMock(return_value={
            "found": True,
            "email": "cached@acme.com",
            "verification_status": "verified",
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        result = await orch.enrich_single(row)

        assert result.found is True
        # Providers should NOT have been called
        for prov in orch.providers.values():
            prov.find_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_negative_cache_does_not_short_circuit(self):
        """A cached miss (found=False) should NOT prevent trying providers."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(
                found=True, email="john@acme.com", credits_used=1.0,
                data={"email": "john@acme.com"},
            ),
        })
        # Cache returns a negative hit
        orch.db.cache_get = AsyncMock(return_value={"found": False, "email": None})

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        result = await orch.enrich_single(row)

        # The provider should still have been called despite negative cache
        assert result.found is True


# ---------------------------------------------------------------------------
# Domain Stats Tests
# ---------------------------------------------------------------------------

class TestDomainStats:
    @pytest.mark.asyncio
    async def test_domain_attempt_recorded_on_hit(self):
        """A successful find_email records a domain hit."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(
                found=True, email="john@acme.com", credits_used=1.0,
                data={"email": "john@acme.com"},
            ),
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        await orch.enrich_single(row)

        # record_provider_domain_attempt should be called with hit=True
        orch.db.record_provider_domain_attempt.assert_called()
        call_args = orch.db.record_provider_domain_attempt.call_args
        assert call_args.kwargs.get("hit") is True or call_args.args[2] is True

    @pytest.mark.asyncio
    async def test_domain_attempt_recorded_on_miss(self):
        """A failed find_email records a domain miss."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(found=False, credits_used=1.0),
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        await orch.enrich_single(row)

        # record_provider_domain_attempt should be called with hit=False
        calls = orch.db.record_provider_domain_attempt.call_args_list
        assert len(calls) >= 1
        # At least one call should have hit=False
        has_miss = any(
            c.kwargs.get("hit") is False or (len(c.args) >= 3 and c.args[2] is False)
            for c in calls
        )
        assert has_miss, f"Expected at least one miss recorded, got: {calls}"

    @pytest.mark.asyncio
    async def test_provider_skipped_when_domain_exhausted(self):
        """Provider is skipped when domain stats show 0 hits over 5+ attempts."""
        orch = _make_orchestrator(
            provider_responses={
                ProviderName.APOLLO: ProviderResponse(
                    found=True, email="john@acme.com", credits_used=1.0,
                    data={"email": "john@acme.com"},
                ),
                ProviderName.ICYPEAS: ProviderResponse(
                    found=True, email="john@acme.com", credits_used=1.0,
                    data={"email": "john@acme.com"},
                ),
                ProviderName.FINDYMAIL: ProviderResponse(
                    found=True, email="john@acme.com", credits_used=1.0,
                    data={"email": "john@acme.com"},
                ),
            },
            domain_skip={
                ("apollo", "exhausted.com"): True,
                ("icypeas", "exhausted.com"): True,
                ("findymail", "exhausted.com"): True,
            },
        )

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "exhausted.com"}
        result = await orch.enrich_single(row)

        # All providers skipped for this domain — result is not found
        assert result.found is False

    @pytest.mark.asyncio
    async def test_provider_not_skipped_for_fresh_domain(self):
        """Provider is NOT skipped when domain has no stats."""
        orch = _make_orchestrator(
            provider_responses={
                ProviderName.APOLLO: ProviderResponse(
                    found=True, email="john@fresh.com", credits_used=1.0,
                    data={"email": "john@fresh.com"},
                ),
            },
        )

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "fresh.com"}
        result = await orch.enrich_single(row)

        assert result.found is True


# ---------------------------------------------------------------------------
# Adaptive Waterfall Ordering Tests
# ---------------------------------------------------------------------------

class TestAdaptiveOrdering:
    @pytest.mark.asyncio
    async def test_adaptive_order_applied_from_cost_tracker(self):
        """When cost_tracker recommends a new order, it is applied."""
        cost_tracker = AsyncMock()
        recommended = [ProviderName.FINDYMAIL, ProviderName.ICYPEAS, ProviderName.APOLLO]
        cost_tracker.get_waterfall_recommendation = AsyncMock(return_value=recommended)

        orch = _make_orchestrator(cost_tracker=cost_tracker)

        rows = [{"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}]
        await orch.enrich_batch(rows, campaign_id="c-1")

        # Adaptive order should have been set
        assert orch._adaptive_order == recommended

        # Log action for reordering should have been called
        log_calls = orch.db.log_action.call_args_list
        reorder_calls = [c for c in log_calls if c.kwargs.get("action") == "waterfall_reorder"]
        assert len(reorder_calls) >= 1

    @pytest.mark.asyncio
    async def test_no_adaptive_order_when_no_recommendation(self):
        """When cost_tracker returns None, adaptive order is not set."""
        cost_tracker = AsyncMock()
        cost_tracker.get_waterfall_recommendation = AsyncMock(return_value=None)

        orch = _make_orchestrator(cost_tracker=cost_tracker)

        rows = [{"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}]
        await orch.enrich_batch(rows, campaign_id="c-1")

        assert orch._adaptive_order is None

    @pytest.mark.asyncio
    async def test_no_adaptive_order_without_cost_tracker(self):
        """When cost_tracker is None, adaptive order is not attempted."""
        orch = _make_orchestrator(cost_tracker=None)

        rows = [{"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}]
        await orch.enrich_batch(rows, campaign_id="c-1")

        assert orch._adaptive_order is None

    @pytest.mark.asyncio
    async def test_configured_order_used_as_fallback(self):
        """When no adaptive order, configured order is used."""
        custom_order = [ProviderName.FINDYMAIL, ProviderName.APOLLO, ProviderName.ICYPEAS]
        orch = _make_orchestrator(waterfall_order=custom_order)

        assert orch._configured_order == custom_order
        assert orch._adaptive_order is None


# ---------------------------------------------------------------------------
# Row Status Bug Fix Tests
# ---------------------------------------------------------------------------

class TestRowStatusBugFix:
    @pytest.mark.asyncio
    async def test_not_found_row_marked_failed(self):
        """When enrichment returns not found, row status should be 'failed' not 'complete'."""
        orch = _make_orchestrator()  # all providers return found=False
        orch.db.update_campaign_row = AsyncMock()
        orch.db.update_campaign_status = AsyncMock()

        rows = [{"first_name": "Nobody", "last_name": "Here", "company_domain": "unknown.com"}]
        row_ids = ["row-1"]
        await orch.enrich_batch(
            rows, campaign_id="c-1", campaign_row_ids=row_ids,
        )

        # Check that update_campaign_row was called with "failed"
        update_calls = orch.db.update_campaign_row.call_args_list
        status_calls = [c for c in update_calls if c.args[1] in ("complete", "failed")]
        assert len(status_calls) >= 1
        # The final status for a not-found row should be "failed"
        final_call = status_calls[-1]
        assert final_call.args[1] == "failed"

    @pytest.mark.asyncio
    async def test_found_row_marked_complete(self):
        """When enrichment returns found, row status should be 'complete'."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(
                found=True, email="john@acme.com", credits_used=1.0,
                data={"email": "john@acme.com"},
            ),
        })
        orch.db.update_campaign_row = AsyncMock()
        orch.db.update_campaign_status = AsyncMock()

        rows = [{"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}]
        row_ids = ["row-1"]
        await orch.enrich_batch(
            rows, campaign_id="c-1", campaign_row_ids=row_ids,
        )

        update_calls = orch.db.update_campaign_row.call_args_list
        status_calls = [c for c in update_calls if c.args[1] in ("complete", "failed")]
        assert len(status_calls) >= 1
        final_call = status_calls[-1]
        assert final_call.args[1] == "complete"


# ---------------------------------------------------------------------------
# Database Integration Tests (provider_domain_stats)
# ---------------------------------------------------------------------------

class TestDomainStatsDB:
    """Integration tests that use a real Database against an in-memory SQLite."""

    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "test.db")

    @pytest.mark.asyncio
    async def test_record_and_skip(self, db_path):
        """Record 5 misses, then should_skip returns True."""
        from data.database import Database
        db = Database(db_path)

        for _ in range(5):
            await db.record_provider_domain_attempt("apollo", "deadend.com", hit=False)

        should_skip = await db.should_skip_provider_for_domain("apollo", "deadend.com")
        assert should_skip is True

    @pytest.mark.asyncio
    async def test_no_skip_under_threshold(self, db_path):
        """Under 5 attempts, should_skip returns False even with 0 hits."""
        from data.database import Database
        db = Database(db_path)

        for _ in range(3):
            await db.record_provider_domain_attempt("apollo", "young.com", hit=False)

        should_skip = await db.should_skip_provider_for_domain("apollo", "young.com")
        assert should_skip is False

    @pytest.mark.asyncio
    async def test_no_skip_with_hits(self, db_path):
        """If there are hits, should_skip returns False even with many attempts."""
        from data.database import Database
        db = Database(db_path)

        for _ in range(8):
            await db.record_provider_domain_attempt("apollo", "good.com", hit=False)
        await db.record_provider_domain_attempt("apollo", "good.com", hit=True)

        should_skip = await db.should_skip_provider_for_domain("apollo", "good.com")
        assert should_skip is False

    @pytest.mark.asyncio
    async def test_no_skip_unknown_domain(self, db_path):
        """Unknown domain returns False."""
        from data.database import Database
        db = Database(db_path)

        should_skip = await db.should_skip_provider_for_domain("apollo", "unknown.com")
        assert should_skip is False

    @pytest.mark.asyncio
    async def test_case_insensitive(self, db_path):
        """Provider and domain are normalized to lowercase."""
        from data.database import Database
        db = Database(db_path)

        for _ in range(5):
            await db.record_provider_domain_attempt("Apollo", "DeadEnd.COM", hit=False)

        should_skip = await db.should_skip_provider_for_domain("apollo", "deadend.com")
        assert should_skip is True
