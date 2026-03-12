# Architecture

**Analysis Date:** 2026-03-04

## Pattern Overview

**Overall:** Multi-layer data enrichment pipeline using a waterfall orchestrator pattern with pluggable provider adapters

**Key Characteristics:**
- Waterfall strategy: providers queried in configurable order until first successful match
- Smart row classification: input data analyzed to determine optimal enrichment route
- Multi-API aggregation: supports Apollo, Findymail, Icypeas, ContactOut providers
- Pattern learning: discovered email formats cached and replayed for future matches
- Cost-aware execution: budget tracking prevents overspending across providers
- Quality gates: circuit breakers and rate limiters protect against cascading failures
- Dual interfaces: CLI (Typer) for batch processing, Web UI (Streamlit) for interactive use

## Layers

**Presentation Layer:**
- Purpose: User interaction and result visualization
- Location: `ui/` (Streamlit app), `cli/` (Typer commands)
- Contains: Page components, command handlers, table rendering, progress display
- Depends on: Configuration, Database, Enrichment services
- Used by: End users via CLI or web browser

**API Provider Layer:**
- Purpose: Abstract HTTP communication with external data sources
- Location: `providers/` (base class + implementations)
- Contains: BaseProvider interface, ApolloProvider, FindymailProvider, IcypeasProvider, ContactOutProvider
- Depends on: Pydantic models, httpx async client
- Used by: Waterfall orchestrator for data lookups

**Enrichment Pipeline Layer:**
- Purpose: Coordinate single-row and batch enrichment through providers
- Location: `enrichment/` (waterfall, router, classifier, pattern engine)
- Contains: WaterfallOrchestrator (main coordinator), RouteCategory classifier, provider sequencing logic, email pattern matching
- Depends on: Providers, Database, Budget manager, Circuit breakers, Pattern engine
- Used by: CLI enrich command, UI enrich page

**Quality & Cost Control Layer:**
- Purpose: Enforce limits, detect failures, cache results, verify data
- Location: `quality/` (verification, confidence, circuit breaker), `cost/` (budget, tracker, cache)
- Contains: EmailVerifier (DNS/SMTP checks), CircuitBreaker (failure detection), BudgetManager (daily/monthly limits), CacheManager (TTL-based caching)
- Depends on: Models, Database
- Used by: Waterfall orchestrator, CLI

**Data Access Layer:**
- Purpose: Persistent storage and retrieval
- Location: `data/` (SQLite database manager)
- Contains: Database class wrapping WAL-mode SQLite, table operations, cache layer, audit logging
- Depends on: Pydantic models, sqlite3
- Used by: All other layers for persistence

**Configuration Layer:**
- Purpose: Load and validate environment settings
- Location: `config/` (settings.py)
- Contains: Settings model, ProviderConfig, ICPPreset definitions
- Depends on: python-dotenv, Pydantic
- Used by: All layers at initialization

## Data Flow

**Single Row Enrichment (Waterfall):**

1. Input row arrives (via CLI file, UI form, or API)
2. Row normalized (full_name split into first/last if needed)
3. Cache lookup by (provider, enrichment_type, query_hash)
4. If hit: return cached result
5. Classify row to RouteCategory (NAME_AND_DOMAIN, NAME_AND_COMPANY, UNROUTABLE, etc.)
6. Build provider sequence from router based on category and waterfall_order
7. For each step in sequence:
   - Check budget allows this provider
   - Check circuit breaker not open
   - Acquire rate limiter slot
   - Execute step (pattern_match, find_email, search_people, verify_email, etc.)
   - Record result on circuit breaker and budget manager
8. On first successful match:
   - Learn email pattern if applicable
   - Cache result with TTL
   - Persist Person/Company to database
   - Calculate confidence score
   - Return EnrichmentResult
9. On complete miss: return not-found result

**Batch Enrichment:**

1. Campaign created, rows inserted to campaign_rows table
2. WaterfallOrchestrator.enrich_batch() processes up to 5 concurrent rows (bounded semaphore)
3. Each row processed via enrich_single() in parallel worker
4. Results accumulated in order
5. Campaign status updated on completion/failure

**State Management:**

- Row input data: stored in `campaign_rows.input_data` JSON
- Enrichment results: stored in `enrichment_results` table with query input, source provider, found flag
- Person/Company entities: upserted to `people`/`companies` tables (deduplicated by name+domain)
- Cache: `cache` table with TTL-based expiration and hit counting
- Audit log: `action_logs` table tracks enrichment events and errors
- Budget: in-memory BudgetManager tracks daily/monthly spend per provider, persisted to `credit_usage` table

## Key Abstractions

**RouteCategory (Enumeration):**
- Purpose: Classify input row to determine enrichment approach
- Examples: `NAME_AND_DOMAIN` (best case), `NAME_AND_COMPANY` (need domain lookup first), `UNROUTABLE` (insufficient data)
- Pattern: Enum with 8 distinct categories driving different provider sequences

**ProviderResponse (Data Class):**
- Purpose: Standardized return from any provider call
- Includes: found flag, email, phone, linkedin_url, confidence, credits_used, response_time_ms, error message
- Pattern: All providers return this; waterfall orchestrator inspects and reuses fields

**EnrichmentResult (Pydantic Model):**
- Purpose: Complete record of a single enrichment attempt
- Includes: person_id, campaign_id, enrichment_type, source_provider, found flag, confidence_score, verification_status, cost_credits, waterfall_position
- Pattern: Immutable after creation, persisted to database

**BaseProvider (Abstract Class):**
- Purpose: Interface all external API adapters must implement
- Methods: find_email(), search_companies(), search_people(), enrich_company(), verify_email(), check_credits(), health_check()
- Pattern: Async methods with consistent ProviderResponse returns; subclasses handle Apollo/Findymail/Icypeas/ContactOut-specific API details

## Entry Points

**CLI Entry Point:**
- Location: `cli/main.py::main()`
- Triggers: User runs `python -m cli.main` or installed `clay-dupe` command
- Responsibilities: Set up logging, initialize Typer app with 4 commands (enrich, search, verify, stats)

**Web UI Entry Point:**
- Location: `ui/app.py`
- Triggers: User runs `streamlit run ui/app.py`
- Responsibilities: Initialize Streamlit app, cache database/settings singletons, set up multi-page navigation

**Enrich Command (CLI):**
- Location: `cli/main.py::enrich()`
- Triggers: `clay-dupe enrich input.csv --output output.csv`
- Responsibilities: Read CSV, auto-detect columns, estimate costs, run waterfall, export results

**Enrich Page (UI):**
- Location: `ui/pages/enrich.py`
- Triggers: User navigates to Enrich page in Streamlit app
- Responsibilities: File upload UI, column mapper form, campaign creation, real-time progress display

## Error Handling

**Strategy:** Fail-open with detailed logging; individual row/step failures don't block entire batch

**Patterns:**
- Provider errors (timeouts, 4xx/5xx): logged at WARNING, circuit breaker records failure, waterfall continues to next provider
- Row classification failure (unroutable): logged at WARNING, returns not-found result
- Database errors: logged at ERROR, result may not persist but enrichment continues
- Budget exhaustion: row skipped at INFO level, waterfall stops trying
- Rate limiter acquisition: logged at WARNING if timeout, step skipped

## Cross-Cutting Concerns

**Logging:**
- Module-level logger via `logging.getLogger(__name__)`
- Levels: DEBUG for pattern matches/cache hits, INFO for budget/rate limit decisions, WARNING for provider failures, ERROR for persistence failures
- Configured in CLI main() with ISO timestamp + level + module name

**Validation:**
- Pydantic BaseModel for all data classes with field validators
- Email normalization: lowercase, strip whitespace
- Domain normalization: remove https://, www., trailing slash, lowercase
- Country code mapping: US/USA/United States → US
- Field signal detection: bitfield of 9 field types checked via regex patterns

**Authentication:**
- API keys loaded from environment variables (APOLLO_API_KEY, FINDYMAIL_API_KEY, etc.)
- Passed to provider constructors at initialization
- No in-memory secret logging; error messages mask credentials

**Concurrency:**
- Async/await throughout providers and waterfall (httpx AsyncClient, asyncio tasks)
- Batch enrichment uses asyncio.Semaphore(5) to bound concurrent rows
- Database uses WAL mode + busy_timeout for read concurrency
- Rate limiters per provider (SlidingWindowRateLimiter)

---

*Architecture analysis: 2026-03-04*
