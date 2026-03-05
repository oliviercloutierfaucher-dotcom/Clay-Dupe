"""Tests for malformed API response handling across all 4 providers.

Each test feeds a malformed response through the provider and verifies
that the result is a graceful ProviderResponse(found=False) — not an
unhandled exception.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from providers.apollo import ApolloProvider
from providers.findymail import FindymailProvider
from providers.icypeas import IcypeasProvider
from providers.contactout import ContactOutProvider
from providers.base import ProviderResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_request_returning(data: dict, elapsed_ms: int = 50):
    """Return an AsyncMock that resolves to (data, elapsed_ms)."""
    return AsyncMock(return_value=(data, elapsed_ms))


def _provider_with_mock(cls, mock_request):
    """Instantiate a provider and replace _request with a mock."""
    provider = cls(api_key="test-key", client=AsyncMock())
    provider._request = mock_request
    return provider


# ---------------------------------------------------------------------------
# Apollo — malformed find_email responses
# ---------------------------------------------------------------------------

class TestApolloMalformedResponses:
    @pytest.mark.asyncio
    async def test_missing_person_key(self):
        """Response with no 'person' key → found=False."""
        prov = _provider_with_mock(
            ApolloProvider, _mock_request_returning({"unrelated": "data"})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert isinstance(resp, ProviderResponse)
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_person_is_none(self):
        """person=None → found=False."""
        prov = _provider_with_mock(
            ApolloProvider, _mock_request_returning({"person": None})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_person_missing_email_fields(self):
        """person dict exists but has no email/email_status → found=False."""
        prov = _provider_with_mock(
            ApolloProvider, _mock_request_returning({"person": {"id": "123"}})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Completely empty dict → found=False."""
        prov = _provider_with_mock(
            ApolloProvider, _mock_request_returning({})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_person_email_status_unknown(self):
        """Unknown email_status value → found=False."""
        prov = _provider_with_mock(
            ApolloProvider,
            _mock_request_returning({
                "person": {"email": "j@acme.com", "email_status": "unavailable"}
            }),
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False


# ---------------------------------------------------------------------------
# Findymail — malformed find_email responses
# ---------------------------------------------------------------------------

class TestFindymailMalformedResponses:
    @pytest.mark.asyncio
    async def test_missing_email_key(self):
        """No 'email' field → found=False."""
        prov = _provider_with_mock(
            FindymailProvider, _mock_request_returning({"status": "ok"})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_email_is_none(self):
        """email=None → found=False."""
        prov = _provider_with_mock(
            FindymailProvider, _mock_request_returning({"email": None})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_email_is_empty_string(self):
        """email='' → found=False."""
        prov = _provider_with_mock(
            FindymailProvider, _mock_request_returning({"email": ""})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Completely empty dict → found=False."""
        prov = _provider_with_mock(
            FindymailProvider, _mock_request_returning({})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False


# ---------------------------------------------------------------------------
# Icypeas — malformed find_email responses
# ---------------------------------------------------------------------------

class TestIcypeasMalformedResponses:
    @pytest.mark.asyncio
    async def test_missing_emails_key(self):
        """No 'emails' array → found=False."""
        prov = _provider_with_mock(
            IcypeasProvider, _mock_request_returning({"status": "FOUND"})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_emails_empty_array(self):
        """emails=[] → found=False."""
        prov = _provider_with_mock(
            IcypeasProvider,
            _mock_request_returning({"status": "FOUND", "emails": []}),
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_status_not_found(self):
        """status != 'FOUND' → found=False even if emails present."""
        prov = _provider_with_mock(
            IcypeasProvider,
            _mock_request_returning({
                "status": "ERROR",
                "emails": [{"email": "j@acme.com", "certainty": "SURE"}],
            }),
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Completely empty dict → found=False."""
        prov = _provider_with_mock(
            IcypeasProvider, _mock_request_returning({})
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_emails_item_missing_email_field(self):
        """First email item has no 'email' key → found=True but email is None."""
        prov = _provider_with_mock(
            IcypeasProvider,
            _mock_request_returning({
                "status": "FOUND",
                "emails": [{"certainty": "SURE"}],
            }),
        )
        resp = await prov.find_email("John", "Doe", "acme.com")
        # found=True because status=FOUND and emails is non-empty,
        # but email field is None
        assert resp.found is True
        assert resp.email is None


# ---------------------------------------------------------------------------
# ContactOut — malformed find_email responses
# ---------------------------------------------------------------------------

class TestContactOutMalformedResponses:
    @pytest.mark.asyncio
    async def test_missing_email_arrays(self):
        """No work_email or personal_email → found=False."""
        prov = _provider_with_mock(
            ContactOutProvider, _mock_request_returning({"profile": {}})
        )
        # ContactOut find_email calls _parse_email_response for non-LinkedIn
        # We need to mock the actual endpoint path
        resp = ContactOutProvider._parse_email_response({"profile": {}}, 50)
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_empty_email_arrays(self):
        """work_email=[], personal_email=[] → found=False."""
        resp = ContactOutProvider._parse_email_response(
            {"work_email": [], "personal_email": [], "profile": {}}, 50
        )
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_email_arrays_are_none(self):
        """work_email=None, personal_email=None → found=False."""
        resp = ContactOutProvider._parse_email_response(
            {"work_email": None, "personal_email": None, "profile": None}, 50
        )
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_empty_response(self):
        """Completely empty dict → found=False."""
        resp = ContactOutProvider._parse_email_response({}, 50)
        assert resp.found is False

    @pytest.mark.asyncio
    async def test_profile_missing(self):
        """No profile key → still parses emails, no crash."""
        resp = ContactOutProvider._parse_email_response(
            {"work_email": ["j@acme.com"]}, 50
        )
        assert resp.found is True
        assert resp.email == "j@acme.com"
