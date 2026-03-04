"""Convenience wrapper for resolving a company name to its domain.

Uses Apollo's free organisation search under the hood via the
:class:`WaterfallOrchestrator`.
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from enrichment.waterfall import WaterfallOrchestrator

logger = logging.getLogger(__name__)


async def find_domain(
    company_name: str,
    orchestrator: WaterfallOrchestrator,
) -> Optional[str]:
    """Look up the primary domain for a company by name.

    Constructs a minimal row containing only ``company_name`` and runs
    it through the waterfall.  For a ``COMPANY_ONLY`` route category the
    orchestrator will invoke Apollo's organisation search (a free call)
    and return the domain if one is discovered.

    Parameters
    ----------
    company_name:
        The human-readable company name (e.g. ``"Acme Corp"``).
    orchestrator:
        A fully initialised :class:`WaterfallOrchestrator`.

    Returns
    -------
    Optional[str]
        The normalised domain (e.g. ``"acme.com"``) or ``None``.
    """
    if not company_name or not company_name.strip():
        logger.warning("find_domain called with empty company_name")
        return None

    row: dict = {"company_name": company_name.strip()}

    try:
        result = await orchestrator.enrich_single(row)
    except Exception:
        logger.exception("find_domain failed for company: %s", company_name)
        return None

    if not result.found:
        return None

    # Try to extract the domain from the result data
    domain = result.result_data.get("domain")
    if not domain:
        # Check nested company structures
        companies = result.result_data.get("companies", [])
        if companies and isinstance(companies, list):
            domain = companies[0].get("domain")

    if not domain:
        domain = result.result_data.get("data", {}).get("domain")

    if domain and isinstance(domain, str):
        domain = domain.strip().lower()
        # Strip protocol prefixes if present
        for prefix in ("https://", "http://"):
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.rstrip("/")

    return None
