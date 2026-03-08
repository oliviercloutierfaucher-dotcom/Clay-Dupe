# Phase 11: Salesforce Integration - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Check enrichment targets against Salesforce to prevent duplicate outreach and save enrichment credits. Read-only SF access — query Accounts by domain, flag matches, skip enrichment for companies already in SF. No write-back to Salesforce (out of scope for v2.0).

</domain>

<decisions>
## Implementation Decisions

### Authentication
- **Username/password + security token** auth only (no OAuth for v2.0)
- Uses `simple-salesforce` library with standard login
- Production org only (login.salesforce.com) — no sandbox toggle needed
- Credentials stored in `.env`: `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN`
- Settings page gets a Salesforce card with 3 input fields + Test Connection button
- Health check validates credentials by attempting login

### Dedup Matching Logic
- **Primary match field:** `Unique_Domain__c` (custom field on Account)
- **Fallback field:** standard `Website` field
- Query: `SELECT Id, Name, Website, Unique_Domain__c FROM Account WHERE Unique_Domain__c = '{domain}' OR Website LIKE '%{domain}%'`
- **Batch queries** — collect domains, run single SOQL with IN clause (up to ~200 per query)
- Domain normalization happens on our side before querying (strip www, protocol, trailing slash)

### Where Dedup Runs
- **Pre-enrichment gate** — check SF right before spending enrichment credits
- If company IS in SF: **flag + skip enrichment** (save credits)
- User can **manually override** — select flagged companies and "Enrich Anyway"
- SF check results cached locally to avoid repeated queries for same domain

### SF Fallback Behavior
- **Claude's discretion** — pick safest default when SF is unavailable
- Recommended: warn + proceed with enrichment (don't block pipeline because SF is down)

### SF Status Display
- **New column** in companies table: "SF Status" with badge
- Badge states: "In SF" (green), empty if not found
- **Click badge opens SF Account record** in new tab (link to SF instance)
- **SF Status filter** added to companies page: All, In SF, Not in SF
- Sortable/filterable like other columns

### Settings Display
- **Claude's discretion** for connection test detail level
- Recommended: show org name + account count on successful test

### Claude's Discretion
- SF fallback behavior when connection is unavailable
- Connection test detail level in settings
- Cache TTL for SF dedup results
- Exact SOQL query optimization (e.g., LIMIT, field selection)
- How to handle the ~200 IN clause limit for large batches

</decisions>

<specifics>
## Specific Ideas

- Unique_Domain__c is a custom field already in the user's SF org — this is the primary matching key
- The whole point is to save enrichment credits: "just want to be able to check if account is already in SF" (user quote from milestone planning)
- Pre-enrichment SF dedup saves ~$150/10K run at 30% duplicate rate (from research)
- Read-only for v2.0 — write-back to SF as Leads is explicitly v3.0 (SF-08, SF-09)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ui/validation.py`: `validate_api_keys()` pattern — extend for SF health check
- `ui/pages/settings.py`: Provider cards with Test Connection button — add SF card
- `ui/pages/companies.py`: Companies table with filters (status, source, ICP score) — add SF Status filter/column
- `enrichment/waterfall.py`: `WaterfallOrchestrator` — insert pre-enrichment SF check gate
- `data/database.py`: `upsert_company()` with COALESCE merge — add sf_account_id, sf_status fields
- `config/settings.py`: `ProviderConfig` with api_key field — extend for SF multi-field credentials

### Established Patterns
- Provider health_check() returns bool — SF health check follows same pattern
- Settings stored in .env, loaded via load_dotenv() with reload support
- Companies table uses st.dataframe with sortable columns and filter row above
- All async DB operations go through _connect() with asyncio.Lock (Phase 10)

### Integration Points
- `enrichment/waterfall.py` — pre-enrichment hook point for SF dedup check
- `ui/pages/companies.py` — add SF Status column + filter to existing table
- `ui/pages/settings.py` — add SF provider card alongside existing 5 providers
- `ui/validation.py` — add SF to startup validation alongside existing providers
- `data/schema.sql` — add sf_account_id, sf_status to companies table

</code_context>

<deferred>
## Deferred Ideas

- **Fuzzy name matching for SF dedup** (SF-05) — v2.x, complex and false-positive prone
- **Cache SF results for 24h** (SF-06) — v2.x, optimize after basic flow works
- **Configurable dedup mode per campaign** (SF-07) — v2.x, skip/flag/disabled toggle
- **Push enriched contacts to SF as Leads** (SF-08) — v3.0, bidirectional sync
- **Field mapping SF -> Clay** (SF-09) — v3.0, custom field configuration

</deferred>

---

*Phase: 11-salesforce-integration*
*Context gathered: 2026-03-08*
