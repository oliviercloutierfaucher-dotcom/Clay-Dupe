"""Icypeas provider — email finder, verifier & bulk search."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from providers.base import BaseProvider, ProviderResponse
from config.settings import ProviderName
from data.models import Company, Person

logger = logging.getLogger(__name__)


class IcypeasProvider(BaseProvider):
    """Icypeas API integration.

    Docs: https://app.icypeas.com/api
    Rate limits: 10 req/sec (single), 1 req/sec (bulk).
    Auth: raw API key in Authorization header (no Bearer prefix).
    """

    name = ProviderName.ICYPEAS
    base_url = "https://app.icypeas.com/api"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Certainty -> confidence mapping
    # ------------------------------------------------------------------
    @staticmethod
    def _map_certainty(certainty: str) -> str:
        """Map Icypeas certainty levels to standard confidence values."""
        mapping = {
            "ULTRA_SURE": "verified",
            "SURE": "unverified",
            "PROBABLE": "risky",
        }
        return mapping.get(certainty, "unknown")

    # ------------------------------------------------------------------
    # find_email
    # ------------------------------------------------------------------
    async def find_email(
        self, first_name: str, last_name: str, domain: str
    ) -> ProviderResponse:
        """POST /api/sync/email-search — find email by name + domain."""
        url = f"{self.base_url}/sync/email-search"
        payload = {
            "firstname": first_name,
            "lastname": last_name,
            "domainOrCompany": domain,
        }

        try:
            data, elapsed_ms = await self._request(
                "POST", url, headers=self._headers(), json=payload,
            )
        except httpx.HTTPStatusError as exc:
            return self._handle_http_error(exc)

        status = data.get("status")
        emails = data.get("emails", [])

        if status == "FOUND" and emails:
            first_email = emails[0]
            email = first_email.get("email")
            certainty = first_email.get("certainty", "")
            confidence = self._map_certainty(certainty)

            return ProviderResponse(
                found=True,
                data=data,
                email=email,
                confidence=confidence,
                credits_used=1,
                response_time_ms=elapsed_ms,
            )

        return ProviderResponse(
            found=False,
            data=data,
            credits_used=0,
            response_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # search_companies — not supported
    # ------------------------------------------------------------------
    async def search_companies(self, **filters) -> list[Company]:
        return []

    # ------------------------------------------------------------------
    # search_people — not supported
    # ------------------------------------------------------------------
    async def search_people(self, **filters) -> list[Person]:
        return []

    # ------------------------------------------------------------------
    # enrich_company — not supported
    # ------------------------------------------------------------------
    async def enrich_company(self, domain: str) -> ProviderResponse:
        return ProviderResponse(found=False, data={}, error="Not supported")

    # ------------------------------------------------------------------
    # verify_email
    # ------------------------------------------------------------------
    async def verify_email(self, email: str) -> ProviderResponse:
        """POST /api/sync/email-verification — verify a single email."""
        url = f"{self.base_url}/sync/email-verification"
        payload = {"email": email}

        try:
            data, elapsed_ms = await self._request(
                "POST", url, headers=self._headers(), json=payload,
            )
        except httpx.HTTPStatusError as exc:
            return self._handle_http_error(exc)

        status = data.get("status", "unknown")

        confidence_map = {
            "VALID": "verified",
            "INVALID": "invalid",
            "RISKY": "risky",
            "UNKNOWN": "unknown",
        }
        confidence = confidence_map.get(status, "unknown")

        return ProviderResponse(
            found=True,
            data=data,
            email=data.get("email", email),
            confidence=confidence,
            credits_used=1,
            response_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # find_email_batch — bulk async endpoint override
    # ------------------------------------------------------------------
    async def find_email_batch(self, rows: list[dict]) -> list[ProviderResponse]:
        """Bulk email search using the Icypeas async bulk API.

        1. Submit bulk job via POST /api/bulk (max 5000 rows).
        2. Poll results via POST /api/bulk-single-searchs/read.
        3. Poll every 2 seconds until all rows are resolved.
        4. Paginate with limit=100 and next=true.
        """
        if not rows:
            return []

        # ------ Step 1: Submit the bulk job ------
        batch_data = []
        for row in rows:
            batch_data.append([
                row.get("first_name", ""),
                row.get("last_name", ""),
                row.get("domain", ""),
            ])

        submit_url = f"{self.base_url}/bulk"
        submit_payload = {
            "name": f"batch_{id(rows)}",
            "task": "email-search",
            "data": batch_data[:5000],
        }

        try:
            submit_resp, _ = await self._request(
                "POST", submit_url, headers=self._headers(), json=submit_payload,
            )
        except httpx.HTTPStatusError as exc:
            error_resp = self._handle_http_error(exc)
            return [error_resp] * len(rows)

        item = submit_resp.get("item", {})
        bulk_id = item.get("_id")

        if not bulk_id:
            error_resp = ProviderResponse(
                found=False,
                data=submit_resp,
                error="Icypeas: bulk submission failed — no bulk ID returned",
            )
            return [error_resp] * len(rows)

        # ------ Step 2 & 3: Poll for results ------
        read_url = f"{self.base_url}/bulk-single-searchs/read"
        collected_items: list[dict] = []
        total_expected = len(rows)

        while len(collected_items) < total_expected:
            await asyncio.sleep(2)

            # Paginate through available results
            page_items: list[dict] = []
            keep_reading = True

            while keep_reading:
                read_payload = {
                    "file": bulk_id,
                    "mode": "bulk",
                    "limit": 100,
                    "next": True,
                }

                try:
                    read_resp, _ = await self._request(
                        "POST", read_url, headers=self._headers(), json=read_payload,
                    )
                except httpx.HTTPStatusError as exc:
                    error_resp = self._handle_http_error(exc)
                    # Return what we have so far plus errors for the rest
                    remaining = total_expected - len(collected_items)
                    return (
                        self._parse_bulk_items(collected_items)
                        + [error_resp] * remaining
                    )

                items = read_resp.get("items", [])
                if not items:
                    keep_reading = False
                    break

                page_items.extend(items)

                # If we got fewer than 100 items, we've exhausted this page
                if len(items) < 100:
                    keep_reading = False

            # Check for still-processing items (status "NONE")
            resolved = []
            has_pending = False
            for item in page_items:
                status = item.get("status", "NONE")
                if status == "NONE":
                    has_pending = True
                else:
                    resolved.append(item)

            collected_items.extend(resolved)

            # If nothing is still pending and we got no new pages, we're done
            if not has_pending and not page_items:
                break

        return self._parse_bulk_items(collected_items, total_expected)

    def _parse_bulk_items(
        self, items: list[dict], expected_count: int | None = None
    ) -> list[ProviderResponse]:
        """Convert raw bulk result items into ProviderResponse objects."""
        results: list[ProviderResponse] = []

        for item in items:
            status = item.get("status", "")
            emails = item.get("emails", [])

            if status == "DEBITED" and emails:
                first_email = emails[0]
                email = first_email.get("email")
                certainty = first_email.get("certainty", "")
                confidence = self._map_certainty(certainty)

                results.append(ProviderResponse(
                    found=True,
                    data=item,
                    email=email,
                    confidence=confidence,
                    credits_used=1,
                ))
            else:
                # NOT_FOUND or any other terminal status
                results.append(ProviderResponse(
                    found=False,
                    data=item,
                    credits_used=0,
                ))

        # Pad with not-found responses if we got fewer results than expected
        if expected_count is not None:
            while len(results) < expected_count:
                results.append(ProviderResponse(
                    found=False,
                    data={},
                    error="Icypeas: bulk result missing for this row",
                ))

        return results

    # ------------------------------------------------------------------
    # check_credits — not available via API
    # ------------------------------------------------------------------
    async def check_credits(self) -> Optional[dict]:
        return None

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------
    async def health_check(self) -> bool:
        """Test connectivity with a lightweight email search call."""
        try:
            resp = await self.find_email("test", "user", "example.com")
            return resp.error is None
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Icypeas health check failed: HTTP %d", exc.response.status_code,
            )
            return False
        except httpx.TimeoutException:
            logger.warning("Icypeas health check failed: timeout")
            return False
        except OSError as exc:
            logger.warning("Icypeas health check failed: connection error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Error handling helper
    # ------------------------------------------------------------------
    @staticmethod
    def _handle_http_error(exc: httpx.HTTPStatusError) -> ProviderResponse:
        status = exc.response.status_code
        if status == 401:
            error_msg = "Icypeas: invalid or missing API key"
        elif status == 429:
            error_msg = "Icypeas: rate limited"
        else:
            error_msg = f"Icypeas: HTTP {status} error"

        return ProviderResponse(
            found=False,
            data={},
            error=error_msg,
        )
