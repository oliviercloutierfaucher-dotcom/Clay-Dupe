# Feature Research

**Domain:** B2B Prospecting Platform v2.0 -- Salesforce dedup, AI email generation, company sourcing
**Researched:** 2026-03-07
**Confidence:** MEDIUM-HIGH

---

## Context

This is a **subsequent milestone** for an existing enrichment platform (v1.0 shipped with 14,586 LOC, 277 tests). The core waterfall engine, 5-provider cascade, budget controls, circuit breakers, caching, CSV import/export, Streamlit UI, and CLI are all built. v2.0 transforms the platform from enrichment-only into an end-to-end prospecting tool: source companies, check Salesforce for duplicates, enrich contacts, generate personalized emails, export for Outreach.io.

The three new capability areas are: (1) Salesforce account/contact dedup checking, (2) AI-personalized cold email generation, (3) multi-source company sourcing with company-to-contact pipeline.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist when told "Salesforce dedup, AI emails, company sourcing." Missing these = product feels broken.

#### Salesforce Integration

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Account lookup by domain** | Core dedup mechanism -- match enriched companies against SF Accounts by website field | LOW | SOQL: `SELECT Id, Name, Website FROM Account WHERE Website LIKE '%domain%'`. Use `simple-salesforce` library (Python, well-maintained, supports 3.9-3.13). Already have `company.domain` in data model. |
| **Contact lookup by email** | Prevent emailing existing SF contacts -- the whole point of dedup | LOW | SOQL: `SELECT Id, Email, AccountId FROM Contact WHERE Email = 'x@y.com'`. Batch via `WHERE Email IN (...)` for efficiency (max ~200 values per SOQL query). |
| **Flag duplicate rows in UI** | Users need to see which rows are already in Salesforce before deciding what to do | LOW | Add `sf_account_id`, `sf_contact_id` fields to Person/Company models. Display as color-coded column in Streamlit table (green = new, red = exists in SF). |
| **Skip/include toggle for SF matches** | Some users want to skip duplicates automatically, others want to review first | LOW | Campaign-level setting: `sf_dedup_mode: skip | flag | disabled`. Default to `flag` (safest -- lets user decide). |
| **SF connection settings in UI** | Users must configure SF credentials without editing config files | LOW | Settings page already exists in Streamlit. Add SF credential fields (username, password, security token). Test connection button. Store in env vars or encrypted config. |
| **Bulk dedup check before enrichment** | Check ALL rows against SF BEFORE spending credits -- this is the cost-saving promise | MEDIUM | Batch SOQL queries with chunked `IN` clauses. Run as pre-enrichment pipeline step. This is the key architectural decision: dedup happens BEFORE the waterfall, not after. |

#### AI Email Generation

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Generate personalized email from enriched data** | Core feature -- take person name, title, company info and produce a cold email | MEDIUM | OpenAI API call with structured prompt. Input: Person + Company model fields. Output: subject line + email body. GPT-4o-mini at ~$0.0002/email (500 input + 200 output tokens typical). |
| **Template/prompt customization** | Users have different value props, tones, CTAs -- one template = useless | MEDIUM | User-editable prompt template with variables: `{{first_name}}`, `{{company_name}}`, `{{industry}}`, `{{title}}`, `{{employee_count}}`, `{{city}}`. Store templates in DB. Provide 2-3 starter templates. |
| **Batch generation for entire campaign** | Nobody generates emails one at a time for 500+ contacts | MEDIUM | Async batch with rate limiting. OpenAI allows high concurrency on GPT-4o-mini. Chunk into batches of 50, write results back to DB. Reuse existing campaign/batch infrastructure. |
| **Preview before export** | Users MUST review AI-generated emails -- hallucinations happen | LOW | Display generated subject + body in expandable row in Streamlit results table. Inline edit button for manual tweaks before export. |
| **Export to Outreach-ready CSV** | Outreach.io import requires specific columns | LOW | Extend existing CSV export with email_subject and email_body columns. Match Outreach.io import format: email, first_name, last_name, subject, body. |

#### Company Sourcing

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Apollo company search with filters** | Already have `search_companies` in Apollo provider -- expose in UI | LOW | Method exists. Wire to UI with filter form: employee count range, location, industry/keyword tags. Apollo company search is FREE (no credits consumed). |
| **CSV import for company lists** | Already built for contacts -- extend to company-first workflow | LOW | Existing CSV import + fuzzy column mapping. Add flow: import companies -> find contacts -> enrich contacts. Minor: need column mapping for Company fields (name, domain, industry). |
| **Manual company add** | Quick-add for individually discovered companies | LOW | Simple form: company name, domain, industry, employee count. Create Company record, queue for contact discovery. |
| **Company-to-contact discovery** | After sourcing companies, find decision-maker contacts | MEDIUM | Use Apollo `search_people` (already built, FREE with master key) filtered by company domain + title/seniority filters. Then enrich found contacts via existing waterfall. This is the key pipeline link. |
| **Source tracking** | Know where each company came from | LOW | Already have `source_provider` on Company model. Add `source_type` enum: `apollo_search`, `csv_import`, `manual`. |

### Differentiators (Competitive Advantage)

Features that set this apart from Clay ($149-800/mo) or manual Apollo + spreadsheet workflows.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Pre-enrichment SF dedup (cost savings)** | Check SF BEFORE burning enrichment credits. Clay enriches first, then you discover duplicates and waste credits. This saves real money at scale. | MEDIUM | Unique selling point. For 10K contacts at ~$0.05/contact avg, skipping 30% known SF contacts saves ~$150/run. Pays for itself immediately. |
| **End-to-end pipeline in one tool** | Source -> dedup SF -> enrich -> generate emails -> export. No more 5-tab, 3-tool workflow (Apollo search + Clay enrich + ChatGPT emails + manual dedup). | HIGH | Orchestration capstone. Build individual components first, wire together last. |
| **Cost-per-lead tracking end-to-end** | Track total cost from sourcing through enrichment through email generation per lead. No other self-hosted tool does this. | LOW | Already have cost tracking per enrichment. Add OpenAI token cost (~$0.0002/email). Sum per person_id across all operations. |
| **Confidence-aware email personalization** | Use enrichment confidence scores to adjust email specificity. High-confidence data = reference specific title/industry. Low-confidence = safer generic hooks. | LOW | Pass confidence_score into prompt template. Conditional logic: "If confidence > 80, reference {{title}} at {{company_name}}. Otherwise, use general language." Personalized emails get 46% open rate vs 35% generic. |
| **ICP scoring from enriched data** | Auto-score companies against Ideal Customer Profile (1-15M EBITDA, 10-100 employees, A&D/medical/industrial). Filter before spending credits on contact enrichment. | MEDIUM | Rule-based scoring using Company model fields: employee_count, revenue_usd, industry match against user-defined ICP criteria. Score 0-100. |
| **Micro-campaign auto-segmentation** | Auto-group sourced companies into 10-20 person micro-campaigns by industry/size for hyper-personalized outreach | MEDIUM | Research shows micro-campaigns (10-20 recipients) achieve 18% response rates vs 2.1% for 500+ recipient blasts (5x improvement). Cluster companies by industry + employee_range, generate campaign-specific prompt variations. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Bidirectional Salesforce sync** | "Push enriched data back to SF automatically" | Write access to production SF is dangerous -- data quality issues, field mapping complexity, overwriting existing data, SF admin approval required. Massive scope increase for v2.0. | Read-only SF check for v2.0. Export CSV that SF admins import via Data Loader with their own field mapping. Revisit SF write-back in v3.0 with proper field mapping UI and sandbox testing. |
| **Full AI autonomy (no human review)** | "Just generate and send emails automatically" | AI hallucinations, wrong tone, factual errors about the company. One bad email to a prospect = burned relationship. Research: 67% of decision makers accept AI emails ONLY if relevant and credible. | Generate + review workflow. Always require human approval before export. Flag low-confidence generations with warning icons. |
| **Multi-LLM provider support** | "Support Claude, GPT, Gemini, Llama for email gen" | Complexity explosion -- different prompt formats, quality levels, pricing. Testing matrix grows 3-4x for marginal benefit. | Use OpenAI GPT-4o-mini only: cheapest ($0.15/M input, $0.60/M output tokens), fast, good enough for cold email. Abstract the interface (base class + generate method) so swapping providers later is a config change, but ship with one. |
| **Real-time Salesforce webhooks** | "Get notified when new SF accounts are created so we skip them instantly" | Requires SF admin setup (Outbound Messages or Platform Events), webhook server, always-on infrastructure. Way beyond self-hosted SQLite tool scope. | Batch SF check before each enrichment run. Cache SF results for 24h. Good enough for prospecting cadence -- nobody prospects the same list hourly. |
| **Additional sourcing providers (Grata, Inven, Ocean.io)** | "More sources = better company discovery" | Each provider has different API, auth, data format, pricing. Apollo search is free and sufficient for v2.0 target ICP. | Ship with Apollo search + CSV import. These cover 90%+ of use cases for niche industrial prospecting. Add Grata/Inven as v3.0 sourcing providers only if Apollo data gaps emerge with real usage. |
| **Email sending from the platform** | "Send emails directly, not just generate them" | Deliverability management (SPF, DKIM, DMARC, warm-up), bounce handling, reputation management is an entire product category (Outreach, Salesloft, Smartlead). | Generate Outreach.io-compatible CSV. Users import into their existing sending infrastructure. Keeps platform focused on sourcing + enrichment + generation. |
| **Company enrichment from multiple providers** | "Waterfall for company data too, not just contacts" | Company data is less variable across providers than contact data. Apollo company search returns sufficient fields for ICP scoring and email personalization context. Diminishing returns vs contact waterfall. | Apollo company enrich (already built, 1 credit) for gaps. Add company waterfall only if Apollo company data proves insufficient for email personalization quality. |

---

## Feature Dependencies

```
[SF Connection Settings]
    |
    v
[SF Account Lookup by Domain] + [SF Contact Lookup by Email]
    |
    v
[Batch Pre-enrichment SF Dedup] ----requires----> [Existing Waterfall Engine]
    |
    v
[Flag/Skip Duplicates in UI]


[Apollo Company Search UI] ----requires----> [Existing Apollo Provider]
    |
    v
[Company-to-Contact Discovery] ----requires----> [Existing Apollo search_people]
    |
    v
[Contact Enrichment via Waterfall] <------------- [Existing Waterfall Engine]


[OpenAI API Integration]
    |
    v
[Prompt Template System]
    |
    v
[Email Generation] ----requires----> [Enriched Person + Company data]
    |
    v
[Email Preview/Edit in UI]
    |
    v
[Export to Outreach-ready CSV] ----requires----> [Existing CSV Export]


[End-to-End Pipeline Orchestration] ----requires----> ALL ABOVE COMPONENTS
```

### Dependency Notes

- **SF Dedup requires SF Connection first:** Must configure and test SF credentials before any dedup logic works. Build connection/auth as the foundation.
- **Company-to-Contact Discovery requires Apollo search_people:** Already built in v1.0. Just needs UI wiring and orchestration to pipe company domains into people search filters.
- **AI Email Generation requires enriched data:** Must have Person + Company data populated (from enrichment). Runs AFTER the waterfall completes, not before.
- **End-to-End Pipeline Orchestration requires ALL components:** This is the capstone feature. Every individual component must work standalone before wiring together. Build last.
- **Pre-enrichment SF Dedup hooks into existing campaign pipeline:** New pre-processing step inserted between CSV import/company sourcing and waterfall dispatch. Must not break existing campaign flow.

---

## MVP Definition

### v2.0 Launch With (Core Pipeline)

Minimum features that deliver the "source -> dedup -> enrich -> email -> export" promise.

- [ ] **SF Connection + Auth** -- simple-salesforce, username/password/security-token auth, test connection button in Settings page. Foundation for all dedup.
- [ ] **Batch SF Dedup Check** -- Query SF Accounts by domain and Contacts by email before enrichment. Flag matches in UI. Campaign-level skip/flag/disabled setting.
- [ ] **Apollo Company Search UI** -- Expose existing `search_companies` with filter form (employee range, location, industry keywords). Save results as Company records in DB.
- [ ] **Company-to-Contact Discovery** -- Given sourced companies, find decision-makers via Apollo `search_people` (FREE). Filter by title/seniority. Queue found contacts for enrichment.
- [ ] **OpenAI Email Generation** -- GPT-4o-mini integration via `openai` Python package. User-editable prompt template with variable substitution. Batch generation for campaigns.
- [ ] **Email Preview + Outreach Export** -- View generated emails in expandable UI rows. Inline edit. CSV export with email, first_name, last_name, subject, body columns.

### Add After Validation (v2.x)

Features to add once core pipeline works with real data and real API keys.

- [ ] **ICP Scoring** -- Auto-score companies against ideal customer profile criteria. Add when: users manually filtering companies and wanting automation.
- [ ] **Micro-campaign Auto-segmentation** -- Group companies into targeted micro-campaigns by industry/size. Add when: users creating 10+ similar campaigns manually.
- [ ] **Confidence-aware Email Tone** -- Adjust email specificity based on enrichment confidence. Add when: users complaining about generic-sounding emails for well-known contacts.
- [ ] **SF Result Caching** -- Cache SF dedup results for 24h to avoid repeated SOQL queries. Add when: re-running campaigns against same company lists.
- [ ] **Multiple Saved Email Templates** -- Save/load different prompt templates for different industries or use cases. Add when: users copy-pasting prompts between campaigns.
- [ ] **Cost-per-lead Dashboard** -- Aggregate sourcing + enrichment + email gen costs per lead. Add when: users asking "what does each lead actually cost me?"

### Future Consideration (v3.0+)

Defer until v2.0 is validated with real prospecting workflows.

- [ ] **Salesforce Write-back** -- Push enriched contacts into SF as Leads. Defer: requires field mapping UI, data quality guarantees, SF admin cooperation, sandbox testing.
- [ ] **Additional Sourcing Providers** -- Grata, Inven, Ocean.io integration. Defer: Apollo + CSV covers initial ICP. Add when Apollo data gaps are documented.
- [ ] **Multi-LLM Support** -- Claude, Gemini alternatives. Defer: GPT-4o-mini is cheapest and sufficient. Interface is abstracted, swap is a config change.
- [ ] **Outreach.io API Integration** -- Direct push to sequences. Defer: Outreach API requires OAuth per customer, complex setup. CSV import is sufficient.
- [ ] **Email A/B Testing** -- Generate multiple email variants per contact, track which performs better. Defer: requires sending infrastructure integration to track opens/replies.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Depends On |
|---------|------------|---------------------|----------|------------|
| SF Connection + Auth | HIGH | LOW | P1 | Nothing (new) |
| SF Account Lookup by Domain | HIGH | LOW | P1 | SF Connection |
| SF Contact Lookup by Email | HIGH | LOW | P1 | SF Connection |
| Batch Pre-enrichment SF Dedup | HIGH | MEDIUM | P1 | SF Lookups |
| Flag/Skip Duplicates in UI | HIGH | LOW | P1 | SF Dedup |
| Apollo Company Search UI | HIGH | LOW | P1 | Existing Apollo provider |
| Company-to-Contact Discovery | HIGH | MEDIUM | P1 | Apollo search UI |
| OpenAI Integration + Email Gen | HIGH | MEDIUM | P1 | Enriched data |
| Prompt Template System | HIGH | MEDIUM | P1 | OpenAI integration |
| Batch Email Generation | HIGH | MEDIUM | P1 | Email gen + templates |
| Email Preview in UI | MEDIUM | LOW | P1 | Email generation |
| Outreach-ready CSV Export | HIGH | LOW | P1 | Email generation |
| Manual Company Add | MEDIUM | LOW | P2 | Company model |
| ICP Scoring | MEDIUM | MEDIUM | P2 | Company data |
| Cost-per-lead Tracking | MEDIUM | LOW | P2 | Existing cost tracker |
| Micro-campaign Segmentation | MEDIUM | MEDIUM | P2 | Company sourcing |
| Multiple Email Templates | MEDIUM | LOW | P2 | Template system |
| SF Result Caching | LOW | LOW | P3 | SF dedup |
| Confidence-aware Email Tone | LOW | LOW | P3 | Email gen + confidence |

**Priority key:**
- P1: Must have for v2.0 launch -- delivers the core "source -> dedup -> enrich -> email" promise
- P2: Should have, add in v2.x when core pipeline is validated with real data
- P3: Nice to have, add when specific pain points emerge from usage

---

## Competitor Feature Analysis

| Feature | Clay.com ($149-800/mo) | Apollo.io (standalone, $49-119/mo) | Our Platform (self-hosted, API costs only) |
|---------|------------------------|------------------------------------|--------------------------------------------|
| Company Sourcing | 100+ data sources, waterfall across all | Built-in search (free), 275M+ database | Apollo search (free) + CSV import. Sufficient for niche A&D/medical/industrial ICP. |
| Salesforce Dedup | CRM integration add-on, checks AFTER enrichment | Basic CRM sync, not pre-enrichment | Pre-enrichment dedup via SOQL. Check BEFORE spending credits. Direct cost savings. |
| AI Email Generation | Claygent + GPT-4 integration, custom prompts | AI messaging in paid plans only | GPT-4o-mini with user-editable templates. ~$0.0002/email. No platform subscription. |
| Email Personalization | Deep personalization from 100+ enrichment fields | Basic merge fields from Apollo data | Personalization from enriched Company + Person fields (5 providers). Confidence-aware tone. |
| Waterfall Enrichment | 100+ providers, automatic fallback | Single-source (Apollo data only) | 4-provider waterfall: Apollo -> Icypeas -> Findymail -> Datagma. 92-95% find rate. |
| End-to-End Pipeline | Full pipeline in one platform | Search -> partial enrich, separate tools for email/dedup | Source -> dedup SF -> enrich -> generate email -> export. One pipeline. |
| Pricing | $149-800/mo PLUS per-credit enrichment costs | $49-119/mo + API credits | Self-hosted: ~$466/mo for 10K contacts (API credits only). No platform subscription fee. |
| Data Privacy | SaaS -- prospect data on Clay servers | SaaS -- data on Apollo servers | Self-hosted -- prospect data stays on your infrastructure. Critical for teams with sensitive ICP lists. |

**Key competitive insight:** Clay is the feature-rich incumbent but costs $149-800/mo on top of enrichment credits. Apollo standalone lacks email generation and multi-provider enrichment. Our platform's sweet spot is: self-hosted cost savings + pre-enrichment SF dedup (saves credits) + end-to-end pipeline in one tool for teams prospecting niche verticals.

---

## Implementation Cost Estimates

| Component | New Code Estimate | Key Libraries | Notes |
|-----------|-------------------|---------------|-------|
| SF Integration | ~400-600 LOC | `simple-salesforce` | Connection manager, SOQL query builder, batch chunker, settings UI |
| AI Email Generation | ~500-700 LOC | `openai` | OpenAI client, prompt template engine, batch generator, preview UI |
| Company Sourcing UI | ~300-400 LOC | Existing Apollo provider | Filter form, results display, company-to-contact flow, manual add form |
| Pipeline Orchestration | ~400-600 LOC | Existing waterfall engine | Step sequencing: source -> dedup -> enrich -> generate -> export |
| Model Extensions | ~100-200 LOC | Existing Pydantic models | New fields on Person/Company, new EmailDraft model, SF match fields |
| Tests | ~500-800 LOC | pytest, pytest-asyncio | Unit tests for each component, integration tests for pipeline |
| **Total** | **~2,200-3,300 LOC** | | Roughly 15-23% of existing v1.0 codebase size |

---

## Sources

- [Salesforce findDuplicates API](https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_calls_findduplicates.htm) -- Official SF duplicate detection endpoint
- [simple-salesforce Documentation](https://simple-salesforce.readthedocs.io/en/latest/) -- Python SF REST client, SOQL query support
- [simple-salesforce PyPI](https://pypi.org/project/simple-salesforce/) -- Supports Python 3.9-3.13
- [SOQL for Duplicate Accounts](https://coefficient.io/use-cases/soql-queries-duplicate-accounts-salesforce) -- SOQL patterns for Account/Contact matching by domain/email
- [Salesforce Duplicate Rules Guide](https://www.salesforceben.com/salesforce-duplicate-rules/) -- How SF native dedup matching rules work
- [Apollo Organization Search API](https://docs.apollo.io/reference/organization-search) -- Company search endpoint, filters, free credits
- [Apollo People Search API](https://docs.apollo.io/reference/people-api-search) -- People search endpoint, title/seniority filters
- [Apollo Search Filters Overview](https://knowledge.apollo.io/hc/en-us/articles/4412665755661-Search-Filters-Overview) -- Available search filters by plan
- [Hunter.io AI Cold Email Guide](https://hunter.io/ai-cold-email-guide) -- AI email generation best practices 2025
- [MarketBetter: AI Email Personalization at Scale](https://marketbetter.ai/blog/ai-email-personalization-scale/) -- Signal-based personalization, 18% response rates
- [Autobound Cold Email Guide 2026](https://www.autobound.ai/blog/cold-email-guide-2026) -- Micro-campaigns (10-20 recipients) vs large blasts
- [Cold Email Statistics 2025 - SalesCaptain](https://www.salescaptain.io/blog/cold-email-statistics) -- Personalized subject lines: 46% open rate
- [B2B Cold Email Benchmarks 2025](https://remotereps247.com/b2b-cold-email-benchmarks-2025-response-rates-by-industry/) -- Response rates by industry
- [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing) -- GPT-4o-mini: $0.15/M input, $0.60/M output tokens
- [Clay.com Platform](https://www.clay.com) -- Competitor: 100+ data sources, waterfall enrichment
- [Clay AI Review - Digital Bloom](https://thedigitalbloom.com/learn/clay-platform-review/) -- Feature breakdown, Claygent AI agent, pricing tiers
- [Clay Reviews on G2](https://www.g2.com/products/clay-com-clay/reviews) -- User feedback, pricing complaints

---
*Feature research for: B2B Prospecting Platform v2.0 (Salesforce dedup, AI email gen, company sourcing)*
*Researched: 2026-03-07*
