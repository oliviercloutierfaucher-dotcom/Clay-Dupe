"""Email verification pipeline using Reoon API (preferred) or DNS/SMTP fallback."""
from __future__ import annotations

import asyncio
import logging
import random
import smtplib
import string
import time
from typing import Optional

import dns.resolver
import httpx

logger = logging.getLogger(__name__)


class SMTPRateLimiter:
    """Rate limiter for SMTP probes. Max 1 per domain per 5s, 2/sec globally."""

    def __init__(self, per_domain_interval: float = 5.0, global_per_second: float = 2.0):
        self.per_domain_interval = per_domain_interval
        self.global_per_second = global_per_second
        self._domain_last_probe: dict[str, float] = {}
        self._global_last_probe: float = 0.0
        self._lock = asyncio.Lock()

    async def wait_for_slot(self, domain: str):
        """Wait until we can probe this domain without getting blacklisted."""
        async with self._lock:
            now = time.monotonic()
            min_global_wait = (1.0 / self.global_per_second)
            global_wait = max(0, min_global_wait - (now - self._global_last_probe))
            domain_wait = 0.0
            if domain in self._domain_last_probe:
                domain_wait = max(0, self.per_domain_interval - (now - self._domain_last_probe[domain]))
            wait_time = max(global_wait, domain_wait)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            now = time.monotonic()
            self._global_last_probe = now
            self._domain_last_probe[domain] = now


class EmailVerifier:
    """Email verification with Reoon API (preferred) or local SMTP fallback.

    If a Reoon API key is provided, verification uses their API for
    accurate results without risking IP blacklisting. Otherwise falls
    back to the 4-stage local pipeline: syntax -> MX -> catch-all -> SMTP.
    """

    from providers.validators import _EMAIL_RE
    EMAIL_REGEX = _EMAIL_RE

    REOON_API_URL = "https://emailverifier.reoon.com/api/v1/verify"

    # Map Reoon status to our internal format
    _REOON_STATUS_MAP = {
        "valid": {"valid": True, "smtp_result": "valid", "confidence_modifier": 20},
        "invalid": {"valid": False, "smtp_result": "invalid", "confidence_modifier": -40},
        "disposable": {"valid": False, "smtp_result": "disposable", "confidence_modifier": -50},
        "accept_all": {"valid": True, "smtp_result": "catch_all", "confidence_modifier": -15, "catch_all": True},
        "unknown": {"valid": False, "smtp_result": "unknown", "confidence_modifier": 0},
        "spamtrap": {"valid": False, "smtp_result": "spamtrap", "confidence_modifier": -50},
    }

    def __init__(self, sender_domain: str = "verify.example.com", reoon_api_key: str = ""):
        self.sender_domain = sender_domain
        self.reoon_api_key = reoon_api_key
        self._catch_all_cache: dict[str, Optional[bool]] = {}
        self._rate_limiter = SMTPRateLimiter()

    # ------------------------------------------------------------------
    # Reoon API verification (preferred path)
    # ------------------------------------------------------------------

    async def _verify_reoon(self, email: str) -> dict:
        """Verify email via Reoon API. Returns standard result dict."""
        result = {
            "email": email,
            "valid": False,
            "catch_all": False,
            "mx_found": True,
            "smtp_result": "unknown",
            "confidence_modifier": 0,
            "verification_source": "reoon",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.REOON_API_URL,
                    params={
                        "email": email,
                        "key": self.reoon_api_key,
                        "mode": "quick",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            status = data.get("status", "unknown").lower()
            mapped = self._REOON_STATUS_MAP.get(status, self._REOON_STATUS_MAP["unknown"])

            result["valid"] = mapped["valid"]
            result["smtp_result"] = mapped["smtp_result"]
            result["confidence_modifier"] = mapped["confidence_modifier"]
            result["catch_all"] = mapped.get("catch_all", False)
            result["mx_found"] = data.get("mx_found", True)
            result["reoon_raw"] = data

        except httpx.HTTPStatusError as exc:
            logger.warning("Reoon API error for %s: HTTP %d", email, exc.response.status_code)
            result["smtp_result"] = "api_error"
        except (httpx.RequestError, Exception) as exc:
            logger.warning("Reoon API request failed for %s: %s", email, exc)
            result["smtp_result"] = "api_error"

        return result

    # ------------------------------------------------------------------
    # Local SMTP fallback (used when no Reoon key)
    # ------------------------------------------------------------------

    def check_syntax(self, email: str) -> bool:
        """Stage 1: RFC 5322 regex check. Instant, free."""
        if not email or not isinstance(email, str):
            return False
        return bool(self.EMAIL_REGEX.match(email))

    def check_mx(self, domain: str) -> list[str]:
        """Stage 2: Return MX hosts sorted by priority. Uses dnspython."""
        try:
            answers = dns.resolver.resolve(domain, 'MX')
            mx_hosts = [(r.preference, str(r.exchange).rstrip('.')) for r in answers]
            mx_hosts.sort(key=lambda x: x[0])
            return [host for _, host in mx_hosts]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers, dns.exception.Timeout):
            return []

    async def detect_catch_all(self, domain: str) -> Optional[bool]:
        """Stage 3: Probe with random fake address to detect catch-all."""
        if domain in self._catch_all_cache:
            return self._catch_all_cache[domain]

        mx_hosts = self.check_mx(domain)
        if not mx_hosts:
            self._catch_all_cache[domain] = None
            return None

        fake_local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
        fake_email = f"{fake_local}@{domain}"

        try:
            await self._rate_limiter.wait_for_slot(domain)
            result = self._smtp_probe(fake_email, mx_hosts[0])
            is_catch_all = result == "accepted"
            self._catch_all_cache[domain] = is_catch_all
            return is_catch_all
        except Exception:
            self._catch_all_cache[domain] = None
            return None

    async def verify_smtp(self, email: str) -> str:
        """Stage 4: SMTP RCPT TO probe. Returns 'valid'/'invalid'/'catch_all'/'unknown'."""
        domain = email.split('@')[1]
        mx_hosts = self.check_mx(domain)
        if not mx_hosts:
            return "unknown"

        catch_all = await self.detect_catch_all(domain)
        if catch_all:
            return "catch_all"

        await self._rate_limiter.wait_for_slot(domain)
        result = self._smtp_probe(email, mx_hosts[0])
        if result == "accepted":
            return "valid"
        elif result == "rejected":
            return "invalid"
        else:
            return "unknown"

    def _smtp_probe(self, email: str, mx_host: str) -> str:
        """Low-level SMTP RCPT TO probe. Returns 'accepted'/'rejected'/'error'."""
        try:
            with smtplib.SMTP(mx_host, 25, timeout=10) as smtp:
                smtp.ehlo(self.sender_domain)
                smtp.mail(f"verify@{self.sender_domain}")
                code, _ = smtp.rcpt(email)
                if code == 250:
                    return "accepted"
                elif code >= 500:
                    return "rejected"
                else:
                    return "error"
        except (smtplib.SMTPException, OSError, TimeoutError):
            return "error"

    async def _verify_local(self, email: str) -> dict:
        """Full 4-stage local pipeline. Short-circuits on definitive result."""
        result = {
            "email": email,
            "valid": False,
            "catch_all": False,
            "mx_found": False,
            "smtp_result": "unknown",
            "confidence_modifier": 0,
            "verification_source": "local_smtp",
        }

        if not self.check_syntax(email):
            result["smtp_result"] = "invalid_syntax"
            result["confidence_modifier"] = -50
            return result

        domain = email.split('@')[1]

        mx_hosts = self.check_mx(domain)
        if not mx_hosts:
            result["smtp_result"] = "no_mx"
            result["confidence_modifier"] = -40
            return result
        result["mx_found"] = True

        catch_all = await self.detect_catch_all(domain)
        if catch_all:
            result["catch_all"] = True
            result["smtp_result"] = "catch_all"
            result["valid"] = True
            result["confidence_modifier"] = -15
            return result

        await self._rate_limiter.wait_for_slot(domain)
        smtp_result = self._smtp_probe(email, mx_hosts[0])
        if smtp_result == "accepted":
            result["valid"] = True
            result["smtp_result"] = "valid"
            result["confidence_modifier"] = 20
        elif smtp_result == "rejected":
            result["smtp_result"] = "invalid"
            result["confidence_modifier"] = -40
        else:
            result["smtp_result"] = "unknown"
            result["confidence_modifier"] = 0

        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify(self, email: str) -> dict:
        """Verify an email address. Uses Reoon API if configured, else local SMTP.

        Always does a syntax check first (free, instant). Then routes to
        the appropriate backend.
        """
        # Quick syntax check before calling any API
        if not self.check_syntax(email):
            return {
                "email": email,
                "valid": False,
                "catch_all": False,
                "mx_found": False,
                "smtp_result": "invalid_syntax",
                "confidence_modifier": -50,
                "verification_source": "syntax_check",
            }

        if self.reoon_api_key:
            result = await self._verify_reoon(email)
            # If Reoon API fails, fall back to local
            if result.get("smtp_result") == "api_error":
                logger.info("Reoon failed for %s, falling back to local SMTP", email)
                return await self._verify_local(email)
            return result

        return await self._verify_local(email)
