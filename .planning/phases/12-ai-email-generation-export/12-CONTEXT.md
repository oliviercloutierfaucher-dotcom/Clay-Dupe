# Phase 12: AI Email Generation + Export - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate personalized cold emails from enriched contact/company data using Claude AI. Users can create prompt templates with variable substitution, batch-generate emails for campaigns, preview/edit/approve before export, and export as Outreach.io-ready CSV. No email sending from the platform — generation and export only.

</domain>

<decisions>
## Implementation Decisions

### Email Tone & Cadence
- **Consultative tone** as default — fits niche B2B targeting CEOs/Owners of small manufacturers
- **3-step sequence**: Intro (value prop), Follow-up (case study/social proof), Breakup (last chance)
- Research shows 70% of responses from emails 2-4, so multi-step is essential
- Each sequence step is a separate generation with awareness of prior steps
- **120 words max** per email — research-backed optimal length for cold B2B
- Templates include: physical address placeholder + unsubscribe link placeholder (CAN-SPAM/CASL compliance)

### Template & Variable System
- **Global templates** — not per-campaign or per-industry (keep simple for v2.0)
- 3 pre-built starter templates: "Consultative Intro", "Case Study Follow-up", "Breakup"
- Users can create custom templates with a system prompt + user prompt template
- **Variable placeholders** use `{variable}` syntax in templates:
  - Contact: `{first_name}`, `{last_name}`, `{title}`, `{company_name}`
  - Company: `{industry}`, `{employee_count}`, `{city}`, `{state}`, `{country}`, `{description}`, `{founded_year}`
  - ICP: `{icp_score}`, `{quality_tier}` (Gold/Silver/Bronze)
  - Custom: `{portfolio}`, `{vertical}` (user-provided fields from enrichment)
- Templates stored in SQLite (new `email_templates` table)
- Model selection: Claude Haiku 4.5 for all emails (cost-effective at ~$0.53/1K with caching)

### Preview & Approval Workflow
- **New UI page**: `ui/pages/emails.py` added to navigation under Tools section
- Flow: Select campaign → Choose template → Generate (single or batch) → Preview → Edit → Approve/Reject → Export
- **Table view** of generated emails with columns: Contact, Company, Subject, Status (draft/approved/rejected)
- Click row to expand inline preview with full email body
- **Edit inline** — user can modify subject and body directly in the preview
- **Bulk actions**: Approve All, Reject All, Regenerate Selected
- **Regenerate** individual emails with optional user note ("make it shorter", "mention their certification")
- Status flow: draft → approved / rejected. Only approved emails appear in export.
- Batch generation shows progress bar (reuse `@st.fragment(run_every=2)` pattern from enrich page)

### Export Format & Destination
- **Primary export**: Outreach.io CSV with columns: `Email`, `First Name`, `Last Name`, `Company`, `Subject`, `Body`, `Sequence Step`
- **Secondary export**: Salesforce Lead CSV using field mapping from research (Company, Website, Quality__c, FirstName, LastName, Title, Email, City, State, Country)
- **Raw export**: All fields, all emails (including rejected) for audit
- Export presets as dropdown on emails page: "Outreach.io", "Salesforce Lead", "Raw"
- Each sequence step is a separate row in Outreach CSV (Step 1, Step 2, Step 3)
- Download via `st.download_button()` — existing pattern

### Claude's Discretion
- Exact prompt engineering for each starter template
- Batch processing chunk size and concurrency
- How to handle generation failures (retry logic, partial results)
- Email subject line generation approach
- Loading skeleton / progress UI specifics
- Whether to use Anthropic Batch API or sequential calls (depends on volume expectations)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data/models.py`: Person (first_name, last_name, title, company_name), Company (industry, employee_count, city, description, icp_score) — all personalization variables already exist
- `data/database.py`: `get_enrichment_results(campaign_id=...)` — fetches enriched data per campaign
- `ui/pages/results.py`: CSV/Excel export with `st.download_button()` — extend pattern for email export
- `ui/pages/enrich.py`: Background thread + `@st.fragment(run_every=2)` polling — reuse for batch generation progress
- `data/io.py`: `ColumnMapper` — could inform export field mapping
- `cost/tracker.py`: Credit tracking per provider — extend for AI generation costs

### Established Patterns
- Background processing: `threading.Thread(target=fn, daemon=True)` with session_state tracking
- Progress polling: `@st.fragment(run_every=2.0)` auto-refreshing fragment
- Campaign model: tracks status (CREATED→RUNNING→COMPLETED), row counts, cost breakdown
- Settings via .env + `load_settings()` — add ANTHROPIC_API_KEY
- All models are Pydantic BaseModel with JSON serialization

### Integration Points
- Navigation: Add `st.Page("pages/emails.py")` to Tools section in `ui/app.py`
- Dependencies: Add `anthropic>=0.40` to requirements.txt + pyproject.toml
- Database: New tables `email_templates` and `generated_emails`
- Settings: Add Anthropic API key field to settings page
- Campaign link: Generated emails reference `campaign_id` to connect back to enrichment data

</code_context>

<specifics>
## Specific Ideas

- Research recommends hybrid approach (AI personalization + structural variation) to avoid Gmail's Gemini AI semantic spam filtering
- For niche B2B targeting small manufacturers, consultative tone works best — these are relationship-based buyers, not transactional
- CASL (Canada) requires opt-in — generated emails should include a CASL warning flag for Canadian contacts
- Cost is negligible: 1,000 contacts x 3-step sequence = 3,000 generations ≈ $2-4 with Claude Haiku

</specifics>

<deferred>
## Deferred Ideas

- **Multi-model support** (Sonnet for Gold tier, Haiku for rest) — v2.x optimization after baseline works
- **A/B testing email variants** — generate 2 versions per contact, track which performs better
- **Email sending from platform** — explicitly out of scope, Outreach handles deliverability
- **Outreach.io API integration** (OUT-01) — v3.0, direct push to sequences
- **Cost-per-lead tracking across full pipeline** (EMAIL-08) — v2.x
- **Multiple saved prompt template libraries** (EMAIL-07) — v2.x

</deferred>

---

*Phase: 12-ai-email-generation-export*
*Context gathered: 2026-03-08*
