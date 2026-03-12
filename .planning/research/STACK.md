# Stack Research: v2.0 New Capabilities

**Domain:** B2B prospecting platform -- Salesforce integration, AI email generation, company sourcing
**Researched:** 2026-03-07
**Confidence:** HIGH (Anthropic SDK, Jinja2), MEDIUM (aiosalesforce vs simple-salesforce decision)

---

## Context

This is a subsequent-milestone research file for v2.0. The existing stack (Python 3.11+, httpx 0.27+, Pydantic v2, SQLite WAL, Streamlit, Typer, aiosqlite, aiometer, tenacity, respx) is deployed and validated in v1.0. This document covers only the **additions** needed for three new capabilities:

1. **Salesforce integration** -- read-only Account/Contact dedup checking
2. **AI email generation** -- personalized cold emails from enriched data
3. **Multi-source company sourcing** -- Apollo search, CSV import, manual add

---

## Recommended Stack Additions

### 1. Salesforce Integration: simple-salesforce

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `simple-salesforce` | >=1.12.9 | Salesforce REST API client for SOQL queries | Most mature Python Salesforce library. 5K+ GitHub stars, actively maintained (Aug 2025 release). Handles OAuth2 username/password + security token flow, SOQL queries, and session management out of the box. |

**Why simple-salesforce over alternatives:**

Our Salesforce use case is narrow: run 2-3 SOQL queries per batch to check if Accounts (by domain) or Contacts (by email) already exist. This is a pre-enrichment step, not in the hot async loop.

- **simple-salesforce** is synchronous (uses `requests` internally, not httpx). This is acceptable because Salesforce checks happen once per batch, not per-row. If async is ever needed, wrap with `asyncio.to_thread()`.
- **aiosalesforce (v0.6.2)** uses httpx natively and is fully async -- a better architectural fit. However: only 16 GitHub stars, last release June 2024, tiny community. For a production tool handling real Salesforce data, the maturity gap is a risk. If aiosalesforce reaches 1.0 with broader adoption, reconsider.
- **Direct httpx calls** to the Salesforce REST API avoids all dependencies but requires implementing the OAuth2 token lifecycle (obtain, refresh, retry on 401) manually. Not worth the effort for 3 SOQL queries.

**Key tradeoff:** simple-salesforce pulls in `requests` as a transitive dependency. The codebase uses httpx everywhere else. This is acceptable because the Salesforce client is isolated (not shared with enrichment providers) and low-frequency. Do NOT use `requests` anywhere else.

**Integration pattern:**
```python
from simple_salesforce import Salesforce

sf = Salesforce(
    username=settings.sf_username,
    password=settings.sf_password,
    security_token=settings.sf_security_token,
    domain="login"  # or "test" for sandbox
)

# Check if account exists by domain
results = sf.query(
    "SELECT Id, Name FROM Account WHERE Website LIKE '%example.com%'"
)

# Check if contact exists by email
results = sf.query(
    "SELECT Id, Email, AccountId FROM Contact WHERE Email = 'john@example.com'"
)
```

**SOQL queries needed for dedup:**
```sql
-- Batch check: find accounts by website domain (batch of domains)
SELECT Id, Name, Website FROM Account
WHERE Website IN ('example.com', 'acme.com', ...)

-- Batch check: find contacts by email
SELECT Id, Email, FirstName, LastName, AccountId FROM Contact
WHERE Email IN ('john@example.com', 'jane@acme.com', ...)
```

Use SOQL `IN` clauses to batch-check up to ~200 values per query (Salesforce SOQL limit is ~20K characters per query). For larger batches, chunk into multiple queries.

---

### 2. AI Email Generation: anthropic SDK

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `anthropic` | >=0.84.0 | Claude API SDK for personalized email generation | Uses httpx internally (requires httpx >=0.25.0, <1) -- aligns with existing stack. Provides both sync and async clients. Full Pydantic v2 typing for request/response. Claude excels at structured text generation with lower hallucination rates, critical for B2B outreach referencing real company data. |

**Why Claude (Anthropic) over OpenAI:**

- **Accuracy over creativity** -- Cold emails reference specific company details (revenue, employee count, industry, recent news). Claude hallucinates less on factual data than GPT models. For B2B outreach, a fabricated fact about a prospect's company destroys credibility.
- **httpx alignment** -- Anthropic SDK uses httpx.AsyncClient internally. No new HTTP client dependency. OpenAI SDK also uses httpx, so this is neutral.
- **Cost** -- Claude 3.5 Haiku (~$0.25/1M input, ~$1.25/1M output tokens) is ideal for email generation. A typical cold email prompt is ~500 tokens in, ~300 tokens out = ~$0.0005/email. At 10K emails/month = ~$5/month. Reserve Sonnet for complex personalization if Haiku output quality is insufficient.

**Why SDK over raw httpx calls:**

The SDK handles auth headers, retry on rate limits, token counting, streaming, and typed responses. Rolling our own would duplicate functionality for zero benefit. The SDK is a single `pip install` with no heavy transitive dependencies beyond httpx.

**Integration pattern:**
```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

async def generate_email(contact: dict, company: dict, template: str) -> str:
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system="You write professional B2B cold emails. Be concise, specific, and value-focused.",
        messages=[{
            "role": "user",
            "content": f"Write a cold email using this template structure:\n{template}\n\n"
                       f"Contact: {contact['first_name']} {contact['last_name']}, "
                       f"{contact['title']} at {company['name']}\n"
                       f"Company: {company['industry']}, {company['employees']} employees, "
                       f"${company['revenue']}M revenue\n"
                       f"Value prop: [your product value here]"
        }]
    )
    return message.content[0].text
```

**Rate limiting:** Use existing `aiometer` to cap concurrent Claude API calls (e.g., `max_at_once=5, max_per_second=2`). Claude Haiku supports high throughput but respect the API rate limits.

**Caching:** Cache generated emails in SQLite keyed by (contact_id, template_hash, model). Avoid re-generating identical emails if enrichment data hasn't changed.

---

### 3. Email Templating: jinja2 (already installed)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `jinja2` | >=3.1 | Template engine for email structure | Already a transitive dependency of Streamlit -- zero new dependency weight. Industry standard for Python templating. Separates email structure (template) from AI-generated personalization. |

**Why Jinja2 matters for this feature:**

The email generation workflow has two layers:
1. **Template** (Jinja2) -- Defines the structure: greeting, opening hook, value proposition, CTA, signature. Users create/edit templates without touching AI prompts.
2. **Personalization** (Claude) -- AI fills in the personalized content within each template section based on enriched company/contact data.

This separation means users can A/B test email structures without re-engineering prompts, and the AI output is constrained to specific sections rather than generating unbounded free-form text.

**Template example:**
```
Subject: {{ subject_line }}

Hi {{ first_name }},

{{ opening_hook }}

{{ value_proposition }}

{{ call_to_action }}

Best,
{{ sender_name }}
{{ sender_title }}
```

---

### 4. Multi-Source Company Sourcing: No New Dependencies

**No new libraries needed.** Company sourcing uses existing capabilities:

| Source | Implementation | Status |
|--------|---------------|--------|
| Apollo company search | `providers/apollo.py` already has `search_companies()` abstract method | Extend existing provider |
| CSV/Excel import | Existing CSV pipeline with fuzzy column mapping | Reuse as-is |
| Manual company add | Streamlit form -> SQLite | Build with existing UI framework |

The `BaseProvider.search_companies(**filters)` abstract method already exists in `providers/base.py` (line 92). Apollo's implementation needs to be built out and connected to the UI/CLI, but this is application code, not a dependency question.

---

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jinja2` | >=3.1 | Email template rendering | Always -- already installed via Streamlit |

No other supporting libraries needed. The existing stack (aiometer for rate limiting, tenacity for retries, aiosqlite for async DB) covers all infrastructure needs.

---

## Installation

```bash
# New v2.0 dependencies only (2 packages)
pip install simple-salesforce>=1.12.9
pip install anthropic>=0.84.0
# jinja2 already installed via streamlit -- no action needed
```

Add to `pyproject.toml` dependencies array:
```toml
"simple-salesforce>=1.12.9",
"anthropic>=0.84.0",
```

**Total new direct dependencies: 2.** This is deliberately minimal.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `simple-salesforce` | `aiosalesforce` >=0.6.2 | If Salesforce checks move into the per-row async enrichment loop (high-frequency). Currently batch pre-check is sufficient. Revisit when aiosalesforce reaches broader adoption (100+ stars, 1.0 release). |
| `simple-salesforce` | Direct httpx to SF REST API | If simple-salesforce causes dependency conflicts with httpx or `requests` versioning. Only worth the OAuth2 implementation effort if conflicts arise. |
| `anthropic` SDK | `openai` SDK | If using GPT models. OpenAI SDK also uses httpx internally. Switch is trivial -- similar interface pattern. Choose based on output quality testing with real email samples. |
| `anthropic` SDK | `litellm` | If you need to support multiple LLM providers behind one interface (Claude + GPT + Gemini). Adds a dependency layer. Only justified if the team wants provider-switching without code changes. |
| Claude 3.5 Haiku | Claude 3.5 Sonnet | For emails requiring deeper company research synthesis. Haiku is ~10x cheaper and sufficient for most templated cold emails. Test with real data before upgrading. |
| Jinja2 templates | Python f-strings | Never. F-strings mix logic and presentation, aren't user-editable, and can't be stored/versioned as template files. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `langchain` | Massive dependency tree (100+ transitive packages). Extreme overkill for single-prompt email generation. Adds abstraction layers that obscure what's actually happening. | Direct `anthropic` SDK -- one `messages.create()` call per email. |
| `llama-index` | RAG framework. We already have structured company data in SQLite -- no document retrieval or vector search needed. | Direct SOQL queries for SF data + direct SQLite queries for enrichment data. |
| `salesforce-bulk` | Bulk API is for large data loading (10K+ records). We only read a few hundred Account/Contact records per batch. | `simple-salesforce` SOQL queries. |
| `requests` (explicitly) | simple-salesforce brings it as a transitive dependency. Do NOT add it to `requirements.txt` directly -- it creates confusion about which HTTP client to use. | Let `requests` come in only via simple-salesforce. All other HTTP calls use httpx. |
| `celery` / `dramatiq` | Task queue requires a broker (Redis/RabbitMQ). Overkill for email generation batches. | Existing `aiometer` + async pattern handles concurrency. |
| `redis` | No distributed caching or queuing needed at team-scale. | SQLite caching (already working). |
| `mail-parser` / `email-validator` | We generate emails, we don't parse or validate inbound mail. Email format validation is already handled by Pydantic email validators. | `pydantic[email]` (already installed). |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `anthropic >=0.84.0` | `httpx >=0.25.0, <1` | Our httpx >=0.27 is within range. No conflict. |
| `anthropic >=0.84.0` | `pydantic >=2.0` | SDK uses Pydantic v2 internally. Compatible with our v2 usage. |
| `anthropic >=0.84.0` | Python >=3.9 | We require 3.11+. No issue. |
| `simple-salesforce >=1.12.9` | Python 3.9-3.13 | Compatible with our 3.11+ requirement. |
| `simple-salesforce >=1.12.9` | `requests` (transitive) | Isolated from our httpx stack. No version conflict expected. |
| `jinja2 >=3.1` | `streamlit >=1.37` | Already a Streamlit dependency. No version conflict. |

---

## Configuration Requirements

New environment variables for `.env`:

```bash
# Salesforce (read-only access)
SALESFORCE_USERNAME=user@company.com
SALESFORCE_PASSWORD=password
SALESFORCE_SECURITY_TOKEN=token
SALESFORCE_DOMAIN=login          # "login" for production, "test" for sandbox

# AI Email Generation
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-haiku-20241022   # default model, overridable per-campaign
```

Add to `config/settings.py` as Pydantic settings fields with validation.

---

## Integration Architecture Notes

### Where new modules live (not under providers/):

The Salesforce client and AI email generator are NOT enrichment providers. They don't follow the waterfall pattern and shouldn't implement `BaseProvider`. Create a new `integrations/` package:

```
integrations/
    __init__.py
    salesforce.py     # SF client singleton, SOQL query helpers, dedup logic
    ai_email.py       # AsyncAnthropic wrapper, template loading, email generation
templates/
    emails/
        default.j2    # Default cold email template
        follow_up.j2  # Follow-up template
```

1. **`integrations/salesforce.py`** -- Singleton `Salesforce` client. Exposes `check_accounts(domains: list[str]) -> dict[str, SFAccount]` and `check_contacts(emails: list[str]) -> dict[str, SFContact]`. Called once per batch before enrichment starts.

2. **`integrations/ai_email.py`** -- Uses `AsyncAnthropic` client. Exposes `generate_emails(contacts: list[dict], template: str) -> list[GeneratedEmail]`. Rate-limited via aiometer. Results cached in SQLite by (contact_id, template_hash).

3. **`templates/emails/`** -- Jinja2 template files. Loaded via `jinja2.FileSystemLoader`. Users add/edit templates without code changes.

4. **Company sourcing** -- Extend existing `providers/apollo.py` search implementation and wire to new Streamlit pages and CLI commands. No new module needed.

---

## Cost Estimates for New Dependencies

| Capability | Per-Unit Cost | Monthly (10K contacts) | Notes |
|------------|--------------|----------------------|-------|
| Salesforce API | $0 | $0 | REST API included in all Salesforce editions. No per-call cost. |
| Claude 3.5 Haiku emails | ~$0.0005/email | ~$5 | ~500 tokens in, ~300 tokens out per email |
| Claude 3.5 Sonnet emails | ~$0.005/email | ~$50 | 10x Haiku cost. Use only if Haiku quality insufficient. |

Combined with existing enrichment costs (~$466/mo for 10K contacts), v2.0 adds negligible cost (~$5/mo for AI emails).

---

## Sources

- [simple-salesforce PyPI](https://pypi.org/project/simple-salesforce/) -- version 1.12.9, released Aug 2025, HIGH confidence
- [simple-salesforce GitHub](https://github.com/simple-salesforce/simple-salesforce) -- 5K+ stars, active maintenance, HIGH confidence
- [simple-salesforce docs](https://simple-salesforce.readthedocs.io/) -- SOQL query patterns, authentication, HIGH confidence
- [aiosalesforce GitHub](https://github.com/georgebv/aiosalesforce) -- v0.6.2, 16 stars, httpx-native async, MEDIUM confidence (low adoption)
- [aiosalesforce PyPI](https://pypi.org/project/aiosalesforce/) -- Python 3.11+, httpx + orjson deps, MEDIUM confidence
- [anthropic PyPI](https://pypi.org/project/anthropic/) -- version 0.84.0, Feb 2026, HIGH confidence
- [anthropic-sdk-python GitHub](https://github.com/anthropics/anthropic-sdk-python) -- httpx.AsyncClient internally, HIGH confidence
- [Anthropic Python SDK docs](https://platform.claude.com/docs/en/api/sdks/python) -- official API reference, HIGH confidence
- [Salesforce SOQL reference](https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_soql_select_examples.htm) -- query syntax, HIGH confidence

---
*Stack research for: Clay-Dupe v2.0 -- Salesforce integration, AI email generation, company sourcing*
*Researched: 2026-03-07*
