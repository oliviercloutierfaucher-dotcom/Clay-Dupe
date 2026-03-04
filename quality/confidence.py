"""Confidence scoring for enrichment results."""
from typing import Optional
from config.settings import ProviderName
from data.models import VerificationStatus


# Provider reliability scores (based on industry data)
PROVIDER_RELIABILITY = {
    ProviderName.APOLLO: 16,
    ProviderName.FINDYMAIL: 20,
    ProviderName.ICYPEAS: 14,
    ProviderName.CONTACTOUT: 15,
}

# Verification status scores
VERIFICATION_SCORES = {
    VerificationStatus.VERIFIED: 30,
    VerificationStatus.UNVERIFIED: 12,
    VerificationStatus.RISKY: 15,
    VerificationStatus.INVALID: 0,
    VerificationStatus.UNKNOWN: 9,
}


def calculate_confidence(
    provider_name: ProviderName,
    verification_status: VerificationStatus,
    provider_confidence: Optional[str] = None,
    cross_provider_count: int = 1,
    is_catch_all: Optional[bool] = None,
    is_free_email: bool = False,
    matches_domain_pattern: bool = True,
    is_role_based: bool = False,
) -> int:
    """Calculate confidence score 0-100 for an enrichment result.

    Components:
    - Provider reliability (0-20): Based on historical accuracy
    - Verification status (0-30): Based on email verification result
    - Cross-provider agreement (0-25): How many providers found same email
    - Domain analysis (0-15): Catch-all, free email, MX analysis
    - Pattern analysis (0-10): Role-based, pattern match

    Returns integer 0-100.
    """
    score = 0

    # 1. Provider reliability (0-20)
    score += PROVIDER_RELIABILITY.get(provider_name, 10)

    # 2. Verification status (0-30)
    score += VERIFICATION_SCORES.get(verification_status, 9)

    # 3. Cross-provider agreement (0-25)
    if cross_provider_count >= 3:
        score += 25
    elif cross_provider_count == 2:
        score += 20
    elif cross_provider_count == 1:
        # Single provider — score depends on which one
        if provider_name == ProviderName.FINDYMAIL:
            score += 15  # Findymail has highest accuracy
        else:
            score += 10

    # 4. Domain analysis (0-15)
    if is_catch_all is True:
        score += 5  # catch-all domains: can't verify, low confidence
    elif is_catch_all is False:
        score += 15  # non-catch-all: verification is meaningful
    else:
        score += 10  # unknown catch-all status

    if is_free_email:
        score = int(score * 0.6)  # Heavy penalty for free emails (gmail, yahoo)

    # 5. Pattern analysis (0-10)
    if is_role_based:
        score += 2  # Role-based (info@, sales@) = low value
    elif matches_domain_pattern:
        score += 10  # Matches known pattern = good
    else:
        score += 6  # Unknown pattern

    return max(0, min(100, score))


def get_confidence_tier(score: int) -> str:
    """Return human-readable tier."""
    if score >= 85:
        return "excellent"
    elif score >= 70:
        return "good"
    elif score >= 50:
        return "fair"
    elif score >= 30:
        return "poor"
    else:
        return "bad"


def should_verify(score: int, verification_status: VerificationStatus) -> bool:
    """Determine if this email needs additional verification."""
    if verification_status == VerificationStatus.VERIFIED:
        return False
    if score >= 70:
        return False  # High confidence, skip verification
    return True
