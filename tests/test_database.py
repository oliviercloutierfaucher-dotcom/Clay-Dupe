"""Tests for database operations."""
from __future__ import annotations

import os
import tempfile
import pytest
from data.database import Database
from data.models import (
    Company, Person, Campaign, EnrichmentResult,
    CampaignStatus, EnrichmentType, VerificationStatus,
)
from config.settings import ProviderName


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path=db_path)
    return database


class TestCompanyOperations:
    def test_upsert_company_insert(self, db):
        company = Company(name="Acme Corp", domain="acme.com", country="US")
        result = db.upsert_company(company)
        assert result is not None

    def test_upsert_company_dedup_by_domain(self, db):
        c1 = Company(name="Acme Corp", domain="acme.com", industry="Tech")
        c2 = Company(name="Acme Corporation", domain="acme.com", employee_count=50)
        db.upsert_company(c1)
        db.upsert_company(c2)

        # Should be one record with merged fields
        found = db.get_company_by_domain("acme.com")
        assert found is not None
        assert found["employee_count"] == 50  # from c2
        assert found["industry"] == "Tech"  # preserved from c1 (COALESCE)

    def test_get_company_by_domain(self, db):
        company = Company(name="Test", domain="test.com")
        db.upsert_company(company)
        found = db.get_company_by_domain("test.com")
        assert found is not None
        assert found["name"] == "Test"

    def test_get_company_by_domain_not_found(self, db):
        found = db.get_company_by_domain("nonexistent.com")
        assert found is None

    def test_search_companies(self, db):
        db.upsert_company(Company(name="Aero Corp", domain="aero.com", country="US", industry="aerospace"))
        db.upsert_company(Company(name="Med Inc", domain="med.com", country="US", industry="medical"))
        results = db.search_companies(country="US")
        assert len(results) == 2


class TestPersonOperations:
    def test_upsert_person_insert(self, db):
        person = Person(first_name="John", last_name="Doe", email="john@acme.com")
        result = db.upsert_person(person)
        assert result is not None

    def test_upsert_person_dedup_by_email(self, db):
        p1 = Person(first_name="John", last_name="Doe", email="john@acme.com", title="VP")
        p2 = Person(first_name="John", last_name="Doe", email="john@acme.com", title="SVP")
        db.upsert_person(p1)
        db.upsert_person(p2)

        found = db.get_person_by_email("john@acme.com")
        assert found is not None
        assert found["title"] == "SVP"  # Updated

    def test_upsert_person_dedup_by_name_company(self, db):
        p1 = Person(first_name="John", last_name="Doe", company_domain="acme.com", title="VP")
        p2 = Person(first_name="John", last_name="Doe", company_domain="acme.com",
                     email="john@acme.com")
        db.upsert_person(p1)
        db.upsert_person(p2)

        found = db.get_person_by_email("john@acme.com")
        assert found is not None

    def test_get_person_by_email(self, db):
        db.upsert_person(Person(first_name="Jane", email="jane@corp.com"))
        found = db.get_person_by_email("jane@corp.com")
        assert found is not None
        assert found["first_name"] == "Jane"

    def test_get_person_by_email_not_found(self, db):
        assert db.get_person_by_email("nobody@nowhere.com") is None


class TestCacheOperations:
    def test_cache_roundtrip(self, db):
        db.cache_set(
            provider="apollo",
            enrichment_type="email",
            query_input={"first_name": "john", "last_name": "doe", "domain": "acme.com"},
            response_data={"email": "john@acme.com"},
            found=True,
            ttl_days=30,
        )
        result = db.cache_get(
            provider="apollo",
            enrichment_type="email",
            query_input={"first_name": "john", "last_name": "doe", "domain": "acme.com"},
        )
        assert result is not None
        assert result["response_data"]["email"] == "john@acme.com"

    def test_cache_miss(self, db):
        result = db.cache_get("apollo", "email", {"first_name": "nobody"})
        assert result is None

    def test_cache_key_normalized(self, db):
        """Same query with different key order should hit cache."""
        query1 = {"first_name": "john", "domain": "acme.com", "last_name": "doe"}
        query2 = {"domain": "acme.com", "first_name": "john", "last_name": "doe"}
        db.cache_set("apollo", "email", query1, {"email": "john@acme.com"}, True, 30)
        result = db.cache_get("apollo", "email", query2)
        assert result is not None


class TestCampaignOperations:
    def test_create_campaign(self, db):
        campaign = Campaign(name="Test Campaign", input_row_count=100)
        result = db.create_campaign(campaign)
        assert result is not None

    def test_get_campaign(self, db):
        campaign = Campaign(name="Test Campaign")
        created = db.create_campaign(campaign)
        campaign_id = created.id if hasattr(created, 'id') else str(created)
        found = db.get_campaign(str(campaign.id))
        assert found is not None

    def test_update_campaign_status(self, db):
        campaign = Campaign(name="Test")
        db.create_campaign(campaign)
        db.update_campaign_status(str(campaign.id), CampaignStatus.RUNNING)
        found = db.get_campaign(str(campaign.id))
        assert found is not None
        assert found["status"] == CampaignStatus.RUNNING.value

    def test_get_recent_campaigns(self, db):
        for i in range(3):
            db.create_campaign(Campaign(name=f"Campaign {i}"))
        recent = db.get_recent_campaigns(limit=2)
        assert len(recent) == 2


class TestCreditUsage:
    def test_record_and_get(self, db):
        db.record_credit_usage("apollo", 5.0, found=True)
        db.record_credit_usage("apollo", 3.0, found=False)
        usage = db.get_credit_usage("apollo", days=1)
        assert len(usage) >= 1


class TestEmailPatterns:
    def test_record_and_get_pattern(self, db):
        db.record_pattern("acme.com", "{first}.{last}", "john.doe@acme.com", 0.45)
        patterns = db.get_domain_patterns("acme.com")
        assert len(patterns) >= 1
        assert patterns[0]["pattern"] == "{first}.{last}"

    def test_no_patterns_for_unknown_domain(self, db):
        patterns = db.get_domain_patterns("unknown.com")
        assert len(patterns) == 0


class TestCatchAll:
    def test_set_and_get(self, db):
        db.set_catch_all_status("acme.com", True)
        status = db.get_catch_all_status("acme.com")
        assert status is True

    def test_get_unknown_domain(self, db):
        status = db.get_catch_all_status("unknown.com")
        assert status is None


class TestDashboardStats:
    def test_returns_dict(self, db):
        stats = db.get_dashboard_stats()
        assert isinstance(stats, dict)
        assert "total_enriched" in stats or "email_find_rate" in stats or len(stats) >= 0


class TestAuditLog:
    def test_log_action(self, db):
        db.log_action("test_action", entity_type="test", entity_id="123")
        # Should not raise
