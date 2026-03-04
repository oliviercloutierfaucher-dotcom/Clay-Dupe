"""Email quality checking — detect disposable, role-based, free provider, spam trap patterns."""
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Disposable / temporary email domains (~100)
# ---------------------------------------------------------------------------
DISPOSABLE_DOMAINS: frozenset[str] = frozenset({
    "mailinator.com",
    "guerrillamail.com",
    "guerrillamail.net",
    "guerrillamail.org",
    "guerrillamail.de",
    "grr.la",
    "guerrillamailblock.com",
    "tempmail.com",
    "temp-mail.org",
    "temp-mail.io",
    "throwaway.email",
    "throwaway.com",
    "yopmail.com",
    "yopmail.fr",
    "yopmail.net",
    "sharklasers.com",
    "guerrillamail.info",
    "spam4.me",
    "trashmail.com",
    "trashmail.me",
    "trashmail.net",
    "trashmail.org",
    "trashymail.com",
    "dispostable.com",
    "maildrop.cc",
    "mailnesia.com",
    "mailcatch.com",
    "fakeinbox.com",
    "fakemail.net",
    "tempail.com",
    "tempr.email",
    "discard.email",
    "discardmail.com",
    "discardmail.de",
    "disposableemailaddresses.emailmiser.com",
    "mailexpire.com",
    "mailforspam.com",
    "safetymail.info",
    "10minutemail.com",
    "10minutemail.net",
    "20minutemail.com",
    "20minutemail.it",
    "minutemail.io",
    "mohmal.com",
    "burnermail.io",
    "inboxbear.com",
    "mailtemp.info",
    "emailondeck.com",
    "getnada.com",
    "nada.email",
    "harakirimail.com",
    "jetable.org",
    "spamgourmet.com",
    "mytemp.email",
    "tempinbox.com",
    "tempmailaddress.com",
    "crazymailing.com",
    "armyspy.com",
    "cuvox.de",
    "dayrep.com",
    "einrot.com",
    "fleckens.hu",
    "gustr.com",
    "jourrapide.com",
    "rhyta.com",
    "superrito.com",
    "teleworm.us",
    "mailnator.com",
    "nomail.xl.cx",
    "spamcero.com",
    "spamfree24.org",
    "trashmail.at",
    "wegwerfmail.de",
    "wegwerfmail.net",
    "wegwerfmail.org",
    "wh4f.org",
    "filzmail.com",
    "mailblocks.com",
    "mailmoat.com",
    "mytrashmail.com",
    "pookmail.com",
    "shortmail.net",
    "sneakemail.com",
    "spamex.com",
    "spamherelots.com",
    "tempmailer.com",
    "temporaryemail.net",
    "temporaryinbox.com",
    "thankyou2010.com",
    "binkmail.com",
    "bobmail.info",
    "chammy.info",
    "devnullmail.com",
    "dodgeit.com",
    "e4ward.com",
    "emailigo.de",
    "emailwarden.com",
    "enterto.com",
    "fastacura.com",
    "getairmail.com",
    "imgof.com",
    "imstations.com",
    "mailzilla.com",
})


# ---------------------------------------------------------------------------
# Role-based email prefixes (~30)
# ---------------------------------------------------------------------------
ROLE_BASED_PREFIXES: frozenset[str] = frozenset({
    "info",
    "sales",
    "support",
    "admin",
    "contact",
    "help",
    "hello",
    "office",
    "team",
    "hr",
    "jobs",
    "careers",
    "marketing",
    "press",
    "media",
    "billing",
    "finance",
    "accounting",
    "legal",
    "compliance",
    "security",
    "abuse",
    "postmaster",
    "webmaster",
    "hostmaster",
    "noreply",
    "no-reply",
    "newsletter",
    "feedback",
    "enquiries",
    "inquiries",
    "reception",
})


# ---------------------------------------------------------------------------
# Free email providers (~20)
# ---------------------------------------------------------------------------
FREE_EMAIL_PROVIDERS: frozenset[str] = frozenset({
    "gmail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.in",
    "hotmail.com",
    "hotmail.co.uk",
    "outlook.com",
    "live.com",
    "live.co.uk",
    "aol.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "mail.com",
    "protonmail.com",
    "proton.me",
    "zoho.com",
    "yandex.com",
    "yandex.ru",
    "gmx.com",
    "gmx.net",
    "tutanota.com",
    "tuta.io",
    "fastmail.com",
})


# ---------------------------------------------------------------------------
# Spam-trap and suspicious-format patterns
# ---------------------------------------------------------------------------
_MD5_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_HEX_LONG_PATTERN = re.compile(r"^[a-f0-9]{16,}$")
_EXCESSIVE_NUMBERS = re.compile(r"\d{6,}")
_CONSECUTIVE_DOTS = re.compile(r"\.\.")
_SUSPICIOUS_LONG_LOCAL = 64  # RFC 5321 max, but anything > 40 is unusual


def _is_spam_trap(local: str, domain: str) -> tuple[bool, Optional[str]]:
    """Detect common spam-trap patterns.

    Returns (is_spam_trap, reason).
    """
    # Well-known trap addresses
    if local in ("abuse", "postmaster"):
        return True, f"{local}@ is a standard RFC-mandated address often used as a spam trap"

    # MD5-looking local parts (honeypot signatures)
    if _MD5_PATTERN.match(local):
        return True, "local part looks like an MD5 hash (likely honeypot)"

    # Long hex strings
    if _HEX_LONG_PATTERN.match(local) and len(local) >= 16:
        return True, "local part is a long hex string (likely auto-generated trap)"

    # Extremely long addresses
    if len(local) > 50:
        return True, "local part is unusually long (>50 chars)"

    return False, None


def _is_suspicious_format(local: str, domain: str) -> tuple[bool, Optional[str]]:
    """Detect emails with suspicious formatting.

    Returns (is_suspicious, reason).
    """
    # Consecutive dots
    if _CONSECUTIVE_DOTS.search(local):
        return True, "local part contains consecutive dots"

    # Starts or ends with dot
    if local.startswith(".") or local.endswith("."):
        return True, "local part starts or ends with a dot"

    # Starts or ends with hyphen
    if local.startswith("-") or local.endswith("-"):
        return True, "local part starts or ends with a hyphen"

    # Excessive consecutive numbers (often auto-generated)
    if _EXCESSIVE_NUMBERS.search(local):
        return True, "local part contains 6+ consecutive digits (likely auto-generated)"

    # Unusually long local part
    if len(local) > 40:
        return True, "local part is longer than 40 characters"

    # Only digits
    if local.isdigit():
        return True, "local part is purely numeric"

    # No alphabetic characters at all
    if not any(c.isalpha() for c in local):
        return True, "local part contains no alphabetic characters"

    return False, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_email_quality(email: str) -> dict:
    """Check email for anti-patterns.

    Returns dict with:
    - is_disposable: bool
    - is_role_based: bool
    - is_free_provider: bool
    - is_spam_trap: bool
    - is_suspicious: bool
    - confidence_penalty: int (total penalty, 0-100)
    - reject: bool (should this email be rejected?)
    - reasons: list[str] (human-readable reasons)
    """
    reasons: list[str] = []
    penalty = 0

    email = email.strip().lower()

    # Basic structural validation
    if "@" not in email:
        return {
            "is_disposable": False,
            "is_role_based": False,
            "is_free_provider": False,
            "is_spam_trap": False,
            "is_suspicious": True,
            "confidence_penalty": 100,
            "reject": True,
            "reasons": ["email address has no @ sign"],
        }

    local, domain = email.rsplit("@", 1)

    if not local or not domain or "." not in domain:
        return {
            "is_disposable": False,
            "is_role_based": False,
            "is_free_provider": False,
            "is_spam_trap": False,
            "is_suspicious": True,
            "confidence_penalty": 100,
            "reject": True,
            "reasons": ["email address is structurally invalid"],
        }

    # ----- Disposable check -----
    is_disposable = domain in DISPOSABLE_DOMAINS
    if is_disposable:
        penalty += 50
        reasons.append(f"{domain} is a known disposable email provider")

    # ----- Role-based check -----
    prefix = local.split(".")[0]  # e.g. "info" from "info.us"
    is_role_based = prefix in ROLE_BASED_PREFIXES or local in ROLE_BASED_PREFIXES
    if is_role_based:
        penalty += 15
        reasons.append(f"'{local}@' is a role-based address, not a personal mailbox")

    # ----- Free provider check -----
    is_free_provider = domain in FREE_EMAIL_PROVIDERS
    if is_free_provider:
        penalty += 10
        reasons.append(f"{domain} is a free email provider")

    # ----- Spam trap check -----
    is_spam_trap, trap_reason = _is_spam_trap(local, domain)
    if is_spam_trap:
        penalty += 40
        reasons.append(trap_reason)

    # ----- Suspicious format check -----
    is_suspicious, suspicious_reason = _is_suspicious_format(local, domain)
    if is_suspicious:
        penalty += 15
        reasons.append(suspicious_reason)

    # Compound penalties — multiple red flags compound the risk
    flags_set = sum([is_disposable, is_role_based, is_spam_trap, is_suspicious])
    if flags_set >= 3:
        penalty += 20
        reasons.append("multiple anti-pattern flags detected (compounding penalty)")

    # Cap penalty
    penalty = min(penalty, 100)

    # Decide whether to reject outright
    reject = (
        is_disposable
        or is_spam_trap
        or penalty >= 60
    )

    return {
        "is_disposable": is_disposable,
        "is_role_based": is_role_based,
        "is_free_provider": is_free_provider,
        "is_spam_trap": is_spam_trap,
        "is_suspicious": is_suspicious,
        "confidence_penalty": penalty,
        "reject": reject,
        "reasons": reasons,
    }


def is_disposable_domain(domain: str) -> bool:
    """Quick check if a domain is disposable."""
    return domain.strip().lower() in DISPOSABLE_DOMAINS


def is_free_email(email: str) -> bool:
    """Quick check if an email uses a free provider."""
    if "@" not in email:
        return False
    _, domain = email.rsplit("@", 1)
    return domain.strip().lower() in FREE_EMAIL_PROVIDERS


def is_role_based_email(email: str) -> bool:
    """Quick check if an email is role-based."""
    if "@" not in email:
        return False
    local, _ = email.rsplit("@", 1)
    local = local.strip().lower()
    prefix = local.split(".")[0]
    return prefix in ROLE_BASED_PREFIXES or local in ROLE_BASED_PREFIXES
