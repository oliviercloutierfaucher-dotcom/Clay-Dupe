"""Input classification for enrichment routing."""
from __future__ import annotations

import re
from data.models import RouteCategory


class FieldSignal:
    """Bitfield flags for what data is present in a row."""
    FIRST_NAME     = 0x001
    LAST_NAME      = 0x002
    FULL_NAME      = 0x004
    EMAIL          = 0x008
    DOMAIN         = 0x010
    COMPANY_NAME   = 0x020
    LINKEDIN       = 0x040
    JOB_TITLE      = 0x080
    PHONE          = 0x100

# Regex patterns for field validation
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
DOMAIN_REGEX = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$')
LINKEDIN_REGEX = re.compile(r'linkedin\.com/in/', re.IGNORECASE)
PHONE_REGEX = re.compile(r'[\d]{7,}')  # 7+ digits after stripping non-digits


def detect_fields(row: dict) -> int:
    """Inspect a row dict and return FieldSignal bitfield.

    Checks these canonical field names: first_name, last_name, full_name, email,
    company_domain, company_name, linkedin_url, title, phone.

    For each field:
    - first_name: non-empty string, at least 1 alpha char
    - last_name: non-empty string, at least 1 alpha char
    - full_name: non-empty, contains at least one space
    - email: matches EMAIL_REGEX
    - company_domain: matches DOMAIN_REGEX (no spaces, has dots, looks like hostname)
    - company_name: non-empty string, at least 2 chars
    - linkedin_url: matches LINKEDIN_REGEX (contains 'linkedin.com/in/')
    - title: non-empty string
    - phone: has 7+ digits after stripping non-digit chars
    """
    signals = 0

    # first_name
    first_name = row.get("first_name")
    if first_name and isinstance(first_name, str) and any(c.isalpha() for c in first_name):
        signals |= FieldSignal.FIRST_NAME

    # last_name
    last_name = row.get("last_name")
    if last_name and isinstance(last_name, str) and any(c.isalpha() for c in last_name):
        signals |= FieldSignal.LAST_NAME

    # full_name
    full_name = row.get("full_name")
    if full_name and isinstance(full_name, str) and " " in full_name.strip():
        signals |= FieldSignal.FULL_NAME

    # email
    email = row.get("email")
    if email and isinstance(email, str) and EMAIL_REGEX.match(email.strip()):
        signals |= FieldSignal.EMAIL

    # company_domain
    domain = row.get("company_domain")
    if domain and isinstance(domain, str) and DOMAIN_REGEX.match(domain.strip()):
        signals |= FieldSignal.DOMAIN

    # company_name
    company_name = row.get("company_name")
    if company_name and isinstance(company_name, str) and len(company_name.strip()) >= 2:
        signals |= FieldSignal.COMPANY_NAME

    # linkedin_url
    linkedin = row.get("linkedin_url")
    if linkedin and isinstance(linkedin, str) and LINKEDIN_REGEX.search(linkedin):
        signals |= FieldSignal.LINKEDIN

    # title
    title = row.get("title")
    if title and isinstance(title, str) and title.strip():
        signals |= FieldSignal.JOB_TITLE

    # phone
    phone = row.get("phone")
    if phone and isinstance(phone, str):
        digits_only = re.sub(r'\D', '', phone)
        if len(digits_only) >= 7:
            signals |= FieldSignal.PHONE

    return signals


def classify_row(signals: int) -> RouteCategory:
    """Map field signals to a RouteCategory.

    Priority order (first match wins):
    1. Has (FIRST_NAME or FULL_NAME) and DOMAIN -> NAME_AND_DOMAIN (full enrichment)
    2. Has (FIRST_NAME or FULL_NAME) and COMPANY_NAME -> NAME_AND_COMPANY
    3. Has LINKEDIN -> LINKEDIN_PERSON
    4. Has EMAIL (without name+domain) -> EMAIL_ONLY (verify only)
    5. Has COMPANY_NAME or DOMAIN (no person name) -> COMPANY_ONLY or DOMAIN_ONLY
    6. Has FIRST_NAME or FULL_NAME (no company info) -> NAME_ONLY
    7. Otherwise -> UNROUTABLE

    Note: If we have a full_name but no first/last, that counts as having a name.
    Rows with email + name + domain get NAME_AND_DOMAIN for full enrichment;
    the existing email can be verified as a bonus within that route.
    """
    has_email = bool(signals & FieldSignal.EMAIL)
    has_linkedin = bool(signals & FieldSignal.LINKEDIN)
    has_name = bool(signals & (FieldSignal.FIRST_NAME | FieldSignal.FULL_NAME))
    has_domain = bool(signals & FieldSignal.DOMAIN)
    has_company = bool(signals & FieldSignal.COMPANY_NAME)

    # 1. NAME_AND_DOMAIN (even if email exists — full enrichment)
    if has_name and has_domain:
        return RouteCategory.NAME_AND_DOMAIN

    # 2. NAME_AND_COMPANY (has name + company but no domain)
    if has_name and has_company:
        return RouteCategory.NAME_AND_COMPANY

    # 3. LINKEDIN_PERSON
    if has_linkedin:
        return RouteCategory.LINKEDIN_PERSON

    # 4. EMAIL_ONLY (only has email, no name+domain for full enrichment)
    if has_email:
        return RouteCategory.EMAIL_ONLY

    # 5. COMPANY_ONLY or DOMAIN_ONLY (no person name)
    if has_company:
        return RouteCategory.COMPANY_ONLY
    if has_domain:
        return RouteCategory.DOMAIN_ONLY

    # 6. NAME_ONLY (no company info)
    if has_name:
        return RouteCategory.NAME_ONLY

    # 7. UNROUTABLE
    return RouteCategory.UNROUTABLE


def classify_batch(rows: list[dict]) -> dict[RouteCategory, list[dict]]:
    """Classify all rows, return grouped by category.
    Each row gets a '_route_category' field added."""
    grouped: dict[RouteCategory, list[dict]] = {cat: [] for cat in RouteCategory}

    for row in rows:
        signals = detect_fields(row)
        category = classify_row(signals)
        row["_route_category"] = category
        grouped[category].append(row)

    return grouped


def split_full_name(full_name: str) -> tuple[str, str]:
    """Split 'John Doe' into ('John', 'Doe'). Handle:
    - Single word -> (word, '')
    - Two words -> (first, last)
    - Three+ words -> (first, rest_joined_as_last)
    """
    parts = full_name.strip().split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))
