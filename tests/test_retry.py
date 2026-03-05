"""Tests for standardized tenacity retry logic across all providers."""
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from providers.apollo import ApolloProvider
from providers.findymail import FindymailProvider
from providers.icypeas import IcypeasProvider
from providers.contactout import ContactOutProvider
from providers.base import _is_retryable


# ---------------------------------------------------------------------------
# _is_retryable helper
# ---------------------------------------------------------------------------

class TestIsRetryable:
    def test_timeout_is_retryable(self):
        assert _is_retryable(httpx.ReadTimeout("timeout")) is True

    def test_connect_timeout_is_retryable(self):
        assert _is_retryable(httpx.ConnectTimeout("timeout")) is True

    def test_429_is_retryable(self):
        response = httpx.Response(429, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("rate limited", request=response.request, response=response)
        assert _is_retryable(exc) is True

    def test_500_is_retryable(self):
        response = httpx.Response(500, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("server error", request=response.request, response=response)
        assert _is_retryable(exc) is True

    def test_502_is_retryable(self):
        response = httpx.Response(502, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("bad gateway", request=response.request, response=response)
        assert _is_retryable(exc) is True

    def test_503_is_retryable(self):
        response = httpx.Response(503, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("unavailable", request=response.request, response=response)
        assert _is_retryable(exc) is True

    def test_401_not_retryable(self):
        response = httpx.Response(401, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("unauthorized", request=response.request, response=response)
        assert _is_retryable(exc) is False

    def test_403_not_retryable(self):
        response = httpx.Response(403, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("forbidden", request=response.request, response=response)
        assert _is_retryable(exc) is False

    def test_422_not_retryable(self):
        response = httpx.Response(422, request=httpx.Request("GET", "https://x.com"))
        exc = httpx.HTTPStatusError("unprocessable", request=response.request, response=response)
        assert _is_retryable(exc) is False

    def test_os_error_is_retryable(self):
        assert _is_retryable(OSError("connection reset")) is True

    def test_value_error_not_retryable(self):
        assert _is_retryable(ValueError("bad value")) is False


# ---------------------------------------------------------------------------
# Retry on transient 500 — verifies tenacity is wired in
# ---------------------------------------------------------------------------

def _make_500_response():
    resp = MagicMock()
    resp.status_code = 500
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error",
        request=httpx.Request("POST", "https://api.test/v1"),
        response=httpx.Response(500, request=httpx.Request("POST", "https://api.test/v1")),
    )
    return resp


def _make_ok_response(data: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestRetryOnTransient500:
    """A simulated transient 500 triggers retry before returning success."""

    @pytest.mark.asyncio
    async def test_apollo_retries_on_500(self):
        provider = ApolloProvider(api_key="test")
        mock_client = AsyncMock()
        # First call: 500, second call: success
        mock_client.request.side_effect = [
            _make_500_response(),
            _make_ok_response({"person": {"email": "a@b.com", "email_status": "verified"}}),
        ]
        provider._client = mock_client
        result = await provider.find_email("John", "Doe", "acme.com")
        assert result.found is True
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_findymail_retries_on_500(self):
        provider = FindymailProvider(api_key="test")
        mock_client = AsyncMock()
        mock_client.request.side_effect = [
            _make_500_response(),
            _make_ok_response({"email": "a@b.com", "status": "valid"}),
        ]
        provider._client = mock_client
        result = await provider.find_email("John", "Doe", "acme.com")
        assert result.found is True
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_icypeas_retries_on_500(self):
        provider = IcypeasProvider(api_key="test")
        mock_client = AsyncMock()
        mock_client.request.side_effect = [
            _make_500_response(),
            _make_ok_response({"status": "FOUND", "emails": [{"email": "a@b.com", "certainty": "SURE"}]}),
        ]
        provider._client = mock_client
        result = await provider.find_email("John", "Doe", "acme.com")
        assert result.found is True
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_contactout_retries_on_500(self):
        provider = ContactOutProvider(api_key="test")
        mock_client = AsyncMock()
        mock_client.request.side_effect = [
            _make_500_response(),
            _make_ok_response({"work_email": ["a@b.com"], "personal_email": [], "profile": {}}),
        ]
        provider._client = mock_client
        result = await provider.find_email("John", "Doe", "acme.com")
        assert result.found is True
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_401_fails_immediately(self):
        provider = ApolloProvider(api_key="bad_key")
        mock_client = AsyncMock()
        resp = MagicMock()
        resp.status_code = 401
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "unauthorized",
            request=httpx.Request("POST", "https://api.test/v1"),
            response=httpx.Response(401, request=httpx.Request("POST", "https://api.test/v1")),
        )
        mock_client.request.return_value = resp
        provider._client = mock_client
        # 401 should propagate immediately via _handle_error, no retry
        result = await provider.find_email("John", "Doe", "acme.com")
        assert result.found is False
        assert "invalid API key" in (result.error or "")
        # Should only call once — no retry for 401
        assert mock_client.request.call_count == 1
