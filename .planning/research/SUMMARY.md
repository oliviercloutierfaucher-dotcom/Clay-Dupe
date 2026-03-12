# Project Research Summary

**Project:** Clay-Dupe v2.0 -- Salesforce Integration, AI Email Generation, Company Sourcing
**Domain:** B2B prospecting platform (extending existing enrichment engine to end-to-end pipeline)
**Researched:** 2026-03-07
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a v2.0 expansion of a production-validated B2B enrichment platform (14,586 LOC, 277 tests, 5-provider waterfall). The goal is to transform it from enrichment-only into a full prospecting pipeline: source companies, check Salesforce for duplicates before spending credits, enrich contacts, generate personalized cold emails, and export for Outreach.io. The existing async architecture (httpx, aiosqlite, aiometer, Streamlit, Typer) is solid and extensible. Only two new dependencies are needed: `simple-salesforce` for CRM dedup and `anthropic` SDK for AI email generation. Jinja2 comes free via Streamlit.

The recommended approach is a three-phase build following the data flow: Sourcing first (creates the input data), Salesforce dedup second (gates the enrichment), AI email generation last (consumes enriched output). Each phase is independently deployable and testable with real data. Architecture research confirms three clean integration patterns: upstream sourcing, pre-enrichment gate, and post-enrichment processor -- none of which require modifying the core waterfall logic beyond a single injection point for the SF checker.

The primary risks are: (1) Salesforce OAuth token lifecycle is more complex than it appears -- tokens rotate on refresh since Spring 2024 and must be persisted immediately, (2) AI-generated emails hallucinate company facts ~15% of the time, which is catastrophic for B2B credibility -- constrained prompts and mandatory human review are non-negotiable, (3) SQLite write contention will emerge when multiple v2.0 features write concurrently -- a write queue must be implemented before adding new write paths. All three risks have well-documented prevention strategies detailed in PITFALLS.md.

---

## Key Findings

### Recommended Stack

The v2.0 stack adds only two direct dependencies to the existing codebase, keeping the footprint minimal.

**Core technologies:**
- **simple-salesforce >=1.12.9**: Salesforce REST API client for SOQL dedup queries -- most mature Python SF library (5K+ stars), handles OAuth and session management out of the box. Synchronous (uses `requests`), but acceptable since SF checks are batch pre-enrichment, not per-row. Isolate from httpx stack.
- **anthropic >=0.84.0**: Claude API SDK for personalized email generation -- uses httpx internally (aligns with existing stack), Pydantic v2 typed responses. Claude 3.5 Haiku at ~$0.0005/email (~$5/month for 10K contacts). Chosen over OpenAI for lower hallucination rates on factual company data, which is critical for B2B outreach referencing real enrichment data.
- **jinja2 >=3.1**: Email template rendering -- already installed as Streamlit transitive dependency. Separates email structure (user-editable templates) from AI personalization.

**Critical "do not add" list:** langchain (overkill), celery/redis (unnecessary for team-scale), salesforce-bulk (we only read hundreds of records), requests explicitly (let it come only via simple-salesforce).

**Research discrepancy noted:** FEATURES.md and ARCHITECTURE.md reference OpenAI/GPT-4o-mini for email generation, while STACK.md recommends Anthropic/Claude after deeper analysis. **Recommendation: use Anthropic SDK with Claude 3.5 Haiku.** Rationale: lower hallucination on factual data, httpx alignment, comparable cost ($0.0005 vs $0.0004/email). Abstract the LLM interface so swapping is a config change if needed.

See `.planning/research/STACK.md` for full installation instructions, version compatibility matrix, and alternatives considered.

### Expected Features

**Must have (table stakes):**
- SF account lookup by domain + contact lookup by email (batch SOQL with IN clauses)
- Bulk pre-enrichment SF dedup with skip/flag/disabled modes
- SF duplicate flags visible in UI (color-coded status column)
- SF connection settings in Streamlit settings page
- Apollo company search with ICP filters exposed in UI
- Company-to-contact discovery (Apollo search_people, FREE)
- AI-personalized email generation from enriched data with editable templates
- Batch email generation with rate limiting
- Email preview/edit in UI before export
- Outreach.io-ready CSV export with email columns

**Should have (differentiators):**
- Pre-enrichment SF dedup as cost-saving mechanism (~$150 saved per 10K run at 30% duplicate rate)
- ICP scoring from enriched company data (rule-based, 0-100 score)
- Micro-campaign auto-segmentation (10-20 person groups by industry/size)
- Confidence-aware email personalization (adjust specificity based on enrichment confidence)
- End-to-end cost-per-lead tracking

**Defer to v3.0+:**
- Bidirectional Salesforce sync (write-back) -- dangerous scope increase, requires field mapping UI
- Multi-LLM provider support -- abstract the interface but ship with one provider
- Email sending from platform -- stay focused on generation, let Outreach handle deliverability
- Additional sourcing providers (Grata, Inven) -- Apollo + CSV covers 90%+ of use cases
- Real-time Salesforce webhooks -- batch check before each run is sufficient

See `.planning/research/FEATURES.md` for full competitor analysis, dependency graph, and implementation cost estimates.

### Architecture Approach

Three new top-level packages (`integrations/`, `outreach/`, `sourcing/`) plug into the existing architecture at distinct pipeline stages. The Salesforce checker is NOT a BaseProvider -- it is a pre-enrichment gate injected as an optional dependency into WaterfallOrchestrator. The email generator is a post-enrichment processor that reads from companies/people tables and writes to its own email_drafts table. Company sourcing wraps existing Apollo methods with ICP filtering and persists to existing tables. Each component owns its own external API connection.

**Major components:**
1. **SourcingPipeline** (`sourcing/`) -- Apollo search, CSV import, manual add. Produces Company/Person records. Wraps existing provider methods.
2. **SalesforceChecker** (`integrations/`) -- Read-only SOQL queries for account/contact dedup. Batch pre-fetch with in-memory cache. Configurable skip/flag/off strategy per campaign.
3. **EmailGenerator** (`outreach/`) -- Anthropic AsyncClient for personalized cold emails. Jinja2 templates for structure. Rate-limited via aiometer. Results cached in email_drafts table.

**Schema changes:** New `email_drafts` table, new `salesforce_config` table, SF status columns on `people` and `companies` tables.

**Estimated new code:** ~2,200-3,300 LOC (15-23% of v1.0 codebase), plus ~500-800 LOC tests.

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, component designs, and anti-patterns to avoid.

### Critical Pitfalls

1. **Salesforce OAuth token rotation** -- Since Spring 2024, SF issues NEW refresh tokens on each refresh, revoking the old one. Must persist new refresh token immediately after each refresh, before using the access token. Store tokens encrypted in SQLite, not in .env or session state.
2. **AI email hallucination** -- LLMs fabricate company facts ~15% of the time. Constrain prompts to ONLY reference provided data fields, use temperature 0.3-0.5, add post-generation validation that checks every proper noun against input data. Never skip human review.
3. **SQLite write contention** -- v2.0 introduces 4+ concurrent write paths. Implement a single async write queue before adding new features. Set busy_timeout to 5000ms minimum. Keep write transactions short.
4. **SF dedup false negatives** -- Exact-match-only catches <60% of real duplicates. Match on multiple fields with scoring: domain (primary), normalized company name (fuzzy 85%), email, LinkedIn URL. Surface uncertain matches (50-85% score) for human review.
5. **Streamlit OAuth callback failure** -- Streamlit cannot handle OAuth redirects natively. Use JWT Bearer flow (no redirect) or a separate FastAPI endpoint for the OAuth dance. Do NOT implement OAuth callback inside Streamlit.
6. **Company sourcing duplicates** -- Multi-source ingestion creates duplicate company records without ingestion-time dedup. Use normalized domain as unique constraint, fuzzy name match as secondary.

See `.planning/research/PITFALLS.md` for full technical debt patterns, security mistakes, UX pitfalls, and recovery strategies.

---

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Company Sourcing + Infrastructure Prep

**Rationale:** Creates the input data that everything else depends on. Lowest technical risk -- wraps existing Apollo methods. Also the right time to implement the SQLite write queue before adding more write-heavy features.

**Delivers:** Apollo company search UI with ICP filters, company-to-contact discovery, CSV import for companies, manual add, source tracking. Write queue infrastructure.

**Addresses:** Company sourcing table stakes, source tracking, company dedup at ingestion

**Avoids:** Pitfall 7 (company sourcing duplicates) -- build ingestion-time dedup from day one. Pitfall 2 (SQLite write contention) -- implement write queue before adding SF and email write paths.

**Estimated scope:** ~5-8 new files, `sourcing/` package, UI page, minimal modification to existing files.

### Phase 2: Salesforce Integration

**Rationale:** Requires companies/people in DB (Phase 1 provides). Must be integrated before email generation so users know which contacts are SF duplicates before generating emails. Core cost-saving value proposition.

**Delivers:** SF connection/auth with encrypted token storage, batch SOQL dedup, skip/flag/disabled modes, SF status in enrich UI, settings page integration.

**Uses:** simple-salesforce, `integrations/` package

**Implements:** Pre-Enrichment Gate pattern (SalesforceChecker injected into WaterfallOrchestrator)

**Avoids:** Pitfall 1 (OAuth token lifecycle) -- build token persistence and health checks from the start. Pitfall 4 (dedup false negatives) -- multi-field matching with scoring. Pitfall 5 (Streamlit OAuth) -- use JWT Bearer or separate endpoint.

**Estimated scope:** ~4-5 new files, modifications to waterfall.py, settings.py, models.py, schema.sql, database.py, 2 UI pages.

### Phase 3: AI Email Generation + Export

**Rationale:** Consumes output of both sourcing and enrichment. Depends on SF status to avoid generating emails for duplicates. Final piece of the end-to-end pipeline.

**Delivers:** Anthropic-powered email generation, Jinja2 template system, batch generation with aiometer rate limiting, email preview/edit in UI, Outreach.io CSV export with email columns.

**Uses:** anthropic SDK, jinja2, `outreach/` package

**Implements:** Post-Enrichment Processor pattern (EmailGenerator reads enriched data, writes to email_drafts)

**Avoids:** Pitfall 3 (AI hallucination) -- constrained prompts, fact anchoring, mandatory human review. Pitfall 6 (spam triggers) -- banned phrases, short emails, spam score heuristic.

**Estimated scope:** ~5-6 new files, new UI page, schema changes, export extension.

### Phase 4: Pipeline Orchestration + Differentiators

**Rationale:** Capstone phase -- wire all components into the end-to-end "source -> dedup -> enrich -> email -> export" flow. Add differentiator features once core pipeline is validated with real data.

**Delivers:** End-to-end pipeline orchestration, ICP scoring, micro-campaign segmentation, confidence-aware email tone, cost-per-lead tracking.

**Addresses:** All differentiator features from FEATURES.md

**Note:** Consider splitting into two sub-phases: orchestration first (critical), then differentiators (iterative based on user feedback).

### Phase Ordering Rationale

- **Sourcing before Salesforce:** SF dedup needs data to check against. Without sourced companies, there is nothing to query.
- **Salesforce before AI Email:** Generating emails for SF duplicates wastes LLM tokens and creates confusing output. Users must see dedup status first.
- **Each phase independently deployable:** Phase 1 is useful alone (better company discovery). Phase 2 adds value without Phase 3 (credit savings from dedup). This enables real-data validation between phases.
- **Infrastructure (write queue) in Phase 1:** Prevents the write contention pitfall from manifesting when Phases 2-3 add concurrent write paths.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Salesforce):** OAuth flow choice (JWT Bearer vs username/password vs OAuth callback) depends on customer's Salesforce edition and admin access. Fuzzy dedup matching thresholds need calibration with real SF data.
- **Phase 3 (AI Email):** Prompt engineering for cold emails is an active field with rapidly changing best practices. Template design needs A/B testing with real prospect data. Spam scoring heuristics need validation against current Gmail/Outlook filters.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Company Sourcing):** Wraps existing Apollo API methods. Well-documented patterns. CSV import already proven in v1.0.
- **Phase 4 (Pipeline Orchestration):** Application-level wiring of completed components. No novel technical challenges.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Only 2 new dependencies, both mature and well-documented. Version compatibility verified against existing httpx/Pydantic stack. |
| Features | MEDIUM-HIGH | Table stakes well-defined from competitor analysis (Clay, Apollo). Differentiators need real-user validation after MVP. |
| Architecture | HIGH | Integration points derived from direct codebase analysis. Three clean patterns (upstream, gate, processor) with no waterfall restructuring. |
| Pitfalls | MEDIUM-HIGH | Salesforce and SQLite pitfalls well-documented with multiple sources. AI email pitfalls based on 2025-2026 data, still evolving as spam filters adapt. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **LLM provider alignment:** STACK.md recommends Claude, FEATURES.md/ARCHITECTURE.md reference OpenAI. Needs final decision and codebase alignment during Phase 3 planning. Recommendation: Claude (Anthropic SDK), but abstract the interface for future flexibility.
- **Salesforce edition requirements:** OAuth flow options depend on which SF edition the customer uses. JWT Bearer requires admin-level Connected App setup. Username/password flow is simpler but less secure. Needs discovery during Phase 2 planning with the actual SF org.
- **Fuzzy dedup thresholds:** Company name matching threshold (85%? 90%?) needs calibration against real Salesforce data. Plan for an adjustment period after initial deployment.
- **Email quality benchmarks:** No baseline for "good enough" AI-generated cold email quality specific to the target ICP (A&D, medical, industrial). Needs 3-5 real-world email generation tests before finalizing templates in Phase 3.
- **Write queue architecture:** PITFALLS.md flags SQLite write contention but the specific write queue pattern (asyncio.Queue with single writer coroutine) needs validation against the existing aiosqlite usage patterns in database.py. Address in Phase 1.

---

## Sources

### Primary (HIGH confidence)
- [simple-salesforce PyPI](https://pypi.org/project/simple-salesforce/) -- v1.12.9, Python 3.9-3.13
- [simple-salesforce GitHub](https://github.com/simple-salesforce/simple-salesforce) -- 5K+ stars, active maintenance
- [anthropic PyPI](https://pypi.org/project/anthropic/) -- v0.84.0, httpx internal, Pydantic v2
- [Salesforce SOQL reference](https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/) -- query patterns
- [Salesforce OAuth flows](https://blog.beyondthecloud.dev/blog/salesforce-oauth-2-0-flows-integrate-in-the-right-way) -- JWT Bearer as redirect-free alternative
- Direct codebase analysis of providers/base.py, enrichment/waterfall.py, data/models.py, data/schema.sql

### Secondary (MEDIUM confidence)
- [Nango: Salesforce OAuth token rotation](https://nango.dev/blog/salesforce-oauth-refresh-token-invalid-grant) -- Spring 2024 behavior change
- [AI cold email hallucination rates](https://ruinunes.com/ai-cold-email/) -- 15% hallucination, 51% of spam is AI-generated
- [Micro-campaign response rates](https://www.autobound.ai/blog/cold-email-guide-2026) -- 18% response rates for 10-20 person campaigns
- [SQLite concurrent writes](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) -- write contention analysis
- [Apollo API docs](https://docs.apollo.io/reference/) -- company search, people search endpoints
- [Hunter.io AI cold email guide](https://hunter.io/ai-cold-email-guide) -- generation best practices

### Tertiary (LOW confidence)
- [aiosalesforce](https://github.com/georgebv/aiosalesforce) -- v0.6.2, 16 stars, potential future alternative if it matures
- AI email spam filter detection patterns -- fast-moving space, 2025-2026 data may shift as filters evolve
- Fuzzy company name matching thresholds -- needs calibration against real data, no universal standard

---
*Research completed: 2026-03-07*
*Ready for roadmap: yes*
