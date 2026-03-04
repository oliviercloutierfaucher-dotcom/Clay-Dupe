"""Tests for confidence scoring and anti-pattern detection."""
from __future__ import annotations

import pytest
from config.settings import ProviderName
from data.models import VerificationStatus
from quality.confidence import calculate_confidence, get_confidence_tier, should_verify
from quality.anti_pattern import check_email_quality


class TestCalculateConfidence:
    def test_verified_findymail_high_score(self):
        score = calculate_confidence(
            provider_name=ProviderName.FINDYMAIL,
            verification_status=VerificationStatus.VERIFIED,
            provider_confidence=None,
            cross_provider_count=1,
            is_catch_all=False,
            is_free_email=False,
            matches_domain_pattern=True,
            is_role_based=False,
        )
        assert score >= 75

    def test_unverified_apollo_catch_all_low_score(self):
        score = calculate_confidence(
            provider_name=ProviderName.APOLLO,
            verification_status=VerificationStatus.UNVERIFIED,
            provider_confidence=None,
            cross_provider_count=1,
            is_catch_all=True,
            is_free_email=False,
            matches_domain_pattern=False,
            is_role_based=False,
        )
        assert 25 <= score <= 55

    def test_multi_provider_agreement_boosts_score(self):
        score_single = calculate_confidence(
            provider_name=ProviderName.APOLLO,
            verification_status=VerificationStatus.VERIFIED,
            provider_confidence=None,
            cross_provider_count=1,
            is_catch_all=False,
            is_free_email=False,
            matches_domain_pattern=False,
            is_role_based=False,
        )
        score_multi = calculate_confidence(
            provider_name=ProviderName.APOLLO,
            verification_status=VerificationStatus.VERIFIED,
            provider_confidence=None,
            cross_provider_count=3,
            is_catch_all=False,
            is_free_email=False,
            matches_domain_pattern=False,
            is_role_based=False,
        )
        assert score_multi > score_single

    def test_free_email_penalty(self):
        score_normal = calculate_confidence(
            provider_name=ProviderName.APOLLO,
            verification_status=VerificationStatus.VERIFIED,
            provider_confidence=None,
            cross_provider_count=1,
            is_catch_all=False,
            is_free_email=False,
            matches_domain_pattern=False,
            is_role_based=False,
        )
        score_free = calculate_confidence(
            provider_name=ProviderName.APOLLO,
            verification_status=VerificationStatus.VERIFIED,
            provider_confidence=None,
            cross_provider_count=1,
            is_catch_all=False,
            is_free_email=True,
            matches_domain_pattern=False,
            is_role_based=False,
        )
        assert score_free < score_normal

    def test_invalid_status_low_score(self):
        score = calculate_confidence(
            provider_name=ProviderName.APOLLO,
            verification_status=VerificationStatus.INVALID,
            provider_confidence=None,
            cross_provider_count=1,
            is_catch_all=False,
            is_free_email=False,
            matches_domain_pattern=False,
            is_role_based=False,
        )
        assert score < 50

    def test_score_within_range(self):
        score = calculate_confidence(
            provider_name=ProviderName.FINDYMAIL,
            verification_status=VerificationStatus.VERIFIED,
            provider_confidence=None,
            cross_provider_count=3,
            is_catch_all=False,
            is_free_email=False,
            matches_domain_pattern=True,
            is_role_based=False,
        )
        assert 0 <= score <= 100


class TestGetConfidenceTier:
    def test_excellent(self):
        assert get_confidence_tier(90) == "excellent"

    def test_good(self):
        assert get_confidence_tier(75) == "good"

    def test_fair(self):
        assert get_confidence_tier(55) == "fair"

    def test_poor(self):
        assert get_confidence_tier(35) == "poor"

    def test_bad(self):
        assert get_confidence_tier(20) == "bad"


class TestShouldVerify:
    def test_low_confidence_should_verify(self):
        assert should_verify(40, VerificationStatus.UNKNOWN) is True

    def test_high_confidence_no_verify(self):
        assert should_verify(85, VerificationStatus.UNKNOWN) is False

    def test_already_verified_no_verify(self):
        assert should_verify(40, VerificationStatus.VERIFIED) is False


class TestCheckEmailQuality:
    def test_normal_email(self):
        result = check_email_quality("john.doe@acme.com")
        assert result["is_disposable"] is False
        assert result["is_role_based"] is False
        assert result["is_free_provider"] is False
        assert result["reject"] is False
        assert result["confidence_penalty"] == 0

    def test_disposable_email(self):
        result = check_email_quality("john@mailinator.com")
        assert result["is_disposable"] is True
        assert result["reject"] is True
        assert result["confidence_penalty"] > 0

    def test_role_based_email(self):
        result = check_email_quality("info@acme.com")
        assert result["is_role_based"] is True
        assert result["confidence_penalty"] > 0

    def test_free_provider_email(self):
        result = check_email_quality("john.doe@gmail.com")
        assert result["is_free_provider"] is True
        assert result["confidence_penalty"] > 0

    def test_support_role_based(self):
        result = check_email_quality("support@acme.com")
        assert result["is_role_based"] is True

    def test_sales_role_based(self):
        result = check_email_quality("sales@acme.com")
        assert result["is_role_based"] is True

    def test_yahoo_free_provider(self):
        result = check_email_quality("john@yahoo.com")
        assert result["is_free_provider"] is True

    def test_hotmail_free_provider(self):
        result = check_email_quality("john@hotmail.com")
        assert result["is_free_provider"] is True
