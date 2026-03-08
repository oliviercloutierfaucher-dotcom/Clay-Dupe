# Architecture: v2.0 Integration — Salesforce, AI Email, Company Sourcing

**Domain:** B2B prospecting platform — extending enrichment-only to end-to-end pipeline
**Researched:** 2026-03-07
**Confidence:** HIGH (integration points derived from direct codebase analysis; API patterns verified via official docs)

---

## Overview

v2.0 adds three capabilities to the existing waterfall enrichment platform:

1. **Salesforce dedup checking** — read-only SOQL queries against Accounts/Contacts to flag or skip duplicates before enrichment
2. **AI-personalized email generation** — OpenAI API calls using enriched company + contact data to produce cold email drafts
3. **Multi-source company sourcing** — Apollo search, CSV import, and manual add as lead generation entry points

These features integrate at different points in the existing pipeline and have a strict dependency order. The architecture below specifies exactly which existing files change, which new files are needed, and how data flows through the system.

---

## Current Architecture (Reference)

```
UI (Streamlit)
  |
  v
CLI (Typer) / UI Pages
  |
  v
Enrichment Layer
  waterfall.py    — orchestrator (cache -> classify -> route -> execute -> persist)
  router.py       — per-route provider sequence
  classifier.py   — row classification into RouteCategory
  pattern_engine  — email pattern matching
  |
  v
Provider Layer
  base.py         — BaseProvider ABC (find_email, search_companies, search_people, enrich_company)
  apollo.py, findymail.py, icypeas.py, datagma.py, contactout.py
  http_pool.py    — shared httpx.AsyncClient
  |
  v
Quality + Cost Layer
  confidence.py, verification.py, circuit_breaker.py
  budget.py, tracker.py, cache.py
  |
  v
Data Layer
  database.py     — all CRUD (aiosqlite, WAL mode)
  models.py       — Pydantic v2 models (Company, Person, Campaign, EnrichmentResult, etc.)
  schema.sql      — 11 tables
  io.py           — CSV/Excel import/export
  sync.py         — run_sync() wrapper for Streamlit
```

---

## Integration Architecture

### Feature 1: Salesforce Dedup Checking

**Where it plugs in:** Between row classification (step 2) and provider execution (step 4) in `WaterfallOrchestrator.enrich_single()`. This is the same insertion point as cross-campaign dedup (step 1b) — Salesforce dedup is a pre-enrichment gate.

**New files:**

| File | Purpose |
|------|---------|
| `integrations/__init__.py` | New top-level package for external CRM integrations |
| `integrations/salesforce.py` | `SalesforceChecker` class — SOQL queries via `simple-salesforce` |
| `data/models.py` (MODIFY) | Add `SalesforceMatch` model, add `sf_account_id`/`sf_contact_id`/`sf_status` fields to `Person` and `Company` |
| `data/schema.sql` (MODIFY) | Add `sf_account_id`, `sf_contact_id`, `sf_status` columns to `people` and `companies` tables; add `salesforce_config` table |
| `data/database.py` (MODIFY) | Add `get_sf_config()`, `save_sf_config()`, `mark_sf_duplicate()` methods |
| `enrichment/waterfall.py` (MODIFY) | Add Salesforce check step between dedup check (1b) and classify (2) |
| `config/settings.py` (MODIFY) | Add `SalesforceConfig` model with instance_url, credentials, dedup_strategy |
| `ui/pages/settings.py` (MODIFY) | Add Salesforce connection config UI section |
| `ui/pages/enrich.py` (MODIFY) | Show SF duplicate status column in results |

**Component design — `SalesforceChecker`:**

```python
# integrations/salesforce.py
from simple_salesforce import Salesforce
from dataclasses import dataclass
from typing import Optional

@dataclass
class SalesforceMatch:
    """Result of a Salesforce dedup check."""
    found_account: bool = False
    found_contact: bool = False
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    contact_id: Optional[str] = None
    contact_email: Optional[str] = None
    account_owner: Optional[str] = None

class SalesforceChecker:
    """Read-only Salesforce integration for duplicate checking.

    NOT a BaseProvider subclass — this is not an enrichment provider.
    It is a pre-enrichment gate that checks if a prospect already exists
    in the CRM before spending credits on enrichment.
    """

    def __init__(self, instance_url: str, username: str, password: str,
                 security_token: str):
        self._sf = Salesforce(
            instance_url=instance_url,
            username=username,
            password=password,
            security_token=security_token,
        )
        self._cache: dict[str, SalesforceMatch] = {}  # domain -> match

    def check_company(self, domain: str) -> SalesforceMatch:
        """SOQL: SELECT Id, Name, OwnerId FROM Account WHERE Website LIKE '%domain%'"""
        ...

    def check_contact(self, email: str) -> SalesforceMatch:
        """SOQL: SELECT Id, Email, AccountId FROM Contact WHERE Email = :email"""
        ...

    def check_batch(self, domains: list[str]) -> dict[str, SalesforceMatch]:
        """Batch check using SOQL IN clause. Max 200 per query (SF limit)."""
        ...
```

**Critical design decision: NOT a BaseProvider.** Salesforce is not an enrichment data source in this system — it is a dedup gate. It does not implement `find_email()`, `search_companies()`, or `enrich_company()`. Making it a provider would pollute the waterfall with a fundamentally different concern (checking if data already exists vs. finding new data). It lives in a separate `integrations/` package.

**Waterfall integration point:**

```python
# In WaterfallOrchestrator.enrich_single(), after cross-campaign dedup (step 1b):

# --- 1c. Salesforce dedup check ---
if self.sf_checker and domain:
    sf_match = self.sf_checker.check_company(domain)
    if sf_match.found_account:
        if self.sf_dedup_strategy == "skip":
            return self._sf_skip_result(sf_match, ...)
        elif self.sf_dedup_strategy == "flag":
            row["_sf_duplicate"] = True
            row["_sf_account_id"] = sf_match.account_id
            # Continue to enrichment but flag the result
```

**Dedup strategy options:**
- `skip` — Do not enrich. Return immediately with SF match data. Zero credit cost.
- `flag` — Enrich normally but tag the result with SF account/contact IDs. User reviews flagged rows post-enrichment.
- `off` — Ignore Salesforce entirely. Default for campaigns where SF is not configured.

**Batch optimization:** For batch enrichment, pre-fetch all SF matches in one SOQL query before entering the per-row waterfall loop. The `check_batch()` method uses `WHERE Website IN (...)` with chunks of 200 (Salesforce SOQL limit). Cache results in-memory for the batch duration.

---

### Feature 2: AI-Personalized Email Generation

**Where it plugs in:** Post-enrichment. This is a downstream consumer of enriched Company + Person data, not part of the waterfall. It runs after enrichment completes and the results are persisted.

**New files:**

| File | Purpose |
|------|---------|
| `outreach/__init__.py` | New top-level package for outreach generation |
| `outreach/email_generator.py` | `EmailGenerator` class — OpenAI API calls for email drafts |
| `outreach/templates.py` | Prompt templates and personalization variable mapping |
| `outreach/models.py` | `EmailDraft` Pydantic model |
| `data/schema.sql` (MODIFY) | Add `email_drafts` table |
| `data/database.py` (MODIFY) | Add `save_email_draft()`, `get_drafts_by_campaign()` methods |
| `data/models.py` (MODIFY) | Add `EmailDraft` model |
| `config/settings.py` (MODIFY) | Add `OpenAIConfig` (api_key, model, temperature, max_tokens) |
| `ui/pages/outreach.py` (NEW) | Email generation UI — select campaign, generate, review, export |
| `ui/app.py` (MODIFY) | Add outreach page to navigation |

**Component design — `EmailGenerator`:**

```python
# outreach/email_generator.py
from openai import AsyncOpenAI
from outreach.models import EmailDraft
from outreach.templates import build_prompt

class EmailGenerator:
    """Generate personalized cold emails from enriched data using OpenAI."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini",
                 temperature: float = 0.7):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._temperature = temperature

    async def generate_single(
        self,
        person: Person,
        company: Company,
        template_name: str = "cold_intro",
        custom_instructions: str = "",
    ) -> EmailDraft:
        """Generate one personalized email for a person at a company."""
        prompt = build_prompt(
            person=person,
            company=company,
            template_name=template_name,
            custom_instructions=custom_instructions,
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            temperature=self._temperature,
            max_tokens=500,
        )
        return EmailDraft(
            person_id=person.id,
            company_id=company.id,
            subject=self._extract_subject(response),
            body=self._extract_body(response),
            template_used=template_name,
            model_used=self._model,
            tokens_used=response.usage.total_tokens,
        )

    async def generate_batch(
        self,
        rows: list[tuple[Person, Company]],
        template_name: str = "cold_intro",
        concurrency: int = 5,
    ) -> list[EmailDraft]:
        """Generate emails for multiple person-company pairs with rate limiting."""
        ...
```

**Why gpt-4o-mini:** Cost-effective for short-form email generation (~$0.15/1M input tokens, ~$0.60/1M output tokens). A 500-token cold email costs roughly $0.0004 per generation. For 10K contacts that is approximately $4 total — negligible vs. enrichment costs. If quality is insufficient, upgrade to gpt-4o for specific templates.

**Template system design:**

```python
# outreach/templates.py
TEMPLATES = {
    "cold_intro": PromptTemplate(
        system="You are a B2B sales development representative...",
        user_template="""
Write a personalized cold email to {person.first_name} {person.last_name},
{person.title} at {company.name}.

Company context:
- Industry: {company.industry}
- Size: {company.employee_count} employees
- Location: {company.city}, {company.state}
- Description: {company.description}

{custom_instructions}

Requirements:
- Subject line (under 50 chars, no clickbait)
- 3-4 sentences max
- Reference something specific about their company
- Clear, non-pushy CTA
""",
    ),
    "follow_up": ...,
    "referral_ask": ...,
}
```

**Key constraint: No Outreach.io API integration (out of scope per PROJECT.md).** Generated emails are stored locally and exported via CSV for manual import into Outreach.io sequences. The `email_drafts` table stores all generated emails with their metadata.

**Data flow:**

```
Enrichment complete (Person + Company in DB)
  |
  v
User selects campaign in Outreach UI page
  |
  v
EmailGenerator.generate_batch() — calls OpenAI for each person-company pair
  |
  v
EmailDraft stored in email_drafts table
  |
  v
User reviews/edits drafts in UI
  |
  v
Export to CSV (columns: email, first_name, subject, body) for Outreach.io import
```

---

### Feature 3: Multi-Source Company Sourcing

**Where it plugs in:** Upstream of enrichment. Company sourcing produces the input rows that feed into the waterfall. Currently, the only entry point is CSV import (via `data/io.py`). This feature adds Apollo search and manual entry as additional input sources.

**New files:**

| File | Purpose |
|------|---------|
| `sourcing/__init__.py` | New top-level package for company/lead sourcing |
| `sourcing/apollo_sourcer.py` | Wraps `ApolloProvider.search_companies()` with ICP filtering |
| `sourcing/csv_sourcer.py` | Refactor of existing `data/io.py` CSV import logic |
| `sourcing/manual_sourcer.py` | Manual company/contact add via form input |
| `sourcing/pipeline.py` | `SourcingPipeline` — unified interface for all sourcing methods |
| `ui/pages/sourcing.py` (NEW) | Company sourcing UI — search, import, manual add |
| `ui/app.py` (MODIFY) | Add sourcing page to navigation, reorder nav |

**No new provider implementation needed.** Apollo's `search_companies()` and `search_people()` methods already exist in `providers/apollo.py`. The sourcing layer wraps these existing methods with ICP preset application and result persistence.

**Component design — `SourcingPipeline`:**

```python
# sourcing/pipeline.py
from data.database import Database
from data.models import Company, Person
from providers.apollo import ApolloProvider
from config.settings import ICPPreset

class SourcingPipeline:
    """Unified company/lead sourcing from multiple channels."""

    def __init__(self, db: Database, apollo: ApolloProvider):
        self.db = db
        self.apollo = apollo

    async def search_apollo(
        self,
        icp_preset: ICPPreset,
        max_results: int = 100,
    ) -> list[Company]:
        """Search Apollo using ICP preset filters. Returns Company models."""
        companies = await self.apollo.search_companies(
            organization_num_employees_ranges=[
                f"{icp_preset.employee_min},{icp_preset.employee_max}"
            ],
            q_organization_keyword_tags=icp_preset.keywords,
        )
        # Persist to companies table
        for company in companies:
            await self.db.upsert_company(company)
        return companies

    async def import_csv(self, file_path: str, column_mapping: dict) -> list[Company]:
        """Import companies from CSV. Reuses existing io.py logic."""
        ...

    async def add_manual(self, company: Company) -> Company:
        """Add a single company manually via form input."""
        await self.db.upsert_company(company)
        return company

    async def source_people_for_companies(
        self,
        companies: list[Company],
        title_filters: list[str],
        seniority_filters: list[str],
    ) -> list[Person]:
        """For each sourced company, find decision-makers via Apollo search."""
        people = []
        for company in companies:
            if company.domain:
                results = await self.apollo.search_people(
                    q_organization_domains_list=[company.domain],
                    person_titles=title_filters,
                    person_seniorities=seniority_filters,
                )
                for person in results:
                    person.company_id = company.id
                    await self.db.upsert_person(person)
                    people.append(person)
        return people
```

**Relationship to existing components:**

- `SourcingPipeline` wraps `ApolloProvider.search_companies()` and `search_people()` — these are FREE Apollo API calls (no credits consumed)
- Results flow into the same `companies` and `people` tables used by enrichment
- After sourcing, the user creates a campaign from sourced companies/people and runs enrichment via the existing waterfall
- ICP presets (`config/settings.py`) already exist and are used directly

---

## Modified Existing Files Summary

| File | What Changes | Why |
|------|-------------|-----|
| `config/settings.py` | Add `SalesforceConfig`, `OpenAIConfig` models; add to `Settings` | New credentials and configuration for SF and AI |
| `data/models.py` | Add `SalesforceMatch`, `EmailDraft` models; add `sf_*` fields to Person/Company | New data types for dedup results and email drafts |
| `data/schema.sql` | Add `email_drafts` table, `salesforce_config` table; add SF columns to people/companies | Persist new data types |
| `data/database.py` | Add methods for SF config, email drafts, company upsert | CRUD for new features |
| `enrichment/waterfall.py` | Add `sf_checker` parameter and SF dedup step between 1b and 2 | Pre-enrichment gate |
| `ui/app.py` | Add sourcing and outreach pages to navigation | New UI entry points |
| `ui/pages/settings.py` | Add SF config section, OpenAI config section | Credential management |
| `ui/pages/enrich.py` | Show SF duplicate status in results table | Surface dedup flags |

## New Files Summary

| File | Package | Purpose |
|------|---------|---------|
| `integrations/__init__.py` | integrations | External CRM connections |
| `integrations/salesforce.py` | integrations | SalesforceChecker -- SOQL dedup queries |
| `outreach/__init__.py` | outreach | Email generation |
| `outreach/email_generator.py` | outreach | OpenAI-powered email drafting |
| `outreach/templates.py` | outreach | Prompt templates and variable mapping |
| `outreach/models.py` | outreach | EmailDraft Pydantic model |
| `sourcing/__init__.py` | sourcing | Company/lead sourcing |
| `sourcing/apollo_sourcer.py` | sourcing | Apollo search wrapper with ICP filtering |
| `sourcing/csv_sourcer.py` | sourcing | Refactored CSV import |
| `sourcing/manual_sourcer.py` | sourcing | Manual add via form |
| `sourcing/pipeline.py` | sourcing | Unified sourcing interface |
| `ui/pages/sourcing.py` | ui | Sourcing UI page |
| `ui/pages/outreach.py` | ui | Email generation UI page |

---

## Data Flow: End-to-End v2.0 Pipeline

```
SOURCING (new)
  Apollo Search --------+
  CSV Import -----------+---> companies + people tables
  Manual Add -----------+

SALESFORCE DEDUP (new)
  Pre-enrichment batch check ---> flag or skip duplicates

ENRICHMENT (existing)
  Waterfall: cache -> classify -> [SF dedup check] -> route -> provider cascade -> persist

AI EMAIL GENERATION (new)
  Post-enrichment: enriched Person + Company ---> OpenAI ---> email_drafts table

EXPORT (existing + extended)
  CSV export with email columns + SF status + generated email drafts
```

---

## Database Schema Changes

### New table: `email_drafts`

```sql
CREATE TABLE IF NOT EXISTS email_drafts (
    id              TEXT PRIMARY KEY,
    person_id       TEXT REFERENCES people(id) ON DELETE CASCADE,
    company_id      TEXT REFERENCES companies(id) ON DELETE SET NULL,
    campaign_id     TEXT REFERENCES campaigns(id) ON DELETE SET NULL,
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    template_used   TEXT,
    model_used      TEXT,
    tokens_used     INTEGER,
    status          TEXT DEFAULT 'draft',  -- draft, approved, exported
    edited_body     TEXT,                  -- user-edited version
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exported_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_email_drafts_campaign
    ON email_drafts(campaign_id);
CREATE INDEX IF NOT EXISTS ix_email_drafts_person
    ON email_drafts(person_id);
CREATE INDEX IF NOT EXISTS ix_email_drafts_status
    ON email_drafts(status);
```

### New table: `salesforce_config`

```sql
CREATE TABLE IF NOT EXISTS salesforce_config (
    id              TEXT PRIMARY KEY DEFAULT 'default',
    instance_url    TEXT NOT NULL,
    username        TEXT NOT NULL,
    -- password/token stored in .env, not in DB
    dedup_strategy  TEXT DEFAULT 'flag',   -- skip, flag, off
    last_connected  TIMESTAMP,
    is_active       BOOLEAN DEFAULT 1
);
```

### Modified columns on `people`

```sql
ALTER TABLE people ADD COLUMN sf_contact_id TEXT;
ALTER TABLE people ADD COLUMN sf_account_id TEXT;
ALTER TABLE people ADD COLUMN sf_status TEXT DEFAULT 'not_checked';
-- sf_status values: not_checked, clean, duplicate_account, duplicate_contact
```

### Modified columns on `companies`

```sql
ALTER TABLE companies ADD COLUMN sf_account_id TEXT;
ALTER TABLE companies ADD COLUMN sf_status TEXT DEFAULT 'not_checked';
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `SourcingPipeline` | Find and persist target companies/people | ApolloProvider, Database, io.py |
| `SalesforceChecker` | Check CRM for existing accounts/contacts | Salesforce API (simple-salesforce), Database |
| `WaterfallOrchestrator` (modified) | Enrichment pipeline with SF dedup gate | SalesforceChecker, all existing deps |
| `EmailGenerator` | Generate personalized emails from enriched data | OpenAI API, Database |
| `PromptTemplates` | Map enriched fields to prompt variables | EmailGenerator |

**Boundary rule:** Each new component owns its own external API connection. SalesforceChecker owns the `simple-salesforce` client. EmailGenerator owns the `openai` AsyncClient. Neither is injected through the provider layer.

---

## Patterns to Follow

### Pattern 1: Pre-Enrichment Gate (Salesforce)

**What:** Check an external system before spending enrichment credits. If match found, either skip (save credits) or flag (enrich but annotate).

**When:** Any pre-enrichment validation against external data. Salesforce is the first instance; future: HubSpot, Pipedrive.

**Implementation:**
- Batch pre-fetch at campaign start (not per-row queries)
- In-memory cache for batch duration (domain -> SalesforceMatch)
- Configurable strategy: skip/flag/off per campaign
- Non-blocking: SF API failure should not block enrichment (log warning, continue)

### Pattern 2: Post-Enrichment Processor (AI Email)

**What:** Consume enriched data to produce derived outputs. Runs after enrichment completes, not during the waterfall.

**When:** Any feature that transforms enriched data into deliverables. Email generation is the first instance; future: report generation, CRM push.

**Implementation:**
- Triggered explicitly by user action (not automatic)
- Reads from companies + people tables (never from raw provider responses)
- Writes to its own table (email_drafts), not enrichment_results
- Rate-limited independently (OpenAI has separate rate limits from enrichment providers)

### Pattern 3: Upstream Sourcing (Company Search)

**What:** Generate the input rows that feed the enrichment pipeline. Currently only CSV import exists.

**When:** Any new lead generation channel.

**Implementation:**
- All sources produce Company/Person models (same Pydantic types)
- All sources persist to the same companies/people tables
- Sourcing is separate from enrichment -- source first, create campaign, then enrich
- ICP presets (already exist) drive search filters

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Making Salesforce a BaseProvider

**What:** Implementing SalesforceChecker as a subclass of BaseProvider.

**Why bad:** BaseProvider defines enrichment operations (find_email, search_companies, enrich_company). Salesforce does not find emails or enrich data -- it checks for duplicates. Forcing it into BaseProvider would require stub implementations of methods it does not support, and it would appear in waterfall provider sequences where it does not belong.

**Instead:** Separate `integrations/` package. SalesforceChecker is injected into WaterfallOrchestrator as an optional dependency, not as a provider in the waterfall sequence.

### Anti-Pattern 2: Calling OpenAI During Enrichment

**What:** Generating emails inside the waterfall loop as each person is enriched.

**Why bad:** Enrichment is credit-sensitive and resumable. Mixing AI generation into the waterfall means: (1) email generation failures affect enrichment resume state, (2) paused campaigns have partially generated emails with no clear resume point, (3) the cost model becomes entangled (enrichment credits + AI tokens in the same budget tracking).

**Instead:** Email generation is a post-enrichment step. User clicks "Generate Emails" after enrichment completes. Separate cost tracking. Separate error handling.

### Anti-Pattern 3: Tight Coupling Between Sourcing and Enrichment

**What:** Auto-triggering enrichment when companies are sourced.

**Why bad:** Sourcing is exploratory -- users search, filter, review results, remove unwanted companies, then decide to enrich. Auto-enrichment wastes credits on companies the user would have filtered out. It also makes the cost model unpredictable.

**Instead:** Source -> Review -> Create Campaign -> Enrich. Each step is explicit. The user controls when credits are spent.

---

## Suggested Build Order

The three features have clear dependencies that dictate implementation order:

### Phase 1: Company Sourcing (Foundation)

**Build first because:** It creates the input data everything else needs. Without sourced companies/people in the database, there is nothing to dedup against Salesforce and nothing to generate emails for. Also, this feature has the lowest technical risk -- it wraps existing Apollo API methods that already work.

**Delivers:**
- `sourcing/` package (pipeline, apollo_sourcer, csv_sourcer, manual_sourcer)
- `ui/pages/sourcing.py` -- search companies, import CSV, add manually
- `data/database.py` additions -- `upsert_company()`, `upsert_person()` if not present
- Wired into existing ICP presets from `config/settings.py`

**Integration points:**
- Wraps `ApolloProvider.search_companies()` and `search_people()` (existing, free calls)
- Persists to existing `companies` and `people` tables
- No changes to waterfall or enrichment pipeline

**Estimated scope:** ~5-8 new files, minimal modification to existing files.

### Phase 2: Salesforce Integration

**Build second because:** Requires companies/people in the database to check against (Phase 1 provides these). Must be integrated before email generation -- users need to know which contacts are SF duplicates before generating emails for them.

**Delivers:**
- `integrations/` package with SalesforceChecker
- Schema changes: SF columns on people/companies, salesforce_config table
- Waterfall modification: SF dedup step between 1b and 2
- Settings UI: SF connection config
- Enrich UI: SF status column

**Integration points:**
- Injected into WaterfallOrchestrator as optional `sf_checker` parameter
- Batch pre-fetch in `enrich_batch()` before entering per-row loop
- Non-blocking: SF failures log warnings, do not block enrichment

**Estimated scope:** ~4-5 new files, modifications to waterfall.py, settings.py, models.py, schema.sql, database.py, and 2 UI pages.

### Phase 3: AI Email Generation

**Build last because:** It consumes the output of both sourcing (companies/people data) and enrichment (verified emails, enriched company details). Also depends on knowing SF duplicate status -- generating emails for contacts that are SF duplicates is wasteful.

**Delivers:**
- `outreach/` package with EmailGenerator, templates, models
- Schema changes: email_drafts table
- New UI page: outreach (generate, review, edit, export)
- CSV export extension: include generated email columns

**Integration points:**
- Reads from companies + people tables (post-enrichment)
- Reads SF status to exclude/warn about duplicates
- Writes to email_drafts table
- Export via extended `data/io.py`

**Estimated scope:** ~5-6 new files, modifications to schema.sql, database.py, models.py, io.py, app.py, and 1 new UI page.

---

## Build Order Rationale

```
Phase 1: Sourcing ---> Phase 2: Salesforce ---> Phase 3: AI Email
     |                      |                      |
     v                      v                      v
  Companies/People     SF dedup flags          Email drafts
  in database          on enriched data        from enriched+deduped data
```

- **Sourcing before Salesforce:** SF dedup checks need data to check. Without sourced companies, the SF checker has nothing to query against.
- **Salesforce before AI Email:** Email generation should respect SF dedup status. Generating emails for SF duplicates wastes OpenAI tokens and creates confusing output.
- **Each phase is independently deployable.** Phase 1 is useful without Phase 2 or 3. Phase 2 is useful without Phase 3. This enables incremental delivery and testing with real data between phases.

---

## Scalability Considerations

| Concern | At 100 companies | At 1K companies | At 10K companies |
|---------|-------------------|------------------|-------------------|
| SF dedup | Single SOQL query | 5 batched queries (200/query limit) | 50 batched queries; consider caching SF accounts locally |
| AI email generation | Sequential, ~30sec | Concurrent (5 parallel), ~5min | Concurrent (10 parallel), ~30min; consider gpt-4o-mini batch API |
| Apollo sourcing | 1-4 API calls | 10-40 API calls, paginated | 100+ API calls; Apollo rate limit (50/min) becomes bottleneck |
| Database | No concern | No concern | Add indexes on sf_account_id, consider email_drafts archiving |

---

## Sources

- [simple-salesforce documentation](https://simple-salesforce.readthedocs.io/en/latest/) -- Python Salesforce REST API client, HIGH confidence
- [simple-salesforce PyPI](https://pypi.org/project/simple-salesforce/) -- current version, HIGH confidence
- [Salesforce SOQL query docs](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_query.htm) -- SOQL query patterns, HIGH confidence
- [OpenAI Python API library](https://developers.openai.com/api/reference/python/) -- AsyncOpenAI client, HIGH confidence
- [OpenAI API models](https://developers.openai.com/api/docs/models) -- gpt-4o-mini pricing and capabilities, HIGH confidence
- Direct codebase analysis of: `providers/base.py`, `providers/apollo.py`, `enrichment/waterfall.py`, `data/models.py`, `data/schema.sql`, `data/database.py`, `config/settings.py` -- HIGH confidence

---

*Architecture research for: v2.0 Salesforce integration, AI email generation, company sourcing*
*Researched: 2026-03-07*
