# Phase 11: Salesforce Integration - Research

**Researched:** 2026-03-08
**Domain:** Salesforce REST API integration via simple-salesforce, pre-enrichment dedup gate
**Confidence:** HIGH

## Summary

Phase 11 adds read-only Salesforce integration to check company domains against SF Accounts before spending enrichment credits. The user has locked authentication via username/password/security token using the `simple-salesforce` library. The primary match field is a custom `Unique_Domain__c` field with fallback to the standard `Website` field.

The integration touches four existing files (settings page, companies page, waterfall orchestrator, database schema) plus one new module (SF client). The `simple-salesforce` library (v1.12.9) provides a clean Python API for SOQL queries with built-in pagination and an IN-clause formatter. The main technical challenge is batching domain lookups efficiently (SOQL query limit is 100,000 characters, not a count limit on IN values) and inserting a pre-enrichment gate into the existing waterfall without disrupting the enrichment pipeline.

**Primary recommendation:** Build a thin `SalesforceClient` class wrapping `simple-salesforce` with `check_domains_batch()` and `health_check()` methods. Add `sf_account_id` and `sf_status` columns to the companies table. Insert the SF check as a pre-enrichment gate in the waterfall orchestrator.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Username/password + security token** auth only (no OAuth for v2.0)
- Uses `simple-salesforce` library with standard login
- Production org only (login.salesforce.com) -- no sandbox toggle needed
- Credentials stored in `.env`: `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN`
- Settings page gets a Salesforce card with 3 input fields + Test Connection button
- Health check validates credentials by attempting login
- **Primary match field:** `Unique_Domain__c` (custom field on Account)
- **Fallback field:** standard `Website` field
- Query: `SELECT Id, Name, Website, Unique_Domain__c FROM Account WHERE Unique_Domain__c = '{domain}' OR Website LIKE '%{domain}%'`
- **Batch queries** -- collect domains, run single SOQL with IN clause (up to ~200 per query)
- Domain normalization happens on our side before querying (strip www, protocol, trailing slash)
- **Pre-enrichment gate** -- check SF right before spending enrichment credits
- If company IS in SF: **flag + skip enrichment** (save credits)
- User can **manually override** -- select flagged companies and "Enrich Anyway"
- SF check results cached locally to avoid repeated queries for same domain
- **New column** in companies table: "SF Status" with badge
- Badge states: "In SF" (green), empty if not found
- **Click badge opens SF Account record** in new tab (link to SF instance)
- **SF Status filter** added to companies page: All, In SF, Not in SF
- Sortable/filterable like other columns

### Claude's Discretion
- SF fallback behavior when connection is unavailable
- Connection test detail level in settings
- Cache TTL for SF dedup results
- Exact SOQL query optimization (e.g., LIMIT, field selection)
- How to handle the ~200 IN clause limit for large batches

### Deferred Ideas (OUT OF SCOPE)
- **Fuzzy name matching for SF dedup** (SF-05) -- v2.x
- **Cache SF results for 24h** (SF-06) -- v2.x
- **Configurable dedup mode per campaign** (SF-07) -- v2.x
- **Push enriched contacts to SF as Leads** (SF-08) -- v3.0
- **Field mapping SF -> Clay** (SF-09) -- v3.0
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SF-01 | User can configure Salesforce connection credentials in settings page | Settings page card pattern established (see `ui/pages/settings.py`); `simple-salesforce` auth via username/password/token is one-liner |
| SF-02 | User can test Salesforce connection and see success/failure status | Health check pattern from `providers/base.py`; SF test = attempt `Salesforce()` login, catch `SalesforceAuthenticationFailed` |
| SF-03 | System checks if company domain exists as Account in Salesforce before enrichment | SOQL query with `Unique_Domain__c` + `Website` fallback; batch via `format_soql` IN clause; gate in `waterfall.py` |
| SF-04 | System flags rows that match existing Salesforce accounts in the enrichment UI | New `sf_account_id`/`sf_status` columns on companies table; badge display in `companies.py` dataframe |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| simple-salesforce | 1.12.9 | Salesforce REST API client | De facto Python SF client; 4k+ GitHub stars; auth, SOQL, pagination built-in |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | >=1.0 | Load SF credentials from .env | Already in project; same pattern as other API keys |
| pydantic | >=2.0 | SalesforceConfig model | Already in project; matches ProviderConfig pattern |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| simple-salesforce | aiosalesforce | Async-native but less mature, smaller community; simple-salesforce is synchronous but sufficient for batch queries run from Streamlit sync context |

**Installation:**
```bash
pip install simple-salesforce
```

Add to `requirements.txt` and `pyproject.toml` dependencies.

## Architecture Patterns

### Recommended Project Structure
```
providers/
  salesforce.py         # SalesforceClient class (thin wrapper)
config/
  settings.py           # Add SalesforceConfig model + env loading
ui/pages/
  settings.py           # Add SF card (3 fields + Test Connection)
  companies.py          # Add SF Status column + filter
enrichment/
  waterfall.py          # Add pre-enrichment SF gate
data/
  schema.sql            # Add sf_account_id, sf_status to companies
  database.py           # Add SF-related query methods
  models.py             # Add sf_account_id, sf_status to Company model
```

### Pattern 1: SalesforceClient as Thin Wrapper
**What:** A `SalesforceClient` class in `providers/salesforce.py` that wraps `simple-salesforce.Salesforce` with project-specific methods.
**When to use:** All SF interactions go through this class.
**Example:**
```python
# Source: simple-salesforce docs + project patterns
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceAuthenticationFailed
from simple_salesforce.format import format_soql

class SalesforceClient:
    def __init__(self, username: str, password: str, security_token: str):
        self.username = username
        self.password = password
        self.security_token = security_token
        self._sf: Salesforce | None = None

    def _connect(self) -> Salesforce:
        """Lazy-connect to Salesforce."""
        if self._sf is None:
            self._sf = Salesforce(
                username=self.username,
                password=self.password,
                security_token=self.security_token,
            )
        return self._sf

    def health_check(self) -> dict:
        """Test connection. Returns org info on success."""
        sf = Salesforce(
            username=self.username,
            password=self.password,
            security_token=self.security_token,
        )
        # Query org name and account count for display
        org = sf.query("SELECT Name FROM Organization LIMIT 1")
        count = sf.query("SELECT COUNT() FROM Account")
        return {
            "connected": True,
            "org_name": org["records"][0]["Name"] if org["records"] else "Unknown",
            "account_count": count["totalSize"],
        }

    def check_domains_batch(self, domains: list[str]) -> dict[str, dict]:
        """Check multiple domains against SF Accounts.

        Returns dict mapping domain -> {id, name, website, unique_domain}
        for domains found in SF. Missing domains are not in the dict.
        """
        sf = self._connect()
        results = {}

        # Chunk into batches of ~150 to stay within SOQL character limits
        for chunk in _chunked(domains, 150):
            soql = format_soql(
                "SELECT Id, Name, Website, Unique_Domain__c "
                "FROM Account "
                "WHERE Unique_Domain__c IN {domains}",
                domains=chunk,
            )
            response = sf.query_all(soql)
            for record in response["records"]:
                ud = record.get("Unique_Domain__c", "")
                if ud:
                    normalized = _normalize_domain(ud)
                    results[normalized] = {
                        "sf_account_id": record["Id"],
                        "sf_account_name": record["Name"],
                        "sf_website": record.get("Website"),
                    }

            # Fallback: check Website field for domains not yet matched
            unmatched = [d for d in chunk if d not in results]
            if unmatched:
                # Website LIKE queries must be individual OR clauses
                like_clauses = " OR ".join(
                    f"Website LIKE '%{d}%'" for d in unmatched
                )
                fallback_soql = (
                    f"SELECT Id, Name, Website, Unique_Domain__c "
                    f"FROM Account WHERE {like_clauses}"
                )
                fb_response = sf.query_all(fallback_soql)
                for record in fb_response["records"]:
                    website = record.get("Website", "")
                    if website:
                        normalized = _normalize_domain(website)
                        if normalized in unmatched:
                            results[normalized] = {
                                "sf_account_id": record["Id"],
                                "sf_account_name": record["Name"],
                                "sf_website": website,
                            }

        return results
```

### Pattern 2: Pre-enrichment Gate in Waterfall
**What:** Before the waterfall runs provider calls, check SF and skip companies already in SF.
**When to use:** In `enrich_batch()` and `enrich_single()` -- after row normalization, before provider calls.
**Example:**
```python
# In waterfall.py enrich_batch(), before processing each chunk:
if sf_client and sf_client.is_connected():
    domains = [row.get("company_domain", "") for row in chunk_rows]
    domains = [d for d in domains if d]
    sf_matches = sf_client.check_domains_batch(domains)

    for row in chunk_rows:
        domain = row.get("company_domain", "")
        if domain in sf_matches:
            # Update company record with SF info
            await self.db.update_company_sf_status(
                domain, sf_matches[domain]["sf_account_id"]
            )
            # Skip enrichment for this row (save credits)
            # ... return pre-built "skipped_sf" result
```

### Pattern 3: Settings Card for SF Credentials
**What:** Follow existing provider card pattern but with 3 text inputs (username, password, token) instead of 1 API key.
**When to use:** In `ui/pages/settings.py`, add a new section before or after provider cards.
**Example:**
```python
# In settings.py -- new Salesforce section
st.subheader("Salesforce Integration")
with st.container(border=True):
    sf_cols = st.columns([3, 1])
    with sf_cols[0]:
        st.markdown("### Salesforce")
    # ... 3 input fields + Test Connection button
```

### Anti-Patterns to Avoid
- **Don't make SF a "provider" in the ProviderName enum:** SF is not an enrichment provider -- it's a dedup gate. It doesn't belong in the waterfall order or provider health checks. Keep it separate.
- **Don't query SF per-row:** Always batch domains. Per-row queries will exhaust API limits quickly.
- **Don't use LIKE for primary matching:** The `Unique_Domain__c` field enables exact matching via IN clause. LIKE is only for Website fallback.
- **Don't block enrichment when SF is down:** The user's pipeline should not halt because SF has an outage.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SF authentication | Custom OAuth/SOAP flow | `simple-salesforce.Salesforce(username, password, security_token)` | Handles session management, token refresh internally |
| SOQL IN clause formatting | Manual string formatting with quoting | `simple_salesforce.format.format_soql()` | Handles escaping, quoting, None values |
| SF query pagination | Manual nextRecordsUrl following | `sf.query_all()` | Automatically follows pagination links |
| Domain normalization | New normalizer | Reuse `Company.normalize_domain()` validator from `data/models.py` | Already strips www, protocol, trailing slash |

**Key insight:** `simple-salesforce` handles all the tricky parts of SF API interaction (session tokens, SOQL escaping, pagination). The project already has domain normalization in the Company model. Don't duplicate either.

## Common Pitfalls

### Pitfall 1: SOQL Injection via Domain Values
**What goes wrong:** Domains containing single quotes (e.g., `o'reilly.com`) break SOQL string literals.
**Why it happens:** Raw string interpolation in SOQL queries.
**How to avoid:** Always use `format_soql()` from simple-salesforce which handles escaping.
**Warning signs:** `SalesforceMalformedRequest` errors in production.

### Pitfall 2: SF Session Expiry
**What goes wrong:** The Salesforce session token expires (default 2 hours for API sessions) and subsequent queries fail.
**Why it happens:** Long-running application with cached SF client.
**How to avoid:** Catch `SalesforceExpiredSession` and re-authenticate. Or create a new `Salesforce()` instance per batch operation (simple but safe).
**Warning signs:** `SalesforceExpiredSession` exceptions after idle periods.

### Pitfall 3: SOQL Character Limit with Large Batches
**What goes wrong:** A SOQL query with 200+ domains in the IN clause exceeds the 100,000 character SOQL limit or creates excessively long queries.
**Why it happens:** Each domain adds ~30-50 characters to the query string.
**How to avoid:** Chunk domains into batches of ~150. At 50 chars/domain average, 150 domains = ~7,500 chars, well within limits.
**Warning signs:** `SalesforceMalformedRequest` with "query too long" message.

### Pitfall 4: Website Field LIKE Queries Are Slow
**What goes wrong:** `Website LIKE '%domain%'` doesn't use indexes in SF and scans all Accounts.
**Why it happens:** Leading wildcard (`%domain%`) prevents index usage in any database.
**How to avoid:** Use `Unique_Domain__c` as primary match (exact match, indexed). Only fall back to Website for domains not found via `Unique_Domain__c`. Consider limiting Website fallback to smaller batches.
**Warning signs:** Slow query response times (>5s) for Website fallback queries.

### Pitfall 5: simple-salesforce Is Synchronous
**What goes wrong:** SF queries block the event loop if called from async context.
**Why it happens:** `simple-salesforce` uses `requests` internally, not `httpx` or `aiohttp`.
**How to avoid:** Run SF calls via `run_sync()` pattern (already established in project) or call from synchronous Streamlit context. For the waterfall pre-enrichment gate (which is async), wrap SF calls in `asyncio.to_thread()`.
**Warning signs:** Event loop blocking, timeouts in other concurrent operations.

### Pitfall 6: SF Instance URL for Account Links
**What goes wrong:** Can't construct clickable links to SF Account records without knowing the instance URL.
**Why it happens:** SF Account URLs are `https://{instance}.salesforce.com/{account_id}` and the instance varies.
**How to avoid:** After login, `simple-salesforce` exposes `sf.sf_instance` (e.g., `na1.salesforce.com`). Store this alongside credentials or extract it per session. Account URL format: `https://{sf.sf_instance}/{account_id}`.
**Warning signs:** Hardcoded instance URLs that break for different orgs.

## Code Examples

Verified patterns from official sources:

### Authentication
```python
# Source: https://pypi.org/project/simple-salesforce/
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceAuthenticationFailed

try:
    sf = Salesforce(
        username='user@example.com',
        password='password',
        security_token='token',
    )
    print(f"Connected to: {sf.sf_instance}")
except SalesforceAuthenticationFailed as e:
    print(f"Auth failed: {e}")
```

### SOQL Query with IN Clause
```python
# Source: https://simple-salesforce.readthedocs.io/en/stable/user_guide/queries.html
from simple_salesforce.format import format_soql

domains = ["acme.com", "globex.com", "initech.com"]
soql = format_soql(
    "SELECT Id, Name, Website, Unique_Domain__c "
    "FROM Account "
    "WHERE Unique_Domain__c IN {domains}",
    domains=domains,
)
# Result: SELECT Id, Name, Website, Unique_Domain__c FROM Account WHERE Unique_Domain__c IN ('acme.com','globex.com','initech.com')

result = sf.query_all(soql)
for record in result["records"]:
    print(record["Id"], record["Name"])
```

### Get Organization Info (for health check display)
```python
# Source: simple-salesforce docs
org_result = sf.query("SELECT Id, Name FROM Organization LIMIT 1")
org_name = org_result["records"][0]["Name"]

count_result = sf.query("SELECT COUNT() FROM Account")
account_count = count_result["totalSize"]
```

### Construct Account URL
```python
# Source: simple-salesforce sf_instance attribute
instance_url = f"https://{sf.sf_instance}"
account_url = f"{instance_url}/{account_id}"
# e.g., https://na1.salesforce.com/001XXXXXXXXXXXXXXX
```

### Domain Normalization (existing project pattern)
```python
# Source: data/models.py Company.normalize_domain
# Already handles: strip www, http/https, trailing slash
# Reuse for SF domain matching
from data.models import Company
normalized = Company.normalize_domain("https://www.acme.com/")
# Result: "acme.com"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SOAP API for SF queries | REST API via simple-salesforce | 2015+ | Simpler, JSON responses, no XML parsing |
| OAuth2 for all SF integrations | Username/password still supported for server-to-server | Current | Simpler setup for internal tools (user's choice) |
| Per-row SF lookups | Batch SOQL with IN clause | Best practice | 10-100x fewer API calls |

**Deprecated/outdated:**
- `beatbox` Python SF library: abandoned, use `simple-salesforce`
- SF SOAP API for queries: REST API is standard for new integrations

## Open Questions

1. **Unique_Domain__c field format**
   - What we know: It's a custom field on the user's SF Account object
   - What's unclear: Is it always a bare domain (e.g., "acme.com") or does it sometimes include protocol/www?
   - Recommendation: Normalize on our side before comparing; first batch query will reveal format

2. **SF API daily limits**
   - What we know: SF Enterprise Edition allows 100,000 API calls/24h; each `query_all` counts as 1+ calls depending on pagination
   - What's unclear: User's specific SF edition and API quota
   - Recommendation: Log API call count; with batch queries of 150 domains, a 10,000-company pipeline uses ~67 API calls -- well within limits

3. **Cache TTL for SF dedup results (Claude's discretion)**
   - Recommendation: Simple in-memory dict per session, no persistent cache for v2.0. The CONTEXT.md defers persistent caching to SF-06 (v2.x). For the current phase, a session-scoped dict keyed by domain avoids re-querying the same domain within a single enrichment run.

4. **SF fallback behavior (Claude's discretion)**
   - Recommendation: When SF is unavailable, log a warning and proceed with enrichment (don't block). Show a yellow warning banner in the UI: "Salesforce connection unavailable -- enriching without dedup check." This is the safest default because blocking enrichment due to SF downtime is worse than potentially enriching a few duplicates.

5. **Handling >200 IN clause items (Claude's discretion)**
   - Recommendation: Chunk into batches of 150 domains per SOQL query. Process chunks sequentially. 150 is conservative and keeps queries well under the 100K character SOQL limit while batching efficiently.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 0.23+ |
| Config file | pyproject.toml (no pytest.ini) |
| Quick run command | `pytest tests/test_salesforce.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SF-01 | SF credentials load from env, SalesforceConfig model validates | unit | `pytest tests/test_salesforce.py::test_sf_config_loading -x` | No -- Wave 0 |
| SF-02 | Health check returns org name + account count on success, error on failure | unit | `pytest tests/test_salesforce.py::test_sf_health_check -x` | No -- Wave 0 |
| SF-03 | check_domains_batch matches domains via Unique_Domain__c and Website fallback | unit | `pytest tests/test_salesforce.py::test_domain_batch_check -x` | No -- Wave 0 |
| SF-03 | Pre-enrichment gate skips rows with SF matches | unit | `pytest tests/test_salesforce.py::test_pre_enrichment_sf_gate -x` | No -- Wave 0 |
| SF-04 | Company model includes sf_account_id/sf_status, DB persists them | unit | `pytest tests/test_salesforce.py::test_company_sf_fields -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_salesforce.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_salesforce.py` -- covers SF-01, SF-02, SF-03, SF-04 (all mocked, no real SF calls)
- [ ] Framework install: `pip install simple-salesforce` -- new dependency
- [ ] Fixtures: mock `Salesforce` class, mock SOQL responses

## Sources

### Primary (HIGH confidence)
- [simple-salesforce PyPI](https://pypi.org/project/simple-salesforce/) - v1.12.9, auth methods, API surface
- [simple-salesforce queries docs](https://simple-salesforce.readthedocs.io/en/stable/user_guide/queries.html) - SOQL query API, format_soql, query_all
- Project codebase - settings.py, validation.py, waterfall.py, companies.py, schema.sql, models.py patterns

### Secondary (MEDIUM confidence)
- [Salesforce SOQL limits](https://www.salesforceben.com/salesforce-soql-queries-and-limits/) - 100K character query limit
- [SOQL IN clause usage](https://www.xgeek.net/salesforce/two-ways-to-use-soql-in-clause/) - IN clause syntax patterns

### Tertiary (LOW confidence)
- SF API daily call limits (100K for Enterprise) - from training data, varies by edition

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - simple-salesforce is well-documented, version verified on PyPI
- Architecture: HIGH - integration points are clear from existing codebase analysis
- Pitfalls: HIGH - well-known SF integration gotchas (session expiry, SOQL injection, sync blocking)
- SOQL limits: MEDIUM - 100K char limit confirmed by multiple sources but exact IN-clause item limit varies

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable library, well-established patterns)
