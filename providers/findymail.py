"""Findymail provider — email finder & verifier."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from providers.base import BaseProvider, ProviderResponse
from config.settings import ProviderName
from data.models import Company, Person

logger = logging.getLogger(__name__)


class FindymailProvider(BaseProvider):
    """Findymail API integration.

    Docs: https://app.findymail.com/docs
    Rate limit: 300 concurrent requests, no daily cap.
    """

    name = ProviderName.FINDYMAIL
    base_url = "https://app.findymail.com/api"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # find_email
    # ------------------------------------------------------------------
    async def find_email(
        self, first_name: str, last_name: str, domain: str
    ) -> ProviderResponse:
        """POST /api/search/name — find email by full name + domain."""
        url = f"{self.base_url}/search/name"
        payload = {
            "name": f"{first_name} {last_name}",
            "domain": domain,
        }

        try:
            data, elapsed_ms = await self._request(
                "POST", url, headers=self._headers(), json=payload,
            )
        except httpx.HTTPStatusError as exc:
            return self._handle_http_error(exc)

        email = data.get("email")
        if email:
            return ProviderResponse(
                found=True,
                data=data,
                email=email,
                confidence="high",
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
        """POST /api/verify — verify a single email address."""
        url = f"{self.base_url}/verify"
        payload = {"email": email}

        try:
            data, elapsed_ms = await self._request(
                "POST", url, headers=self._headers(), json=payload,
            )
        except httpx.HTTPStatusError as exc:
            return self._handle_http_error(exc)

        status = data.get("status", "unknown")

        confidence_map = {
            "valid": "verified",
            "invalid": "invalid",
            "catch_all": "catch_all",
            "unknown": "unknown",
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
    # check_credits
    # ------------------------------------------------------------------
    async def check_credits(self) -> Optional[dict]:
        """GET /api/credits — return remaining credit balance."""
        url = f"{self.base_url}/credits"
        data, _ = await self._request(
            "GET", url, headers=self._headers(),
        )
        return data

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------
    async def health_check(self) -> bool:
        """Check connectivity by fetching credit balance."""
        try:
            await self.check_credits()
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Findymail health check failed: HTTP %d", exc.response.status_code,
            )
            return False
        except httpx.TimeoutException:
            logger.warning("Findymail health check failed: timeout")
            return False
        except OSError as exc:
            logger.warning("Findymail health check failed: connection error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # find_email_batch — uses default sequential implementation
    # ------------------------------------------------------------------
    # Inherited from BaseProvider.find_email_batch (no batch endpoint).

    # ------------------------------------------------------------------
    # Error handling helper
    # ------------------------------------------------------------------
    @staticmethod
    def _handle_http_error(exc: httpx.HTTPStatusError) -> ProviderResponse:
        status = exc.response.status_code
        if status == 401:
            error_msg = "Findymail: invalid or missing API token"
        elif status == 422:
            error_msg = "Findymail: missing required fields"
        elif status == 429:
            error_msg = "Findymail: rate limited"
        else:
            error_msg = f"Findymail: HTTP {status} error"

        return ProviderResponse(
            found=False,
            data={},
            error=error_msg,
        )
