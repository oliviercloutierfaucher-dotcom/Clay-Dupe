"""Tests for waterfall edge cases: all providers fail, mid-cascade timeout, budget exhaustion."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from config.settings import ProviderName
from data.models import (
    EnrichmentType, VerificationStatus, CampaignStatus,
    Campaign, EnrichmentResult,
)
from providers.base import ProviderResponse
from enrichment.waterfall import WaterfallOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orchestrator(
    provider_responses: dict[ProviderName, ProviderResponse | Exception] | None = None,
    budget_can_spend: bool = True,
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
    )
    return orch


# ---------------------------------------------------------------------------
# Scenario 1: All providers fail on a single row
# ---------------------------------------------------------------------------

class TestAllProvidersFail:
    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_not_found(self):
        """When every provider raises an exception, result is not_found."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "https://x"),
                response=httpx.Response(500, request=httpx.Request("POST", "https://x")),
            ),
            ProviderName.ICYPEAS: httpx.TimeoutException("timeout"),
            ProviderName.FINDYMAIL: OSError("connection reset"),
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        result = await orch.enrich_single(row)

        assert result.found is False
        assert result.enrichment_type == EnrichmentType.EMAIL

    @pytest.mark.asyncio
    async def test_all_providers_not_found_graceful(self):
        """When all providers return found=False, result is graceful not_found."""
        orch = _make_orchestrator()  # default: all return found=False
        row = {"first_name": "Nobody", "last_name": "Here", "company_domain": "unknown.com"}
        result = await orch.enrich_single(row)

        assert result.found is False


# ---------------------------------------------------------------------------
# Scenario 2: Mid-cascade timeout
# ---------------------------------------------------------------------------

class TestMidCascadeTimeout:
    @pytest.mark.asyncio
    async def test_timeout_on_second_provider_continues(self):
        """If the second provider times out, third provider still runs."""
        orch = _make_orchestrator(provider_responses={
            ProviderName.APOLLO: ProviderResponse(found=False, credits_used=1.0),
            ProviderName.ICYPEAS: httpx.TimeoutException("timeout"),
            ProviderName.FINDYMAIL: ProviderResponse(
                found=True, email="john@acme.com", credits_used=1.0,
                data={"email": "john@acme.com"},
            ),
        })

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        result = await orch.enrich_single(row)

        assert result.found is True
        assert result.cost_credits >= 1.0  # at least findymail credit


# ---------------------------------------------------------------------------
# Scenario 3: Budget exhaustion mid-batch
# ---------------------------------------------------------------------------

class TestBudgetExhaustionMidBatch:
    @pytest.mark.asyncio
    async def test_budget_exhausted_skips_paid_steps(self):
        """When budget is exhausted, paid steps are skipped gracefully."""
        orch = _make_orchestrator(budget_can_spend=False)

        row = {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"}
        result = await orch.enrich_single(row)

        assert result.found is False
        # Budget refusal means no credits consumed
        assert result.cost_credits == 0.0


# ---------------------------------------------------------------------------
# Scenario 4: Unroutable row
# ---------------------------------------------------------------------------

class TestUnroutableRow:
    @pytest.mark.asyncio
    async def test_empty_row_is_unroutable(self):
        """A row with no useful fields returns not_found."""
        orch = _make_orchestrator()
        result = await orch.enrich_single({})

        assert result.found is False


# ---------------------------------------------------------------------------
# Scenario 5: Batch with pause
# ---------------------------------------------------------------------------

class TestBatchPause:
    @pytest.mark.asyncio
    async def test_batch_stops_on_pause(self):
        """Batch loop stops when campaign status becomes PAUSED."""
        orch = _make_orchestrator()
        # Make get_campaign return PAUSED after first chunk
        campaign = MagicMock()
        campaign.status = CampaignStatus.PAUSED
        orch.db.get_campaign = AsyncMock(return_value=campaign)
        orch.db.update_campaign_status = AsyncMock()

        rows = [{"first_name": f"P{i}", "last_name": "L", "company_domain": "x.com"}
                for i in range(200)]
        results = await orch.enrich_batch(rows, campaign_id="c-1", chunk_size=50)

        # Should have stopped before processing all 200 rows
        assert len(results) < 200
