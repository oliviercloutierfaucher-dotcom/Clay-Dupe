# Implementation Guide — Applying Research to Codebase

**Date:** 2026-03-08
**For:** Any Claude session working on Clay-Dupe v2.0
**Context:** 13 research reports in `.planning/research/`. This document maps findings to specific code changes.

---

## Current State (Confirmed by Other Session)

- **Phases 10-11: DONE** (Infrastructure, Company Sourcing, Salesforce Integration)
- **Phase 12: NEXT** (AI Email Generation)
- **Phase 13: Cloud Deployment**
- Actual roadmap is 4 phases (10-13), not the 6-phase proposal in SUMMARY_FOR_CONTEXT.md

---

## How to Add New Providers (Research: `FREE_API_PROVIDERS.md`)

### Pattern to Follow
Every provider extends `BaseProvider` in `providers/base.py`. See `providers/apollo.py` as reference.

### Steps for a New Provider (e.g., Hunter.io)

1. **Add to ProviderName enum** in `config/settings.py` (line ~16) AND `data/models.py`:
   ```python
   class ProviderName(str, Enum):
       APOLLO = "apollo"
       FINDYMAIL = "findymail"
       ICYPEAS = "icypeas"
       CONTACTOUT = "contactout"
       DATAGMA = "datagma"
       HUNTER = "hunter"          # NEW
       PEOPLEDATALABS = "pdl"     # NEW
       PROSPEO = "prospeo"        # NEW
   ```

2. **Create provider file** `providers/hunter.py`:
   - Class `HunterProvider(BaseProvider)`
   - Set `name = ProviderName.HUNTER`, `base_url = "https://api.hunter.io/v2"`
   - Implement `find_email()`, `verify_email()`, `enrich_company()` (domain search)
   - Authentication: API key as query param `?api_key=`
   - Return `ProviderResponse` with `found`, `email`, `confidence`, `credits_used`

3. **Add env var** `HUNTER_API_KEY` to `.env.example` and `config/settings.py` `load_settings()`

4. **Update default waterfall** in `config/settings.py` (line ~160):
   ```python
   # Default: "apollo,icypeas,findymail,datagma"
   # Recommended: "apollo,icypeas,findymail,hunter,datagma"
   ```

5. **Register in UI** `ui/pages/settings.py` `_PROVIDER_CLASSES` dict

6. **Update router.py** if the provider has special capabilities (e.g., Hunter domain search for NAME_AND_COMPANY route)

### Priority Providers to Add (from research)
| Provider | Free Tier | Best For | Effort |
|----------|-----------|----------|--------|
| Hunter.io | 25 searches + 50 verifications/month | Email verification, domain search | Small |
| PeopleDataLabs | 100 lookups/month | Richest data fields (100+ per record) | Medium |
| Prospeo | 75 emails/month | LinkedIn URL enrichment | Small |

---

## LinkedIn Workflow (Research: `LINKEDIN_ENRICHMENT.md`)

### What Exists
- `RouteCategory.LINKEDIN_PERSON` already in `enrichment/classifier.py`
- `enrichment/router.py` routes LINKEDIN_PERSON: ContactOut first, then rest of waterfall
- `classifier.py` detects LinkedIn URLs via regex `r'linkedin\.com/in/'`

### What to Add
1. **LinkedIn URL normalization** in `data/models.py` `Person.normalize_linkedin_url()` — extract public identifier, lowercase, strip query params. Regex from research:
   ```python
   r'(?:https?://)?(?:\w+\.)?linkedin\.com/in/([\w-]+)/?'
   ```

2. **Sales Navigator CSV import** — add column detection for LinkedIn URL column in `enrichment/classifier.py` `detect_fields()`. Sales Nav exports have columns: First Name, Last Name, Company, Title, LinkedIn URL

3. **Update router.py** LINKEDIN_PERSON sequence — research recommends:
   Apollo (60-70% hit) → ContactOut (+10-15%) → Prospeo (+5-10%) → Hunter (+3-5%)

4. **UI: "Paste LinkedIn URLs" input** on `ui/pages/enrich.py` — text area where user pastes URLs, system creates rows with linkedin_url field, classifies as LINKEDIN_PERSON

---

## Salesforce CSV Export (Research: `SALESFORCE_CSV_EXPORT.md`)

### User's Required Fields (from screenshot)
```
Company Name | Website | Quality | Year Established | Number of Employees |
Description | First Name | Last Name | Title | Email | Portfolio | Vertical |
Account Owner | Lead Owner | City | Province | Country
```

### Field Mapping to SF API Names
| Our Field | SF Lead API Name | SF Account API Name | Notes |
|-----------|-----------------|--------------------|----|
| Company Name | `Company` | `Name` | Required on both |
| Website | `Website` | `Website` | |
| Quality | `Quality__c` | `Quality__c` | Custom picklist: Gold/Silver/Bronze |
| Year Established | — | `YearStarted` | No standard Lead field |
| Number of Employees | `NumberOfEmployees` | `NumberOfEmployees` | Integer |
| Description | `Description` | `Description` | |
| First Name | `FirstName` | — | On Lead/Contact only |
| Last Name | `LastName` | — | Required on Lead/Contact |
| Title | `Title` | — | On Lead/Contact only |
| Email | `Email` | — | On Lead/Contact only |
| Portfolio | `Portfolio__c` | `Portfolio__c` | Custom field |
| Vertical | `Vertical__c` | `Vertical__c` | Custom field |
| Account Owner | `OwnerId` | `OwnerId` | Needs SF User ID, not name |
| Lead Owner | `OwnerId` | — | Needs SF User ID, not name |
| City | `City` | `BillingCity` | |
| Province | `State` | `BillingState` | MUST be separate from Country |
| Country | `Country` | `BillingCountry` | MUST be separate from Province |

### Implementation
- Add `data/export.py` with `ExportPreset` class
- Presets: `SF_LEAD`, `SF_ACCOUNT_CONTACT`, `HUBSPOT`, `OUTREACH`, `RAW`
- Each preset maps internal field names → output column headers
- Owner mapping: either hardcode a default owner name, or add a lookup table in settings
- UI: dropdown to select preset on `ui/pages/results.py`, preview before download

---

## AI Email Generation (Research: `AI_EMAIL_PERSONALIZATION.md`)

### This Is Phase 12 — Implementation Details

**Architecture:**
- New module: `email_gen/` with `generator.py`, `templates.py`, `prompts.py`
- Use Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) for volume — $0.53/1K emails with batch+cache
- Use Claude Sonnet for high-value prospects (Gold tier)

**Key Design Decisions from Research:**
- Optimal email length: **120 words**
- 70% of responses come from emails **2-4 in sequence** — generate multi-step cadences
- Data quality > model quality — feed enriched company data, ICP match reasons, industry context
- Gmail's Gemini AI does semantic spam filtering — use **hybrid approach** (AI personalization + structural variation)
- Include human-in-the-loop: preview → edit → approve → regenerate

**Prompt Template System:**
```python
class EmailTemplate(BaseModel):
    name: str
    tone: str  # "consultative", "casual", "challenger", "data-driven"
    system_prompt: str
    user_prompt_template: str  # with {company_name}, {title}, {industry}, etc.
    sequence_position: int  # 1=intro, 2=follow-up, 3=value-add, 4=breakup
```

**Variables Available from Enrichment:**
- Company: name, domain, industry, employee_count, ebitda_estimate, year_founded, description, city/state/country
- Contact: first_name, last_name, title, seniority, department, linkedin_url
- ICP: quality_tier (Gold/Silver/Bronze), icp_score, matched_criteria
- Custom: portfolio, vertical (user-provided)

**Cost Estimation:**
- Claude Haiku: ~$1.50/1K emails ($0.53 with batch API + prompt caching)
- For 1,000 contacts × 4-email sequence = 4,000 generations ≈ $2-6

**Dependencies to Add:**
```
anthropic>=0.40              # Claude API client
```

---

## ICP Scoring Improvements (Research: `ICP_SCORING_BEST_PRACTICES.md`)

### Current Implementation
- `enrichment/icp_scorer.py` — scores companies against ICP presets
- `config/settings.py` — `ICPPreset` model with industries, keywords, employee/ebitda ranges, countries

### Improvements from Research
1. **EBITDA estimation** when not available:
   ```python
   def estimate_ebitda(employee_count: int, industry: str) -> Optional[int]:
       ratios = {
           "aerospace": {"rev_per_emp": 325_000, "margin": 0.125},
           "medical_device": {"rev_per_emp": 275_000, "margin": 0.15},
           "custom_manufacturing": {"rev_per_emp": 225_000, "margin": 0.115},
           "niche_industrial": {"rev_per_emp": 200_000, "margin": 0.14},
       }
       r = ratios.get(industry, {"rev_per_emp": 250_000, "margin": 0.12})
       return int(employee_count * r["rev_per_emp"] * r["margin"])
   ```

2. **Certification detection** — scan company descriptions/websites for: AS9100, ISO 13485, ITAR, NADCAP, ISO 9001. Each certification boosts niche score.

3. **Scoring weights** (from research):
   - EBITDA fit: 30%
   - Industry match: 25%
   - Employee count fit: 15%
   - Niche indicators: 15%
   - Geography: 10%
   - Intent signals: 5% (low for niche manufacturers)

---

## Email Verification Improvements (Research: `EMAIL_VERIFICATION_DEEP_DIVE.md`)

### Current Implementation
- `quality/verification.py` — SMTP + DNS verification
- `quality/confidence.py` — confidence scoring

### Free Improvements
1. **Add 7-layer pipeline** (most layers are free local checks):
   - Layer 1: Syntax validation (regex) — FREE
   - Layer 2: DNS resolution — FREE
   - Layer 3: MX record check — FREE
   - Layer 4: Disposable email detection (maintain blocklist) — FREE
   - Layer 5: Role-based detection (info@, sales@, admin@) — FREE
   - Layer 6: SMTP RCPT TO check — FREE but risky for IP rep
   - Layer 7: Catch-all domain detection — FREE

2. **Free verification APIs to add**:
   - ZeroBounce: 100 verifications/month free
   - Emailable: 250 verifications/month free

---

## Domain Finding Improvements (Research: `DOMAIN_FINDING.md`)

### Current: Apollo company search returns domain
### Add Free Fallbacks:

1. **DNS guessing** (FREE, catches 30-40%):
   ```python
   async def guess_domain(company_name: str) -> Optional[str]:
       slug = company_name.lower().replace(" ", "").replace(",", "")
       for tld in [".com", ".io", ".co", ".net", ".org"]:
           domain = slug + tld
           if await has_mx_records(domain):
               return domain
       return None
   ```

2. **Serper.dev** ($0.001/query, 2,500 free on signup):
   - Search `"{company_name}" site:company website`
   - Parse top results, exclude social/directory domains
   - Add as fallback after Apollo in NAME_AND_COMPANY route

---

## Company Data Sources (Research: `COMPANY_DATA_SOURCES.md`)

### Free Sources for A&D / Medical Device / Industrial
These could be future sourcing channels on `ui/pages/companies.py`:

| Source | API | Data Available | Cost |
|--------|-----|----------------|------|
| SAM.gov | Yes (free) | A&D contractors, NAICS, contract values | Free |
| ThomasNet | Scrape only | 500K manufacturers, certifications | Free |
| Companies House UK | Yes (free) | UK company financials, directors | Free |
| SEC EDGAR | Yes (free) | Supplier mentions in 10-K filings | Free |

### NAICS Codes for Target Industries
Add to `config/settings.py` ICP presets:
- 332710 Machine Shops
- 332999 All Other Miscellaneous Fabricated Metal
- 334511 Search/Navigation Equipment (A&D)
- 336411-336419 Aircraft/Space Vehicle Manufacturing
- 339112 Surgical and Medical Instruments
- 339113 Surgical Appliance and Supplies
- 339114 Dental Equipment and Supplies

---

## Compliance Notes (Research: `COMPLIANCE_AND_REGULATIONS.md`)

### Must-Have for v2.0 (since targeting US/UK/Canada)
1. **CAN-SPAM (US)**: Include physical address + unsubscribe in AI-generated emails
2. **CASL (Canada)**: Flag Canadian contacts — require "conspicuous publication" evidence or implied consent. Add warning in UI before enriching/emailing CA contacts.
3. **UK PECR**: Corporate emails OK, named individuals need legitimate interest basis

### Implementation
- Add `country` check in email generation — if contact is CA, add CASL warning
- AI email templates MUST include: physical address placeholder, unsubscribe link placeholder
- Add suppression/DNC list table in schema (check before enrichment)

---

## UI Improvements (Research: `UI_ARCHITECTURE.md`)

### Key Recommendations
- **AgGrid** for main tables (better than st.dataframe for sorting/filtering/bulk actions)
- **`@st.fragment(run_every=2)`** for real-time enrichment progress polling
- **Threading + `cache_resource`** for background jobs (already partially implemented)
- **Service layer** with zero Streamlit imports for future framework migration

### Add to `requirements.txt`:
```
streamlit-aggrid>=1.0        # advanced data tables
plotly>=5.0                  # dashboard charts
```

---

## Architecture Validations (Research: `SELF_HOSTED_ARCHITECTURE.md`)

### Confirmed Correct
- SQLite with WAL mode ✓
- asyncio + aiosqlite ✓
- httpx shared client ✓
- Circuit breakers ✓
- tenacity for retry ✓
- Write lock (asyncio.Lock) ✓

### Consider Adopting
1. **`__init_subclass__` auto-registration** for providers — zero config when adding new ones
2. **TTL differentiation**: 30 days company, 7-14 days contacts, 90 days patterns (currently all 30 days)
3. **Field-level encryption** for PII (AES-256-GCM) if deploying for multiple users

---

## Outreach.io CSV Export (Research: `OUTREACH_CSV_FORMAT.md`)

### Critical for EMAIL-05

**Import Mechanics:**
- CSV only, UTF-8, max 100,000 rows
- **Email is the primary key** for deduplication
- Dates: YYYY-MM-DD, phones: E.164 format
- Three dupe modes: Skip, Overwrite Existing, Update Missing

**Major Gotchas:**
- **Outreach does NOT support adding to sequences via CSV** — always 2-step (import, then add to sequence via UI/API)
- **Map to "Account" not "Company"** — using "Company" silently fails with zero account associations
- Custom fields use numbered convention: `custom1` through `custom24+`

**Prospect Fields:**
- Identity: First Name, Last Name, Email (required), Title, Company
- 5 phone types: Work, Mobile, Home, Voip, Other
- Full address: Street, City, State, Zip, Country (separate fields)
- Social: LinkedIn URL, Twitter, GitHub, Facebook, etc.
- Tags (comma-separated), Source, Score, Time Zone

**API Alternative (for programmatic sequence assignment):**
- REST API with OAuth 2.0, 10,000 requests/hour
- `POST /api/v2/sequenceStates` to add prospects to sequences
- Requires prospect ID + sequence ID + mailbox ID

**Cross-Platform Export Strategy:**
- Salesloft allows Cadence ID column in CSV
- Apollo allows Sequence column in CSV
- Instantly needs Email as first column
- Build multiple presets: SF_LEAD, OUTREACH, SALESLOFT, APOLLO, INSTANTLY, RAW

---

## Anthropic Batch API (Research: `ANTHROPIC_BATCH_API.md`)

### Critical for EMAIL-03 (Batch Generation)

**Batch API Lifecycle:**
1. Submit: `POST /v1/messages/batches` — up to 100K requests or 256MB per batch
2. Poll: `GET /v1/messages/batches/{id}` — status: in_progress, ended, canceling
3. Retrieve: `GET /v1/messages/batches/{id}/results` — JSONL stream
4. Use `custom_id` on each request to map results back to inputs

**Key Numbers:**
- 50% discount on all tokens vs real-time
- Most batches complete within 1 hour (24-hour SLA)
- Results available for 29 days
- Partial failures handled: succeeded/errored/canceled/expired — only billed for succeeded

**Prompt Caching (stacks with batch discount):**
- Cache reads: 0.1x base input cost (90% off)
- Use 1-hour TTL (`cache_control: {"type": "ephemeral", "ttl": 3600}`) for batches
- Minimum cacheable: 4,096 tokens for Haiku 4.5
- Static system prompt (tone, structure, compliance) = cached across entire batch

**Cost with Haiku 4.5 + Batch + Cache:**
- ~$0.00065 per email
- 1,000 emails: ~$0.65
- 4,000 emails (4-step sequence): ~$2.60
- 10,000 emails: ~$6.50

**Python SDK:**
```python
from anthropic import AsyncAnthropic
client = AsyncAnthropic()

# Submit batch
batch = await client.messages.batches.create(requests=[...])

# Poll
batch = await client.messages.batches.retrieve(batch.id)

# Retrieve results
async for result in client.messages.batches.results(batch.id):
    if result.result.type == "succeeded":
        email_text = result.result.message.content[0].text
```

**Architecture:**
- Batch API for bulk generation (campaign-level)
- Standard Messages API for single-email regeneration during user review
- Store generated emails as drafts in DB → user reviews → approve/edit/regenerate

---

## Docker + Streamlit Deployment (Research: `DOCKER_STREAMLIT_DEPLOYMENT.md`)

### Critical for Phase 13

**Platform Recommendation:**
- **Railway (~$5-7/mo)**: Simplest deploy, persistent volumes ($0.15/GB), brief downtime on redeploy
- **Fly.io (~$3-5/mo)**: Cheapest, better CLI, persistent volumes, daily snapshots
- **DigitalOcean App Platform: NO** — no persistent volumes (can't use SQLite)

**Dockerfile:**
- Base: `python:3.11-slim` (not Alpine — C compilation issues)
- Single-stage is fine
- Health check: `/_stcore/health` (built-in)

**SQLite in Docker:**
- Mount the DIRECTORY not the file — SQLite creates `-wal` and `-shm` companions
- WAL mode works fine on Linux named volumes
- Never `cp` an active DB — use `sqlite3 .backup`
- **Cannot scale to multiple containers** — single container only (fine for internal tool)

**Secrets:**
- Environment variables at runtime (never bake into image)
- Railway/Fly.io both inject env vars natively and support rotation without rebuild

**Production `.streamlit/config.toml`:**
```toml
[server]
headless = true
port = 8501
address = "0.0.0.0"
fileWatcherType = "none"

[browser]
gatherUsageStats = false
```

**Reverse Proxy:** Caddy over Nginx (auto-HTTPS, WebSocket works automatically). Railway/Fly.io handle TLS automatically.

---

## Quick Reference: All 16 Research Files

| File | Use When |
|------|----------|
| `COMPETITIVE_LANDSCAPE.md` | Strategic decisions, feature prioritization |
| `FREE_API_PROVIDERS.md` | Adding new providers, choosing free tiers |
| `SALESFORCE_CSV_EXPORT.md` | Building CSV export, SF field mapping |
| `OUTREACH_CSV_FORMAT.md` | Outreach.io export, cross-platform CSV presets |
| `LINKEDIN_ENRICHMENT.md` | LinkedIn workflow, URL normalization |
| `WATERFALL_OPTIMIZATION.md` | Tuning provider order, catch-all handling |
| `AI_EMAIL_PERSONALIZATION.md` | Phase 12 — prompts, personalization, deliverability |
| `ANTHROPIC_BATCH_API.md` | Phase 12 — batch generation, caching, SDK usage |
| `ICP_SCORING_BEST_PRACTICES.md` | Scoring improvements, EBITDA estimation |
| `EMAIL_VERIFICATION_DEEP_DIVE.md` | Verification pipeline improvements |
| `COMPANY_DATA_SOURCES.md` | New sourcing channels (SAM.gov, ThomasNet) |
| `SELF_HOSTED_ARCHITECTURE.md` | Architecture decisions, scaling guidance |
| `COMPLIANCE_AND_REGULATIONS.md` | Legal requirements per country |
| `UI_ARCHITECTURE.md` | Streamlit patterns, AgGrid, fragments |
| `DOMAIN_FINDING.md` | Domain discovery, DNS guessing, Serper.dev |
| `DOCKER_STREAMLIT_DEPLOYMENT.md` | Phase 13 — Docker, Railway, Fly.io, SQLite persistence |
