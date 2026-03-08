"""Email generation engine — variable substitution, single/batch generation, cost tracking.

Uses Anthropic Claude Haiku 4.5 for email generation with prompt caching
on the system prompt for cost efficiency.
"""
from __future__ import annotations

from data.models import EmailTemplate


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
