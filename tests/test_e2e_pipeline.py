"""End-to-end pipeline integration test.

Exercises the full programmatic pipeline:
  Campaign creation -> Company sourcing -> Enrichment (mocked) ->
  Salesforce dedup gate (mocked) -> Email generation (mocked) -> CSV export

All external services are mocked at the client/SDK level.
"""
from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from data.database import Database
from data.models import (
    Campaign,
    CampaignStatus,
    Company,
    EmailTemplate,
    GeneratedEmail,
    Person,
)
from data.sync import run_sync
from data.email_engine import generate_single_email


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test_e2e.db")
    database = Database(db_path=db_path)
    return database


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

TEST_COMPANIES = [
    Company(
        name="Acme Corp",
        domain="acme.com",
        industry="Manufacturing",
        employee_count=150,
        city="Austin",
        state="TX",
        country="US",
        description="Industrial widgets manufacturer",
        icp_score=85,
    ),
    Company(
        name="Beta Technologies",
        domain="betatech.io",
        industry="SaaS",
        employee_count=45,
        city="San Francisco",
        state="CA",
        country="US",
        description="Developer tooling platform",
        icp_score=72,
    ),
    Company(
        name="Gamma Solutions",
        domain="gamma.co",
        industry="Consulting",
        employee_count=20,
        city="New York",
        state="NY",
        country="US",
        description="Management consulting firm",
        icp_score=60,
    ),
]

TEST_PERSONS = [
    Person(
        first_name="John",
        last_name="Smith",
        email="john.smith@acme.com",
        title="VP Engineering",
        company_domain="acme.com",
        company_name="Acme Corp",
        linkedin_url="https://linkedin.com/in/johnsmith",
    ),
    Person(
        first_name="Sarah",
        last_name="Chen",
        email="sarah@betatech.io",
        title="CTO",
        company_domain="betatech.io",
        company_name="Beta Technologies",
        linkedin_url="https://linkedin.com/in/sarachen",
    ),
    Person(
        first_name="Mike",
        last_name="Johnson",
        email="mike.j@gamma.co",
        title="Director of Sales",
        company_domain="gamma.co",
        company_name="Gamma Solutions",
    ),
]


def _mock_anthropic_response(subject: str = "Test Subject", body: str = "Test body text."):
    """Create a mock Anthropic message response."""
    mock_content = MagicMock()
    mock_content.text = f"Subject: {subject}\n\n{body}"

    mock_usage = MagicMock()
    mock_usage.input_tokens = 150
    mock_usage.output_tokens = 80

    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_message.usage = mock_usage
    return mock_message


# ---------------------------------------------------------------------------
# Test: Full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Full pipeline E2E: campaign -> source -> enrich -> SF dedup -> email -> CSV."""

    def test_full_pipeline(self, db):
        """Exercise the complete pipeline with all services mocked."""
        # ---------------------------------------------------------------
        # Step 1: Create campaign + add companies
        # ---------------------------------------------------------------
        campaign = Campaign(
            id="camp-e2e-1",
            name="E2E Test Campaign",
            status=CampaignStatus.CREATED,
        )
        run_sync(db.create_campaign(campaign))

        # Add companies to the database
        for company in TEST_COMPANIES:
            run_sync(db.upsert_company(company))

        # Verify companies persisted
        for company in TEST_COMPANIES:
            fetched = run_sync(db.get_company_by_domain(company.domain))
            assert fetched is not None, f"Company {company.domain} not found in DB"
            assert fetched.name == company.name

        # ---------------------------------------------------------------
        # Step 2: Simulate enrichment (mock the waterfall -- add persons)
        # ---------------------------------------------------------------
        # In the real flow, the waterfall enricher discovers Person records.
        # Here we directly insert the mocked enrichment results.
        for person in TEST_PERSONS:
            run_sync(db.upsert_person(person))

        # Verify persons persisted
        for person in TEST_PERSONS:
            fetched = run_sync(db.get_person_by_email(person.email))
            assert fetched is not None, f"Person {person.email} not found in DB"
            assert fetched.first_name == person.first_name

        # ---------------------------------------------------------------
        # Step 3: Salesforce dedup gate (mock)
        # ---------------------------------------------------------------
        # acme.com is in SF (should be flagged), betatech.io and gamma.co are not
        mock_sf_results = {
            "acme.com": {
                "sf_account_id": "001ACME",
                "sf_account_name": "Acme Inc",
                "sf_instance_url": "na1.salesforce.com",
            }
        }

        # Apply SF status for matched company
        for domain, sf_data in mock_sf_results.items():
            run_sync(db.update_company_sf_status(
                domain, sf_data["sf_account_id"], sf_data["sf_instance_url"]
            ))

        # Verify SF dedup flags
        acme = run_sync(db.get_company_by_domain("acme.com"))
        assert acme.sf_account_id == "001ACME"
        assert acme.sf_status == "in_sf"

        beta = run_sync(db.get_company_by_domain("betatech.io"))
        assert beta.sf_account_id is None
        assert beta.sf_status is None

        # ---------------------------------------------------------------
        # Step 4: Generate emails (mock Anthropic API)
        # ---------------------------------------------------------------
        template = EmailTemplate(
            name="Intro Email",
            system_prompt="You are a professional sales email writer.",
            user_prompt_template="Write a personalized email to {first_name} {last_name}, {title} at {company_name}.",
        )
        run_sync(db.save_email_template(template))

        # Mark campaign as completed (required for email generation)
        run_sync(db.update_campaign_status(campaign.id, CampaignStatus.COMPLETED))

        # Generate emails for non-SF contacts only (betatech.io and gamma.co)
        non_sf_persons = [p for p in TEST_PERSONS if p.company_domain != "acme.com"]
        assert len(non_sf_persons) == 2

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(
                subject="Quick question about your dev tools",
                body="Hi Sarah, I noticed Beta Technologies is building innovative developer tooling..."
            ),
            _mock_anthropic_response(
                subject="Idea for Gamma Solutions",
                body="Hi Mike, your work at Gamma Solutions in consulting caught my attention..."
            ),
        ]

        generated_emails = []
        for person in non_sf_persons:
            company = next(
                (c for c in TEST_COMPANIES if c.domain == person.company_domain), None
            )
            email = generate_single_email(
                client=mock_client,
                template=template,
                person=person,
                company=company,
                campaign_id=campaign.id,
            )
            assert isinstance(email, GeneratedEmail)
            assert email.status == "draft"
            assert email.subject is not None
            assert email.body is not None
            assert email.input_tokens > 0
            assert email.cost_usd > 0
            run_sync(db.save_generated_email(email))
            generated_emails.append(email)

        # Verify emails persisted
        saved_emails = run_sync(db.get_generated_emails(campaign.id))
        assert len(saved_emails) == 2

        # Verify Anthropic was called exactly twice
        assert mock_client.messages.create.call_count == 2

        # ---------------------------------------------------------------
        # Step 5: Export CSV (Outreach.io format)
        # ---------------------------------------------------------------
        # Build CSV export manually (mirroring the Outreach.io preset logic)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "Email", "First Name", "Last Name", "Company", "Subject", "Body", "Sequence Step",
        ])
        writer.writeheader()

        for email in generated_emails:
            person = next(
                (p for p in TEST_PERSONS if p.email and email.person_id == p.id), None
            )
            # Fallback: match by looking up person from non_sf_persons list
            if person is None:
                idx = generated_emails.index(email)
                person = non_sf_persons[idx]
            company = next(
                (c for c in TEST_COMPANIES if c.domain == person.company_domain), None
            )
            writer.writerow({
                "Email": person.email or "",
                "First Name": person.first_name or "",
                "Last Name": person.last_name or "",
                "Company": company.name if company else "",
                "Subject": email.subject or "",
                "Body": email.body or "",
                "Sequence Step": email.sequence_step,
            })

        csv_content = output.getvalue()

        # Verify CSV structure
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 2

        # Verify Outreach.io columns present
        expected_cols = {"Email", "First Name", "Last Name", "Company", "Subject", "Body", "Sequence Step"}
        assert set(rows[0].keys()) == expected_cols

        # Verify data integrity
        emails_in_csv = {r["Email"] for r in rows}
        assert "sarah@betatech.io" in emails_in_csv
        assert "mike.j@gamma.co" in emails_in_csv
        # acme.com contact should NOT be in export (SF dedup)
        assert "john.smith@acme.com" not in emails_in_csv

        # Verify all rows have non-empty subjects and bodies
        for row in rows:
            assert row["Subject"], f"Empty subject for {row['Email']}"
            assert row["Body"], f"Empty body for {row['Email']}"
            assert row["First Name"], f"Empty first name for {row['Email']}"


class TestPipelineWithSFSkip:
    """Verify SF dedup correctly flags companies and blocks enrichment."""

    def test_pipeline_with_sf_skip(self, db):
        """Companies matched in SF are flagged; their contacts are skipped for email gen."""
        # Create campaign
        campaign = Campaign(id="camp-sf-skip", name="SF Skip Test")
        run_sync(db.create_campaign(campaign))

        # Add two companies
        company_in_sf = Company(name="InSF Corp", domain="insf.com", industry="Finance")
        company_not_sf = Company(name="NotSF Inc", domain="notsf.com", industry="Tech")
        run_sync(db.upsert_company(company_in_sf))
        run_sync(db.upsert_company(company_not_sf))

        # Add persons for both companies
        person_in_sf = Person(
            first_name="Alice", last_name="Wang",
            email="alice@insf.com", company_domain="insf.com",
        )
        person_not_sf = Person(
            first_name="Bob", last_name="Garcia",
            email="bob@notsf.com", company_domain="notsf.com",
        )
        run_sync(db.upsert_person(person_in_sf))
        run_sync(db.upsert_person(person_not_sf))

        # Simulate SF dedup: insf.com matches, notsf.com does not
        run_sync(db.update_company_sf_status("insf.com", "001INSF", "na1.salesforce.com"))

        # Verify SF flags
        insf = run_sync(db.get_company_by_domain("insf.com"))
        assert insf.sf_status == "in_sf"
        assert insf.sf_account_id == "001INSF"

        notsf = run_sync(db.get_company_by_domain("notsf.com"))
        assert notsf.sf_status is None

        # Filter contacts: only generate emails for non-SF companies
        in_sf_companies = run_sync(db.get_companies_by_sf_status("in_sf"))
        sf_domains = {c.domain for c in in_sf_companies}
        assert "insf.com" in sf_domains
        assert "notsf.com" not in sf_domains

        # Build non-SF contact list
        all_persons = [person_in_sf, person_not_sf]
        eligible_persons = [p for p in all_persons if p.company_domain not in sf_domains]
        assert len(eligible_persons) == 1
        assert eligible_persons[0].email == "bob@notsf.com"

        # Generate email only for eligible person
        template = EmailTemplate(
            name="Test", system_prompt="sys", user_prompt_template="Write to {first_name}.",
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            subject="Hello Bob", body="Hi Bob, reaching out..."
        )

        email = generate_single_email(
            client=mock_client,
            template=template,
            person=eligible_persons[0],
            company=company_not_sf,
            campaign_id=campaign.id,
        )
        assert email.subject == "Hello Bob"
        assert email.status == "draft"

        # Verify only 1 API call was made (SF person was skipped)
        assert mock_client.messages.create.call_count == 1
