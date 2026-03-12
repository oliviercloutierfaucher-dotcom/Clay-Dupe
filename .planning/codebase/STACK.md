# Technology Stack

**Analysis Date:** 2026-03-04

## Languages

**Primary:**
- Python 3.x - Full application (CLI, API providers, data models, database layer)

## Runtime

**Environment:**
- Python 3.x (no explicit version lock found in codebase)

**Package Manager:**
- pip
- Lockfile: `requirements.txt` present

## Frameworks

**Core:**
- Typer 0.12+ - CLI framework for command-line interface (`cli/main.py`)
- Streamlit 1.37+ - Web UI framework for dashboard and multi-page app (`ui/app.py`, `ui/pages/`)
- Pydantic 2.0+ - Data validation and settings management (`config/settings.py`, `data/models.py`)

**Testing:**
- pytest 8.0+ - Test runner
- pytest-asyncio 0.23+ - Async test support

**Async/Networking:**
- httpx 0.27+ with HTTP/2 support - Async HTTP client for API calls (`providers/base.py`)
- nest-asyncio 1.6+ - Allow nested asyncio event loops (needed for Typer + async)

## Key Dependencies

**Critical:**
- python-dotenv 1.0+ - Environment variable loading (`config/settings.py`)
- pydantic[email] - Email validation via Pydantic
- dnspython 2.4+ - DNS resolution for domain handling

**Data Processing:**
- pandas 2.0+ - Data import/export, CSV handling (`data/io.py`)
- openpyxl 3.1+ - Excel file support for input/output
- rapidfuzz 3.0+ - Fuzzy matching for deduplication/enrichment

**UI/Display:**
- rich 13.0+ - Rich terminal formatting and tables (`cli/main.py`)
- streamlit-sortables 0.3+ - Sortable UI components in Streamlit

## Configuration

**Environment:**
- Loaded via `.env` file using python-dotenv
- `.env.example` provided as template

**Key Environment Variables:**
- `APOLLO_API_KEY` - Apollo.io API credentials
- `FINDYMAIL_API_KEY` - Findymail API credentials
- `ICYPEAS_API_KEY` - Icypeas API credentials
- `CONTACTOUT_API_KEY` - ContactOut API credentials
- `WATERFALL_ORDER` - Provider prioritization order (default: "apollo,icypeas,findymail,contactout")
- `CACHE_TTL_DAYS` - Cache expiration in days (default: 30)
- `DB_PATH` - SQLite database file path (default: "clay_dupe.db")

**Build:**
- No explicit build tool configuration found
- Application runs directly as Python modules (CLI via typer, UI via streamlit command)

## Database

**Primary:**
- SQLite 3 - Local embedded database (`data/database.py`)
- WAL mode enabled for concurrent reads/writes
- Foreign keys enforced

**Schema:**
- companies - Company information and enrichment data
- people - Contact/person information
- campaigns - Batch enrichment campaign tracking
- campaign_rows - Individual rows in a campaign
- enrichment_results - Results from enrichment lookups
- credit_usage - Daily credit consumption tracking
- cache - Query result cache with TTL expiration
- email_patterns - Discovered email format patterns per domain
- domain_catch_all - Cached catch-all domain detection status
- audit_log - Action audit trail

Location: `data/schema.sql`

## Platform Requirements

**Development:**
- Python 3.x with pip
- .env file with API keys for providers
- SQLite 3 (included with Python)

**Production:**
- Same as development (no server runtime required)
- Application deployment: CLI runs locally or on server; Streamlit UI via `streamlit run ui/app.py`
- Database: SQLite file (portable, local)

## API Rate Limiting & Concurrency

**HTTP Client Configuration (`providers/base.py`):**
- httpx timeout: 30 seconds
- Max connections: 100
- Max keepalive connections: 30
- Async operations throughout provider layer

**Application-Level Limits:**
- `max_concurrent_requests: int = 5` (default, configurable in settings)
- Per-provider rate limiters available via `quality/circuit_breaker.py`
- Request batching supported for providers with batch APIs

---

*Stack analysis: 2026-03-04*
