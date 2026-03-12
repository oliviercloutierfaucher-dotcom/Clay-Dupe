"""Tests for security and bug fixes — Plan 12.1-01.

Covers:
- SOQL injection escaping (_escape_soql)
- CLI factory function argument correctness
- Icypeas bulk polling timeout guard
- ContactOut batch polling max-iteration guard
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SOQL escaping tests
# ---------------------------------------------------------------------------

class TestEscapeSoql:
    """Verify _escape_soql handles dangerous characters."""

    def test_escape_soql_single_quotes(self):
        from providers.salesforce import _escape_soql
        assert _escape_soql("O'Brien") == "O\\'Brien"

    def test_escape_soql_backslashes(self):
        from providers.salesforce import _escape_soql
        # Backslashes must be escaped FIRST to avoid double-escaping
        result = _escape_soql("a\\b")
        assert "\\\\" in result  # original backslash becomes \\

    def test_escape_soql_like_wildcards(self):
        from providers.salesforce import _escape_soql
        result = _escape_soql("50%_off")
        assert "\\%" in result
        assert "\\_" in result

    def test_escape_soql_control_chars(self):
        from providers.salesforce import _escape_soql
        result = _escape_soql("ab\x00cd")
        assert "\x00" not in result
        assert "abcd" in result

    def test_escape_soql_clean_domain(self):
        from providers.salesforce import _escape_soql
        assert _escape_soql("example.com") == "example.com"


# ---------------------------------------------------------------------------
# CLI factory function tests
# ---------------------------------------------------------------------------

class TestCliFactoryFunctions:
    """Verify create_circuit_breakers() and create_rate_limiters() work with zero args."""

    def test_cli_circuit_breakers_no_args(self):
        from quality.circuit_breaker import create_circuit_breakers
        result = create_circuit_breakers()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_cli_rate_limiters_no_args(self):
        from quality.circuit_breaker import create_rate_limiters
        result = create_rate_limiters()
        assert isinstance(result, dict)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Icypeas polling timeout tests
# ---------------------------------------------------------------------------

class TestIcypeasPollingTimeout:
    """Verify Icypeas bulk polling exits after MAX_POLL_TIMEOUT."""

    @pytest.mark.asyncio
    async def test_icypeas_polling_timeout(self):
        """Mock the polling loop so it never resolves; verify it exits via timeout."""
        import providers.icypeas as icypeas_mod
        from providers.icypeas import IcypeasProvider

        provider = IcypeasProvider(api_key="test-key")

        # Mock _request to return a successful bulk submission
        submit_response = {"item": {"_id": "bulk123"}}
        # Poll response that always has pending items (never resolves)
        poll_response = {"items": [{"status": "NONE"}]}

        call_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "bulk-single-searchs/read" in url:
                return (poll_response, 50)
            return (submit_response, 50)

        provider._request = mock_request

        # Use a very small timeout for testing
        original_timeout = icypeas_mod.MAX_POLL_TIMEOUT
        icypeas_mod.MAX_POLL_TIMEOUT = 2  # 2 seconds for test

        start = time.monotonic()
        try:
            results = await provider.find_email_batch([
                {"first_name": "Test", "last_name": "User", "domain": "example.com"}
            ])
        finally:
            icypeas_mod.MAX_POLL_TIMEOUT = original_timeout

        elapsed = time.monotonic() - start
        # Should exit within a reasonable time (timeout + some margin)
        assert elapsed < 10, f"Polling took {elapsed:.1f}s, expected < 10s"
        # Should have been called at least once
        assert call_count >= 2  # submit + at least one poll


# ---------------------------------------------------------------------------
# ContactOut polling max-iteration tests
# ---------------------------------------------------------------------------

class TestContactOutPollingMaxIterations:
    """Verify ContactOut batch polling exits after MAX_POLL_ITERATIONS."""

    @pytest.mark.asyncio
    async def test_contactout_polling_max_iterations(self):
        """Mock the polling loop so it never returns DONE; verify it exits via iteration cap."""
        from providers.contactout import ContactOutProvider, MAX_POLL_ITERATIONS

        provider = ContactOutProvider(api_key="test-key")

        poll_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal poll_count
            if "batch" in url and method == "POST":
                return ({"job_id": "job123"}, 50)
            # Polling: always return PROCESSING
            poll_count += 1
            return ({"status": "PROCESSING", "results": []}, 50)

        provider._request = mock_request

        # Use small iteration cap for testing
        import providers.contactout as contactout_mod
        original_max = contactout_mod.MAX_POLL_ITERATIONS
        contactout_mod.MAX_POLL_ITERATIONS = 3  # 3 iterations for test

        try:
            results = await provider._poll_batch_job("job123")
        finally:
            contactout_mod.MAX_POLL_ITERATIONS = original_max

        # Should return empty list (exceeded max iterations)
        assert results == []
        # Should have polled exactly MAX_POLL_ITERATIONS times
        assert poll_count == 3
