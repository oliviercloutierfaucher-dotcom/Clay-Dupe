"""ContactOut provider — LinkedIn-first email finder with batch support."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config.settings import ProviderName
from data.models import Company, Person
from providers.base import BaseProvider, ProviderResponse
from providers.validators import validate_domain, validate_linkedin_url, validate_name

logger = logging.getLogger(__name__)

MAX_POLL_ITERATIONS = 60  # Maximum polling iterations for batch jobs


class ContactOutProvider(BaseProvider):
    """ContactOut API integration.

    Docs: https://api.contactout.com
    Auth: custom ``token`` header (NOT Authorization/Bearer).
    """

    name = ProviderName.CONTACTOUT
    base_url = "https://api.contactout.com"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "token": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: Optional[dict] = None) -> tuple[dict, int]:
        """GET from ContactOut and return (json, elapsed_ms)."""
        url = f"{self.base_url}{path}"
        return await self._request("GET", url, headers=self._headers(), params=params)

    async def _post(self, path: str, payload: dict) -> tuple[dict, int]:
        """POST to ContactOut and return (json, elapsed_ms)."""
        url = f"{self.base_url}{path}"
        return await self._request("POST", url, headers=self._headers(), json=payload)

    @staticmethod
    def _is_linkedin_url(value: str) -> bool:
        """Return True if *value* looks like a LinkedIn profile URL."""
        if not value:
            return False
        lower = value.lower().strip()
        return "linkedin.com" in lower

    @staticmethod
    def _handle_error(exc: httpx.HTTPStatusError) -> ProviderResponse:
        """Convert an HTTP error into a ProviderResponse with a useful message."""
        status = exc.response.status_code
        if status == 404:
            # Profile not found -- not a real error, just a miss.
            return ProviderResponse(found=False, data={}, credits_used=0)
        if status == 401:
            msg = "ContactOut: invalid or missing API token"
        elif status == 429:
            retry_after = exc.response.headers.get("Retry-After")
            msg = "ContactOut: rate limited (429)"
            if retry_after:
                msg += f" -- Retry-After: {retry_after}s"
        else:
            msg = f"ContactOut: HTTP {status} error"
        return ProviderResponse(found=False, data={}, error=msg)

    # ------------------------------------------------------------------
    # _parse_email_response  (shared between single + batch)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_email_response(data: dict, elapsed_ms: int = 0) -> ProviderResponse:
        """Turn a ContactOut person payload into a ProviderResponse."""
        work_emails: list[str] = data.get("work_email", []) or []
        personal_emails: list[str] = data.get("personal_email", []) or []
        profile: dict = data.get("profile", {}) or {}

        email = work_emails[0] if work_emails else (personal_emails[0] if personal_emails else None)
        found = email is not None

        return ProviderResponse(
            found=found,
            data=data,
            email=email,
            linkedin_url=profile.get("linkedin_url"),
            confidence="high" if found else None,
            credits_used=1.0 if found else 0.0,
            response_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # find_email
    # ------------------------------------------------------------------

    async def find_email(
        self, first_name: str, last_name: str, domain: str
    ) -> ProviderResponse:
        """Find an email for a person.

        Two modes:
        1. If *domain* contains ``linkedin.com`` it is treated as a
           LinkedIn profile URL and the LinkedIn endpoint is used.
        2. Otherwise, the name + company enrichment endpoint is used
           (with *domain* passed as *company_name*).

        Returns 1 credit on a hit, 0 on a miss.
        """
        if self._is_linkedin_url(domain):
            return await self.find_email_by_linkedin(domain)

        first_name = validate_name("ContactOut", first_name, "first_name")
        last_name = validate_name("ContactOut", last_name, "last_name")
        domain = validate_domain("ContactOut", domain)
        # Fall back to name + company enrichment
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "company_name": domain,
            "include": ["work_email"],
        }

        try:
            data, elapsed = await self._post("/v1/people/enrich", payload)
        except httpx.HTTPStatusError as exc:
            resp = self._handle_error(exc)
            resp.response_time_ms = 0
            return resp

        return self._parse_email_response(data, elapsed)

    # ------------------------------------------------------------------
    # find_email_by_linkedin
    # ------------------------------------------------------------------

    async def find_email_by_linkedin(self, linkedin_url: str) -> ProviderResponse:
        """Find an email using a LinkedIn profile URL.

        ``GET /v1/people/linkedin?profile=<url>&include=work_email,personal_email``

        The ``include`` parameter is **required** -- without it no emails
        are returned by the API.
        """
        linkedin_url = validate_linkedin_url("ContactOut", linkedin_url)
        params = {
            "profile": linkedin_url,
            "include": "work_email,personal_email",
        }

        try:
            data, elapsed = await self._get("/v1/people/linkedin", params=params)
        except httpx.HTTPStatusError as exc:
            resp = self._handle_error(exc)
            resp.response_time_ms = 0
            return resp

        return self._parse_email_response(data, elapsed)

    # ------------------------------------------------------------------
    # search_people
    # ------------------------------------------------------------------

    async def search_people(self, **filters: Any) -> list[Person]:
        """Search for people via GET /v1/people/search.

        Accepted filters:
            name: str
            company_name: str (mapped from ``company``)
        """
        params: dict[str, str] = {}
        if "name" in filters:
            params["name"] = filters["name"]
        if "company" in filters:
            params["company_name"] = filters["company"]
        elif "company_name" in filters:
            params["company_name"] = filters["company_name"]

        params["include"] = "work_email"

        try:
            data, _ = await self._get("/v1/people/search", params=params)
        except httpx.HTTPStatusError as exc:
            self._handle_error(exc)
            return []

        profiles = data.get("profiles", data.get("results", []))
        if not isinstance(profiles, list):
            profiles = []

        now = datetime.now(timezone.utc)
        people: list[Person] = []
        for p in profiles:
            profile = p.get("profile", p) or {}
            work_emails = p.get("work_email", []) or []
            personal_emails = p.get("personal_email", []) or []

            full_name = profile.get("full_name", "")
            parts = full_name.split(None, 1)
            first = parts[0] if parts else None
            last = parts[1] if len(parts) > 1 else None

            people.append(
                Person(
                    first_name=first,
                    last_name=last,
                    full_name=full_name or None,
                    title=profile.get("title"),
                    company_name=profile.get("company"),
                    linkedin_url=profile.get("linkedin_url"),
                    email=work_emails[0] if work_emails else None,
                    personal_email=personal_emails[0] if personal_emails else None,
                    source_provider=ProviderName.CONTACTOUT,
                    enriched_at=now,
                )
            )
        return people

    # ------------------------------------------------------------------
    # search_companies — not supported
    # ------------------------------------------------------------------

    async def search_companies(self, **filters: Any) -> list[Company]:
        """ContactOut does not support company search -- returns empty list."""
        return []

    # ------------------------------------------------------------------
    # enrich_company
    # ------------------------------------------------------------------

    async def enrich_company(self, domain: str) -> ProviderResponse:
        """Enrich a company via GET /v1/domain/enrich?domain=<domain>."""
        domain = validate_domain("ContactOut", domain)
        try:
            data, elapsed = await self._get(
                "/v1/domain/enrich", params={"domain": domain},
            )
        except httpx.HTTPStatusError as exc:
            resp = self._handle_error(exc)
            resp.response_time_ms = 0
            return resp

        found = bool(data and data.get("company", data))
        return ProviderResponse(
            found=found,
            data=data,
            credits_used=1.0 if found else 0.0,
            response_time_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # find_email_batch  (override)
    # ------------------------------------------------------------------

    async def find_email_batch(self, rows: list[dict]) -> list[ProviderResponse]:
        """Batch email lookup.

        Rows that contain a ``linkedin_url`` are grouped and submitted via
        ``POST /v2/people/linkedin/batch`` (max 30 per request).  The
        endpoint returns a ``job_id`` which must be polled (``GET
        /v2/people/linkedin/batch/<job_id>``) every 3 seconds until
        ``status == "DONE"``.

        Rows *without* a LinkedIn URL fall back to sequential single
        ``find_email`` calls.
        """
        # Partition rows into LinkedIn-batch-eligible vs sequential.
        linkedin_indices: list[int] = []
        linkedin_urls: list[str] = []
        sequential_indices: list[int] = []

        for idx, row in enumerate(rows):
            li_url = row.get("linkedin_url", "")
            # Also accept the domain field if it looks like a LinkedIn URL
            if not li_url and self._is_linkedin_url(row.get("domain", "")):
                li_url = row["domain"]
            if li_url and self._is_linkedin_url(li_url):
                linkedin_indices.append(idx)
                linkedin_urls.append(li_url)
            else:
                sequential_indices.append(idx)

        # Pre-allocate results list.
        results: list[Optional[ProviderResponse]] = [None] * len(rows)

        # ---- Batch path (LinkedIn URLs) ----
        for chunk_start in range(0, len(linkedin_urls), 30):
            chunk_urls = linkedin_urls[chunk_start : chunk_start + 30]
            chunk_indices = linkedin_indices[chunk_start : chunk_start + 30]

            payload = {
                "profiles": chunk_urls,
                "include": ["work_email", "personal_email"],
            }

            try:
                data, _ = await self._post("/v2/people/linkedin/batch", payload)
            except httpx.HTTPStatusError as exc:
                error_resp = self._handle_error(exc)
                for ci in chunk_indices:
                    results[ci] = error_resp
                continue

            job_id = data.get("job_id")
            if not job_id:
                # Unexpected response -- treat every row as a miss.
                miss = ProviderResponse(found=False, data=data, credits_used=0)
                for ci in chunk_indices:
                    results[ci] = miss
                continue

            # Poll until DONE
            batch_results = await self._poll_batch_job(job_id)

            # Map results back.  The API returns results in the same
            # order as the submitted profiles.
            for offset, ci in enumerate(chunk_indices):
                if offset < len(batch_results):
                    results[ci] = batch_results[offset]
                else:
                    results[ci] = ProviderResponse(
                        found=False, data={}, credits_used=0,
                    )

        # ---- Sequential path (no LinkedIn URL) ----
        for idx in sequential_indices:
            row = rows[idx]
            resp = await self.find_email(
                row.get("first_name", ""),
                row.get("last_name", ""),
                row.get("domain", ""),
            )
            results[idx] = resp

        # Safety: replace any lingering None entries.
        return [
            r if r is not None else ProviderResponse(found=False, data={}, credits_used=0)
            for r in results
        ]

    async def _poll_batch_job(self, job_id: str) -> list[ProviderResponse]:
        """Poll ``GET /v2/people/linkedin/batch/<job_id>`` with adaptive
        backoff (1s -> 5s max) until the job reaches ``status == "DONE"``."""
        poll_url = f"/v2/people/linkedin/batch/{job_id}"
        poll_interval = 1.0   # start fast, back off exponentially
        max_interval = 5.0
        iterations = 0

        while True:
            iterations += 1
            if iterations > MAX_POLL_ITERATIONS:
                logger.warning(
                    "ContactOut batch polling exceeded %d iterations",
                    MAX_POLL_ITERATIONS,
                )
                return []
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, max_interval)

            try:
                data, elapsed = await self._get(poll_url)
            except httpx.HTTPStatusError as exc:
                error_resp = self._handle_error(exc)
                return [error_resp]

            status = data.get("status", "")
            if status.upper() == "DONE":
                # Parse individual results
                people = data.get("results", [])
                if not isinstance(people, list):
                    people = []
                return [
                    self._parse_email_response(p, elapsed) for p in people
                ]

            # If the API returns an explicit failure status, bail out.
            if status.upper() in ("FAILED", "ERROR"):
                return [
                    ProviderResponse(
                        found=False,
                        data=data,
                        error=f"ContactOut batch job {job_id} failed",
                        credits_used=0,
                    )
                ]
            # Otherwise keep polling.

    # ------------------------------------------------------------------
    # check_credits — not directly supported
    # ------------------------------------------------------------------

    async def check_credits(self) -> Optional[dict]:
        """ContactOut does not expose a credit-check endpoint."""
        return None

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify the token is valid by making a lightweight API call."""
        try:
            await self._get(
                "/v1/domain/enrich", params={"domain": "contactout.com"},
            )
            return True
        except httpx.HTTPStatusError as exc:
            # A 404 is fine (just means no data), but 401 means bad token.
            if exc.response.status_code == 404:
                return True
            logger.warning(
                "ContactOut health check failed: HTTP %d",
                exc.response.status_code,
            )
            return False
        except httpx.TimeoutException:
            logger.warning("ContactOut health check failed: timeout")
            return False
        except OSError as exc:
            logger.warning(
                "ContactOut health check failed: connection error: %s", exc,
            )
            return False
