"""Waterfall orchestrator -- the heart of the enrichment pipeline.

Coordinates cache lookups, row classification, provider sequencing,
pattern matching, budget checks, circuit breakers, rate limiting,
and result persistence for single and batch enrichment runs.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time

import aiometer
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cost.budget import BudgetManager
    from data.database import Database
    from enrichment.pattern_engine import PatternEngine
    from providers.base import BaseProvider

from config.settings import ProviderName
from data.models import (
    Company,
    EnrichmentResult,
    EnrichmentType,
    Person,
    RouteCategory,
    VerificationStatus,
)
from enrichment.classifier import classify_row, detect_fields, split_full_name
from enrichment.router import get_provider_sequence
from providers.base import ProviderResponse
from quality.circuit_breaker import CircuitBreaker, SlidingWindowRateLimiter
from quality.confidence import calculate_confidence

logger = logging.getLogger(__name__)

# Maximum concurrent enrichments in a batch run.
_DEFAULT_BATCH_CONCURRENCY = 5


class WaterfallOrchestrator:
    """Drives enrichment through a waterfall of providers.

    The orchestrator owns the full pipeline for a single row:

    1. Check the local cache for a prior result.
    2. Classify the row to determine its :class:`RouteCategory`.
    3. Build the provider sequence via :func:`get_provider_sequence`.
    4. Execute steps in order -- pattern match first, then provider calls.
    5. On success: learn pattern, cache the result, persist to the database.
    6. On complete miss: return a not-found result.
    """

    def __init__(
        self,
        db: Database,
        providers: dict[ProviderName, BaseProvider],
        pattern_engine: PatternEngine,
        budget: BudgetManager,
        circuit_breakers: dict[ProviderName, CircuitBreaker],
        rate_limiters: dict[ProviderName, Any],
    ) -> None:
        self.db = db
        self.providers = providers
        self.pattern_engine = pattern_engine
        self.budget = budget
        self.circuit_breakers = circuit_breakers
        self.rate_limiters = rate_limiters

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich_single(
        self,
        row: dict,
        campaign_id: Optional[str] = None,
    ) -> EnrichmentResult:
        """Run the full enrichment pipeline for a single input row.

        Parameters
        ----------
        row:
            Dictionary containing person/company fields (``first_name``,
            ``last_name``, ``company_domain``, ``company_name``, etc.).
        campaign_id:
            Optional campaign identifier for tracking and budgeting.

        Returns
        -------
        EnrichmentResult
            Always returns a result -- check ``found`` to know if data
            was discovered.
        """
        start_ts = time.monotonic()

        # --- Normalise name fields when only full_name is present --------
        row = self._normalise_row(row)

        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        domain = row.get("company_domain", "")
        company_name = row.get("company_name", "")

        # --- Determine enrichment type -----------------------------------
        enrichment_type = self._infer_enrichment_type(row)

        # --- 1. Cache check ----------------------------------------------
        cache_query = self._build_cache_query(row, enrichment_type)
        for provider_name in self.providers:
            cached = await self.db.cache_get(
                provider=provider_name.value,
                enrichment_type=enrichment_type.value,
                query_input=cache_query,
            )
            if cached is not None:
                logger.debug(
                    "Cache hit for %s/%s query=%s",
                    provider_name.value,
                    enrichment_type.value,
                    cache_query,
                )
                elapsed_ms = int((time.monotonic() - start_ts) * 1000)
                return self._build_result(
                    enrichment_type=enrichment_type,
                    provider_name=provider_name,
                    response_data=cached,
                    found=cached.get("found", False),
                    query_input=cache_query,
                    campaign_id=campaign_id,
                    response_time_ms=elapsed_ms,
                    from_cache=True,
                    email=cached.get("email"),
                    verification_status=VerificationStatus(
                        cached["verification_status"]
                    )
                    if cached.get("verification_status")
                    else VerificationStatus.UNKNOWN,
                )

        # --- 2. Classify -------------------------------------------------
        signals = detect_fields(row)
        category = classify_row(signals)

        if category == RouteCategory.UNROUTABLE:
            logger.warning("Row is unroutable: %s", row)
            elapsed_ms = int((time.monotonic() - start_ts) * 1000)
            return self._not_found_result(
                enrichment_type=enrichment_type,
                query_input=cache_query,
                campaign_id=campaign_id,
                response_time_ms=elapsed_ms,
            )

        # --- 3. Provider sequence ----------------------------------------
        waterfall_order = list(self.providers.keys())
        has_linkedin = bool(row.get("linkedin_url"))
        steps = get_provider_sequence(category, waterfall_order, has_linkedin=has_linkedin)

        if not steps:
            logger.warning("No steps for category=%s row=%s", category, row)
            elapsed_ms = int((time.monotonic() - start_ts) * 1000)
            return self._not_found_result(
                enrichment_type=enrichment_type,
                query_input=cache_query,
                campaign_id=campaign_id,
                response_time_ms=elapsed_ms,
            )

        # --- 4. Execute steps in order -----------------------------------
        total_credits = 0.0
        last_response: Optional[ProviderResponse] = None

        for position, step in enumerate(steps):
            action = step["action"]
            provider_name: Optional[ProviderName] = step.get("provider")

            try:
                response = await self._execute_step(step, row, campaign_id=campaign_id)
            except Exception:
                logger.exception(
                    "Step %d (%s) failed for row %s",
                    position,
                    action,
                    cache_query,
                )
                continue

            if response is None:
                continue

            last_response = response
            total_credits += response.credits_used

            # --- Handle domain discovery ---------------------------------
            if action == "find_domain" and response.found:
                found_domain = response.data.get("domain", "")
                if found_domain:
                    row["company_domain"] = found_domain
                    domain = found_domain
                    logger.info(
                        "Resolved domain for %s -> %s",
                        company_name,
                        found_domain,
                    )
                continue  # proceed to next step (pattern match / find_email)

            # --- Handle search results that populate row fields ----------
            if action in ("search_companies", "search_people") and response.found:
                self._merge_search_data(row, response)
                domain = row.get("company_domain", domain)
                continue

            # --- Success on email / verify / enrich ----------------------
            if response.found and action in (
                "pattern_match",
                "find_email",
                "verify_email",
                "enrich_company",
            ):
                elapsed_ms = int((time.monotonic() - start_ts) * 1000)

                verification_status = self._extract_verification_status(response)
                email = response.email

                # 5a. Learn pattern
                if email and first_name and last_name and domain:
                    try:
                        await self.pattern_engine.learn_pattern(
                            email, first_name, last_name, domain,
                        )
                    except Exception:
                        logger.exception("Failed to learn pattern for %s", email)

                # 5b. Cache result
                effective_provider = provider_name or ProviderName.APOLLO
                response_cache = self._response_to_cache_dict(response, verification_status)
                try:
                    await self.db.cache_set(
                        provider=effective_provider.value,
                        enrichment_type=enrichment_type.value,
                        query_input=cache_query,
                        response_data=response_cache,
                        found=True,
                    )
                except Exception:
                    logger.exception("Failed to cache result")

                # 5c. Persist person / company to DB
                person_id = await self._persist_entities(
                    row, response, effective_provider,
                )

                confidence = calculate_confidence(
                    provider_name=effective_provider,
                    verification_status=verification_status,
                )

                result = EnrichmentResult(
                    person_id=person_id,
                    campaign_id=campaign_id,
                    enrichment_type=enrichment_type,
                    query_input=cache_query,
                    source_provider=effective_provider,
                    result_data=response.data,
                    found=True,
                    confidence_score=confidence,
                    verification_status=verification_status,
                    cost_credits=total_credits,
                    response_time_ms=elapsed_ms,
                    waterfall_position=position,
                    from_cache=False,
                )

                try:
                    await self.db.save_enrichment_result(result)
                except Exception:
                    logger.exception("Failed to save enrichment result")

                await self.db.log_action(
                    action="enrichment_success",
                    entity_type="person",
                    entity_id=person_id,
                    details={
                        "provider": effective_provider.value,
                        "enrichment_type": enrichment_type.value,
                        "waterfall_position": position,
                        "campaign_id": campaign_id,
                    },
                )

                return result

        # --- 6. All steps exhausted, not found ---------------------------
        elapsed_ms = int((time.monotonic() - start_ts) * 1000)
        not_found = self._not_found_result(
            enrichment_type=enrichment_type,
            query_input=cache_query,
            campaign_id=campaign_id,
            response_time_ms=elapsed_ms,
            cost_credits=total_credits,
        )

        try:
            await self.db.save_enrichment_result(not_found)
        except Exception:
            logger.exception("Failed to save not-found result")

        await self.db.log_action(
            action="enrichment_not_found",
            entity_type="row",
            details={
                "query_input": cache_query,
                "enrichment_type": enrichment_type.value,
                "campaign_id": campaign_id,
                "steps_tried": len(steps),
            },
        )

        return not_found

    async def enrich_batch(
        self,
        rows: list[dict],
        campaign_id: str,
        progress_callback: Optional[Callable[[int, int, EnrichmentResult], Any]] = None,
    ) -> list[EnrichmentResult]:
        """Enrich a batch of rows with bounded concurrency.

        Parameters
        ----------
        rows:
            List of input row dicts.
        campaign_id:
            Campaign to attribute results to.
        progress_callback:
            Optional ``(completed, total, result)`` callback fired after
            each row finishes.

        Returns
        -------
        list[EnrichmentResult]
            Results in the same order as the input rows.
        """
        completed = 0

        async def _worker(indexed_row: tuple[int, dict]) -> EnrichmentResult:
            nonlocal completed
            index, row = indexed_row
            try:
                result = await self.enrich_single(row, campaign_id=campaign_id)
            except Exception:
                logger.exception("Batch worker failed for row %d", index)
                result = self._not_found_result(
                    enrichment_type=self._infer_enrichment_type(row),
                    query_input=self._build_cache_query(
                        row, self._infer_enrichment_type(row),
                    ),
                    campaign_id=campaign_id,
                )
            completed += 1
            if progress_callback is not None:
                try:
                    progress_callback(completed, len(rows), result)
                except Exception:
                    logger.exception("Progress callback error")
            return result

        ordered_results: list[EnrichmentResult] = await aiometer.run_all(
            [functools.partial(_worker, (i, row)) for i, row in enumerate(rows)],
            max_at_once=_DEFAULT_BATCH_CONCURRENCY,
        )

        return ordered_results

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: dict,
        row: dict,
        campaign_id: Optional[str] = None,
    ) -> Optional[ProviderResponse]:
        """Execute a single waterfall step.

        Performs budget, circuit-breaker, and rate-limit checks before
        calling the appropriate provider method.  Records success or
        failure on the circuit breaker and budget manager afterwards.

        Returns ``None`` when the step is skipped (budget cap, circuit
        open, etc.) or the provider is unavailable.
        """
        action: str = step["action"]
        provider_name: Optional[ProviderName] = step.get("provider")
        is_free: bool = step.get("is_free", False)

        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        domain = row.get("company_domain", "")
        company_name = row.get("company_name", "")

        # --- Pattern match (no provider needed) --------------------------
        if action == "pattern_match":
            if not (first_name and last_name and domain):
                return None
            try:
                email = await self.pattern_engine.try_pattern_match(
                    first_name, last_name, domain,
                )
            except Exception:
                logger.exception("Pattern match error for %s@%s", first_name, domain)
                return None

            if email:
                return ProviderResponse(
                    found=True,
                    data={"email": email, "source": "pattern_match"},
                    email=email,
                    credits_used=0.0,
                )
            return ProviderResponse(found=False, credits_used=0.0)

        # --- Provider-based steps ----------------------------------------
        if provider_name is None:
            logger.warning("Step %s has no provider, skipping", action)
            return None

        provider = self.providers.get(provider_name)
        if provider is None:
            logger.warning("Provider %s not available, skipping", provider_name.value)
            return None

        # Budget gate (skip for free actions)
        if not is_free:
            if not await self.budget.can_spend(
                provider_name, credits=1.0, campaign_id=campaign_id,
            ):
                logger.info(
                    "Budget exhausted for %s, skipping step %s",
                    provider_name.value,
                    action,
                )
                return None

        # Circuit breaker gate
        cb = self.circuit_breakers.get(provider_name)
        if cb is not None and not cb.can_execute():
            logger.info(
                "Circuit open for %s, skipping step %s",
                provider_name.value,
                action,
            )
            return None

        # Rate limiter
        rl = self.rate_limiters.get(provider_name)
        if rl is not None:
            try:
                await rl.acquire()
            except Exception:
                logger.exception("Rate limiter error for %s", provider_name.value)
                return None

        # --- Dispatch to provider method ---------------------------------
        response: Optional[ProviderResponse] = None
        try:
            if action == "find_email":
                response = await provider.find_email(first_name, last_name, domain)

            elif action == "find_domain":
                companies = await provider.search_companies(company_name=company_name)
                if companies:
                    found_domain = companies[0].domain
                    response = ProviderResponse(
                        found=bool(found_domain),
                        data={"domain": found_domain or "", "company_name": companies[0].name},
                        credits_used=0.0,
                    )
                else:
                    response = ProviderResponse(found=False, credits_used=0.0)

            elif action == "search_companies":
                companies = await provider.search_companies(
                    company_name=company_name,
                    domain=domain or None,
                )
                if companies:
                    response = ProviderResponse(
                        found=True,
                        data={
                            "companies": [c.model_dump(mode="json") for c in companies],
                        },
                        credits_used=0.0,
                    )
                else:
                    response = ProviderResponse(found=False, credits_used=0.0)

            elif action == "search_people":
                kwargs: dict[str, Any] = {}
                if first_name:
                    kwargs["first_name"] = first_name
                if last_name:
                    kwargs["last_name"] = last_name
                if domain:
                    kwargs["domain"] = domain
                if company_name:
                    kwargs["company_name"] = company_name
                people = await provider.search_people(**kwargs)
                if people:
                    response = ProviderResponse(
                        found=True,
                        data={
                            "people": [p.model_dump(mode="json") for p in people],
                        },
                        email=people[0].email,
                        linkedin_url=people[0].linkedin_url,
                        credits_used=0.0,
                    )
                else:
                    response = ProviderResponse(found=False, credits_used=0.0)

            elif action == "verify_email":
                email = row.get("email", "")
                response = await provider.verify_email(email)

            elif action == "enrich_company":
                response = await provider.enrich_company(domain)

            else:
                logger.warning("Unknown action: %s", action)
                return None

        except Exception as exc:
            logger.exception(
                "Provider %s action %s raised an error",
                provider_name.value,
                action,
            )
            # Record failure on circuit breaker
            if cb is not None:
                error_code = getattr(exc, "status_code", None)
                cb.record_failure(error_code=error_code)
            return None

        # --- Post-call bookkeeping ---------------------------------------
        if response is not None:
            if cb is not None:
                if response.error:
                    cb.record_failure()
                else:
                    cb.record_success()

            if not is_free and response.credits_used > 0:
                await self.budget.record_spend(
                    provider=provider_name,
                    credits=response.credits_used,
                    campaign_id=campaign_id,
                    found=response.found,
                )

        return response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_row(row: dict) -> dict:
        """Ensure ``first_name`` / ``last_name`` are present when
        ``full_name`` is provided but the split fields are missing."""
        row = dict(row)  # shallow copy to avoid mutating caller's data
        if not row.get("first_name") and row.get("full_name"):
            first, last = split_full_name(row["full_name"])
            row.setdefault("first_name", first)
            row.setdefault("last_name", last)
        return row

    @staticmethod
    def _infer_enrichment_type(row: dict) -> EnrichmentType:
        """Guess the primary enrichment type from the row contents."""
        if row.get("email"):
            return EnrichmentType.EMAIL
        if row.get("company_domain") and not row.get("first_name"):
            return EnrichmentType.COMPANY
        if row.get("company_name") and not row.get("first_name"):
            return EnrichmentType.DOMAIN
        if row.get("linkedin_url"):
            return EnrichmentType.LINKEDIN
        return EnrichmentType.EMAIL

    @staticmethod
    def _build_cache_query(row: dict, enrichment_type: EnrichmentType) -> dict:
        """Build a stable dictionary for cache key generation."""
        query: dict[str, str] = {}
        for key in (
            "first_name",
            "last_name",
            "full_name",
            "email",
            "company_domain",
            "company_name",
            "linkedin_url",
        ):
            val = row.get(key)
            if val:
                query[key] = str(val).strip().lower()
        query["enrichment_type"] = enrichment_type.value
        return query

    @staticmethod
    def _extract_verification_status(response: ProviderResponse) -> VerificationStatus:
        """Pull verification status from a provider response."""
        raw = response.data.get("verification_status") or response.data.get("email_status")
        if raw:
            try:
                return VerificationStatus(raw)
            except ValueError:
                pass
        if response.confidence:
            conf_lower = response.confidence.lower()
            if conf_lower in ("verified", "valid"):
                return VerificationStatus.VERIFIED
            if conf_lower in ("risky", "accept_all"):
                return VerificationStatus.RISKY
            if conf_lower in ("invalid", "bounce"):
                return VerificationStatus.INVALID
        return VerificationStatus.UNKNOWN

    @staticmethod
    def _response_to_cache_dict(
        response: ProviderResponse,
        verification_status: VerificationStatus,
    ) -> dict:
        """Serialise a provider response for the cache layer."""
        return {
            "found": response.found,
            "email": response.email,
            "phone": response.phone,
            "linkedin_url": response.linkedin_url,
            "data": response.data,
            "verification_status": verification_status.value,
        }

    async def _persist_entities(
        self,
        row: dict,
        response: ProviderResponse,
        provider_name: ProviderName,
    ) -> Optional[str]:
        """Save a Person (and optionally a Company) to the database.

        Returns the person ID if one was saved, otherwise ``None``.
        """
        now = datetime.now(timezone.utc)
        person_id: Optional[str] = None

        try:
            person = Person(
                first_name=row.get("first_name"),
                last_name=row.get("last_name"),
                full_name=row.get("full_name"),
                title=row.get("title"),
                company_name=row.get("company_name"),
                company_domain=row.get("company_domain"),
                email=response.email,
                linkedin_url=response.linkedin_url or row.get("linkedin_url"),
                source_provider=provider_name,
                enriched_at=now,
            )
            saved = await self.db.upsert_person(person)
            person_id = saved.id
        except Exception:
            logger.exception("Failed to persist person")

        # Persist company if we have domain data in the response
        company_data = response.data.get("company") or {}
        company_domain = company_data.get("domain") or row.get("company_domain")
        if company_domain and company_data:
            try:
                company = Company(
                    name=company_data.get("name", row.get("company_name", "")),
                    domain=company_domain,
                    industry=company_data.get("industry"),
                    employee_count=company_data.get("employee_count"),
                    employee_range=company_data.get("employee_range"),
                    description=company_data.get("description"),
                    city=company_data.get("city"),
                    state=company_data.get("state"),
                    country=company_data.get("country"),
                    linkedin_url=company_data.get("linkedin_url"),
                    website_url=company_data.get("website_url"),
                    source_provider=provider_name,
                    enriched_at=now,
                )
                await self.db.upsert_company(company)
            except Exception:
                logger.exception("Failed to persist company")

        return person_id

    @staticmethod
    def _merge_search_data(row: dict, response: ProviderResponse) -> None:
        """Merge discovered data from a search response back into *row*
        so that subsequent steps can use it (e.g. discovered domain)."""
        data = response.data
        companies = data.get("companies", [])
        if companies:
            first_company = companies[0]
            if first_company.get("domain") and not row.get("company_domain"):
                row["company_domain"] = first_company["domain"]
            if first_company.get("name") and not row.get("company_name"):
                row["company_name"] = first_company["name"]

        people = data.get("people", [])
        if people:
            first_person = people[0]
            if first_person.get("email") and not row.get("email"):
                row["email"] = first_person["email"]
            if first_person.get("company_domain") and not row.get("company_domain"):
                row["company_domain"] = first_person["company_domain"]
            if first_person.get("linkedin_url") and not row.get("linkedin_url"):
                row["linkedin_url"] = first_person["linkedin_url"]

    def _build_result(
        self,
        enrichment_type: EnrichmentType,
        provider_name: ProviderName,
        response_data: dict,
        found: bool,
        query_input: dict,
        campaign_id: Optional[str],
        response_time_ms: int,
        from_cache: bool,
        email: Optional[str] = None,
        verification_status: VerificationStatus = VerificationStatus.UNKNOWN,
        cost_credits: float = 0.0,
        waterfall_position: Optional[int] = None,
    ) -> EnrichmentResult:
        """Construct an :class:`EnrichmentResult` with confidence score."""
        confidence = calculate_confidence(
            provider_name=provider_name,
            verification_status=verification_status,
        )
        return EnrichmentResult(
            campaign_id=campaign_id,
            enrichment_type=enrichment_type,
            query_input=query_input,
            source_provider=provider_name,
            result_data=response_data,
            found=found,
            confidence_score=confidence,
            verification_status=verification_status,
            cost_credits=cost_credits,
            response_time_ms=response_time_ms,
            waterfall_position=waterfall_position,
            from_cache=from_cache,
        )

    @staticmethod
    def _not_found_result(
        enrichment_type: EnrichmentType,
        query_input: dict,
        campaign_id: Optional[str] = None,
        response_time_ms: int = 0,
        cost_credits: float = 0.0,
    ) -> EnrichmentResult:
        """Build a standardised not-found :class:`EnrichmentResult`."""
        return EnrichmentResult(
            campaign_id=campaign_id,
            enrichment_type=enrichment_type,
            query_input=query_input,
            source_provider=ProviderName.APOLLO,  # placeholder
            result_data={},
            found=False,
            confidence_score=0,
            verification_status=VerificationStatus.UNKNOWN,
            cost_credits=cost_credits,
            response_time_ms=response_time_ms,
            from_cache=False,
        )
