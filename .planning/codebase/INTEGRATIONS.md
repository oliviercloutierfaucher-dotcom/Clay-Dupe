# External Integrations

**Analysis Date:** 2026-03-04

## APIs & External Services

**Email & Contact Enrichment (Four-Provider Waterfall):**
- **Apollo.io** - Primary email/contact/company data provider
  - SDK/Client: Custom async provider class `ApolloProvider` in `providers/apollo.py`
  - Auth: `APOLLO_API_KEY` environment variable
  - Base URL: `https://api.apollo.io/api/v1`
  - Auth Method: X-Api-Key header
  - Rate Limit: 50 requests/min on free tier
  - Supports: Email finding, company search, people search, company enrichment
  - Cost: 1 credit on match, 0 on no-match

- **Icypeas** - Secondary enrichment provider
  - SDK/Client: Custom async provider class `IcypeasProvider` in `providers/icypeas.py`
  - Auth: `ICYPEAS_API_KEY` environment variable

- **Findymail** - Tertiary enrichment provider
  - SDK/Client: Custom async provider class `FindymailProvider` in `providers/findymail.py`
  - Auth: `FINDYMAIL_API_KEY` environment variable

- **ContactOut** - Fallback enrichment provider
  - SDK/Client: Custom async provider class `ContactOutProvider` in `providers/contactout.py`
  - Auth: `CONTACTOUT_API_KEY` environment variable

**Waterfall Pattern:**
- Providers called in sequence: Apollo → Icypeas → Findymail → ContactOut
- Order configurable via `WATERFALL_ORDER` env var
- Execution stops at first successful match
- All requests use httpx async client with 30-second timeout

## Data Storage

**Databases:**
- **SQLite (Local)**
  - Connection: File path specified by `DB_PATH` env var (default: "clay_dupe.db")
  - Client: sqlite3 standard library + custom `Database` wrapper class in `data/database.py`
  - Features:
    - WAL mode (Write-Ahead Logging) for concurrent reads/writes
    - Foreign key constraints enforced
    - Busy timeout: 5000ms for concurrent access handling
    - Context manager-based connection pooling

**File Storage:**
- Local filesystem only
- Input: CSV/Excel files via `data/io.py` (reads via pandas)
- Output: CSV/Excel exports via `data/io.py`
- Database file: Local SQLite `.db` file

**Caching:**
- In-database cache table (`cache` table in SQLite)
- TTL-based expiration (configurable via `CACHE_TTL_DAYS` env var, default: 30 days)
- Cache key: SHA-256 hash of normalized query (provider + enrichment_type + query_input)
- Tracks hit count and expiration timestamp
- Automatic purge of expired entries via `cache_purge_expired()` method

## Authentication & Identity

**Auth Provider:**
- Custom approach per API provider
- No centralized auth service
- Each provider uses API key authentication (passed in HTTP headers)

**Implementation:**
- `config/settings.py`: Loads provider API keys from environment variables
- `config/settings.py`: ProviderConfig dataclass validates key presence
- `providers/base.py`: BaseProvider base class manages HTTP client and authentication headers
- Provider-specific auth implementation in each provider class (e.g., `ApolloProvider._headers()`)

## Monitoring & Observability

**Error Tracking:**
- None detected - error handling via exception propagation and logging

**Logs:**
- Logging via Python standard `logging` module
- CLI: Rich library for terminal output formatting
- Streamlit: Native Streamlit logging/printing
- Location: `cli/main.py` sets up logger with `logging.getLogger(__name__)`

**Audit Trail:**
- `audit_log` table in SQLite database
- Logged via `Database.log_action()` method
- Tracks: user_id, action, entity_type, entity_id, details (JSON), timestamp

## Cost & Credit Tracking

**Credit Usage Tracking:**
- `credit_usage` table in SQLite database
- Daily aggregation per provider
- Tracks: credits_used, api_calls_made, successful_lookups, failed_lookups
- Methods: `Database.record_credit_usage()`, `Database.get_credit_usage()`

**Budget Management:**
- `BudgetManager` class in `cost/budget.py` - enforces daily/monthly credit limits per provider
- `CostTracker` class in `cost/tracker.py` - tracks cumulative costs across providers
- Configuration: Daily/monthly limits via `ProviderConfig.daily_credit_limit` and `ProviderConfig.monthly_credit_limit`

## CI/CD & Deployment

**Hosting:**
- Not detected - application is designed for local/self-hosted deployment
- CLI: Run locally via `typer` CLI
- UI: Run locally/self-hosted via `streamlit run ui/app.py`

**CI Pipeline:**
- Not detected - no GitHub Actions, GitLab CI, or similar configuration found

## Environment Configuration

**Required env vars (from `.env.example`):**
- `APOLLO_API_KEY` - Apollo.io API key
- `FINDYMAIL_API_KEY` - Findymail API key
- `ICYPEAS_API_KEY` - Icypeas API key
- `CONTACTOUT_API_KEY` - ContactOut API key
- `WATERFALL_ORDER` - Provider order (optional, default provided)
- `CACHE_TTL_DAYS` - Cache lifetime in days (optional)
- `DB_PATH` - SQLite database file path (optional)

**Secrets location:**
- `.env` file in project root (not committed to git per `.gitignore`)
- Template provided in `.env.example`

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Data Models & External References

**Provider Integration Points:**
- `BaseProvider` abstract class in `providers/base.py` - all providers implement this interface
- `ProviderResponse` dataclass - standardized response format across all providers
- Shared models: `Company`, `Person`, `EnrichmentResult` in `data/models.py`

**Multi-Provider Routing:**
- `enrichment/router.py` - Routes enrichment requests to appropriate provider(s)
- `enrichment/waterfall.py` - Implements waterfall fallback pattern across provider list

---

*Integration audit: 2026-03-04*
