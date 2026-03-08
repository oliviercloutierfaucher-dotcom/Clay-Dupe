"""Email generation engine — variable substitution, single/batch generation, cost tracking.

Uses Anthropic Claude Haiku 4.5 for email generation with prompt caching
on the system prompt for cost efficiency.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from data.models import EmailTemplate, GeneratedEmail, Person, Company

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HAIKU_INPUT_PRICE_PER_MTOK = 1.00   # $1.00 per million input tokens
HAIKU_OUTPUT_PRICE_PER_MTOK = 5.00  # $5.00 per million output tokens

BATCH_DELAY_SECONDS = 1.2  # Delay between API calls for rate limit safety


# ---------------------------------------------------------------------------
# Variable Substitution
# ---------------------------------------------------------------------------

def _build_variables(person: Person, company: Optional[Company]) -> dict[str, str]:
    """Build variable dict from Person + Company models."""
    comp_name = ""
    industry = ""
    employee_count = ""
    city = ""
    state = ""
    country = ""
    description = ""
    founded_year = ""
    icp_score = ""
    quality_tier = "Unknown"

    if company is not None:
        comp_name = company.name or person.company_name or ""
        industry = company.industry or ""
        employee_count = str(company.employee_count) if company.employee_count is not None else ""
        city = company.city or ""
        state = company.state or ""
        country = company.country or ""
        description = company.description or ""
        founded_year = str(company.founded_year) if company.founded_year is not None else ""
        icp_score = str(company.icp_score) if company.icp_score is not None else ""
        quality_tier = _score_to_tier(company.icp_score)
    else:
        comp_name = person.company_name or ""

    return {
        "first_name": person.first_name or "",
        "last_name": person.last_name or "",
        "title": person.title or "",
        "company_name": comp_name,
        "industry": industry,
        "employee_count": employee_count,
        "city": city,
        "state": state,
        "country": country,
        "description": description,
        "founded_year": founded_year,
        "icp_score": icp_score,
        "quality_tier": quality_tier,
    }


def _score_to_tier(score: Optional[int]) -> str:
    """Convert ICP score to quality tier label."""
    if score is None:
        return "Unknown"
    if score >= 80:
        return "Gold"
    if score >= 60:
        return "Silver"
    return "Bronze"


def _substitute_variables(template: str, variables: dict[str, str]) -> str:
    """Replace {variable} placeholders. Unknown variables left as-is."""
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))
    return re.sub(r"\{(\w+)\}", replacer, template)


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------

def _parse_subject_body(response_text: str) -> tuple[str, str]:
    """Parse 'Subject: [subject]\\n\\n[body]' format from Claude's response.

    Fallback: if no 'Subject:' prefix, use first line as subject, rest as body.
    """
    text = response_text.strip()

    if text.startswith("Subject:"):
        # Split on first double newline
        parts = text.split("\n\n", 1)
        subject_line = parts[0].replace("Subject:", "", 1).strip()
        body = parts[1].strip() if len(parts) > 1 else ""
        return subject_line, body

    # Fallback: first line = subject, rest = body
    lines = text.split("\n\n", 1)
    subject = lines[0].strip()
    body = lines[1].strip() if len(lines) > 1 else ""
    return subject, body


# ---------------------------------------------------------------------------
# Cost Calculation
# ---------------------------------------------------------------------------

def calculate_email_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a single email generation (Haiku 4.5 pricing)."""
    input_cost = (input_tokens / 1_000_000) * HAIKU_INPUT_PRICE_PER_MTOK
    output_cost = (output_tokens / 1_000_000) * HAIKU_OUTPUT_PRICE_PER_MTOK
    return input_cost + output_cost


# ---------------------------------------------------------------------------
# Single Email Generation
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _call_anthropic(client: anthropic.Anthropic, system_prompt: str, user_prompt: str):
    """Make a retryable Anthropic API call with prompt caching."""
    return client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )


def generate_single_email(
    client: anthropic.Anthropic,
    template: EmailTemplate,
    person: Person,
    company: Optional[Company],
    campaign_id: str,
    user_note: Optional[str] = None,
) -> GeneratedEmail:
    """Generate a single email using Claude Haiku 4.5.

    On exception: returns a GeneratedEmail with status='failed' and error in body.
    """
    try:
        variables = _build_variables(person, company)
        user_prompt = _substitute_variables(template.user_prompt_template, variables)

        if user_note:
            user_prompt += f"\n\nAdditional instruction: {user_note}"

        message = _call_anthropic(client, template.system_prompt, user_prompt)

        response_text = message.content[0].text
        subject, body = _parse_subject_body(response_text)

        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        cost = calculate_email_cost(input_tokens, output_tokens)

        return GeneratedEmail(
            campaign_id=campaign_id,
            template_id=template.id,
            person_id=person.id,
            company_id=company.id if company else None,
            sequence_step=template.sequence_step,
            subject=subject,
            body=body,
            status="draft",
            user_note=user_note,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
    except Exception as exc:
        logger.error("Email generation failed for person %s: %s", person.id, exc)
        return GeneratedEmail(
            campaign_id=campaign_id,
            template_id=template.id,
            person_id=person.id,
            company_id=company.id if company else None,
            sequence_step=template.sequence_step,
            subject=None,
            body=str(exc),
            status="failed",
        )


# ---------------------------------------------------------------------------
# Batch Generation (background thread target)
# ---------------------------------------------------------------------------

def run_batch_generation(
    campaign_id: str,
    template_id: str,
    person_ids: list[str],
    db_path: str,
    api_key: str,
) -> None:
    """Run batch email generation in a background thread.

    Creates a new Database instance for thread safety. Processes contacts
    sequentially with a delay between API calls.

    This function is the target for ``threading.Thread(target=run_batch_generation, ...)``.
    """
    from data.database import Database

    client = anthropic.Anthropic(api_key=api_key)
    bg_db = Database(db_path=db_path)

    template = asyncio.run(bg_db.get_email_template(template_id))
    if template is None:
        logger.error("Template not found: %s", template_id)
        return

    for i, person_id in enumerate(person_ids):
        try:
            person, company = asyncio.run(bg_db.get_person_with_company(person_id))

            email = generate_single_email(
                client=client,
                template=template,
                person=person,
                company=company,
                campaign_id=campaign_id,
            )
            asyncio.run(bg_db.save_generated_email(email))

        except Exception as exc:
            logger.error("Batch generation error for person %s: %s", person_id, exc)
            failed_email = GeneratedEmail(
                campaign_id=campaign_id,
                template_id=template_id,
                person_id=person_id,
                status="failed",
                body=str(exc),
            )
            asyncio.run(bg_db.save_generated_email(failed_email))

        # Rate limit delay between calls (skip after last)
        if i < len(person_ids) - 1:
            time.sleep(BATCH_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# Starter Templates
# ---------------------------------------------------------------------------

STARTER_TEMPLATES: list[EmailTemplate] = [
    EmailTemplate(
        name="Consultative Intro",
        description="First touch - value proposition focused on their specific challenges",
        system_prompt=(
            "You are a B2B sales email writer specializing in niche manufacturing. "
            "Write consultative, professional cold emails for CEOs/Owners of small manufacturers. "
            "Tone: warm, knowledgeable, peer-to-peer (not salesy). "
            "Structure: 1) Personalized opener referencing their company, "
            "2) One specific challenge they likely face, "
            "3) How you solve it (one sentence), "
            "4) Soft CTA (ask a question, not demand a meeting). "
            "STRICT: Maximum 120 words. No jargon. No exclamation marks. "
            "Output format: Subject: [subject line]\n\n[email body]"
        ),
        user_prompt_template=(
            "Write a cold intro email to {first_name} {last_name}, "
            "{title} at {company_name}. "
            "Company details: {industry} manufacturer, ~{employee_count} employees, "
            "located in {city}, {state}. {description}"
        ),
        sequence_step=1,
        is_default=True,
    ),
    EmailTemplate(
        name="Case Study Follow-up",
        description="Second touch - social proof with relevant case study reference",
        system_prompt=(
            "You are following up on a cold email to a small manufacturer CEO/Owner. "
            "This is email 2 of 3. They did NOT reply to the intro email. "
            "Reference a relevant (fictional but realistic) case study of a similar company. "
            "Tone: helpful, not pushy. Show you understand their world. "
            "Structure: 1) Brief reference to prior email (one line), "
            "2) Case study: similar company, specific result, "
            "3) Bridge to their situation, "
            "4) Easy CTA (reply with one word, or 15-min call). "
            "STRICT: Maximum 120 words. "
            "Output format: Subject: [subject line]\n\n[email body]"
        ),
        user_prompt_template=(
            "Write follow-up email #2 to {first_name} {last_name}, "
            "{title} at {company_name} ({industry}, {employee_count} employees, "
            "{city}, {state}). Quality tier: {quality_tier}."
        ),
        sequence_step=2,
        is_default=True,
    ),
    EmailTemplate(
        name="Breakup",
        description="Final touch - closing the loop with a low-pressure exit",
        system_prompt=(
            "You are writing the final email in a 3-email cold sequence to a small manufacturer CEO/Owner. "
            "They haven't replied to 2 prior emails. This is the 'breakup' email. "
            "Tone: respectful, brief, no guilt-tripping. "
            "Structure: 1) Acknowledge they're busy (one line), "
            "2) Restate the core value prop (one line), "
            "3) Give them an easy out ('no worries if the timing isn't right'), "
            "4) Leave door open ('feel free to reach out anytime'). "
            "STRICT: Maximum 80 words (shorter than other emails). "
            "Output format: Subject: [subject line]\n\n[email body]"
        ),
        user_prompt_template=(
            "Write breakup email #3 to {first_name} at {company_name} ({industry})."
        ),
        sequence_step=3,
        is_default=True,
    ),
]
