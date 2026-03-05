"""Input validation for provider method arguments.

Validates inputs *before* API calls are made so credits are not consumed
on obviously invalid data.
"""
from __future__ import annotations

import re

from providers.exceptions import ProviderValidationError

# Simple but practical patterns — not full RFC compliance.
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_LINKEDIN_RE = re.compile(r"https?://(www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+/?", re.IGNORECASE)


def validate_domain(provider: str, domain: str) -> str:
    """Validate and normalise a domain string. Returns cleaned domain."""
    if not domain or not domain.strip():
        raise ProviderValidationError(provider, "domain is required")
    cleaned = domain.strip().lower()
    # Strip protocol if present
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    cleaned = cleaned.removeprefix("www.").rstrip("/")
    if not _DOMAIN_RE.match(cleaned):
        raise ProviderValidationError(provider, f"invalid domain format: {domain!r}")
    return cleaned


def validate_email(provider: str, email: str) -> str:
    """Validate and normalise an email address. Returns cleaned email."""
    if not email or not email.strip():
        raise ProviderValidationError(provider, "email is required")
    cleaned = email.strip().lower()
    if not _EMAIL_RE.match(cleaned):
        raise ProviderValidationError(provider, f"invalid email format: {email!r}")
    return cleaned


def validate_name(provider: str, name: str, field: str = "name") -> str:
    """Validate a name field is non-empty. Returns stripped name."""
    if not name or not name.strip():
        raise ProviderValidationError(provider, f"{field} is required")
    return name.strip()


def validate_linkedin_url(provider: str, url: str) -> str:
    """Validate a LinkedIn profile URL. Returns cleaned URL."""
    if not url or not url.strip():
        raise ProviderValidationError(provider, "LinkedIn URL is required")
    cleaned = url.strip()
    if not _LINKEDIN_RE.match(cleaned):
        raise ProviderValidationError(provider, f"invalid LinkedIn URL: {url!r}")
    return cleaned
