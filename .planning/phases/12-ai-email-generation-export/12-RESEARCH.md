# Phase 12: AI Email Generation + Export - Research

**Researched:** 2026-03-08
**Domain:** Anthropic Claude API integration, email generation, CSV export
**Confidence:** HIGH

## Summary

Phase 12 adds AI-powered cold email generation using Claude Haiku 4.5 via the Anthropic Python SDK. The architecture follows the project's established patterns: Pydantic models for data, SQLite for persistence, background threading for batch operations, `@st.fragment(run_every=2)` for progress polling, and `st.download_button()` for exports. Two new database tables (`email_templates` and `generated_emails`) store templates and generated content. A new Streamlit page (`ui/pages/emails.py`) provides the full workflow: select campaign, choose template, generate, preview/edit, approve/reject, and export.

The Anthropic SDK (`anthropic>=0.40`) provides a straightforward `client.messages.create()` API. For the expected volumes (hundreds to low thousands of emails per batch), sequential calls with a simple threading.Thread background worker are sufficient. The Batch API (50% discount, up to 24h processing) is an option but adds complexity for marginal cost savings at this scale -- Claude Haiku 4.5 is already very cheap at $1/MTok input and $5/MTok output ($0.50/$2.50 with batch). Prompt caching on the system prompt (shared across all emails in a batch) provides 90% input savings on the cached portion, which is the bigger win.

**Primary recommendation:** Use sequential `client.messages.create()` calls with prompt caching on system prompt, running in a background `threading.Thread` with the established polling fragment pattern. Add `anthropic>=0.40` to dependencies. Store templates and generated emails in SQLite. Export as CSV via pandas DataFrame + `st.download_button()`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Email Tone & Cadence**: Consultative tone default. 3-step sequence (Intro, Follow-up, Breakup). 120 words max per email. CAN-SPAM/CASL compliance placeholders.
- **Template & Variable System**: Global templates (not per-campaign). 3 pre-built starters. `{variable}` syntax. Templates stored in SQLite (`email_templates` table). Model: Claude Haiku 4.5 (`claude-haiku-4-5`).
- **Preview & Approval Workflow**: New page `ui/pages/emails.py` in Tools navigation section. Flow: Select campaign > Choose template > Generate > Preview > Edit > Approve/Reject > Export. Table view with Status column (draft/approved/rejected). Inline edit of subject and body. Bulk actions (Approve All, Reject All, Regenerate Selected). Regenerate with optional user note.
- **Export Format & Destination**: Three presets -- Outreach.io CSV, Salesforce Lead CSV, Raw CSV. Outreach columns: Email, First Name, Last Name, Company, Subject, Body, Sequence Step. Salesforce columns: Company, Website, Quality__c, FirstName, LastName, Title, Email, City, State, Country. Each sequence step = separate row.

### Claude's Discretion
- Exact prompt engineering for each starter template
- Batch processing chunk size and concurrency
- How to handle generation failures (retry logic, partial results)
- Email subject line generation approach
- Loading skeleton / progress UI specifics
- Whether to use Anthropic Batch API or sequential calls

### Deferred Ideas (OUT OF SCOPE)
- Multi-model support (Sonnet for Gold tier, Haiku for rest)
- A/B testing email variants
- Email sending from platform
- Outreach.io API integration (OUT-01)
- Cost-per-lead tracking across full pipeline (EMAIL-08)
- Multiple saved prompt template libraries (EMAIL-07)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EMAIL-01 | User can generate personalized cold emails from enriched contact/company data | Anthropic SDK `client.messages.create()` with system prompt + user prompt variable substitution. Person/Company models already have all needed fields. |
| EMAIL-02 | User can create and edit email prompt templates with variable substitution | New `email_templates` SQLite table with system_prompt, user_prompt_template, and `{variable}` placeholders. CRUD via Database class. |
| EMAIL-03 | User can batch-generate emails for an entire campaign | Background `threading.Thread` with sequential API calls. Progress tracking via `generated_emails` table status updates + `@st.fragment(run_every=2)` polling. |
| EMAIL-04 | User can preview and edit generated emails before export | Streamlit `st.data_editor` or manual `st.text_area`/`st.text_input` for inline editing. Status workflow: draft > approved/rejected. |
| EMAIL-05 | User can export emails as Outreach.io-ready CSV | pandas DataFrame with Outreach.io column mapping + `st.download_button()`. Three export presets. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | >=0.40 | Claude API client | Official Anthropic Python SDK. Stable, well-documented `client.messages.create()` API. |
| streamlit | >=1.37 | UI framework | Already in use. Provides `st.download_button()`, `st.data_editor`, `@st.fragment`. |
| pandas | >=2.0 | Data manipulation & CSV export | Already in use. DataFrame to CSV/Excel conversion for exports. |
| pydantic | >=2.0 | Data models | Already in use. New EmailTemplate and GeneratedEmail models. |
| aiosqlite | >=0.20 | Database access | Already in use. New tables for templates and generated emails. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | >=8.2 | Retry logic | Already in use. Wrap API calls with retry on transient failures (rate limits, network errors). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sequential API calls | Anthropic Batch API | 50% cost savings but up to 24h latency. At Haiku pricing ($1/MTok input), 3,000 emails costs ~$2-4. Not worth the complexity for sub-$5 batches. |
| Claude Haiku 4.5 | Claude Haiku 3.5 | Haiku 3.5 is 20% cheaper ($0.80 vs $1.00/MTok input) but user locked decision on Haiku 4.5. |

**Installation:**
```bash
pip install "anthropic>=0.40"
```

Add to `requirements.txt` and `pyproject.toml` dependencies.

## Architecture Patterns

### Recommended Project Structure
```
data/
  models.py            # Add EmailTemplate, GeneratedEmail models
  schema.sql           # Add email_templates, generated_emails tables
  database.py          # Add CRUD methods for templates and emails
config/
  settings.py          # Add ANTHROPIC_API_KEY env var loading
ui/
  pages/
    emails.py          # New page: email generation + export workflow
  app.py               # Add emails.py to Tools navigation
```

### Pattern 1: Background Email Generation (Reuse Enrich Pattern)
**What:** Run email generation in a daemon thread with progress polling
**When to use:** Batch generation of 10+ emails
**Example:**
```python
# Source: Existing pattern from ui/pages/enrich.py

def _run_email_generation_bg(
    campaign_id: str,
    template_id: str,
    contact_ids: list[str],
    db_path: str,
    api_key: str,
) -> None:
    """Background thread for batch email generation."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    bg_db = Database(db_path=db_path)

    # Load template
    template = asyncio.run(bg_db.get_email_template(template_id))

    for contact_id in contact_ids:
        try:
            # Load contact + company data
            person, company = asyncio.run(bg_db.get_person_with_company(contact_id))

            # Substitute variables in user prompt
            variables = _build_variables(person, company)
            user_prompt = _substitute_variables(template.user_prompt_template, variables)

            # Call Claude
            message = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=512,
                system=template.system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            body = message.content[0].text

            # Save generated email
            asyncio.run(bg_db.save_generated_email(...))
        except Exception:
            asyncio.run(bg_db.save_generated_email(status="failed", ...))

# Launch from Streamlit:
thread = threading.Thread(
    target=_run_email_generation_bg,
    args=(campaign_id, template_id, contact_ids, db.db_path, api_key),
    daemon=True,
)
thread.start()
```

### Pattern 2: Variable Substitution
**What:** Replace `{variable}` placeholders in templates with actual data
**When to use:** Before sending prompt to Claude
**Example:**
```python
import re

def _build_variables(person: Person, company: Company) -> dict[str, str]:
    """Build variable dict from Person + Company models."""
    return {
        "first_name": person.first_name or "",
        "last_name": person.last_name or "",
        "title": person.title or "",
        "company_name": company.name or person.company_name or "",
        "industry": company.industry or "",
        "employee_count": str(company.employee_count or ""),
        "city": company.city or "",
        "state": company.state or "",
        "country": company.country or "",
        "description": company.description or "",
        "founded_year": str(company.founded_year or ""),
        "icp_score": str(company.icp_score or ""),
        "quality_tier": _score_to_tier(company.icp_score),
    }

def _score_to_tier(score: int | None) -> str:
    if score is None:
        return "Unknown"
    if score >= 80:
        return "Gold"
    if score >= 60:
        return "Silver"
    return "Bronze"

def _substitute_variables(template: str, variables: dict[str, str]) -> str:
    """Replace {variable} placeholders. Unknown variables left as-is."""
    def replacer(match):
        key = match.group(1)
        return variables.get(key, match.group(0))
    return re.sub(r"\{(\w+)\}", replacer, template)
```

### Pattern 3: Prompt Caching for System Prompt
**What:** Cache the system prompt across batch calls to reduce input token costs by 90%
**When to use:** When generating multiple emails with the same template
**Example:**
```python
# Source: Anthropic prompt caching docs
message = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=512,
    system=[
        {
            "type": "text",
            "text": template.system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[{"role": "user", "content": user_prompt}],
)
```

### Pattern 4: Export CSV with Presets
**What:** Generate CSV downloads with different column mappings
**When to use:** Outreach.io, Salesforce, Raw export
**Example:**
```python
# Source: Existing pattern from ui/pages/results.py

EXPORT_PRESETS = {
    "Outreach.io": {
        "columns": ["Email", "First Name", "Last Name", "Company",
                     "Subject", "Body", "Sequence Step"],
    },
    "Salesforce Lead": {
        "columns": ["Company", "Website", "Quality__c", "FirstName",
                     "LastName", "Title", "Email", "City", "State", "Country"],
    },
    "Raw": None,  # All columns
}

def build_export_df(emails: list[GeneratedEmail], preset: str) -> pd.DataFrame:
    rows = []
    for email in emails:
        if preset != "Raw" and email.status != "approved":
            continue
        rows.append({...})
    df = pd.DataFrame(rows)
    if preset_config := EXPORT_PRESETS.get(preset):
        if preset_config.get("columns"):
            df = df[preset_config["columns"]]
    return df
```

### Anti-Patterns to Avoid
- **Storing API key in database:** Use .env via `os.getenv("ANTHROPIC_API_KEY")` like other providers
- **Async Anthropic client in Streamlit:** The sync `Anthropic()` client is simpler and avoids event loop issues. Use it inside the background thread.
- **Generating subject + body in one call then parsing:** Make the prompt explicitly return JSON or use a clear delimiter. Better yet, generate subject as part of the prompt instructions and parse from the response.
- **Sharing Database connection across threads:** Create a new `Database(db_path=...)` instance in the background thread (established pattern from `_run_enrichment_bg`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retries to Claude API | Custom retry loop | `tenacity` with `@retry(stop=stop_after_attempt(3), wait=wait_exponential())` | Rate limit handling, backoff, jitter already solved |
| CSV column mapping | Custom string manipulation | pandas DataFrame column rename/reorder | Edge cases with encoding, escaping, quoting |
| Template variable parsing | Custom string parser | `re.sub(r"\{(\w+)\}", replacer, template)` | Simple regex covers the `{variable}` syntax perfectly |
| Background job progress | Custom polling mechanism | `@st.fragment(run_every=2.0)` polling DB counts | Established pattern in enrich.py |

**Key insight:** The entire email generation pipeline reuses patterns already in the codebase. The only truly new dependency is the Anthropic SDK, and its API surface is minimal (one `messages.create()` call).

## Common Pitfalls

### Pitfall 1: Anthropic Rate Limits
**What goes wrong:** Batch generation hits rate limits (RPM/TPM) and fails mid-batch
**Why it happens:** Claude Haiku 4.5 has rate limits per tier. Tier 1 is 50 RPM.
**How to avoid:** Add 0.5-1s delay between calls (similar to Apollo 1.5s delay pattern). Use tenacity retry with exponential backoff on 429 errors. Track progress so interrupted batches can resume.
**Warning signs:** HTTP 429 responses, `RateLimitError` exceptions

### Pitfall 2: Empty or Null Variables in Templates
**What goes wrong:** Template generates email with blank fields: "Hi , I noticed your company ..."
**Why it happens:** Person or Company fields are None/empty
**How to avoid:** Validate that critical variables (first_name, company_name) are non-empty before generation. Skip or flag contacts with insufficient data. Provide fallback values in system prompt instructions ("if any variable is empty, use a generic alternative").
**Warning signs:** Generated emails with double spaces or missing names

### Pitfall 3: Email Body Exceeds 120 Words
**What goes wrong:** Claude generates verbose emails despite word limit in prompt
**Why it happens:** LLMs approximate word counts, especially with technical content
**How to avoid:** Include explicit word count constraint in system prompt. Use `max_tokens=512` as a hard ceiling. Post-process to validate word count and flag violations for user review.
**Warning signs:** Emails consistently 150+ words

### Pitfall 4: Subject Line Parsing Ambiguity
**What goes wrong:** Can't reliably separate subject from body in Claude's response
**Why it happens:** Freeform text output without structure
**How to avoid:** Instruct Claude to output in a structured format: `Subject: [subject]\n\n[body]`. Parse with simple string split. Alternatively, make two calls (subject + body) but doubles cost.
**Warning signs:** Subject lines containing body text or vice versa

### Pitfall 5: Thread Safety with Streamlit Session State
**What goes wrong:** Background thread tries to update session_state directly
**Why it happens:** Streamlit session_state is not thread-safe
**How to avoid:** Background thread writes progress to database only. Polling fragment reads from database. Never share session_state with background threads. This is the established pattern from enrich.py.
**Warning signs:** Random KeyError or stale state in UI

## Code Examples

### Database Schema for Email Tables
```sql
-- email_templates table
CREATE TABLE IF NOT EXISTS email_templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    system_prompt   TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    sequence_step   INTEGER DEFAULT 1,  -- 1=Intro, 2=Follow-up, 3=Breakup
    is_default      BOOLEAN DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- generated_emails table
CREATE TABLE IF NOT EXISTS generated_emails (
    id              TEXT PRIMARY KEY,
    campaign_id     TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
    template_id     TEXT REFERENCES email_templates(id) ON DELETE SET NULL,
    person_id       TEXT REFERENCES people(id) ON DELETE CASCADE,
    company_id      TEXT REFERENCES companies(id) ON DELETE SET NULL,
    sequence_step   INTEGER DEFAULT 1,
    subject         TEXT,
    body            TEXT,
    status          TEXT DEFAULT 'draft',   -- draft, approved, rejected, failed
    user_note       TEXT,                   -- optional note for regeneration
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0.0,
    generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_generated_emails_campaign
    ON generated_emails(campaign_id);
CREATE INDEX IF NOT EXISTS ix_generated_emails_person
    ON generated_emails(person_id);
CREATE INDEX IF NOT EXISTS ix_generated_emails_status
    ON generated_emails(status);
CREATE INDEX IF NOT EXISTS ix_generated_emails_campaign_status
    ON generated_emails(campaign_id, status);
```

### Pydantic Models
```python
# Source: Pattern from data/models.py

class EmailTemplate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_uuid)
    name: str
    description: Optional[str] = None
    system_prompt: str
    user_prompt_template: str
    sequence_step: int = 1  # 1=Intro, 2=Follow-up, 3=Breakup
    is_default: bool = False
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class GeneratedEmail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_uuid)
    campaign_id: str
    template_id: Optional[str] = None
    person_id: str
    company_id: Optional[str] = None
    sequence_step: int = 1
    subject: Optional[str] = None
    body: Optional[str] = None
    status: str = "draft"  # draft, approved, rejected, failed
    user_note: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    generated_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
```

### Starter Template Prompts (Claude's Discretion)
```python
STARTER_TEMPLATES = [
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
            "Output format: Subject: [subject line]\\n\\n[email body]"
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
            "Output format: Subject: [subject line]\\n\\n[email body]"
        ),
        user_prompt_template=(
            "Write follow-up email #2 to {first_name} {last_name}, "
            "{title} at {company_name} ({industry}, {employee_count} employees, "
            "{city}, {state}). Quality tier: {quality_tier}."
        ),
        sequence_step=2,
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
            "Output format: Subject: [subject line]\\n\\n[email body]"
        ),
        user_prompt_template=(
            "Write breakup email #3 to {first_name} at {company_name} ({industry})."
        ),
        sequence_step=3,
    ),
]
```

### Anthropic Client Initialization
```python
# Source: Anthropic SDK docs - add to settings.py pattern
# In config/settings.py, add to load_settings():
#   ANTHROPIC_API_KEY from os.getenv("ANTHROPIC_API_KEY", "")

# In the email generation module:
import anthropic

def get_anthropic_client(api_key: str) -> anthropic.Anthropic:
    """Create Anthropic client. Use sync client for background thread."""
    return anthropic.Anthropic(api_key=api_key)
```

### Cost Calculation
```python
# Claude Haiku 4.5 pricing (standard, non-batch)
HAIKU_INPUT_PRICE_PER_MTOK = 1.00   # $1.00 per million input tokens
HAIKU_OUTPUT_PRICE_PER_MTOK = 5.00  # $5.00 per million output tokens
HAIKU_CACHE_HIT_PRICE_PER_MTOK = 0.10  # $0.10 per million cached input tokens

def calculate_email_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a single email generation."""
    input_cost = (input_tokens / 1_000_000) * HAIKU_INPUT_PRICE_PER_MTOK
    output_cost = (output_tokens / 1_000_000) * HAIKU_OUTPUT_PRICE_PER_MTOK
    return input_cost + output_cost
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `anthropic.Anthropic().completions.create()` | `anthropic.Anthropic().messages.create()` | 2024 | Messages API is the only supported API. Completions deprecated. |
| Claude 3 Haiku (`claude-3-haiku-20240307`) | Claude Haiku 4.5 (`claude-haiku-4-5`) | Oct 2025 | Newer model, better quality, slightly higher price but far better output. |
| No prompt caching | `cache_control: {"type": "ephemeral"}` on system prompt | 2024 | 90% cost reduction on cached input tokens. Essential for batch jobs. |

**Deprecated/outdated:**
- `anthropic.HUMAN_PROMPT` / `anthropic.AI_PROMPT` constants: Legacy completion API. Use messages API.
- `claude-3-haiku-20240307`: Still available but `claude-haiku-4-5` is the current Haiku model.

## Open Questions

1. **Subject line generation reliability**
   - What we know: Claude can output structured format (`Subject: ...\n\n...body...`)
   - What's unclear: Whether parsing is 100% reliable across all prompt variations
   - Recommendation: Use `Subject:` prefix parsing with fallback (if no `Subject:` found, use first line as subject). Log parsing failures for monitoring.

2. **Optimal delay between API calls**
   - What we know: Rate limits vary by tier. Tier 1 = 50 RPM for Haiku.
   - What's unclear: Exact tier of user's account
   - Recommendation: Start with 1.2s delay (50 RPM safe). Add tenacity retry with exponential backoff on 429. Let users configure delay in settings if needed.

3. **Regeneration with prior step context**
   - What we know: Each sequence step should be "aware" of prior steps per CONTEXT.md
   - What's unclear: Whether to include full prior email text or just a summary
   - Recommendation: For step 2+, include the prior step's generated email in the user prompt as context. This adds ~200 tokens per prior step -- negligible cost.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 + pytest-asyncio >=0.23 |
| Config file | None (uses pytest defaults, conftest.py exists) |
| Quick run command | `pytest tests/test_email_generation.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EMAIL-01 | Generate email from person+company data | unit | `pytest tests/test_email_generation.py::test_generate_single_email -x` | Wave 0 |
| EMAIL-01 | Variable substitution in templates | unit | `pytest tests/test_email_generation.py::test_variable_substitution -x` | Wave 0 |
| EMAIL-02 | CRUD email templates in database | unit | `pytest tests/test_email_generation.py::test_template_crud -x` | Wave 0 |
| EMAIL-03 | Batch generation creates emails for all contacts | unit | `pytest tests/test_email_generation.py::test_batch_generation -x` | Wave 0 |
| EMAIL-04 | Update email status (approve/reject) | unit | `pytest tests/test_email_generation.py::test_email_status_update -x` | Wave 0 |
| EMAIL-04 | Inline edit saves subject and body | unit | `pytest tests/test_email_generation.py::test_email_inline_edit -x` | Wave 0 |
| EMAIL-05 | Export Outreach.io CSV format | unit | `pytest tests/test_email_generation.py::test_export_outreach_csv -x` | Wave 0 |
| EMAIL-05 | Export Salesforce Lead CSV format | unit | `pytest tests/test_email_generation.py::test_export_salesforce_csv -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_email_generation.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_email_generation.py` -- covers EMAIL-01 through EMAIL-05 (unit tests with mocked Anthropic client)
- [ ] Framework install: `pip install "anthropic>=0.40"` -- new dependency

## Sources

### Primary (HIGH confidence)
- [Anthropic Python SDK - Messages API](https://platform.claude.com/docs/en/api/python/messages/create) - Client initialization, model names, response structure, system prompts
- [Anthropic Pricing](https://platform.claude.com/docs/en/about-claude/pricing) - Haiku 4.5: $1/MTok input, $5/MTok output, batch 50% off, cache hits 0.1x
- [Anthropic Message Batches API](https://platform.claude.com/docs/en/api/creating-message-batches) - Batch API format, 100K request limit, 24h processing

### Secondary (MEDIUM confidence)
- Existing codebase patterns: `ui/pages/enrich.py` (background thread + polling), `ui/pages/results.py` (CSV export), `data/models.py` (Pydantic patterns), `data/schema.sql` (table structure)

### Tertiary (LOW confidence)
- None -- all findings verified with primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Anthropic SDK is well-documented, single dependency addition
- Architecture: HIGH - Reuses 100% of existing patterns (threading, polling, export, DB)
- Pitfalls: HIGH - Rate limits, variable substitution, and thread safety are well-understood from enrichment pipeline experience

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable domain, Anthropic SDK mature)
