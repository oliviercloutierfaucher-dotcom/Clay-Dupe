"""Convenience wrapper for finding a person's email address.

Delegates all orchestration logic to :class:`WaterfallOrchestrator` and
returns the discovered email string (or ``None``).
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from enrichment.waterfall import WaterfallOrchestrator

logger = logging.getLogger(__name__)


async def find_email(
    row: dict,
    orchestrator: WaterfallOrchestrator,
) -> Optional[str]:
    """Find an email address for the person described in *row*.

    This is a thin convenience wrapper around
    :meth:`WaterfallOrchestrator.enrich_single`.  It constructs the
    appropriate input and extracts the email from the enrichment result.

    Parameters
    ----------
    row:
        Dictionary with person/company fields.  Expected keys include
        some combination of ``first_name``, ``last_name``, ``full_name``,
        ``company_domain``, ``company_name``, and ``linkedin_url``.
    orchestrator:
        A fully initialised :class:`WaterfallOrchestrator`.

    Returns
    -------
    Optional[str]
        The email address if found, otherwise ``None``.
    """
    try:
        result = await orchestrator.enrich_single(row)
    except Exception:
        logger.exception("find_email failed for row: %s", row)
        return None

    if not result.found:
        return None

    # The email may live in result_data or at the top-level fields
    email = result.result_data.get("email")
    if not email:
        email = result.result_data.get("data", {}).get("email")

    if email and isinstance(email, str):
        return email.strip().lower()

    return None
