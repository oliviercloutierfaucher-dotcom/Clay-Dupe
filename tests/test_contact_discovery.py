"""Tests for contact discovery module."""
import asyncio
from unittest.mock import AsyncMock, patch, call

import pytest

from data.models import Company, Person
from enrichment.contact_discovery import discover_contact, batch_discover_contacts
from providers.apollo import ApolloProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_apollo():
    """ApolloProvider with mocked search_people."""
    apollo = AsyncMock(spec=ApolloProvider)
    return apollo


@pytest.fixture
def company_with_domain() -> Company:
    return Company(
        id="comp-001",
        name="AeroTech Corp",
        domain="aerotech.com",
        industry="aerospace",
    )


@pytest.fixture
def company_no_domain() -> Company:
    return Company(
        id="comp-002",
        name="NoDomain Inc",
    )


@pytest.fixture
def sample_person() -> Person:
    return Person(
        id="person-001",
        first_name="John",
        last_name="Doe",
        title="CEO",
        seniority="c_suite",
    )


# ---------------------------------------------------------------------------
# discover_contact tests
# ---------------------------------------------------------------------------

class TestDiscoverContact:
    @pytest.mark.asyncio
    async def test_calls_apollo_with_correct_filters(self, mock_apollo, company_with_domain, sample_person):
        """discover_contact() calls Apollo search_people with correct title/seniority filters."""
        mock_apollo.search_people.return_value = [sample_person]

        await discover_contact(mock_apollo, company_with_domain)

        mock_apollo.search_people.assert_called_once_with(
            q_organization_domains_list=["aerotech.com"],
            person_titles=["CEO", "Owner", "Founder", "President",
                           "Managing Director", "General Manager"],
            person_seniorities=["c_suite", "owner"],
            per_page=5,
        )

    @pytest.mark.asyncio
    async def test_returns_first_person_with_company_id(self, mock_apollo, company_with_domain, sample_person):
        """discover_contact() returns first Person result with company_id set."""
        mock_apollo.search_people.return_value = [sample_person]

        result = await discover_contact(mock_apollo, company_with_domain)

        assert result is not None
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.company_id == "comp-001"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_domain(self, mock_apollo, company_no_domain):
        """discover_contact() returns None when company has no domain."""
        result = await discover_contact(mock_apollo, company_no_domain)

        assert result is None
        mock_apollo.search_people.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_empty_results(self, mock_apollo, company_with_domain):
        """discover_contact() returns None when Apollo returns empty results."""
        mock_apollo.search_people.return_value = []

        result = await discover_contact(mock_apollo, company_with_domain)

        assert result is None


# ---------------------------------------------------------------------------
# batch_discover_contacts tests
# ---------------------------------------------------------------------------

class TestBatchDiscoverContacts:
    @pytest.mark.asyncio
    async def test_batch_processes_multiple_companies(self, mock_apollo):
        """batch_discover_contacts() processes multiple companies."""
        companies = [
            Company(id="c1", name="Co1", domain="co1.com"),
            Company(id="c2", name="Co2", domain="co2.com"),
            Company(id="c3", name="Co3", domain="co3.com"),
        ]
        persons = [
            Person(first_name="Alice", title="CEO"),
            Person(first_name="Bob", title="Owner"),
            Person(first_name="Carol", title="Founder"),
        ]
        mock_apollo.search_people.side_effect = [[p] for p in persons]

        with patch("enrichment.contact_discovery.asyncio.sleep", new_callable=AsyncMock):
            results = await batch_discover_contacts(mock_apollo, companies)

        assert len(results) == 3
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        # Each company should have a contact
        for i, (company, person) in enumerate(results):
            assert company.id == companies[i].id
            assert person is not None
            assert person.company_id == companies[i].id

    @pytest.mark.asyncio
    async def test_batch_rate_limiting(self, mock_apollo):
        """batch_discover_contacts() sleeps 1.5s between calls."""
        companies = [
            Company(id="c1", name="Co1", domain="co1.com"),
            Company(id="c2", name="Co2", domain="co2.com"),
            Company(id="c3", name="Co3", domain="co3.com"),
        ]
        mock_apollo.search_people.return_value = [
            Person(first_name="Test", title="CEO")
        ]

        with patch("enrichment.contact_discovery.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await batch_discover_contacts(mock_apollo, companies)

        # Should sleep between items (2 sleeps for 3 items)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.5)

    @pytest.mark.asyncio
    async def test_batch_progress_callback(self, mock_apollo):
        """batch_discover_contacts() calls progress_callback if provided."""
        companies = [
            Company(id="c1", name="Co1", domain="co1.com"),
            Company(id="c2", name="Co2", domain="co2.com"),
        ]
        mock_apollo.search_people.return_value = [
            Person(first_name="Test", title="CEO")
        ]
        callback = AsyncMock()

        with patch("enrichment.contact_discovery.asyncio.sleep", new_callable=AsyncMock):
            await batch_discover_contacts(mock_apollo, companies, progress_callback=callback)

        assert callback.call_count == 2
        callback.assert_any_call(0, 2)
        callback.assert_any_call(1, 2)

    @pytest.mark.asyncio
    async def test_batch_handles_no_domain_companies(self, mock_apollo):
        """batch_discover_contacts() skips companies without domain."""
        companies = [
            Company(id="c1", name="Co1", domain="co1.com"),
            Company(id="c2", name="NoDomain"),
        ]
        mock_apollo.search_people.return_value = [
            Person(first_name="Test", title="CEO")
        ]

        with patch("enrichment.contact_discovery.asyncio.sleep", new_callable=AsyncMock):
            results = await batch_discover_contacts(mock_apollo, companies)

        assert len(results) == 2
        assert results[0][1] is not None  # has domain, got contact
        assert results[1][1] is None      # no domain, no contact
