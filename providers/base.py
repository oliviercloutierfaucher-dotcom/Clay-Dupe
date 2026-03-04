"""Abstract base class for all enrichment providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
import time
import httpx

from config.settings import ProviderName
from data.models import Company, Person


@dataclass
class ProviderResponse:
    """Standard response from any provider call."""
    found: bool
    data: dict = field(default_factory=dict)
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    confidence: Optional[str] = None
    credits_used: float = 0.0
    response_time_ms: int = 0
    error: Optional[str] = None


class BaseProvider(ABC):
    """Interface that all providers implement."""

    name: ProviderName
    base_url: str

    def __init__(self, api_key: str, client: Optional[httpx.AsyncClient] = None):
        self.api_key = api_key
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
            )
        return self._client

    async def _request(self, method: str, url: str, **kwargs) -> tuple[dict, int]:
        """Make an HTTP request and return (response_json, elapsed_ms).
        Subclasses should use this for all API calls."""
        client = await self._get_client()
        start = time.monotonic()
        response = await client.request(method, url, **kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        response.raise_for_status()
        return response.json(), elapsed_ms

    @abstractmethod
    async def find_email(self, first_name: str, last_name: str, domain: str) -> ProviderResponse:
        """Find email for a person at a domain."""
        ...

    @abstractmethod
    async def search_companies(self, **filters) -> list[Company]:
        """Search for companies matching filters."""
        ...

    @abstractmethod
    async def search_people(self, **filters) -> list[Person]:
        """Search for people matching filters."""
        ...

    @abstractmethod
    async def enrich_company(self, domain: str) -> ProviderResponse:
        """Get company details from domain."""
        ...

    async def verify_email(self, email: str) -> ProviderResponse:
        """Verify an email address. Not all providers support this."""
        return ProviderResponse(found=False, data={}, error="Not supported")

    async def find_email_batch(self, rows: list[dict]) -> list[ProviderResponse]:
        """Batch email finding. Default: sequential single calls.
        Providers with batch APIs should override this."""
        results = []
        for row in rows:
            result = await self.find_email(
                row.get("first_name", ""),
                row.get("last_name", ""),
                row.get("domain", ""),
            )
            results.append(result)
        return results

    async def check_credits(self) -> Optional[dict]:
        """Check remaining credits. Returns None if not supported."""
        return None

    async def health_check(self) -> bool:
        """Test if the API key is valid and the service is reachable."""
        try:
            await self.check_credits()
            return True
        except Exception:
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
