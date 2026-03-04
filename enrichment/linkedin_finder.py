"""Convenience wrapper for finding a person's LinkedIn profile URL.

Uses Apollo's people search to locate the profile, then extracts the
``linkedin_url`` field from the result.
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from enrichment.waterfall import WaterfallOrchestrator

logger = logging.getLogger(__name__)


async def find_linkedin(
    first_name: str,
    last_name: str,
    company: str,
    orchestrator: WaterfallOrchestrator,
) -> Optional[str]:
    """Search for a person and return their LinkedIn URL if found.

    Constructs a row with name and company information and runs it
    through the waterfall.  The ``NAME_AND_COMPANY`` route will first
    resolve the domain via Apollo (free), then attempt email discovery
    which often surfaces the LinkedIn URL as a side-effect.

    Parameters
    ----------
    first_name:
        Person's first name.
    last_name:
        Person's last name.
    company:
        Company name the person is associated with.
    orchestrator:
        A fully initialised :class:`WaterfallOrchestrator`.

    Returns
    -------
    Optional[str]
        The LinkedIn profile URL (e.g.
        ``"https://linkedin.com/in/johndoe"``) or ``None``.
    """
    if not first_name or not last_name:
        logger.warning("find_linkedin called with missing name fields")
        return None

    row: dict = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
    }
    if company and company.strip():
        row["company_name"] = company.strip()

    try:
        result = await orchestrator.enrich_single(row)
    except Exception:
        logger.exception(
            "find_linkedin failed for %s %s at %s",
            first_name,
            last_name,
            company,
        )
        return None

    if not result.found:
        return None

    # Extract linkedin_url from various locations in the result
    linkedin_url = result.result_data.get("linkedin_url")

    if not linkedin_url:
        # Check nested people structures
        people = result.result_data.get("people", [])
        if people and isinstance(people, list):
            linkedin_url = people[0].get("linkedin_url")

    if not linkedin_url:
        linkedin_url = result.result_data.get("data", {}).get("linkedin_url")

    if linkedin_url and isinstance(linkedin_url, str):
        linkedin_url = linkedin_url.strip()
        # Normalise to https
        if linkedin_url.startswith("http://"):
            linkedin_url = "https://" + linkedin_url[7:]
        elif not linkedin_url.startswith("https://"):
            linkedin_url = "https://" + linkedin_url
        return linkedin_url

    return None
