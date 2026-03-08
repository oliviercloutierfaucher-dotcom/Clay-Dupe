"""Contact discovery module.

Finds CEO/Owner/Founder contacts at companies via Apollo people search.
Designed for sequential processing with rate limiting to stay within
Apollo's 50 req/min limit.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from data.models import Company, Person
from providers.apollo import ApolloProvider

logger = logging.getLogger(__name__)

# Target titles for decision-maker discovery
TARGET_TITLES = [
    "CEO", "Owner", "Founder", "President",
    "Managing Director", "General Manager",
]

TARGET_SENIORITIES = ["c_suite", "owner"]

# Delay between API calls to respect Apollo rate limits (50 req/min)
RATE_LIMIT_DELAY = 1.5


async def discover_contact(
    apollo: ApolloProvider,
    company: Company,
) -> Optional[Person]:
    """Find the primary decision-maker at a company via Apollo.

    Searches for CEO/Owner/Founder-level contacts. Returns the best
    match (first result, ranked by Apollo relevance) with company_id
    set to the company's id.

    Returns None if company has no domain or no results found.
    """
    if company.domain is None:
        logger.debug("Skipping %s: no domain", company.name)
        return None

    results = await apollo.search_people(
        q_organization_domains_list=[company.domain],
        person_titles=TARGET_TITLES,
        person_seniorities=TARGET_SENIORITIES,
        per_page=5,
    )

    if not results:
        logger.debug("No contacts found for %s (%s)", company.name, company.domain)
        return None

    # Take the first (most relevant) result
    person = results[0]
    person.company_id = company.id
    return person


async def batch_discover_contacts(
    apollo: ApolloProvider,
    companies: list[Company],
    progress_callback: Optional[Callable] = None,
) -> list[tuple[Company, Optional[Person]]]:
    """Discover contacts for multiple companies with rate limiting.

    Processes companies sequentially (not parallel) to respect Apollo's
    50 req/min rate limit. Sleeps 1.5 seconds between API calls.

    Args:
        apollo: ApolloProvider instance
        companies: List of companies to find contacts for
        progress_callback: Optional async callback(current_index, total)

    Returns:
        List of (company, person_or_none) tuples
    """
    results: list[tuple[Company, Optional[Person]]] = []
    total = len(companies)

    for i, company in enumerate(companies):
        if progress_callback is not None:
            await progress_callback(i, total)

        person = await discover_contact(apollo, company)
        results.append((company, person))

        # Rate limit: sleep between calls (but not after the last one)
        if i < total - 1 and company.domain is not None:
            await asyncio.sleep(RATE_LIMIT_DELAY)

    return results
