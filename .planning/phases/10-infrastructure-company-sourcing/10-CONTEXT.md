# Phase 10: Infrastructure + Company Sourcing - Context

**Gathered:** 2026-03-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Enable users to source companies from multiple channels (Apollo search, CSV import, manual add), discover CEO/Owner/Founder contacts at each company, auto-score against ICP criteria, and manage a persistent company database — with safe concurrent writes and validated API keys. This phase creates the input data that Salesforce dedup (Phase 11) and AI email generation (Phase 12) depend on.

</domain>

<decisions>
## Implementation Decisions

### Sourcing Workflow
- Three company sources for v2.0: Apollo search (free, already built), CSV import (covers Grata/Inven/Ocean.io lists), manual add
- Flow: search/import companies → save to DB → find contacts → enrich contacts
- CSV import goes through same pipeline as Apollo-sourced companies (find contacts → enrich)
- Apollo search page already exists with ICP presets — extend it for company-first workflow

### Contact Discovery
- Target contacts: **CEO, Owner, or Founder only** — real decision-makers
- **1 best match per company** — most targeted approach
- Use Apollo `search_people()` (FREE with master API key) filtered by title/seniority
- After finding contacts, queue them for enrichment via existing waterfall

### ICP Scoring
- Score is **informational only** — does not gate contact discovery or enrichment
- ICP criteria must be **editable in UI** — not just hardcoded presets
- Keep existing presets (A&D, Medical Device, Niche Industrial) but allow creating custom profiles
- v2.0 scoring based on available data: employee count, industry keywords, geography
- Target geography: **US, Canada, UK, Ireland**
- Rich scoring criteria identified for v3.0 (requires AI/scraping): niche product, recurring revenue, IP/patents, installed base quality, regulatory moat

### Company Management
- Companies **persist forever** in DB — accumulate over time, not campaign-scoped
- **Auto-merge by domain** when same company appears from multiple sources — keep best fields
- **Simple status only**: new, contacted, skipped (no pipeline stages)
- Company organization: Claude's discretion (flat list with filters recommended)

### API Key Validation
- Validate on **every app startup** + manual test button in settings (both)
- **Block enrichment + warn** when keys are missing/invalid — show which keys are bad on dashboard
- Waterfall only uses providers with validated keys
- Use existing `health_check()` method on all providers

### Claude's Discretion
- Company list UI layout (table with sortable columns recommended)
- SQLite write queue implementation pattern
- Exact ICP scoring algorithm and default weights
- Company merge conflict resolution strategy (which source's data wins per field)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ApolloProvider.search_companies(**filters)` — fully functional, FREE, returns typed Company objects
- `ApolloProvider.search_people(**filters)` — fully functional, FREE with master key, returns Person objects
- `ColumnMapper` in data/io.py — 70+ column aliases, fuzzy matching, CSV/Excel support
- `ICPPreset` model in config/settings.py — has employee_min/max, ebitda_min/max, industries, keywords, countries
- Search page (ui/pages/search.py) — ICP preset selector, filter inputs, Apollo integration, campaign creation
- Settings page (ui/pages/settings.py) — provider config cards, test connection buttons, waterfall ordering
- Company model (data/models.py) — has domain validator, source_provider, all firmographic fields
- Person model (data/models.py) — has company_id FK, email_status enum, auto full_name builder

### Established Patterns
- All providers extend BaseProvider with shared HTTP client, retry logic, ProviderResponse dataclass
- Database uses aiosqlite with singleton connection, JSON storage for complex fields
- UI pages use Streamlit with session state for data persistence
- ICP presets are Pydantic models loaded from config

### Integration Points
- Companies table has `uix_companies_domain` — unique constraint on domain for dedup
- Search page already creates campaigns from selected results
- `upsert_company()` and `upsert_person()` exist in database.py
- Provider `health_check()` method exists on all 5 providers

</code_context>

<specifics>
## Specific Ideas

- Apollo is the starting point for search, but most companies come from external sources (Grata, Inven, Ocean.io) via CSV
- User wants to eventually score companies on rich signals: niche product, recurring revenue, IP, installed base quality, regulatory moat — but these require AI/web scraping not available in v2.0
- "Why do we source from Apollo? Isn't there a better way?" — user wants smarter sourcing long-term

</specifics>

<deferred>
## Deferred Ideas

- **Website/LinkedIn scraping for company intelligence** — rich ICP scoring based on product analysis, revenue model, IP, client quality. Would require web scraping infrastructure. Captured for v3.0.
- **Additional sourcing providers (Grata, Inven, Ocean.io API)** — direct API integration instead of CSV. Captured for v3.0.
- **AI-powered company analysis** — use Claude/GPT to analyze company websites and score ICP fit. Captured for v3.0.

</deferred>

---

*Phase: 10-infrastructure-company-sourcing*
*Context gathered: 2026-03-07*
