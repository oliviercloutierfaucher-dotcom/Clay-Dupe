"""Convenience wrapper for enriching a company from its domain.

Delegates to :class:`WaterfallOrchestrator` and returns a fully
populated :class:`Company` model (or ``None``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from enrichment.waterfall import WaterfallOrchestrator

from config.settings import ProviderName
from data.models import Company

logger = logging.getLogger(__name__)


async def enrich_company(
    domain: str,
    orchestrator: WaterfallOrchestrator,
) -> Optional[Company]:
    """Enrich a company by its domain, returning a :class:`Company` model.

    Constructs a ``DOMAIN_ONLY`` row and runs it through the waterfall,
    which will invoke Apollo's organisation enrich endpoint.  The raw
    provider response is mapped into a :class:`Company` Pydantic model.

    Parameters
    ----------
    domain:
        The company's website domain (e.g. ``"acme.com"``).
    orchestrator:
        A fully initialised :class:`WaterfallOrchestrator`.

    Returns
    -------
    Optional[Company]
        A populated :class:`Company` instance, or ``None`` if the domain
        could not be enriched.
    """
    if not domain or not domain.strip():
        logger.warning("enrich_company called with empty domain")
        return None

    # Normalise domain
    domain = domain.strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    if domain.startswith("www."):
        domain = domain[4:]
    domain = domain.rstrip("/")

    row: dict = {"company_domain": domain}

    try:
        result = await orchestrator.enrich_single(row)
    except Exception:
        logger.exception("enrich_company failed for domain: %s", domain)
        return None

    if not result.found:
        return None

    data = result.result_data
    if not data:
        return None

    # The data may be nested under a "company" key or flat
    company_data = data.get("company", data)

    try:
        company = Company(
            name=company_data.get("name", ""),
            domain=company_data.get("domain", domain),
            industry=company_data.get("industry"),
            industry_tags=company_data.get("industry_tags", []),
            employee_count=company_data.get("employee_count"),
            employee_range=company_data.get("employee_range"),
            founded_year=company_data.get("founded_year"),
            description=company_data.get("description"),
            city=company_data.get("city"),
            state=company_data.get("state"),
            country=company_data.get("country"),
            full_address=company_data.get("full_address"),
            linkedin_url=company_data.get("linkedin_url"),
            website_url=company_data.get("website_url"),
            phone=company_data.get("phone"),
            source_provider=ProviderName(result.source_provider)
            if isinstance(result.source_provider, str)
            else result.source_provider,
            apollo_id=company_data.get("apollo_id") or company_data.get("id"),
            enriched_at=datetime.now(timezone.utc),
        )
    except Exception:
        logger.exception(
            "Failed to build Company model from enrichment data for %s",
            domain,
        )
        return None

    return company
