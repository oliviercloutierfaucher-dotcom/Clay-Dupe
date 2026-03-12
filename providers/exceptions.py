"""Typed exceptions for provider error boundaries."""
from __future__ import annotations


class ProviderError(Exception):
    """Base exception for all provider errors."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"{provider}: {message}")


class ProviderAuthError(ProviderError):
    """Invalid or missing API key (HTTP 401/403)."""


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, provider: str, retry_after: int | None = None):
        self.retry_after = retry_after
        msg = "rate limited (429)"
        if retry_after:
            msg += f" — Retry-After: {retry_after}s"
        super().__init__(provider, msg)


class ProviderNotFoundError(ProviderError):
    """Resource not found (HTTP 404)."""


class ProviderValidationError(ProviderError):
    """Invalid request parameters (HTTP 422)."""


class ProviderTimeoutError(ProviderError):
    """Request timed out."""


class ProviderConnectionError(ProviderError):
    """Network connectivity failure."""


class ProviderAPIError(ProviderError):
    """Unexpected API error (5xx or unrecognized status)."""

    def __init__(self, provider: str, status_code: int, message: str | None = None):
        self.status_code = status_code
        super().__init__(provider, message or f"HTTP {status_code} error")
