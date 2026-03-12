"""Smart routing — dynamic per-row provider sequence."""
from __future__ import annotations

from typing import Optional
from config.settings import ProviderName
from data.models import RouteCategory


def get_provider_sequence(
    category: RouteCategory,
    waterfall_order: list[ProviderName],
    has_linkedin: bool = False,
) -> list[dict]:
    """Return the ordered sequence of enrichment steps for this route category.

    Each step is a dict:
    {
        "action": str,           # "pattern_match", "find_email", "find_domain",
                                 # "search_companies", "search_people", "verify_email",
                                 # "enrich_company"
        "provider": Optional[ProviderName],  # None for pattern_match
        "is_free": bool,
        "description": str,      # Human-readable
    }

    Routes:

    NAME_AND_DOMAIN (best case):
      1. {"action": "pattern_match", "provider": None, "is_free": True}
      2. For each provider in waterfall_order:
         {"action": "find_email", "provider": provider, "is_free": False}

    NAME_AND_COMPANY (need domain first):
      0. {"action": "find_domain", "provider": ProviderName.APOLLO, "is_free": True}
      then: same as NAME_AND_DOMAIN

    LINKEDIN_PERSON:
      1. {"action": "find_email", "provider": ProviderName.CONTACTOUT, "is_free": False}
      2. Then fall through to rest of waterfall_order (excluding contactout)

    COMPANY_ONLY:
      0. {"action": "search_companies", "provider": ProviderName.APOLLO, "is_free": True}
      0b. {"action": "search_people", "provider": ProviderName.APOLLO, "is_free": True}
      (Further steps depend on results — return just the pre-enrichment steps)

    EMAIL_ONLY:
      1. {"action": "verify_email", "provider": ProviderName.FINDYMAIL, "is_free": False}

    DOMAIN_ONLY:
      1. {"action": "enrich_company", "provider": ProviderName.APOLLO, "is_free": False}

    NAME_ONLY:
      1. {"action": "search_people", "provider": ProviderName.APOLLO, "is_free": True}
      (Further steps depend on results)

    UNROUTABLE:
      Return empty list.
    """
    steps: list[dict] = []

    if category == RouteCategory.NAME_AND_DOMAIN:
        # Best case: we have name + domain, try pattern match then waterfall
        steps.append({
            "action": "pattern_match",
            "provider": None,
            "is_free": True,
            "description": "Try known email patterns for domain",
        })
        for provider in waterfall_order:
            steps.append({
                "action": "find_email",
                "provider": provider,
                "is_free": False,
                "description": f"Find email via {provider.value}",
            })

    elif category == RouteCategory.NAME_AND_COMPANY:
        # Need to resolve domain first, then same as NAME_AND_DOMAIN
        steps.append({
            "action": "find_domain",
            "provider": ProviderName.APOLLO,
            "is_free": True,
            "description": "Look up company domain via Apollo",
        })
        steps.append({
            "action": "pattern_match",
            "provider": None,
            "is_free": True,
            "description": "Try known email patterns for domain",
        })
        for provider in waterfall_order:
            steps.append({
                "action": "find_email",
                "provider": provider,
                "is_free": False,
                "description": f"Find email via {provider.value}",
            })

    elif category == RouteCategory.LINKEDIN_PERSON:
        # ContactOut first for LinkedIn profiles, then rest of waterfall
        steps.append({
            "action": "find_email",
            "provider": ProviderName.CONTACTOUT,
            "is_free": False,
            "description": "Find email from LinkedIn via ContactOut",
        })
        for provider in waterfall_order:
            if provider != ProviderName.CONTACTOUT:
                steps.append({
                    "action": "find_email",
                    "provider": provider,
                    "is_free": False,
                    "description": f"Find email via {provider.value}",
                })

    elif category == RouteCategory.COMPANY_ONLY:
        # Search for company info and people at the company
        steps.append({
            "action": "search_companies",
            "provider": ProviderName.APOLLO,
            "is_free": True,
            "description": "Search for company details via Apollo",
        })
        steps.append({
            "action": "search_people",
            "provider": ProviderName.APOLLO,
            "is_free": True,
            "description": "Search for people at company via Apollo",
        })

    elif category == RouteCategory.EMAIL_ONLY:
        # Free local verification first (syntax + MX + SMTP probe)
        steps.append({
            "action": "verify_email_local",
            "provider": None,
            "is_free": True,
            "description": "Verify email locally via DNS/SMTP probe",
        })
        # Paid external verification as fallback
        steps.append({
            "action": "verify_email",
            "provider": ProviderName.FINDYMAIL,
            "is_free": False,
            "description": "Verify email address via Findymail",
        })

    elif category == RouteCategory.DOMAIN_ONLY:
        # Enrich company info from domain
        steps.append({
            "action": "enrich_company",
            "provider": ProviderName.APOLLO,
            "is_free": False,
            "description": "Enrich company data from domain via Apollo",
        })

    elif category == RouteCategory.NAME_ONLY:
        # Try to find the person with just a name
        steps.append({
            "action": "search_people",
            "provider": ProviderName.APOLLO,
            "is_free": True,
            "description": "Search for person by name via Apollo",
        })

    # UNROUTABLE returns empty list (no steps)

    return steps


def estimate_steps_cost(steps: list[dict]) -> dict:
    """Estimate the cost of a step sequence.
    Returns {max_credits: int, min_credits: int, description: str}.
    max_credits = sum of all non-free steps (worst case: all providers tried)
    min_credits = cost of first non-free step (best case: first provider finds it)
    """
    paid_steps = [s for s in steps if not s["is_free"]]

    max_credits = len(paid_steps)
    min_credits = 1 if paid_steps else 0

    if not paid_steps:
        description = "Free (no paid API calls needed)"
    elif max_credits == 1:
        provider = paid_steps[0]["provider"]
        provider_name = provider.value if provider else "unknown"
        description = f"1 credit ({provider_name})"
    else:
        provider_names = []
        for s in paid_steps:
            if s["provider"]:
                name = s["provider"].value
                if name not in provider_names:
                    provider_names.append(name)
        providers_str = ", ".join(provider_names)
        description = (
            f"{min_credits}-{max_credits} credits "
            f"(best case: first provider match; "
            f"worst case: all of {providers_str})"
        )

    return {
        "max_credits": max_credits,
        "min_credits": min_credits,
        "description": description,
    }
