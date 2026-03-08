"""Tests for data models."""
from __future__ import annotations

import pytest
from data.models import (
    Company, Person, EnrichmentResult, Campaign, CreditUsage, CacheEntry,
    EmailPattern, VerificationStatus, EnrichmentType, CampaignStatus, RouteCategory,
)
from config.settings import ProviderName


# ---------------------------------------------------------------------------
# Company model
# ---------------------------------------------------------------------------

class TestCompany:
    def test_domain_normalization_strips_protocol(self):
        c = Company(name="Acme", domain="https://www.ACME.com/")
        assert c.domain == "acme.com"

    def test_domain_normalization_strips_www(self):
        c = Company(name="Acme", domain="www.acme.com")
        assert c.domain == "acme.com"

    def test_domain_normalization_lowercase(self):
        c = Company(name="Acme", domain="ACME.COM")
        assert c.domain == "acme.com"

    def test_domain_normalization_strips_trailing_slash(self):
        c = Company(name="Acme", domain="acme.com/")
        assert c.domain == "acme.com"

    def test_domain_normalization_http(self):
        c = Company(name="Acme", domain="http://acme.com")
        assert c.domain == "acme.com"

    def test_domain_none_stays_none(self):
        c = Company(name="Acme", domain=None)
        assert c.domain is None

    def test_country_normalization_united_states(self):
        c = Company(name="Acme", country="united states")
        assert c.country == "US"

    def test_country_normalization_usa(self):
        c = Company(name="Acme", country="usa")
        assert c.country == "US"

    def test_country_normalization_uk(self):
        c = Company(name="Acme", country="united kingdom")
        assert c.country == "UK"

    def test_country_normalization_canada(self):
        c = Company(name="Acme", country="canada")
        assert c.country == "CA"

    def test_country_already_code(self):
        c = Company(name="Acme", country="US")
        assert c.country == "US"

    def test_country_none_stays_none(self):
        c = Company(name="Acme", country=None)
        assert c.country is None

    def test_source_type_accepts_string(self):
        c = Company(name="Acme", source_type="apollo_search")
        assert c.source_type == "apollo_search"

    def test_source_type_csv_import(self):
        c = Company(name="Acme", source_type="csv_import")
        assert c.source_type == "csv_import"

    def test_source_type_manual(self):
        c = Company(name="Acme", source_type="manual")
        assert c.source_type == "manual"

    def test_source_type_default_none(self):
        c = Company(name="Acme")
        assert c.source_type is None

    def test_icp_score_accepts_integer(self):
        c = Company(name="Acme", icp_score=85)
        assert c.icp_score == 85

    def test_icp_score_zero(self):
        c = Company(name="Acme", icp_score=0)
        assert c.icp_score == 0

    def test_icp_score_hundred(self):
        c = Company(name="Acme", icp_score=100)
        assert c.icp_score == 100

    def test_icp_score_default_none(self):
        c = Company(name="Acme")
        assert c.icp_score is None

    def test_status_default_new(self):
        c = Company(name="Acme")
        assert c.status == "new"

    def test_status_contacted(self):
        c = Company(name="Acme", status="contacted")
        assert c.status == "contacted"

    def test_status_skipped(self):
        c = Company(name="Acme", status="skipped")
        assert c.status == "skipped"


# ---------------------------------------------------------------------------
# Person model
# ---------------------------------------------------------------------------

class TestPerson:
    def test_full_name_auto_build(self):
        p = Person(first_name="John", last_name="Doe")
        assert p.full_name == "John Doe"

    def test_full_name_explicit(self):
        p = Person(first_name="John", last_name="Doe", full_name="Johnny Doe")
        assert p.full_name == "Johnny Doe"

    def test_full_name_first_only(self):
        p = Person(first_name="John")
        assert p.full_name == "John"

    def test_email_normalization(self):
        p = Person(first_name="John", email=" John@ACME.COM ")
        assert p.email == "john@acme.com"

    def test_email_none_stays_none(self):
        p = Person(first_name="John", email=None)
        assert p.email is None

    def test_default_uuid_generated(self):
        p1 = Person(first_name="A")
        p2 = Person(first_name="B")
        assert p1.id != p2.id

    def test_default_verification_status(self):
        p = Person(first_name="John")
        assert p.email_status == VerificationStatus.UNKNOWN


# ---------------------------------------------------------------------------
# EnrichmentResult model
# ---------------------------------------------------------------------------

class TestEnrichmentResult:
    def test_default_values(self):
        er = EnrichmentResult(
            enrichment_type=EnrichmentType.EMAIL,
            source_provider=ProviderName.APOLLO,
        )
        assert er.found is False
        assert er.from_cache is False
        assert er.confidence_score == 0.0

    def test_waterfall_position(self):
        er = EnrichmentResult(
            enrichment_type=EnrichmentType.EMAIL,
            source_provider=ProviderName.FINDYMAIL,
            waterfall_position=2,
            found=True,
        )
        assert er.waterfall_position == 2
        assert er.found is True


# ---------------------------------------------------------------------------
# Campaign model
# ---------------------------------------------------------------------------

class TestCampaign:
    def test_default_status(self):
        c = Campaign(name="Test Campaign")
        assert c.status == CampaignStatus.CREATED

    def test_counter_defaults(self):
        c = Campaign(name="Test")
        assert c.total_rows == 0
        assert c.enriched_rows == 0
        assert c.found_rows == 0
        assert c.failed_rows == 0
        assert c.skipped_rows == 0


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------

class TestEnums:
    def test_route_categories(self):
        assert RouteCategory.NAME_AND_DOMAIN.value == "name_and_domain"
        assert RouteCategory.UNROUTABLE.value == "unroutable"

    def test_provider_names(self):
        assert ProviderName.APOLLO.value == "apollo"
        assert ProviderName.FINDYMAIL.value == "findymail"
        assert ProviderName.ICYPEAS.value == "icypeas"
        assert ProviderName.CONTACTOUT.value == "contactout"

    def test_verification_status(self):
        assert VerificationStatus.VERIFIED.value == "verified"
        assert VerificationStatus.INVALID.value == "invalid"

    def test_enrichment_types(self):
        assert EnrichmentType.EMAIL.value == "email"
        assert EnrichmentType.DOMAIN.value == "domain"
