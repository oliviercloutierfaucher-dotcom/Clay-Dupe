"""Datagma provider — email finder & company enrichment."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from providers.base import BaseProvider, ProviderResponse
from providers.validators import validate_domain, validate_name
from config.settings import ProviderName
from data.models import Company, Person

logger = logging.getLogger(__name__)


class DatagmaProvider(BaseProvider):
    """Datagma API integration.

    Docs: https://docs.datagma.com
    Auth: apiId query parameter (not header-based).
    """

    name = ProviderName.DATAGMA
    base_url = "https://gateway.datagma.net"

    # ------------------------------------------------------------------
    # find_email
    # ------------------------------------------------------------------
    async def find_email(
        self, first_name: str, last_name: str, domain: str
    ) -> ProviderResponse:
        """GET /api/ingress/v6/findEmail — find email by full name + domain."""
        first_name = validate_name("Datagma", first_name, "first_name")
        last_name = validate_name("Datagma", last_name, "last_name")
        domain = validate_domain("Datagma", domain)

        url = f"{self.base_url}/api/ingress/v6/findEmail"
        params = {
            "apiId": self.api_key,
            "fullName": f"{first_name} {last_name}",
            "company": domain,
            "findEmailV2Step": "3",
            "findEmailV2Country": "General",
        }

        try:
            raw, elapsed_ms = await self._request("GET", url, params=params)
        except httpx.HTTPStatusError as exc:
            return self._handle_http_error(exc)

        # Response may nest results under a "data" key
        inner = raw.get("data", {}) if isinstance(raw.get("data"), dict) else raw

        email = inner.get("email")
        email_status = inner.get("emailStatus", "")

        if not email:
            # Check for "Most Probable Email" (unverified guess)
            probable = inner.get("mostProbableEmail") or raw.get("mostProbableEmail")
            if probable:
                return ProviderResponse(
                    found=True,
                    data=raw,
                    email=probable,
                    confidence="guessed",
                    credits_used=0,
                    response_time_ms=elapsed_ms,
                )
            return ProviderResponse(
                found=False,
                data=raw,
                credits_used=0,
                response_time_ms=elapsed_ms,
            )

        confidence = "verified" if email_status == "verified" else "guessed"
        credits = 1.0 if confidence == "verified" else 0

        return ProviderResponse(
            found=True,
            data=raw,
            email=email,
            confidence=confidence,
            credits_used=credits,
            response_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # enrich_company
    # ------------------------------------------------------------------
    async def enrich_company(self, domain: str) -> ProviderResponse:
        """GET /api/ingress/v2/full — enrich company data from domain."""
        domain = validate_domain("Datagma", domain)

        url = f"{self.base_url}/api/ingress/v2/full"
        params = {
            "apiId": self.api_key,
            "data": domain,
            "companyPremium": "true",
        }

        try:
            data, elapsed_ms = await self._request("GET", url, params=params)
        except httpx.HTTPStatusError as exc:
            return self._handle_http_error(exc)

        company_data = {
            "name": data.get("companyName"),
            "domain": domain,
            "industry": data.get("industry"),
            "size": data.get("employeeCount"),
            "description": data.get("description"),
            "linkedin_url": data.get("linkedinUrl"),
            "country": data.get("country"),
            "city": data.get("city"),
            "revenue": data.get("revenue"),
        }

        return ProviderResponse(
            found=True,
            data=company_data,
            credits_used=2.0,
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
    # Error handling helper
    # ------------------------------------------------------------------
    @staticmethod
    def _handle_http_error(exc: httpx.HTTPStatusError) -> ProviderResponse:
        status = exc.response.status_code
        if status == 401:
            error_msg = "Datagma: invalid or missing API key"
        elif status == 422:
            error_msg = "Datagma: invalid request parameters"
        elif status == 429:
            error_msg = "Datagma: rate limited"
        else:
            error_msg = f"Datagma: HTTP {status} error"

        return ProviderResponse(
            found=False,
            data={},
            error=error_msg,
        )
