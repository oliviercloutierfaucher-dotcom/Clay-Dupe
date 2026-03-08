"""Tests for company sourcing: CSV import, manual add, source tracking, domain dedup."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.io import ColumnMapper, read_input_file, apply_mapping, map_to_companies
from data.models import Company


# ---------------------------------------------------------------------------
# ColumnMapper: company-specific column detection
# ---------------------------------------------------------------------------


class TestColumnMapperCompanyFields:
    """ColumnMapper should detect company-specific columns like revenue, ebitda, etc."""

    def test_revenue_aliases(self):
        """Revenue columns should map to revenue_usd."""
        for alias in ["revenue", "annual_revenue", "annual_revenue_usd", "yearly_revenue", "rev", "Revenue USD"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "revenue_usd", (
                f"'{alias}' should map to 'revenue_usd', got {summary['mapped'].get(alias)}"
            )

    def test_ebitda_aliases(self):
        """EBITDA columns should map to ebitda_usd."""
        for alias in ["ebitda", "annual_ebitda", "ebitda_usd", "EBITDA USD"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "ebitda_usd", (
                f"'{alias}' should map to 'ebitda_usd', got {summary['mapped'].get(alias)}"
            )

    def test_founded_year_aliases(self):
        """Founded year columns should map to founded_year."""
        for alias in ["founded", "year_founded", "founding_year", "established"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "founded_year", (
                f"'{alias}' should map to 'founded_year', got {summary['mapped'].get(alias)}"
            )

    def test_employee_count_new_aliases(self):
        """New employee count aliases should map to employee_count."""
        for alias in ["headcount", "num_employees", "total_employees"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "employee_count", (
                f"'{alias}' should map to 'employee_count', got {summary['mapped'].get(alias)}"
            )

    def test_website_url_aliases(self):
        """Website/URL columns should map to website_url."""
        for alias in ["website", "company_url", "homepage"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "website_url", (
                f"'{alias}' should map to 'website_url', got {summary['mapped'].get(alias)}"
            )

    def test_description_aliases(self):
        """Description columns should map to description."""
        for alias in ["about", "company_description", "overview", "summary"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "description", (
                f"'{alias}' should map to 'description', got {summary['mapped'].get(alias)}"
            )

    def test_linkedin_company_aliases(self):
        """Company LinkedIn aliases should map to linkedin_url."""
        for alias in ["linkedin", "linkedin_profile", "company_linkedin"]:
            mapper = ColumnMapper([alias])
            summary = mapper.get_mapping_summary()
            assert summary["mapped"].get(alias) == "linkedin_url", (
                f"'{alias}' should map to 'linkedin_url', got {summary['mapped'].get(alias)}"
            )


# ---------------------------------------------------------------------------
# CSV -> Company mapping
# ---------------------------------------------------------------------------


class TestCSVToCompanyMapping:
    """CSV data should map correctly to Company model fields."""

    def test_csv_maps_to_company_model(self):
        """map_to_companies converts mapped DataFrame rows to Company objects."""
        df = pd.DataFrame({
            "Company Name": ["Acme Corp"],
            "Domain": ["acme.com"],
            "Industry": ["Software"],
            "Employee Count": ["150"],
            "Country": ["US"],
        })
        mapping = {
            "Company Name": "company_name",
            "Domain": "company_domain",
            "Industry": "industry",
            "Employee Count": "employee_count",
            "Country": "country",
        }
        companies = map_to_companies(df, mapping, source_type="csv_import")
        assert len(companies) == 1
        c = companies[0]
        assert isinstance(c, Company)
        assert c.name == "Acme Corp"
        assert c.domain == "acme.com"
        assert c.industry == "Software"
        assert c.employee_count == 150
        assert c.country == "US"

    def test_csv_revenue_and_ebitda(self):
        """Revenue and EBITDA fields are converted to Decimal."""
        df = pd.DataFrame({
            "Company": ["Acme"],
            "Revenue": ["5000000"],
            "EBITDA": ["1200000"],
        })
        mapping = {
            "Company": "company_name",
            "Revenue": "revenue_usd",
            "EBITDA": "ebitda_usd",
        }
        companies = map_to_companies(df, mapping, source_type="csv_import")
        c = companies[0]
        assert c.revenue_usd is not None
        assert float(c.revenue_usd) == 5000000.0
        assert c.ebitda_usd is not None
        assert float(c.ebitda_usd) == 1200000.0

    def test_csv_with_various_column_formats(self):
        """ColumnMapper + map_to_companies handles real-world CSV headers."""
        df = pd.DataFrame({
            "Company Name": ["TechCo"],
            "Website": ["techco.com"],
            "Headcount": ["50"],
            "Annual Revenue": ["10000000"],
            "Founded": ["2010"],
        })
        mapper = ColumnMapper(list(df.columns))
        records = apply_mapping(df, mapper.mapping)
        # Should have mapped at least company_name, website_url or company_domain, employee_count
        mapped_fields = set(mapper.mapping.values())
        assert "company_name" in mapped_fields
        assert "employee_count" in mapped_fields


# ---------------------------------------------------------------------------
# Source type tracking
# ---------------------------------------------------------------------------


class TestSourceTypeTracking:
    """Each sourcing channel must set source_type correctly."""

    def test_csv_import_source_type(self):
        """Companies created from CSV import have source_type='csv_import'."""
        df = pd.DataFrame({"Company": ["Acme"], "Domain": ["acme.com"]})
        mapping = {"Company": "company_name", "Domain": "company_domain"}
        companies = map_to_companies(df, mapping, source_type="csv_import")
        assert companies[0].source_type == "csv_import"

    def test_apollo_search_source_type(self):
        """Companies from Apollo search should have source_type='apollo_search'."""
        df = pd.DataFrame({"Company": ["Acme"], "Domain": ["acme.com"]})
        mapping = {"Company": "company_name", "Domain": "company_domain"}
        companies = map_to_companies(df, mapping, source_type="apollo_search")
        assert companies[0].source_type == "apollo_search"

    def test_manual_source_type(self):
        """Manually added companies should have source_type='manual'."""
        df = pd.DataFrame({"Company": ["Acme"], "Domain": ["acme.com"]})
        mapping = {"Company": "company_name", "Domain": "company_domain"}
        companies = map_to_companies(df, mapping, source_type="manual")
        assert companies[0].source_type == "manual"


# ---------------------------------------------------------------------------
# Domain normalization + dedup
# ---------------------------------------------------------------------------


class TestDomainNormalization:
    """Domain normalization should deduplicate on import."""

    def test_www_prefix_stripped(self):
        """www.acme.com normalizes to acme.com."""
        c = Company(name="Acme", domain="www.acme.com")
        assert c.domain == "acme.com"

    def test_https_prefix_stripped(self):
        """https://acme.com/ normalizes to acme.com."""
        c = Company(name="Acme", domain="https://acme.com/")
        assert c.domain == "acme.com"

    def test_http_prefix_stripped(self):
        """http://acme.com normalizes to acme.com."""
        c = Company(name="Acme", domain="http://acme.com")
        assert c.domain == "acme.com"

    def test_trailing_slash_stripped(self):
        """acme.com/ normalizes to acme.com."""
        c = Company(name="Acme", domain="acme.com/")
        assert c.domain == "acme.com"

    def test_domain_lowercased(self):
        """ACME.COM normalizes to acme.com."""
        c = Company(name="Acme", domain="ACME.COM")
        assert c.domain == "acme.com"

    def test_duplicate_domains_in_csv_merge(self):
        """Two CSV rows with same domain (after normalization) result in one company."""
        df = pd.DataFrame({
            "Company": ["Acme Inc", "Acme Corp"],
            "Domain": ["www.acme.com", "acme.com"],
            "Industry": ["Software", "Technology"],
        })
        mapping = {
            "Company": "company_name",
            "Domain": "company_domain",
            "Industry": "industry",
        }
        companies = map_to_companies(df, mapping, source_type="csv_import")
        # After domain normalization, both should have domain="acme.com"
        # map_to_companies should deduplicate by domain
        domains = [c.domain for c in companies]
        assert len(set(domains)) == len(companies), (
            f"Expected unique domains, got {domains}"
        )
        assert len(companies) == 1
        # First row wins for name, but second row's industry should be kept if first is None
        # In this case both have values, so first wins
        assert companies[0].name == "Acme Inc"
