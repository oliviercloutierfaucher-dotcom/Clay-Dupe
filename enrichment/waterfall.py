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
import httpx
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cost.budget import BudgetManager
    from data.database import Database
    from enrichment.pattern_engine import PatternEngine
    from providers.base import BaseProvider
    from quality.verification import EmailVerifier

from config.settings import ProviderName
from data.models import (
    CampaignStatus,
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

# Rows per chunk — keeps memory bounded for large CSVs.
_DEFAULT_CHUNK_SIZE = 100


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
        cost_tracker: Optional[Any] = None,
        waterfall_order: Optional[list[ProviderName]] = None,
        verifier: Optional[EmailVerifier] = None,
    ) -> None:
        self.db = db
        self.providers = providers
        self.pattern_engine = pattern_engine
        self.budget = budget
        self.circuit_breakers = circuit_breakers
        self.rate_limiters = rate_limiters
        self.cost_tracker = cost_tracker
        self.verifier = verifier
        # Explicit waterfall order from settings (if provided)
        self._configured_order = waterfall_order
        # Adaptive order computed at first batch run
        self._adaptive_order: Optional[list[ProviderName]] = None
        # Per-provider adaptive concurrency: start at default, halve on 429,
        # recover by 1 on each success (min 1, max DEFAULT).
        self._provider_concurrency: dict[ProviderName, int] = {
            p: _DEFAULT_BATCH_CONCURRENCY for p in ProviderName
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich_single(
        self,
        row: dict,
        campaign_id: Optional[str] = None,
        _dedup_person: Optional[Person] = None,
    ) -> EnrichmentResult:
        """Run the full enrichment pipeline for a single input row.

        Parameters
        ----------
        row:
            Dictionary containing person/company fields (``first_name``,
            ``last_name``, ``company_domain``, ``company_name``, etc.).
        campaign_id:
            Optional campaign identifier for tracking and budgeting.
        _dedup_person:
            *Internal*. Pre-fetched cross-campaign dedup result from a
            batch lookup.  When provided the per-row DB query is skipped.

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
            if cached is not None and cached.get("found", False):
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
                    found=True,
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

        # --- 1b. Cross-campaign dedup — check if this contact was already
        #         enriched in a different campaign. Reuses existing data
        #         without consuming additional credits.
        #         When called from enrich_batch, _dedup_person is pre-fetched
        #         in bulk so we skip the per-row DB query.
        if first_name and last_name and domain:
            try:
                existing_person = _dedup_person
                if existing_person is None:
                    existing_person = await self.db.get_person_by_name_domain(
                        first_name, last_name, domain,
                    )
                if existing_person and existing_person.email:
                    logger.debug(
                        "Cross-campaign dedup hit: %s %s @ %s -> %s",
                        first_name, last_name, domain, existing_person.email,
                    )
                    elapsed_ms = int((time.monotonic() - start_ts) * 1000)
                    return self._build_result(
                        enrichment_type=enrichment_type,
                        provider_name=existing_person.source_provider or ProviderName.APOLLO,
                        response_data={"email": existing_person.email, "source": "dedup"},
                        found=True,
                        query_input=cache_query,
                        campaign_id=campaign_id,
                        response_time_ms=elapsed_ms,
                        from_cache=True,
                        email=existing_person.email,
                    )
            except Exception:
                logger.debug("Cross-campaign dedup check failed (non-critical)")

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
        # Use adaptive order > configured order > provider dict order
        waterfall_order = (
            self._adaptive_order
            or self._configured_order
            or list(self.providers.keys())
        )
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
                    await self.db.save_enrichment_atomic(
                        result=result,
                        provider=effective_provider.value,
                        credits=total_credits,
                        found=True,
                    )
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
            if total_credits > 0:
                await self.db.save_enrichment_atomic(
                    result=not_found,
                    provider=(provider_name or ProviderName.APOLLO).value,
                    credits=total_credits,
                    found=False,
                )
            else:
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
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        campaign_row_ids: Optional[list[str]] = None,
    ) -> list[EnrichmentResult]:
        """Enrich a batch of rows with bounded concurrency.

        Rows are processed in explicit chunks to keep memory bounded
        for large CSVs (hundreds or thousands of rows).

        Parameters
        ----------
        rows:
            List of input row dicts.
        campaign_id:
            Campaign to attribute results to.
        progress_callback:
            Optional ``(completed, total, result)`` callback fired after
            each row finishes.
        chunk_size:
            Number of rows per chunk (default 100).
        campaign_row_ids:
            Optional parallel list of campaign_row IDs for per-row
            status tracking.  When provided, each row's status is
            updated to ``processing`` before enrichment and to
            ``complete`` or ``failed`` afterwards.

        Returns
        -------
        list[EnrichmentResult]
            Results in the same order as the input rows.
        """
        all_results: list[EnrichmentResult] = []
        completed = 0
        total = len(rows)

        # Compute adaptive waterfall order from historical data
        if self.cost_tracker is not None and self._adaptive_order is None:
            try:
                recommended = await self.cost_tracker.get_waterfall_recommendation()
                if recommended:
                    self._adaptive_order = recommended
                    order_str = " -> ".join(p.value for p in recommended)
                    logger.info("Adaptive waterfall order applied: %s", order_str)
                    await self.db.log_action(
                        action="waterfall_reorder",
                        entity_type="campaign",
                        entity_id=campaign_id,
                        details={"new_order": [p.value for p in recommended]},
                    )
            except Exception:
                logger.debug("Adaptive ordering failed (non-critical)")

        for chunk_start in range(0, total, chunk_size):
            # --- Pause check between chunks --------------------------------
            try:
                campaign = await self.db.get_campaign(campaign_id)
                if campaign and campaign.status == CampaignStatus.PAUSED:
                    logger.info("Campaign %s paused — stopping batch", campaign_id)
                    break
            except Exception:
                logger.debug("Pause check failed (non-critical)")

            chunk = rows[chunk_start : chunk_start + chunk_size]
            chunk_row_ids = (
                campaign_row_ids[chunk_start : chunk_start + chunk_size]
                if campaign_row_ids
                else None
            )

            # --- Batch cross-campaign dedup for this chunk -------------------
            dedup_map: dict[tuple[str, str, str], Person] = {}
            try:
                lookups: list[tuple[str, str, str]] = []
                for r in chunk:
                    nr = self._normalise_row(r)
                    fn = nr.get("first_name", "")
                    ln = nr.get("last_name", "")
                    dom = nr.get("company_domain", "")
                    if fn and ln and dom:
                        lookups.append((fn, ln, dom))
                if lookups:
                    dedup_map = await self.db.get_persons_by_name_domain_batch(lookups)
            except Exception:
                logger.debug("Batch dedup pre-fetch failed (non-critical)")

            async def _worker(indexed_row: tuple[int, dict, Optional[str]]) -> EnrichmentResult:
                nonlocal completed
                index, row, row_id = indexed_row

                # Mark row as processing
                if row_id:
                    try:
                        await self.db.update_campaign_row(row_id, "processing")
                    except Exception:
                        logger.debug("Failed to mark row %s as processing", row_id)

                # Resolve pre-fetched dedup person for this row
                nr = self._normalise_row(row)
                _dedup_key = (
                    nr.get("first_name", "").strip().lower(),
                    nr.get("last_name", "").strip().lower(),
                    nr.get("company_domain", "").strip().lower(),
                )
                _preloaded = dedup_map.get(_dedup_key)

                try:
                    result = await self.enrich_single(
                        row, campaign_id=campaign_id, _dedup_person=_preloaded,
                    )
                except Exception:
                    logger.exception("Batch worker failed for row %d", index)
                    result = self._not_found_result(
                        enrichment_type=self._infer_enrichment_type(row),
                        query_input=self._build_cache_query(
                            row, self._infer_enrichment_type(row),
                        ),
                        campaign_id=campaign_id,
                    )
                    # Mark row as failed
                    if row_id:
                        try:
                            await self.db.update_campaign_row(
                                row_id, "failed", error="enrichment exception",
                            )
                        except Exception:
                            pass
                else:
                    # Mark row as complete
                    if row_id:
                        status = "complete" if result.found else "failed"
                        try:
                            await self.db.update_campaign_row(
                                row_id, status, person_id=result.person_id,
                            )
                        except Exception:
                            pass

                completed += 1
                if progress_callback is not None:
                    try:
                        progress_callback(completed, total, result)
                    except Exception:
                        logger.exception("Progress callback error")
                return result

            chunk_results: list[EnrichmentResult] = await aiometer.run_all(
                [
                    functools.partial(
                        _worker,
                        (
                            chunk_start + i,
                            row,
                            chunk_row_ids[i] if chunk_row_ids else None,
                        ),
                    )
                    for i, row in enumerate(chunk)
                ],
                max_at_once=_DEFAULT_BATCH_CONCURRENCY,
            )
            all_results.extend(chunk_results)

            # Update campaign progress checkpoint
            try:
                await self.db.update_campaign_status(
                    campaign_id,
                    CampaignStatus.RUNNING,
                    enriched_rows=completed,
                    last_processed_row=chunk_start + len(chunk),
                )
            except Exception:
                logger.debug("Campaign progress update failed (non-critical)")

            # WAL checkpoint between chunks to keep WAL file bounded.
            try:
                await self.db.wal_checkpoint()
            except Exception:
                logger.debug("WAL checkpoint skipped (non-critical)")

        return all_results

    async def resume_batch(
        self,
        campaign_id: str,
        progress_callback: Optional[Callable[[int, int, EnrichmentResult], Any]] = None,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> list[EnrichmentResult]:
        """Resume enrichment for a paused or crashed campaign.

        Queries pending and failed rows from ``campaign_rows``, then
        processes only those — already-completed rows are skipped.
        """
        pending_rows = await self.db.get_pending_rows(campaign_id, limit=100_000)
        if not pending_rows:
            # Also check for failed rows to retry
            failed_rows = await self.db.get_failed_rows(campaign_id, limit=100_000)
            pending_rows = failed_rows

        if not pending_rows:
            logger.info("No pending or failed rows for campaign %s", campaign_id)
            return []

        rows = []
        row_ids = []
        for pr in pending_rows:
            input_data = pr.get("input_data", {})
            if isinstance(input_data, str):
                import json
                try:
                    input_data = json.loads(input_data)
                except (json.JSONDecodeError, TypeError):
                    input_data = {}
            rows.append(input_data)
            row_ids.append(pr["id"])

        return await self.enrich_batch(
            rows,
            campaign_id=campaign_id,
            progress_callback=progress_callback,
            chunk_size=chunk_size,
            campaign_row_ids=row_ids,
        )

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

        # --- Local email verification (no provider needed) ---------------
        if action == "verify_email_local":
            email = row.get("email", "")
            if not email or self.verifier is None:
                return None
            try:
                result = await self.verifier.verify(email)
                return ProviderResponse(
                    found=result.get("valid", False),
                    email=email,
                    data=result,
                    credits_used=0.0,
                )
            except Exception:
                logger.exception("Local email verification error for %s", email)
                return None

        # --- Provider-based steps ----------------------------------------
        if provider_name is None:
            logger.warning("Step %s has no provider, skipping", action)
            return None

        provider = self.providers.get(provider_name)
        if provider is None:
            logger.warning("Provider %s not available, skipping", provider_name.value)
            return None

        # Domain stats gate — skip providers with 0 hits over 5+ attempts for this domain
        if domain and action == "find_email":
            try:
                if await self.db.should_skip_provider_for_domain(
                    provider_name.value, domain,
                ):
                    logger.info(
                        "Skipping %s for domain %s (0 hits in 5+ attempts)",
                        provider_name.value, domain,
                    )
                    return None
            except Exception:
                pass  # non-critical — proceed with the call

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
        step_start = time.monotonic()
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
            step_elapsed = int((time.monotonic() - step_start) * 1000)
            logger.exception(
                "Provider %s action %s raised an error",
                provider_name.value,
                action,
            )
            # Record failure on circuit breaker
            if cb is not None:
                error_code = getattr(exc, "status_code", None)
                cb.record_failure(error_code=error_code)

            # Adaptive concurrency: halve on 429
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                cur = self._provider_concurrency.get(provider_name, _DEFAULT_BATCH_CONCURRENCY)
                self._provider_concurrency[provider_name] = max(1, cur // 2)
                logger.info(
                    "429 from %s — reducing concurrency to %d",
                    provider_name.value,
                    self._provider_concurrency[provider_name],
                )

            # Audit trail: log failed API call
            try:
                error_type = type(exc).__name__
                await self.db.log_action(
                    action="provider_call",
                    entity_type="enrichment",
                    details={
                        "provider": provider_name.value,
                        "action": action,
                        "campaign_id": campaign_id,
                        "status": "error",
                        "error_type": error_type,
                        "duration_ms": step_elapsed,
                        "credits_consumed": 0,
                    },
                )
            except Exception:
                pass
            return None

        step_elapsed = int((time.monotonic() - step_start) * 1000)

        # --- Post-call bookkeeping ---------------------------------------
        if response is not None:
            if cb is not None:
                if response.error:
                    cb.record_failure()
                else:
                    cb.record_success()

            # Adaptive concurrency: recover by 1 on success
            if provider_name is not None and not response.error:
                cur = self._provider_concurrency.get(provider_name, _DEFAULT_BATCH_CONCURRENCY)
                if cur < _DEFAULT_BATCH_CONCURRENCY:
                    self._provider_concurrency[provider_name] = min(cur + 1, _DEFAULT_BATCH_CONCURRENCY)

            # NOTE: credit recording is deferred to save_enrichment_atomic()
            # so budget deduction and result save are atomic.

            # Record domain stats and negative cache for misses
            if domain and action == "find_email":
                try:
                    await self.db.record_provider_domain_attempt(
                        provider_name.value, domain, hit=response.found,
                    )
                except Exception:
                    pass
                # Cache misses so we don't repeat failed lookups
                if not response.found:
                    cache_query = self._build_cache_query(
                        {"first_name": first_name, "last_name": last_name,
                         "company_domain": domain},
                        EnrichmentType.EMAIL,
                    )
                    try:
                        await self.db.cache_set(
                            provider=provider_name.value,
                            enrichment_type=EnrichmentType.EMAIL.value,
                            query_input=cache_query,
                            response_data={"found": False, "email": None},
                            found=False,
                            ttl_days=7,  # shorter TTL for misses
                        )
                    except Exception:
                        pass

            # Audit trail: log every provider API call
            try:
                await self.db.log_action(
                    action="provider_call",
                    entity_type="enrichment",
                    details={
                        "provider": provider_name.value,
                        "action": action,
                        "campaign_id": campaign_id,
                        "status": "success" if response.found else "not_found",
                        "email_found": bool(response.email),
                        "credits_consumed": response.credits_used,
                        "duration_ms": step_elapsed,
                        "error_type": None,
                    },
                )
            except Exception:
                pass

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
            # Extract person-level data from provider response
            response_data = response.data or {}
            people_data: dict = {}
            if isinstance(response_data.get("people"), list) and response_data["people"]:
                people_data = response_data["people"][0]

            person = Person(
                first_name=row.get("first_name"),
                last_name=row.get("last_name"),
                full_name=row.get("full_name"),
                title=row.get("title") or people_data.get("title") or response_data.get("title"),
                seniority=people_data.get("seniority") or response_data.get("seniority"),
                department=people_data.get("department") or response_data.get("department"),
                company_name=row.get("company_name") or people_data.get("company_name"),
                company_domain=row.get("company_domain"),
                email=response.email,
                phone=response.phone or people_data.get("phone") or response_data.get("phone"),
                mobile_phone=people_data.get("mobile_phone") or response_data.get("mobile_phone"),
                linkedin_url=response.linkedin_url or row.get("linkedin_url") or people_data.get("linkedin_url"),
                city=people_data.get("city") or response_data.get("city"),
                state=people_data.get("state") or response_data.get("state"),
                country=people_data.get("country") or response_data.get("country"),
                source_provider=provider_name,
                enriched_at=now,
            )
            saved = await self.db.upsert_person(person)
            person_id = saved.id
        except Exception:
            logger.exception("Failed to persist person")

        # Persist company if we have domain data in the response
        company_data = response.data.get("organization") or response.data.get("company") or {}
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
