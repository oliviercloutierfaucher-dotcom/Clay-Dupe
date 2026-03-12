"""ICP (Ideal Customer Profile) scoring engine.

Scores companies against an ICP preset on four dimensions:
  - Employee count match (30 weight)
  - Industry match (35 weight)
  - Geography match (20 weight)
  - Keyword match (15 weight)

Only dimensions with available data contribute to the final score.
"""
from __future__ import annotations

from config.settings import ICPPreset
from data.models import Company


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

WEIGHT_EMPLOYEE = 30
WEIGHT_INDUSTRY = 35
WEIGHT_GEOGRAPHY = 20
WEIGHT_KEYWORD = 15


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_employee(company: Company, profile: ICPPreset) -> tuple[float, float]:
    """Return (earned, max_possible) for employee count dimension.

    Returns (0, 0) when no data available (dimension excluded).
    """
    if company.employee_count is None:
        return 0.0, 0.0

    count = company.employee_count
    lo, hi = profile.employee_min, profile.employee_max

    if lo <= count <= hi:
        # In range: full score
        return WEIGHT_EMPLOYEE, WEIGHT_EMPLOYEE

    # Close to range: half score
    # "Close" = within 50% of the range boundaries
    half_min = lo * 0.5
    double_max = hi * 2.0

    if count < half_min or count > double_max:
        # Way off: zero
        return 0.0, WEIGHT_EMPLOYEE

    # Partial score for being close
    return WEIGHT_EMPLOYEE * 0.5, WEIGHT_EMPLOYEE


def _score_industry(company: Company, profile: ICPPreset) -> tuple[float, float]:
    """Return (earned, max_possible) for industry dimension.

    Performs case-insensitive substring matching against profile industries.
    Returns (0, 0) when no data available or preset has no industries.
    """
    if not profile.industries:
        return 0.0, 0.0

    if company.industry is None:
        return 0.0, 0.0

    company_industry = company.industry.lower()

    for target in profile.industries:
        target_lower = target.lower()
        # Check both directions: target in company or company in target
        if target_lower in company_industry or company_industry in target_lower:
            return WEIGHT_INDUSTRY, WEIGHT_INDUSTRY

    return 0.0, WEIGHT_INDUSTRY


def _score_geography(company: Company, profile: ICPPreset) -> tuple[float, float]:
    """Return (earned, max_possible) for geography dimension.

    Company.country is already normalized by the model validator.
    Returns (0, 0) when no data available.
    """
    if company.country is None:
        return 0.0, 0.0

    # Country codes are already normalized by Company model validator
    if company.country in profile.countries:
        return WEIGHT_GEOGRAPHY, WEIGHT_GEOGRAPHY

    return 0.0, WEIGHT_GEOGRAPHY


def _score_keywords(company: Company, profile: ICPPreset) -> tuple[float, float]:
    """Return (earned, max_possible) for keyword dimension.

    Scores proportionally based on how many profile keywords appear in
    the company description (case-insensitive).
    Returns (0, 0) when no data available or preset has no keywords.
    """
    if not profile.keywords:
        return 0.0, 0.0

    if company.description is None:
        return 0.0, 0.0

    desc_lower = company.description.lower()
    matched = sum(1 for kw in profile.keywords if kw.lower() in desc_lower)
    total = len(profile.keywords)

    if matched == 0:
        return 0.0, WEIGHT_KEYWORD

    proportion = matched / total
    return WEIGHT_KEYWORD * proportion, WEIGHT_KEYWORD


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_company(company: Company, profile: ICPPreset) -> int:
    """Score a company against an ICP profile.

    Returns an integer 0-100. Only dimensions with available data
    contribute to the score. If no data is available for any dimension,
    returns 0.
    """
    dimensions = [
        _score_employee(company, profile),
        _score_industry(company, profile),
        _score_geography(company, profile),
        _score_keywords(company, profile),
    ]

    total_earned = sum(d[0] for d in dimensions)
    total_possible = sum(d[1] for d in dimensions)

    if total_possible == 0:
        return 0

    return int(total_earned / total_possible * 100)


def batch_score_companies(
    companies: list[Company], profile: ICPPreset
) -> list[tuple[Company, int]]:
    """Score multiple companies against an ICP profile.

    Returns list of (company, score) tuples. Pure computation, no async.
    """
    return [(c, score_company(c, profile)) for c in companies]
