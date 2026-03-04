"""Email verification pipeline using DNS and SMTP probing."""
from __future__ import annotations

import asyncio
import re
import random
import smtplib
import string
import time
from typing import Optional

import dns.resolver


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
            # Global rate limit
            min_global_wait = (1.0 / self.global_per_second)
            global_wait = max(0, min_global_wait - (now - self._global_last_probe))
            # Per-domain rate limit
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
    """4-stage email verification: syntax -> MX -> catch-all -> SMTP."""

    # RFC 5322 simplified email regex
    EMAIL_REGEX = re.compile(
        r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
    )

    def __init__(self, sender_domain: str = "verify.example.com"):
        self.sender_domain = sender_domain
        self._catch_all_cache: dict[str, Optional[bool]] = {}
        self._rate_limiter = SMTPRateLimiter()

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

    def detect_catch_all(self, domain: str) -> Optional[bool]:
        """Stage 3: Probe with random fake address to detect catch-all.
        True = catch-all, False = not catch-all, None = inconclusive."""
        if domain in self._catch_all_cache:
            return self._catch_all_cache[domain]

        mx_hosts = self.check_mx(domain)
        if not mx_hosts:
            self._catch_all_cache[domain] = None
            return None

        # Generate random fake email
        fake_local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
        fake_email = f"{fake_local}@{domain}"

        try:
            result = self._smtp_probe(fake_email, mx_hosts[0])
            is_catch_all = result == "accepted"
            self._catch_all_cache[domain] = is_catch_all
            return is_catch_all
        except Exception:
            self._catch_all_cache[domain] = None
            return None

    def verify_smtp(self, email: str) -> str:
        """Stage 4: SMTP RCPT TO probe. Returns 'valid'/'invalid'/'catch_all'/'unknown'."""
        domain = email.split('@')[1]
        mx_hosts = self.check_mx(domain)
        if not mx_hosts:
            return "unknown"

        # Check catch-all first
        catch_all = self.detect_catch_all(domain)
        if catch_all:
            return "catch_all"

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

    def verify(self, email: str) -> dict:
        """Full 4-stage pipeline. Short-circuits on definitive result."""
        result = {
            "email": email,
            "valid": False,
            "catch_all": False,
            "mx_found": False,
            "smtp_result": "unknown",
            "confidence_modifier": 0,
        }

        # Stage 1: Syntax
        if not self.check_syntax(email):
            result["smtp_result"] = "invalid_syntax"
            result["confidence_modifier"] = -50
            return result

        domain = email.split('@')[1]

        # Stage 2: MX check
        mx_hosts = self.check_mx(domain)
        if not mx_hosts:
            result["smtp_result"] = "no_mx"
            result["confidence_modifier"] = -40
            return result
        result["mx_found"] = True

        # Stage 3: Catch-all detection
        catch_all = self.detect_catch_all(domain)
        if catch_all:
            result["catch_all"] = True
            result["smtp_result"] = "catch_all"
            result["valid"] = True  # Probably valid but can't be sure
            result["confidence_modifier"] = -15
            return result

        # Stage 4: SMTP verification
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
