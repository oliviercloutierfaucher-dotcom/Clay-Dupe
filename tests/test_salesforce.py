"""Tests for Salesforce integration: client, config, and database extensions."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from data.database import Database
from data.models import Company

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestSalesforceConfig:
    def test_loads_from_env_vars(self):
        """SalesforceConfig loads credentials from environment variables."""
        from config.settings import load_salesforce_config

        with patch.dict(os.environ, {
            "SALESFORCE_USERNAME": "user@example.com",
            "SALESFORCE_PASSWORD": "pass123",
            "SALESFORCE_SECURITY_TOKEN": "tok456",
        }):
            cfg = load_salesforce_config()
            assert cfg.username == "user@example.com"
            assert cfg.password == "pass123"
            assert cfg.security_token == "tok456"

    def test_is_configured_true_when_all_set(self):
        from config.settings import SalesforceConfig

        cfg = SalesforceConfig(username="u", password="p", security_token="t")
        assert cfg.is_configured() is True

    def test_is_configured_false_when_missing_username(self):
        from config.settings import SalesforceConfig

        cfg = SalesforceConfig(username="", password="p", security_token="t")
        assert cfg.is_configured() is False

    def test_is_configured_false_when_missing_password(self):
        from config.settings import SalesforceConfig

        cfg = SalesforceConfig(username="u", password="", security_token="t")
        assert cfg.is_configured() is False

    def test_is_configured_false_when_missing_token(self):
        from config.settings import SalesforceConfig

        cfg = SalesforceConfig(username="u", password="p", security_token="")
        assert cfg.is_configured() is False

    def test_is_configured_false_when_all_empty(self):
        from config.settings import SalesforceConfig

        cfg = SalesforceConfig()
        assert cfg.is_configured() is False


# ---------------------------------------------------------------------------
# Client tests
# ---------------------------------------------------------------------------

class TestSalesforceClientHealthCheck:
    @patch("providers.salesforce.Salesforce")
    def test_health_check_success(self, MockSF):
        """health_check() returns connected=True with org info."""
        from providers.salesforce import SalesforceClient

        mock_instance = MagicMock()
        mock_instance.query.side_effect = [
            {"records": [{"Name": "Acme Corp"}]},   # org query
            {"totalSize": 42},                        # account count
        ]
        type(mock_instance).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        MockSF.return_value = mock_instance

        client = SalesforceClient("user", "pass", "token")
        result = client.health_check()

        assert result["connected"] is True
        assert result["org_name"] == "Acme Corp"
        assert result["account_count"] == 42
        assert result["sf_instance"] == "na1.salesforce.com"

    @patch("providers.salesforce.Salesforce")
    def test_health_check_auth_failure(self, MockSF):
        """health_check() re-raises SalesforceAuthenticationFailed."""
        from providers.salesforce import SalesforceClient
        from simple_salesforce.exceptions import SalesforceAuthenticationFailed

        MockSF.side_effect = SalesforceAuthenticationFailed(500, "Bad credentials")

        client = SalesforceClient("user", "badpass", "token")
        with pytest.raises(SalesforceAuthenticationFailed):
            client.health_check()


class TestSalesforceClientCheckDomains:
    def _make_client(self):
        from providers.salesforce import SalesforceClient
        return SalesforceClient("user", "pass", "token")

    @patch("providers.salesforce.Salesforce")
    def test_empty_input_returns_empty(self, MockSF):
        """check_domains_batch([]) returns empty dict."""
        client = self._make_client()
        result = client.check_domains_batch([])
        assert result == {}

    @patch("providers.salesforce.Salesforce")
    def test_unique_domain_match(self, MockSF):
        """Matches via Unique_Domain__c field."""
        mock_sf = MagicMock()
        type(mock_sf).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        mock_sf.query_all.return_value = {
            "records": [{
                "Id": "001ABC",
                "Name": "Acme Inc",
                "Unique_Domain__c": "acme.com",
                "Website": "https://www.acme.com",
            }]
        }
        MockSF.return_value = mock_sf

        client = self._make_client()
        result = client.check_domains_batch(["acme.com"])

        assert "acme.com" in result
        assert result["acme.com"]["sf_account_id"] == "001ABC"
        assert result["acme.com"]["sf_account_name"] == "Acme Inc"

    @patch("providers.salesforce.Salesforce")
    def test_website_fallback(self, MockSF):
        """Falls back to Website LIKE match for unmatched domains."""
        mock_sf = MagicMock()
        type(mock_sf).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        # First call: Unique_Domain__c query returns no matches
        # Second call: Website LIKE fallback returns match
        mock_sf.query_all.side_effect = [
            {"records": []},  # Unique_Domain__c miss
            {"records": [{
                "Id": "001DEF",
                "Name": "Beta Corp",
                "Website": "https://beta.com",
            }]},
        ]
        MockSF.return_value = mock_sf

        client = self._make_client()
        result = client.check_domains_batch(["beta.com"])

        assert "beta.com" in result
        assert result["beta.com"]["sf_account_id"] == "001DEF"

    @patch("providers.salesforce.Salesforce")
    def test_chunks_large_lists(self, MockSF):
        """Chunks domain lists into batches of 150."""
        mock_sf = MagicMock()
        type(mock_sf).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        mock_sf.query_all.return_value = {"records": []}
        MockSF.return_value = mock_sf

        client = self._make_client()
        domains = [f"domain{i}.com" for i in range(300)]
        client.check_domains_batch(domains)

        # Should have called query_all multiple times (2 chunks of 150 for Unique_Domain__c)
        # Plus fallback calls for unmatched domains
        assert mock_sf.query_all.call_count >= 2

    @patch("providers.salesforce.Salesforce")
    def test_normalizes_domains(self, MockSF):
        """Normalizes domains before comparison."""
        mock_sf = MagicMock()
        type(mock_sf).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        mock_sf.query_all.return_value = {
            "records": [{
                "Id": "001GHI",
                "Name": "Gamma LLC",
                "Unique_Domain__c": "gamma.com",
                "Website": None,
            }]
        }
        MockSF.return_value = mock_sf

        client = self._make_client()
        result = client.check_domains_batch(["https://www.Gamma.com/"])

        assert "gamma.com" in result
        assert result["gamma.com"]["sf_account_id"] == "001GHI"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestCompanyModelSFFields:
    def test_accepts_sf_fields(self):
        """Company model accepts sf_account_id, sf_status, sf_instance_url."""
        c = Company(
            name="Test Co",
            sf_account_id="001ABC",
            sf_status="in_sf",
            sf_instance_url="na1.salesforce.com",
        )
        assert c.sf_account_id == "001ABC"
        assert c.sf_status == "in_sf"
        assert c.sf_instance_url == "na1.salesforce.com"

    def test_sf_status_defaults_to_none(self):
        """sf_status defaults to None."""
        c = Company(name="Test Co")
        assert c.sf_account_id is None
        assert c.sf_status is None
        assert c.sf_instance_url is None


# ---------------------------------------------------------------------------
# Database tests
# ---------------------------------------------------------------------------

def _make_test_db() -> tuple[Database, str]:
    """Create a fresh in-memory-like temp DB with schema applied."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_sf.db")
    db = Database(db_path)
    return db, db_path


class TestDatabaseSFStatus:
    @pytest.mark.asyncio
    async def test_update_company_sf_status(self):
        """update_company_sf_status() persists sf_account_id and sf_status."""
        db, _ = _make_test_db()
        try:
            company = Company(name="Acme", domain="acme.com")
            await db.upsert_company(company)

            await db.update_company_sf_status("acme.com", "001ABC", "na1.salesforce.com")

            result = await db.get_company_by_domain("acme.com")
            assert result is not None
            assert result.sf_account_id == "001ABC"
            assert result.sf_status == "in_sf"
            assert result.sf_instance_url == "na1.salesforce.com"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_get_companies_by_sf_status(self):
        """get_companies_by_sf_status() filters by sf_status."""
        db, _ = _make_test_db()
        try:
            c1 = Company(name="InSF", domain="insf.com")
            c2 = Company(name="NotSF", domain="notsf.com")
            await db.upsert_company(c1)
            await db.upsert_company(c2)
            await db.update_company_sf_status("insf.com", "001X", "na1.salesforce.com")

            in_sf = await db.get_companies_by_sf_status("in_sf")
            assert len(in_sf) == 1
            assert in_sf[0].domain == "insf.com"

            all_companies = await db.get_companies_by_sf_status(None)
            assert len(all_companies) == 2
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_upsert_preserves_sf_account_id(self):
        """upsert_company preserves sf_account_id if already set."""
        db, _ = _make_test_db()
        try:
            c = Company(name="Acme", domain="acme.com")
            await db.upsert_company(c)
            await db.update_company_sf_status("acme.com", "001ABC", "na1.salesforce.com")

            # Upsert again without SF fields — should preserve existing
            c2 = Company(name="Acme Updated", domain="acme.com")
            await db.upsert_company(c2)

            result = await db.get_company_by_domain("acme.com")
            assert result is not None
            assert result.sf_account_id == "001ABC"
            assert result.sf_status == "in_sf"
            assert result.name == "Acme Updated"
        finally:
            await db.close()
