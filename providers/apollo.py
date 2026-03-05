"""Apollo.io provider implementation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config.settings import ProviderName
from data.models import Company, Person
from providers.base import BaseProvider, ProviderResponse
from providers.validators import validate_domain, validate_name

logger = logging.getLogger(__name__)


class ApolloProvider(BaseProvider):
    """Apollo.io enrichment provider.

    Rate limit: 50 requests/min on the free tier.
    """

    name = ProviderName.APOLLO
    base_url = "https://api.apollo.io/api/v1"

    def __init__(self, api_key: str, client: Optional[httpx.AsyncClient] = None):
        super().__init__(api_key, client)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

    async def _post(self, path: str, payload: dict) -> tuple[dict, int]:
        """POST to Apollo and return (json, elapsed_ms)."""
        url = f"{self.base_url}{path}"
        return await self._request("POST", url, headers=self._headers(), json=payload)

    async def _get(self, path: str, params: Optional[dict] = None) -> tuple[dict, int]:
        """GET from Apollo and return (json, elapsed_ms)."""
        url = f"{self.base_url}{path}"
        return await self._request("GET", url, headers=self._headers(), params=params)

    @staticmethod
    def _handle_error(exc: httpx.HTTPStatusError) -> ProviderResponse:
        """Convert an HTTP error into a ProviderResponse with a useful message."""
        status = exc.response.status_code
        if status == 401:
            msg = "Apollo: invalid API key"
        elif status == 403:
            msg = "Apollo: forbidden — a master API key may be required"
        elif status == 422:
            msg = "Apollo: unprocessable entity — check request parameters"
        elif status == 429:
            retry_after = exc.response.headers.get("Retry-After")
            msg = "Apollo: rate limited (429)"
            if retry_after:
                msg += f" — Retry-After: {retry_after}s"
        else:
            msg = f"Apollo: HTTP {status} error"
        return ProviderResponse(found=False, error=msg)

    # ------------------------------------------------------------------
    # find_email
    # ------------------------------------------------------------------

    async def find_email(
        self, first_name: str, last_name: str, domain: str
    ) -> ProviderResponse:
        """Find an email via POST /people/match.

        Costs 1 credit on a match, 0 on no match.
        """
        first_name = validate_name("Apollo", first_name, "first_name")
        last_name = validate_name("Apollo", last_name, "last_name")
        domain = validate_domain("Apollo", domain)
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "domain": domain,
        }
        try:
            data, elapsed = await self._post("/people/match", payload)
        except httpx.HTTPStatusError as exc:
            resp = self._handle_error(exc)
            resp.response_time_ms = 0
            return resp

        person = data.get("person")
        if person is None:
            return ProviderResponse(
                found=False,
                data=data,
                credits_used=0,
                response_time_ms=elapsed,
            )

        email = person.get("email")
        email_status = person.get("email_status")

        if email_status == "verified":
            found = True
            confidence = "verified"
            credits = 1.0
        elif email_status == "guessed":
            found = True
            confidence = "guessed"
            credits = 1.0
        else:
            # null or "unavailable"
            found = False
            confidence = None
            credits = 0.0

        return ProviderResponse(
            found=found,
            data=data,
            email=email if found else None,
            linkedin_url=person.get("linkedin_url"),
            confidence=confidence,
            credits_used=credits,
            response_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # search_companies
    # ------------------------------------------------------------------

    async def search_companies(self, **filters: Any) -> list[Company]:
        """Search companies via POST /mixed_companies/search.

        Accepted filters:
            organization_num_employees_ranges: list[str]  e.g. ["1,50", "51,200"]
            organization_locations: list[str]
            q_organization_keyword_tags: list[str]
            page: int
            per_page: int  (max 100)
        FREE — no credits consumed.
        """
        payload: dict[str, Any] = {}
        for key in (
            "organization_num_employees_ranges",
            "organization_locations",
            "q_organization_keyword_tags",
        ):
            if key in filters:
                payload[key] = filters[key]

        payload["page"] = filters.get("page", 1)
        payload["per_page"] = min(filters.get("per_page", 25), 100)

        try:
            data, _ = await self._post("/mixed_companies/search", payload)
        except httpx.HTTPStatusError as exc:
            self._handle_error(exc)
            return []

        organizations = data.get("organizations", [])
        now = datetime.now(timezone.utc)

        companies: list[Company] = []
        for org in organizations:
            companies.append(
                Company(
                    apollo_id=org.get("id"),
                    name=org.get("name", ""),
                    domain=org.get("primary_domain"),
                    website_url=org.get("website_url"),
                    industry=org.get("industry"),
                    employee_count=org.get("estimated_num_employees"),
                    founded_year=org.get("founded_year"),
                    linkedin_url=org.get("linkedin_url"),
                    phone=org.get("phone"),
                    full_address=org.get("raw_address"),
                    city=org.get("city"),
                    state=org.get("state"),
                    country=org.get("country"),
                    description=org.get("short_description"),
                    revenue_usd=org.get("annual_revenue"),
                    source_provider=ProviderName.APOLLO,
                    enriched_at=now,
                )
            )
        return companies

    # ------------------------------------------------------------------
    # search_people
    # ------------------------------------------------------------------

    async def search_people(self, **filters: Any) -> list[Person]:
        """Search people via POST /mixed_people/search.

        Accepted filters:
            person_titles: list[str]
            person_seniorities: list[str]  (c_suite, vp, director, manager)
            q_organization_domains_list: list[str]
            organization_num_employees_ranges: list[str]
            organization_locations: list[str]
            page: int
            per_page: int  (max 100)
        FREE — no credits consumed. Requires a master API key.
        Does NOT return emails.
        """
        payload: dict[str, Any] = {}
        for key in (
            "person_titles",
            "person_seniorities",
            "q_organization_domains_list",
            "organization_num_employees_ranges",
            "organization_locations",
        ):
            if key in filters:
                payload[key] = filters[key]

        payload["page"] = filters.get("page", 1)
        payload["per_page"] = min(filters.get("per_page", 25), 100)

        try:
            data, _ = await self._post("/mixed_people/search", payload)
        except httpx.HTTPStatusError as exc:
            self._handle_error(exc)
            return []

        people_raw = data.get("people", [])
        now = datetime.now(timezone.utc)

        people: list[Person] = []
        for p in people_raw:
            org = p.get("organization") or {}
            departments = p.get("departments") or []
            department = departments[0] if departments else None

            people.append(
                Person(
                    apollo_id=p.get("id"),
                    first_name=p.get("first_name"),
                    last_name=p.get("last_name"),
                    full_name=p.get("name"),
                    title=p.get("title"),
                    seniority=p.get("seniority"),
                    department=department,
                    linkedin_url=p.get("linkedin_url"),
                    city=p.get("city"),
                    state=p.get("state"),
                    country=p.get("country"),
                    company_name=org.get("name"),
                    company_domain=org.get("primary_domain"),
                    company_id=p.get("organization_id"),
                    source_provider=ProviderName.APOLLO,
                    enriched_at=now,
                )
            )
        return people

    # ------------------------------------------------------------------
    # enrich_company
    # ------------------------------------------------------------------

    async def enrich_company(self, domain: str) -> ProviderResponse:
        """Enrich a company via GET /organizations/enrich?domain=...

        Costs 1 credit.
        """
        domain = validate_domain("Apollo", domain)
        try:
            data, elapsed = await self._get("/organizations/enrich", params={"domain": domain})
        except httpx.HTTPStatusError as exc:
            resp = self._handle_error(exc)
            resp.response_time_ms = 0
            return resp

        org = data.get("organization")
        if org is None:
            return ProviderResponse(
                found=False,
                data=data,
                credits_used=1.0,
                response_time_ms=elapsed,
            )

        return ProviderResponse(
            found=True,
            data=data,
            linkedin_url=org.get("linkedin_url"),
            phone=org.get("phone"),
            credits_used=1.0,
            response_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # find_email_batch  (override)
    # ------------------------------------------------------------------

    async def find_email_batch(self, rows: list[dict]) -> list[ProviderResponse]:
        """Batch email lookup via POST /people/bulk_match.

        Max 10 per call. Larger lists are chunked automatically.
        Deduplicates within each chunk by (first_name, last_name, domain) to
        avoid wasting API credits on repeated entries.
        """
        all_results: list[ProviderResponse] = []

        for i in range(0, len(rows), 10):
            chunk = rows[i : i + 10]

            # --- Deduplicate within chunk ---
            # Map each unique (first_name, last_name, domain) to its first
            # occurrence index within the chunk, and track which chunk
            # positions share the same key.
            unique_details: list[dict] = []
            unique_keys: list[tuple[str, str, str]] = []
            # Maps dedup key -> index into unique_details
            key_to_unique_idx: dict[tuple[str, str, str], int] = {}
            # Maps each chunk position -> index into unique_details
            chunk_pos_to_unique_idx: list[int] = []

            for pos, r in enumerate(chunk):
                fn = r.get("first_name", "").strip().lower()
                ln = r.get("last_name", "").strip().lower()
                dom = r.get("domain", "").strip().lower()
                key = (fn, ln, dom)

                if key in key_to_unique_idx:
                    chunk_pos_to_unique_idx.append(key_to_unique_idx[key])
                else:
                    idx = len(unique_details)
                    key_to_unique_idx[key] = idx
                    chunk_pos_to_unique_idx.append(idx)
                    unique_details.append({
                        "first_name": r.get("first_name", ""),
                        "last_name": r.get("last_name", ""),
                        "domain": r.get("domain", ""),
                    })
                    unique_keys.append(key)

            saved = len(chunk) - len(unique_details)
            if saved:
                logger.debug(
                    "Apollo batch: deduped chunk of %d to %d unique entries (saved %d credits)",
                    len(chunk), len(unique_details), saved,
                )

            # --- Send only unique entries to the API ---
            try:
                data, elapsed = await self._post(
                    "/people/bulk_match", {"details": unique_details},
                )
            except httpx.HTTPStatusError as exc:
                error_resp = self._handle_error(exc)
                error_resp.response_time_ms = 0
                all_results.extend([error_resp] * len(chunk))
                continue

            matches = data.get("matches", [])

            # Parse unique results into a list indexed by unique position
            unique_responses: list[ProviderResponse] = []
            for j, match in enumerate(matches):
                status = match.get("status")
                person = match.get("person")

                if status == "no_match" or person is None:
                    unique_responses.append(
                        ProviderResponse(
                            found=False,
                            data=match,
                            credits_used=0.0,
                            response_time_ms=elapsed,
                        )
                    )
                    continue

                email = person.get("email")
                email_status = person.get("email_status")

                if email_status == "verified":
                    found = True
                    confidence = "verified"
                    credits = 1.0
                elif email_status == "guessed":
                    found = True
                    confidence = "guessed"
                    credits = 1.0
                else:
                    found = False
                    confidence = None
                    credits = 0.0

                unique_responses.append(
                    ProviderResponse(
                        found=found,
                        data=match,
                        email=email if found else None,
                        linkedin_url=person.get("linkedin_url"),
                        confidence=confidence,
                        credits_used=credits,
                        response_time_ms=elapsed,
                    )
                )

            # Pad if API returned fewer matches than unique entries sent
            for _ in range(len(unique_details) - len(unique_responses)):
                unique_responses.append(
                    ProviderResponse(
                        found=False,
                        data={},
                        credits_used=0.0,
                        response_time_ms=elapsed,
                    )
                )

            # --- Map results back to all original rows (including duplicates) ---
            for pos in range(len(chunk)):
                unique_idx = chunk_pos_to_unique_idx[pos]
                all_results.append(unique_responses[unique_idx])

        return all_results

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check API health via GET /rate_limits."""
        try:
            await self._get("/rate_limits")
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Apollo health check failed: HTTP %d", exc.response.status_code,
            )
            return False
        except httpx.TimeoutException:
            logger.warning("Apollo health check failed: timeout")
            return False
        except OSError as exc:
            logger.warning("Apollo health check failed: connection error: %s", exc)
            return False
