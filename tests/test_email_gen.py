"""Tests for email generation data layer and engine."""
from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch
import pytest
from data.database import Database
from data.models import (
    EmailTemplate, GeneratedEmail, Person, Company, Campaign,
)
from data.sync import run_sync


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test_email.db")
    database = Database(db_path=db_path)
    return database


def _make_campaign(db, campaign_id: str = "camp-1") -> Campaign:
    """Create a campaign in the DB and return it."""
    c = Campaign(id=campaign_id, name=f"Test Campaign {campaign_id}")
    run_sync(db.create_campaign(c))
    return c


def _make_person(db, person_id: str = "p-1", email: str = "test@test.com") -> Person:
    """Create a person in the DB and return it."""
    p = Person(id=person_id, first_name="Test", last_name="User", email=email)
    run_sync(db.upsert_person(p))
    return p


# ---------------------------------------------------------------
# Task 1: Data layer tests
# ---------------------------------------------------------------

class TestEmailTemplateModel:
    def test_create_with_all_fields(self):
        t = EmailTemplate(
            name="Test Template",
            description="A test",
            system_prompt="You are a writer.",
            user_prompt_template="Write to {first_name}.",
            sequence_step=1,
            is_default=True,
        )
        assert t.id  # auto-generated UUID
        assert t.name == "Test Template"
        assert t.system_prompt == "You are a writer."
        assert t.user_prompt_template == "Write to {first_name}."
        assert t.sequence_step == 1
        assert t.is_default is True
        assert t.created_at is not None
        assert t.updated_at is not None

    def test_defaults(self):
        t = EmailTemplate(
            name="Min",
            system_prompt="sys",
            user_prompt_template="usr",
        )
        assert t.sequence_step == 1
        assert t.is_default is False
        assert t.description is None


class TestGeneratedEmailModel:
    def test_create_with_all_fields(self):
        e = GeneratedEmail(
            campaign_id="camp-1",
            person_id="person-1",
            template_id="tmpl-1",
            company_id="comp-1",
            sequence_step=2,
            subject="Hello",
            body="Body text",
            status="approved",
            user_note="make shorter",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.0015,
        )
        assert e.campaign_id == "camp-1"
        assert e.person_id == "person-1"
        assert e.status == "approved"
        assert e.cost_usd == 0.0015
        assert e.id  # auto-generated

    def test_defaults(self):
        e = GeneratedEmail(campaign_id="c", person_id="p")
        assert e.status == "draft"
        assert e.input_tokens == 0
        assert e.output_tokens == 0
        assert e.cost_usd == 0.0
        assert e.subject is None
        assert e.body is None


class TestTemplateCRUD:
    def test_save_and_get_template(self, db):
        t = EmailTemplate(
            name="Intro",
            system_prompt="sys prompt",
            user_prompt_template="Write to {first_name}",
        )
        saved = run_sync(db.save_email_template(t))
        assert saved.id == t.id

        fetched = run_sync(db.get_email_template(t.id))
        assert fetched is not None
        assert fetched.name == "Intro"
        assert fetched.system_prompt == "sys prompt"

    def test_get_all_templates(self, db):
        for i in range(3):
            run_sync(db.save_email_template(EmailTemplate(
                name=f"Template {i}",
                system_prompt="sys",
                user_prompt_template="usr",
            )))
        templates = run_sync(db.get_email_templates())
        assert len(templates) == 3

    def test_delete_template(self, db):
        t = EmailTemplate(name="Del", system_prompt="s", user_prompt_template="u")
        run_sync(db.save_email_template(t))
        run_sync(db.delete_email_template(t.id))
        assert run_sync(db.get_email_template(t.id)) is None

    def test_get_nonexistent_template(self, db):
        assert run_sync(db.get_email_template("nonexistent")) is None


class TestGeneratedEmailCRUD:
    def test_save_and_get(self, db):
        camp = _make_campaign(db, "camp-1")
        person = _make_person(db, "p-1", "p1@test.com")
        e = GeneratedEmail(
            campaign_id=camp.id,
            person_id=person.id,
            subject="Hi",
            body="Hello there",
        )
        run_sync(db.save_generated_email(e))
        results = run_sync(db.get_generated_emails(camp.id))
        assert len(results) == 1
        assert results[0].subject == "Hi"

    def test_filter_by_status(self, db):
        camp = _make_campaign(db, "camp-1")
        for i, status in enumerate(("draft", "approved", "rejected")):
            person = _make_person(db, f"p-{status}", f"p{i}@test.com")
            run_sync(db.save_generated_email(GeneratedEmail(
                campaign_id=camp.id,
                person_id=person.id,
                status=status,
            )))
        drafts = run_sync(db.get_generated_emails(camp.id, status="draft"))
        assert len(drafts) == 1
        approved = run_sync(db.get_generated_emails(camp.id, status="approved"))
        assert len(approved) == 1

    def test_filter_by_campaign(self, db):
        camp_a = _make_campaign(db, "camp-A")
        camp_b = _make_campaign(db, "camp-B")
        p1 = _make_person(db, "p1", "p1@test.com")
        p2 = _make_person(db, "p2", "p2@test.com")
        run_sync(db.save_generated_email(GeneratedEmail(
            campaign_id=camp_a.id, person_id=p1.id,
        )))
        run_sync(db.save_generated_email(GeneratedEmail(
            campaign_id=camp_b.id, person_id=p2.id,
        )))
        assert len(run_sync(db.get_generated_emails(camp_a.id))) == 1
        assert len(run_sync(db.get_generated_emails(camp_b.id))) == 1

    def test_update_email_status(self, db):
        camp = _make_campaign(db, "c")
        person = _make_person(db, "p", "p@test.com")
        e = GeneratedEmail(campaign_id=camp.id, person_id=person.id, status="draft")
        run_sync(db.save_generated_email(e))
        run_sync(db.update_email_status(e.id, "approved"))
        results = run_sync(db.get_generated_emails(camp.id))
        assert results[0].status == "approved"

    def test_update_email_content(self, db):
        camp = _make_campaign(db, "c")
        person = _make_person(db, "p", "p@test.com")
        e = GeneratedEmail(
            campaign_id=camp.id, person_id=person.id,
            subject="Old Subject", body="Old Body",
        )
        run_sync(db.save_generated_email(e))
        run_sync(db.update_email_content(e.id, "New Subject", "New Body"))
        results = run_sync(db.get_generated_emails(camp.id))
        assert results[0].subject == "New Subject"
        assert results[0].body == "New Body"


class TestSeedDefaultTemplates:
    def test_seeds_three_templates(self, db):
        run_sync(db.seed_default_templates())
        templates = run_sync(db.get_email_templates())
        assert len(templates) == 3
        names = {t.name for t in templates}
        assert "Consultative Intro" in names
        assert "Case Study Follow-up" in names
        assert "Breakup" in names

    def test_seed_idempotent(self, db):
        run_sync(db.seed_default_templates())
        run_sync(db.seed_default_templates())
        templates = run_sync(db.get_email_templates())
        assert len(templates) == 3  # Still 3, not 6


class TestEmailStatusWorkflow:
    def test_draft_to_approved_to_rejected(self, db):
        camp = _make_campaign(db, "c")
        person = _make_person(db, "p", "p@test.com")
        e = GeneratedEmail(campaign_id=camp.id, person_id=person.id, status="draft")
        run_sync(db.save_generated_email(e))

        run_sync(db.update_email_status(e.id, "approved"))
        result = run_sync(db.get_generated_emails(camp.id))
        assert result[0].status == "approved"

        run_sync(db.update_email_status(e.id, "rejected"))
        result = run_sync(db.get_generated_emails(camp.id))
        assert result[0].status == "rejected"


class TestGetPersonWithCompany:
    def test_person_with_company(self, db):
        company = Company(name="Acme", domain="acme.com")
        run_sync(db.upsert_company(company))
        person = Person(
            first_name="John", last_name="Doe",
            email="john@acme.com", company_domain="acme.com",
        )
        run_sync(db.upsert_person(person))
        # Fetch the person to get the actual ID
        fetched_person = run_sync(db.get_person_by_email("john@acme.com"))
        p, c = run_sync(db.get_person_with_company(fetched_person.id))
        assert p is not None
        assert p.first_name == "John"
        assert c is not None
        assert c.name == "Acme"

    def test_person_without_company(self, db):
        person = Person(first_name="Jane", last_name="Doe", email="jane@solo.com")
        run_sync(db.upsert_person(person))
        fetched = run_sync(db.get_person_by_email("jane@solo.com"))
        p, c = run_sync(db.get_person_with_company(fetched.id))
        assert p is not None
        assert c is None


# ---------------------------------------------------------------
# Task 2: Email engine tests
# ---------------------------------------------------------------

from data.email_engine import (
    _build_variables,
    _substitute_variables,
    _score_to_tier,
    _parse_subject_body,
    calculate_email_cost,
    generate_single_email,
    run_batch_generation,
    STARTER_TEMPLATES,
)


class TestBuildVariables:
    def test_full_person_and_company(self):
        person = Person(
            first_name="John", last_name="Doe", title="CEO",
            company_name="Acme Corp",
        )
        company = Company(
            name="Acme Corp", industry="Manufacturing",
            employee_count=50, city="Austin", state="TX",
            country="US", description="Makes widgets",
            founded_year=1990, icp_score=85,
        )
        variables = _build_variables(person, company)
        assert variables["first_name"] == "John"
        assert variables["last_name"] == "Doe"
        assert variables["title"] == "CEO"
        assert variables["company_name"] == "Acme Corp"
        assert variables["industry"] == "Manufacturing"
        assert variables["employee_count"] == "50"
        assert variables["city"] == "Austin"
        assert variables["state"] == "TX"
        assert variables["country"] == "US"
        assert variables["description"] == "Makes widgets"
        assert variables["founded_year"] == "1990"
        assert variables["icp_score"] == "85"
        assert variables["quality_tier"] == "Gold"

    def test_none_fields_fallback_to_empty(self):
        person = Person(first_name="Jane", last_name="Doe")
        variables = _build_variables(person, None)
        assert variables["title"] == ""
        assert variables["company_name"] == ""
        assert variables["industry"] == ""
        assert variables["quality_tier"] == "Unknown"


class TestSubstituteVariables:
    def test_replaces_known_variables(self):
        template = "Hi {first_name}, I see you work at {company_name}."
        variables = {"first_name": "John", "company_name": "Acme"}
        result = _substitute_variables(template, variables)
        assert result == "Hi John, I see you work at Acme."

    def test_leaves_unknown_variables(self):
        template = "Hi {first_name}, your {unknown_var} is great."
        variables = {"first_name": "John"}
        result = _substitute_variables(template, variables)
        assert result == "Hi John, your {unknown_var} is great."

    def test_empty_template(self):
        assert _substitute_variables("", {}) == ""


class TestScoreToTier:
    def test_gold(self):
        assert _score_to_tier(80) == "Gold"
        assert _score_to_tier(100) == "Gold"

    def test_silver(self):
        assert _score_to_tier(60) == "Silver"
        assert _score_to_tier(79) == "Silver"

    def test_bronze(self):
        assert _score_to_tier(0) == "Bronze"
        assert _score_to_tier(59) == "Bronze"

    def test_unknown(self):
        assert _score_to_tier(None) == "Unknown"


class TestParseSubjectBody:
    def test_standard_format(self):
        text = "Subject: Hello World\n\nThis is the body of the email."
        subject, body = _parse_subject_body(text)
        assert subject == "Hello World"
        assert body == "This is the body of the email."

    def test_fallback_no_subject_prefix(self):
        text = "Hello World\n\nThis is the body."
        subject, body = _parse_subject_body(text)
        assert subject == "Hello World"
        assert body == "This is the body."

    def test_multiline_body(self):
        text = "Subject: Test\n\nLine 1\nLine 2\nLine 3"
        subject, body = _parse_subject_body(text)
        assert subject == "Test"
        assert "Line 1" in body
        assert "Line 3" in body


class TestCalculateEmailCost:
    def test_basic_calculation(self):
        # 1000 input tokens, 500 output tokens
        # Input: 1000/1M * $1.00 = $0.001
        # Output: 500/1M * $5.00 = $0.0025
        cost = calculate_email_cost(1000, 500)
        assert abs(cost - 0.0035) < 1e-10

    def test_zero_tokens(self):
        assert calculate_email_cost(0, 0) == 0.0


def _mock_anthropic_response(text: str = "Subject: Test Subject\n\nTest body text.",
                              input_tokens: int = 100, output_tokens: int = 200):
    """Create a mock Anthropic message response."""
    mock_content = MagicMock()
    mock_content.text = text

    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens

    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_message.usage = mock_usage
    return mock_message


class TestGenerateSingleEmail:
    def test_successful_generation(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()

        template = EmailTemplate(
            name="Test", system_prompt="You are a writer.",
            user_prompt_template="Write to {first_name} at {company_name}.",
        )
        person = Person(first_name="John", last_name="Doe", company_name="Acme")
        company = Company(name="Acme", industry="Tech")

        result = generate_single_email(
            client=mock_client,
            template=template,
            person=person,
            company=company,
            campaign_id="camp-1",
        )
        assert isinstance(result, GeneratedEmail)
        assert result.subject == "Test Subject"
        assert result.body == "Test body text."
        assert result.status == "draft"
        assert result.campaign_id == "camp-1"
        assert result.input_tokens == 100
        assert result.output_tokens == 200
        assert result.cost_usd > 0

        # Verify client was called with correct params
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5"
        assert call_kwargs.kwargs["max_tokens"] == 512

    def test_api_error_returns_failed(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")

        template = EmailTemplate(
            name="Test", system_prompt="sys",
            user_prompt_template="Write to {first_name}.",
        )
        person = Person(first_name="John", last_name="Doe")

        result = generate_single_email(
            client=mock_client,
            template=template,
            person=person,
            company=None,
            campaign_id="camp-1",
        )
        assert result.status == "failed"
        assert "API Error" in result.body


class TestBatchGeneration:
    def test_processes_all_contacts(self, db):
        camp = _make_campaign(db, "camp-batch")
        p1 = _make_person(db, "bp1", "bp1@test.com")
        p2 = _make_person(db, "bp2", "bp2@test.com")

        with patch("data.email_engine.anthropic") as mock_anthropic_mod:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _mock_anthropic_response()
            mock_anthropic_mod.Anthropic.return_value = mock_client

            # Seed a template first
            run_sync(db.seed_default_templates())
            templates = run_sync(db.get_email_templates())
            template_id = templates[0].id

            run_batch_generation(
                campaign_id=camp.id,
                template_id=template_id,
                person_ids=[p1.id, p2.id],
                db_path=db.db_path,
                api_key="test-key",
            )

        emails = run_sync(db.get_generated_emails(camp.id))
        assert len(emails) == 2


class TestStarterTemplates:
    def test_three_templates(self):
        assert len(STARTER_TEMPLATES) == 3

    def test_template_names(self):
        names = {t.name for t in STARTER_TEMPLATES}
        assert "Consultative Intro" in names
        assert "Case Study Follow-up" in names
        assert "Breakup" in names

    def test_sequence_steps(self):
        steps = {t.name: t.sequence_step for t in STARTER_TEMPLATES}
        assert steps["Consultative Intro"] == 1
        assert steps["Case Study Follow-up"] == 2
        assert steps["Breakup"] == 3
