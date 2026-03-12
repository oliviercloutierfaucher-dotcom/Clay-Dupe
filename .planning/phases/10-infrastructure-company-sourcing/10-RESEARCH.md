# Phase 10: Infrastructure + Company Sourcing - Research

**Researched:** 2026-03-07
**Domain:** SQLite write safety, API key validation, company sourcing/import, ICP scoring, contact discovery
**Confidence:** HIGH

## Summary

Phase 10 extends a well-structured Python/Streamlit enrichment platform with three new capabilities: (1) infrastructure hardening via API key validation on startup and a SQLite write queue, (2) multi-channel company sourcing (Apollo search, CSV import, manual add), and (3) contact discovery and ICP scoring. The existing codebase provides strong foundations -- Apollo provider methods (`search_companies`, `search_people`) are already implemented and FREE, the `ColumnMapper` handles CSV import with fuzzy matching, `upsert_company`/`upsert_person` with domain-based dedup exist, and all providers have `health_check()` methods.

The primary technical risk is SQLite write contention. The current Database class uses a singleton `aiosqlite` connection with WAL mode and `busy_timeout=5000`, but has no write serialization lock. Multiple concurrent write paths (company import, contact discovery, enrichment) sharing the singleton connection through `_connect()` could produce `SQLITE_BUSY` errors under load. Adding an `asyncio.Lock` to the `_connect()` context manager is the correct fix -- simple, minimal impact, and proven by the project's existing concurrent DB tests.

**Primary recommendation:** Add `asyncio.Lock` to the Database `_connect()` method for write serialization, validate all provider keys at startup with dashboard status display, then build the company sourcing pipeline reusing existing Apollo methods + ColumnMapper + upsert patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Three company sources for v2.0: Apollo search (free, already built), CSV import (covers Grata/Inven/Ocean.io lists), manual add
- Flow: search/import companies -> save to DB -> find contacts -> enrich contacts
- CSV import goes through same pipeline as Apollo-sourced companies (find contacts -> enrich)
- Target contacts: CEO, Owner, or Founder only -- 1 best match per company
- Use Apollo search_people() (FREE with master API key) filtered by title/seniority
- After finding contacts, queue them for enrichment via existing waterfall
- ICP score is informational only -- does not gate contact discovery or enrichment
- ICP criteria must be editable in UI -- not just hardcoded presets
- Keep existing presets (A&D, Medical Device, Niche Industrial) but allow creating custom profiles
- v2.0 scoring based on: employee count, industry keywords, geography
- Target geography: US, Canada, UK, Ireland
- Companies persist forever in DB -- not campaign-scoped
- Auto-merge by domain when same company from multiple sources -- keep best fields
- Simple status only: new, contacted, skipped
- Validate on every app startup + manual test button in settings (both)
- Block enrichment + warn when keys are missing/invalid -- show which keys are bad on dashboard
- Waterfall only uses providers with validated keys

### Claude's Discretion
- Company list UI layout (table with sortable columns recommended)
- SQLite write queue implementation pattern
- Exact ICP scoring algorithm and default weights
- Company merge conflict resolution strategy (which source's data wins per field)

### Deferred Ideas (OUT OF SCOPE)
- Website/LinkedIn scraping for company intelligence (v3.0)
- Additional sourcing providers API integration (Grata, Inven, Ocean.io) (v3.0)
- AI-powered company analysis (v3.0)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | System validates real API keys on startup and reports status | All 5 providers have `health_check()` methods. `ui/app.py` already checks for missing keys but doesn't call health_check(). Extend startup to call each provider's `health_check()` async and display pass/fail per provider. |
| INFRA-03 | SQLite write queue prevents concurrent write contention | Database uses singleton aiosqlite connection with WAL mode. Add `asyncio.Lock` to `_connect()` to serialize writes. Existing `test_concurrent_db.py` provides test patterns. |
| SRC-01 | User can search for companies via Apollo with ICP filters | `ApolloProvider.search_companies(**filters)` fully implemented and FREE. `ui/pages/search.py` already has ICP preset selector and filter inputs. Extend to save results to companies table. |
| SRC-02 | User can import company lists from CSV/Excel files | `data/io.py` has `ColumnMapper` (70+ aliases, fuzzy match), `read_input_file()`, `apply_mapping()`. Add company-specific column aliases (revenue, ebitda, founded_year). Process through `upsert_company()`. |
| SRC-03 | User can manually add individual companies | Simple Streamlit form -> `Company` model -> `upsert_company()`. Minimal new code. |
| SRC-04 | User can discover contacts at sourced companies via Apollo people search | `ApolloProvider.search_people()` FREE with master key. Filter by `person_titles=["CEO","Owner","Founder"]`, `person_seniorities=["c_suite","owner"]`, `q_organization_domains_list=[domain]`. Take first result, link to company via `company_id`. |
| SRC-05 | System tracks the source of each company | `Company.source_provider` field exists (ProviderName enum). Need to extend with new source types: "csv_import", "manual". Add `source_type` field or extend ProviderName enum. |
| SRC-06 | System auto-scores companies against ICP criteria | New scoring function using `ICPPreset` model fields: employee_min/max, industries, countries. Score 0-100 with weighted criteria. Store as new column on companies table. |
</phase_requirements>

## Standard Stack

### Core (Already in Project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiosqlite | >=0.20 | Async SQLite access | Already used; singleton connection pattern established |
| streamlit | >=1.37 | UI framework | Already used; all pages follow same pattern |
| pydantic | >=2.0 | Data models | Already used; Company/Person models defined |
| httpx | >=0.27 | HTTP client | Already used; shared client pool for providers |
| pandas | >=2.0 | CSV/Excel processing | Already used in data/io.py |
| rapidfuzz | >=3.0 | Fuzzy column matching | Already used in ColumnMapper |

### Supporting (Already in Project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| nest-asyncio | >=1.6 | Async in Streamlit | Already used in data/sync.py |
| tenacity | >=8.2 | Retry logic | Already used in BaseProvider |

### No New Dependencies Required
This phase requires zero new packages. All functionality builds on existing stack.

## Architecture Patterns

### Recommended Project Structure (New/Modified Files)
```
data/
  database.py          # ADD: asyncio.Lock to _connect(), new company queries
  models.py            # ADD: CompanyStatus enum, source_type field, icp_score field
  schema.sql           # ADD: company_status, icp_score, source_type columns
  io.py                # ADD: company-specific column aliases for CSV import
config/
  settings.py          # MODIFY: ICPPreset to support custom profiles, ICP storage
providers/
  apollo.py            # NO CHANGES needed
ui/
  app.py               # MODIFY: startup key validation with health_check() calls
  pages/
    search.py           # MODIFY: save companies to DB, contact discovery flow
    companies.py        # NEW: company list page with table, filters, manual add
    settings.py         # MINOR: validation status display
enrichment/
  icp_scorer.py         # NEW: ICP scoring engine
  contact_discovery.py  # NEW: Apollo people search wrapper for CEO/Owner/Founder
```

### Pattern 1: Write Queue via asyncio.Lock
**What:** Wrap the Database._connect() context manager with an asyncio.Lock to serialize all write operations through the singleton connection.
**When to use:** Every database write operation (already funneled through _connect()).
**Example:**
```python
# In data/database.py
import asyncio

class Database:
    def __init__(self, db_path: str = "clay_dupe.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()
        self._init_db()

    @asynccontextmanager
    async def _connect(self):
        """Serialize writes through asyncio.Lock + singleton connection."""
        async with self._write_lock:
            conn = await self._get_connection()
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
```
**Why this pattern:** The project already uses a singleton connection. SQLite WAL mode allows concurrent reads but only one writer. The Lock ensures no two coroutines attempt writes simultaneously, preventing SQLITE_BUSY errors. This is minimal-impact -- all existing code already goes through `_connect()`.

### Pattern 2: Startup API Key Validation
**What:** On app startup, call health_check() for every configured provider and display results.
**When to use:** In ui/app.py during initialization.
**Example:**
```python
# In ui/app.py
@st.cache_data(ttl=300)  # re-validate every 5 minutes
def validate_api_keys() -> dict[str, bool]:
    """Validate all configured provider API keys."""
    settings = get_settings()
    results = {}
    for pname, pcfg in settings.providers.items():
        if pcfg.api_key:
            provider_cls = PROVIDER_CLASSES[pname]
            provider = provider_cls(api_key=pcfg.api_key)
            results[pname.value] = run_sync(provider.health_check())
        else:
            results[pname.value] = False
    return results
```

### Pattern 3: Company Source Tracking
**What:** Track where each company came from using a source_type field.
**When to use:** Every time a company is created or updated.
**Example:**
```python
# Option: Add source_type as a string column (not extending ProviderName)
# because "csv_import" and "manual" are not providers
class Company(BaseModel):
    # existing fields...
    source_type: Optional[str] = None  # "apollo_search", "csv_import", "manual"
    source_provider: Optional[ProviderName] = None  # keep for provider tracking
```

### Pattern 4: ICP Scoring
**What:** Score companies 0-100 against configurable ICP criteria.
**When to use:** After company creation/import, and when ICP profile changes.
**Example:**
```python
def score_company(company: Company, profile: ICPPreset) -> int:
    """Score a company against ICP criteria. Returns 0-100."""
    score = 0
    max_score = 0

    # Employee count (weight: 30)
    max_score += 30
    if company.employee_count:
        if profile.employee_min <= company.employee_count <= profile.employee_max:
            score += 30
        elif company.employee_count < profile.employee_min * 0.5:
            score += 0
        else:
            score += 15  # partially within range

    # Industry match (weight: 35)
    max_score += 35
    if company.industry:
        industry_lower = company.industry.lower()
        for ind in profile.industries:
            if ind.lower() in industry_lower or industry_lower in ind.lower():
                score += 35
                break

    # Geography match (weight: 20)
    max_score += 20
    if company.country and company.country in profile.countries:
        score += 20

    # Keyword match (weight: 15)
    max_score += 15
    if profile.keywords and company.description:
        desc_lower = company.description.lower()
        matched = sum(1 for kw in profile.keywords if kw.lower() in desc_lower)
        if matched > 0:
            score += min(15, int(15 * matched / len(profile.keywords)))

    return int(score / max_score * 100) if max_score > 0 else 0
```

### Pattern 5: Contact Discovery
**What:** Find CEO/Owner/Founder at a company using Apollo people search.
**When to use:** After company is saved to DB and user triggers contact discovery.
**Example:**
```python
async def discover_contact(apollo: ApolloProvider, company: Company) -> Optional[Person]:
    """Find the best CEO/Owner/Founder contact at a company."""
    if not company.domain:
        return None
    people = await apollo.search_people(
        q_organization_domains_list=[company.domain],
        person_titles=["CEO", "Owner", "Founder", "President",
                       "Managing Director", "General Manager"],
        person_seniorities=["c_suite", "owner"],
        per_page=5,  # get a few candidates
    )
    if not people:
        return None
    # Return best match (first result, Apollo ranks by relevance)
    best = people[0]
    best.company_id = company.id
    return best
```

### Anti-Patterns to Avoid
- **Opening multiple aiosqlite connections:** The singleton pattern is correct for SQLite. Multiple connections cause lock contention.
- **Scoring that gates enrichment:** User decided ICP score is informational only. Never block contact discovery based on score.
- **Campaign-scoped companies:** Companies persist forever. Do not delete on campaign cleanup.
- **Hardcoded ICP profiles only:** Must allow custom profiles. Store in DB or JSON file, not just Python constants.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSV column mapping | Custom parser | Existing `ColumnMapper` in data/io.py | Already handles 70+ aliases with fuzzy matching |
| Company dedup | Domain comparison logic | Existing `upsert_company()` with domain unique index | Already does COALESCE-based merge on conflict |
| API health checking | Custom HTTP validation | Existing `health_check()` on all providers | Already handles 401, timeout, connection errors |
| Async-to-sync bridge | `asyncio.run()` calls | Existing `run_sync()` from data/sync.py | Already handles nested event loops (nest_asyncio) |
| Apollo search | New search logic | Existing `ApolloProvider.search_companies/search_people` | Fully implemented, FREE, returns typed models |
| Retry logic | Custom retry | Existing `tenacity` retry on BaseProvider._request() | Already handles 429, 5xx, timeouts |

**Key insight:** 80% of this phase is connecting existing pieces together. The Apollo methods, ColumnMapper, upsert logic, and health_check are all built. The new work is: write lock, startup validation display, new company list page, ICP scorer, contact discovery orchestration.

## Common Pitfalls

### Pitfall 1: asyncio.Lock Scope
**What goes wrong:** Creating the Lock inside `__init__` when the Database instance is created outside an event loop (e.g., during Streamlit's `@st.cache_resource`).
**Why it happens:** `asyncio.Lock()` in Python 3.10+ does not require an event loop to instantiate (the old behavior was deprecated). However, the Lock must be used within the same event loop context.
**How to avoid:** Create the Lock in `__init__` -- this works fine in Python 3.11+ (project's minimum). The `run_sync()` wrapper uses `nest_asyncio` which patches the running loop.
**Warning signs:** `RuntimeError: Task got Future attached to a different loop`.

### Pitfall 2: Company Source Tracking with ProviderName Enum
**What goes wrong:** Trying to add "csv_import" and "manual" to the `ProviderName` enum, which is used throughout the provider system.
**Why it happens:** `ProviderName` drives provider instantiation, waterfall ordering, and credit tracking. Adding non-provider values breaks these systems.
**How to avoid:** Use a separate `source_type` string field on Company (e.g., "apollo_search", "csv_import", "manual"). Keep `source_provider` for actual provider tracking.
**Warning signs:** `ValueError` when constructing providers from source names.

### Pitfall 3: Blocking Startup Validation
**What goes wrong:** Calling `health_check()` for all 5 providers sequentially on every page load, adding 2-10 seconds of latency.
**Why it happens:** Each health_check makes an HTTP request. Sequential = 5x latency.
**How to avoid:** Run health checks concurrently with `asyncio.gather()` and cache results with `@st.cache_data(ttl=300)`. Show cached status on dashboard, with a manual re-validate button.
**Warning signs:** Slow page loads, timeout errors on startup.

### Pitfall 4: CSV Import Without Domain Normalization
**What goes wrong:** Importing companies from CSV where domains are formatted differently ("www.acme.com", "https://acme.com", "acme.com/") -- creates duplicates.
**Why it happens:** CSV data from Grata/Inven/Ocean.io uses inconsistent domain formats.
**How to avoid:** The existing `Company.normalize_domain` validator handles this. Ensure CSV-imported data goes through the `Company` model constructor before `upsert_company()`.
**Warning signs:** Duplicate companies with different domain formats in the DB.

### Pitfall 5: ICP Score Staleness
**What goes wrong:** Companies scored once on import never get re-scored when ICP profile changes.
**Why it happens:** Score is computed at import time and stored statically.
**How to avoid:** Re-score all companies when ICP profile is edited. Since scoring is pure computation (no API calls), batch re-scoring is fast.
**Warning signs:** Companies showing outdated scores after ICP profile update.

## Code Examples

### Schema Migration: New Company Fields
```sql
-- Add to schema.sql
ALTER TABLE companies ADD COLUMN source_type TEXT DEFAULT 'apollo_search';
ALTER TABLE companies ADD COLUMN icp_score INTEGER;
ALTER TABLE companies ADD COLUMN status TEXT DEFAULT 'new';

CREATE INDEX IF NOT EXISTS ix_companies_status ON companies(status);
CREATE INDEX IF NOT EXISTS ix_companies_icp_score ON companies(icp_score);
CREATE INDEX IF NOT EXISTS ix_companies_source_type ON companies(source_type);
```

Note: SQLite ALTER TABLE only supports ADD COLUMN. For the initial migration, use IF NOT EXISTS pattern or check column existence before ALTER. Alternatively, add columns directly to the CREATE TABLE in schema.sql since the project uses `CREATE TABLE IF NOT EXISTS`.

### Company List Page Pattern (Streamlit)
```python
# ui/pages/companies.py - follows same pattern as search.py and results.py
import streamlit as st
import pandas as pd
from data.sync import run_sync
from ui.app import get_database, get_settings

st.header("Companies")
db = get_database()

# Filters
filter_cols = st.columns(4)
with filter_cols[0]:
    status_filter = st.selectbox("Status", ["All", "new", "contacted", "skipped"])
with filter_cols[1]:
    source_filter = st.selectbox("Source", ["All", "apollo_search", "csv_import", "manual"])
with filter_cols[2]:
    min_score = st.slider("Min ICP Score", 0, 100, 0)
with filter_cols[3]:
    search_term = st.text_input("Search by name/domain")

# Fetch and display
companies = run_sync(db.search_companies(**filters))
# ... render as st.dataframe with sortable columns
```

### Custom ICP Profile Storage
```python
# Store custom ICP profiles in a JSON file alongside the DB
# Or add an icp_profiles table:
CREATE TABLE IF NOT EXISTS icp_profiles (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    config TEXT NOT NULL,  -- JSON: ICPPreset.model_dump_json()
    is_default BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Multiple SQLite connections | Singleton + WAL mode | Already in codebase | Correct for this workload |
| aiosqlite.connect() per call | Singleton with busy_timeout=5000 | Already in codebase | Needs Lock added for write serialization |
| Basic key presence check | health_check() API call validation | All providers have it | Use for startup validation |

**Already current:**
- aiosqlite >=0.20 with WAL mode and row_factory
- Pydantic v2 with model validators
- Streamlit >=1.37 with st.navigation() multi-page
- All models use UUID primary keys and UTC timestamps

## Open Questions

1. **ICP Profile Persistence**
   - What we know: Current ICP presets are hardcoded in settings.py as Python dicts
   - What's unclear: Whether custom profiles should be stored in SQLite, a JSON file, or the .env
   - Recommendation: SQLite table (`icp_profiles`) is cleanest -- reuses existing DB patterns, supports CRUD via the UI

2. **Company Merge Strategy Details**
   - What we know: `upsert_company()` already does COALESCE (keeps first non-null value per field)
   - What's unclear: Whether CSV data should override Apollo data for specific fields (e.g., revenue from Grata may be more accurate)
   - Recommendation: Keep current COALESCE behavior (first non-null wins). Add `source_type` tracking so users can see where data came from. Override logic is v3.0 scope.

3. **Contact Discovery Batch Size**
   - What we know: Apollo search_people() is FREE but rate-limited (50 req/min on free tier)
   - What's unclear: How many companies a user will source at once (10? 100? 1000?)
   - Recommendation: Process in batches of 10 with 1.5s delays to stay within rate limits. Show progress bar.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 + pytest-asyncio >=0.23 |
| Config file | None explicit (uses pyproject.toml or defaults) |
| Quick run command | `pytest tests/ -x --timeout=30` |
| Full suite command | `pytest tests/ -v --timeout=60` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | API key validation returns pass/fail per provider | unit | `pytest tests/test_key_validation.py -x` | No -- Wave 0 |
| INFRA-03 | Write lock prevents concurrent write errors | unit | `pytest tests/test_concurrent_db.py -x` | Yes (extend) |
| SRC-01 | Apollo company search with ICP filters returns results | unit | `pytest tests/test_company_sourcing.py::test_apollo_search -x` | No -- Wave 0 |
| SRC-02 | CSV import maps columns and creates companies | unit | `pytest tests/test_company_sourcing.py::test_csv_import -x` | No -- Wave 0 |
| SRC-03 | Manual company add creates valid company record | unit | `pytest tests/test_company_sourcing.py::test_manual_add -x` | No -- Wave 0 |
| SRC-04 | Contact discovery finds CEO/Owner/Founder | unit | `pytest tests/test_contact_discovery.py -x` | No -- Wave 0 |
| SRC-05 | Source tracking records correct source per company | unit | `pytest tests/test_company_sourcing.py::test_source_tracking -x` | No -- Wave 0 |
| SRC-06 | ICP scoring produces correct scores for known inputs | unit | `pytest tests/test_icp_scoring.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x --timeout=30`
- **Per wave merge:** `pytest tests/ -v --timeout=60`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_key_validation.py` -- covers INFRA-01
- [ ] `tests/test_company_sourcing.py` -- covers SRC-01, SRC-02, SRC-03, SRC-05
- [ ] `tests/test_contact_discovery.py` -- covers SRC-04
- [ ] `tests/test_icp_scoring.py` -- covers SRC-06
- [ ] Extend `tests/test_concurrent_db.py` -- add write lock verification for INFRA-03

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `data/database.py`, `data/models.py`, `data/io.py`, `data/schema.sql` -- all existing patterns verified by reading source
- Codebase analysis: `providers/apollo.py`, `providers/base.py` -- search_companies, search_people, health_check all verified
- Codebase analysis: `ui/pages/search.py`, `ui/pages/settings.py`, `ui/app.py` -- existing UI patterns verified
- Codebase analysis: `config/settings.py` -- ICPPreset model, ProviderName enum, Settings class verified
- Codebase analysis: `tests/test_concurrent_db.py` -- concurrent write test patterns verified

### Secondary (MEDIUM confidence)
- [SQLite WAL documentation](https://sqlite.org/wal.html) -- WAL mode concurrent read/write behavior
- [aiosqlite GitHub](https://github.com/omnilib/aiosqlite) -- singleton connection pattern, thread-per-connection model
- [Concurrency in SQLite](https://www.slingacademy.com/article/concurrency-challenges-in-sqlite-and-how-to-overcome-them/) -- write serialization patterns

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or official SQLite docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in requirements.txt, no new deps needed
- Architecture: HIGH - Patterns verified by reading existing codebase, extending established patterns
- Pitfalls: HIGH - Identified from actual codebase analysis (singleton connection, ProviderName enum constraints)
- ICP scoring algorithm: MEDIUM - Weights are Claude's discretion, but the approach (weighted criteria, 0-100 scale) is standard

**Research date:** 2026-03-07
**Valid until:** 2026-04-07 (stable -- no fast-moving dependencies)
