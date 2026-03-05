# Roadmap: Clay-Dupe Hardening & Scaling Milestone

## Overview

This milestone hardens and scales a functioning self-hosted B2B waterfall enrichment platform. The existing pipeline (4-provider cascade, budget limits, circuit breakers, SQLite persistence, Streamlit UI) is deployed and working. The work follows a strict dependency-ordered sequence: infrastructure foundation first (async DB, Python version lock), then security hardening in three surgical passes (exception handling, data layer, operational), then performance improvements (I/O and database), then the new capabilities that depend on the hardened foundation (pause/resume, audit trail, deduplication, A/B testing), and finally closing test coverage gaps across the hardened codebase.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Infrastructure Foundation** - Pin Python >= 3.11, migrate to aiosqlite, and integrate aiometer — prerequisites for all async refactoring
- [x] **Phase 2: Exception & Response Hardening** - Replace bare exception handlers with typed boundaries and add .get() fallbacks on all API response parsing
- [x] **Phase 3: Data Layer Hardening** - Eliminate SQL injection via parameterized queries and add input validation before all provider API calls
- [x] **Phase 4: Operational Hardening** - Add API key rotation, SMTP rate limiting, and atomic budget/state transactions
- [ ] **Phase 5: I/O & Concurrency Performance** - Implement chunked batch processing, shared HTTP connection pool, and adaptive per-provider concurrency
- [ ] **Phase 6: Cache & Database Performance** - Add cache table indexes, automatic cache eviction, and WAL checkpoint management
- [ ] **Phase 7: Campaign State Management** - Add checkpoint-per-row progress tracking, pause flag, and resume from last checkpoint
- [ ] **Phase 8: New Capabilities** - Deliver cross-campaign deduplication, full audit trail, provider A/B testing, and pattern deduplication
- [ ] **Phase 9: Testing & Quality** - Close coverage gaps: standardized retry logic, CLI integration tests, waterfall edge cases, malformed response handling, concurrent DB access

## Phase Details

### Phase 1: Infrastructure Foundation
**Goal**: Python version is pinned and the async database layer and rate-limited concurrency library are installed and wired in — all future async refactoring lands on a stable foundation
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, TEST-06
**Success Criteria** (what must be TRUE):
  1. Running `python --version` or inspecting pyproject.toml / setup.cfg shows `>= 3.11` constraint; the app refuses to start on Python 3.10
  2. All SQLite reads and writes go through `aiosqlite` — no `sqlite3` blocking calls remain in the async code paths (verified by grep or test)
  3. `aiometer` is importable and used in at least one batch concurrency control path replacing bare `asyncio.Semaphore`
  4. Existing test suite passes with no regressions after the infrastructure swap
**Plans**: TBD

Plans:
- [x] 01-01: Pin Python >= 3.11 in pyproject.toml and verify startup enforcement
- [x] 01-02: Migrate database.py from sqlite3 to aiosqlite with full async/await coverage
- [x] 01-03: Integrate aiometer into waterfall batch loop replacing bare asyncio.Semaphore

### Phase 2: Exception & Response Hardening
**Goal**: Every provider failure mode is named and visible — no exception is silently swallowed, no API response field access can KeyError-crash the pipeline
**Depends on**: Phase 1
**Requirements**: SEC-01, SEC-04
**Success Criteria** (what must be TRUE):
  1. Grepping the providers directory for bare `except Exception` or bare `except:` returns zero results
  2. Every exception handler in provider code either logs with context (provider name, input, error type) or returns a typed `ProviderResult(success=False, reason=...)` — nothing is silently swallowed
  3. Grepping provider response-parsing code for direct dictionary key access (e.g., `response["key"]` on API response objects) returns zero results — all use `.get()` with explicit fallback defaults
  4. A simulated malformed API response (missing expected fields) causes a graceful `ProviderResult(success=False)` return, not an unhandled exception reaching the waterfall caller
**Plans**: TBD

Plans:
- [x] 02-01: Audit and replace bare exception handlers across all 4 providers with typed boundaries
- [x] 02-02: Replace all direct dictionary key access on API responses with .get() fallbacks across all providers

### Phase 3: Data Layer Hardening
**Goal**: The database layer has no SQL injection surface and all provider inputs are validated before credits are consumed on invalid data
**Depends on**: Phase 2
**Requirements**: SEC-02, SEC-03
**Success Criteria** (what must be TRUE):
  1. Grepping `database.py` for f-string or `%`-formatted SQL (e.g., `f"SELECT ... WHERE id={id}"`) returns zero results — every query uses `?` placeholders
  2. Passing a SQL injection string (e.g., `domain="example.com'; DROP TABLE companies; --"`) as a provider input causes a validation error or sanitized query — the database is unaffected
  3. Passing an invalid email, malformed domain, or non-LinkedIn URL to a provider method raises a validation error before any API call is made — no credits are consumed
  4. All existing enrichment workflows (CLI enrich, Streamlit enrich) continue to operate correctly with valid inputs after the parameterization and validation changes
**Plans**: TBD

Plans:
- [x] 03-01: Parameterize all SQL queries in database.py — eliminate string formatting in SQL statements
- [x] 03-02: Add Pydantic v2 field validators for domain, email, name, and LinkedIn URL on provider method inputs

### Phase 4: Operational Hardening
**Goal**: API keys can be rotated live, SMTP verification does not trigger spam detection, and budget checks with credit deductions are atomic — no race conditions, no orphaned state on crash
**Depends on**: Phase 3
**Requirements**: SEC-05, SEC-06, STATE-01
**Success Criteria** (what must be TRUE):
  1. Updating an API key value in .env and triggering a reload (e.g., via CLI command or Streamlit settings) causes subsequent provider calls to use the new key — no application restart required
  2. Running email verification against any single domain in rapid succession stops after the configured per-domain attempt cap (e.g., 3 per hour) and returns a rate-limit result rather than continuing to probe
  3. Killing the application mid-enrichment (SIGKILL during a batch) and inspecting the database shows no rows in an inconsistent state — every row is either fully enriched with credits deducted or fully pending with no credit deducted
  4. Two simultaneous enrichment sessions against the same budget limit do not both pass the budget check — exactly one succeeds, the other receives a budget-exceeded result
**Plans**: TBD

Plans:
- [x] 04-01: Implement API key rotation mechanism — reload from .env without restart
- [x] 04-02: Add per-domain rate limiting on SMTP verification attempts
- [x] 04-03: Wrap budget check, credit deduction, result write, and row status update in a single BEGIN IMMEDIATE transaction

### Phase 5: I/O & Concurrency Performance
**Goal**: Large CSV batches do not materialize all coroutines at once, HTTP connections are reused across provider calls, and per-provider concurrency adapts to live rate limit signals rather than using a fixed hardcoded limit
**Depends on**: Phase 4
**Requirements**: PERF-01, PERF-02, PERF-03
**Success Criteria** (what must be TRUE):
  1. Enriching a 500-row CSV processes rows in explicit chunks (e.g., 100 at a time) — memory profiling shows constant working set, not linear growth with row count
  2. All 4 providers share a single `httpx.AsyncClient` instance — inspecting instantiation confirms no per-provider client creation; TLS handshake does not occur on every API call
  3. After receiving a 429 response from any provider, the system automatically reduces concurrency for that provider and gradually recovers — no manual configuration change required
  4. A 500-row enrichment completes faster than the equivalent sequential run, with no provider receiving more requests per second than its documented rate limit
**Plans**: TBD

Plans:
- [ ] 05-01: Implement chunked batch processing in waterfall.py — explicit chunk iteration replacing asyncio.gather() on full CSV
- [ ] 05-02: Create providers/http_pool.py shared AsyncClient singleton and inject into all 4 provider constructors
- [ ] 05-03: Add adaptive concurrency limits using aiometer — per-provider backoff on 429 with gradual recovery

### Phase 6: Cache & Database Performance
**Goal**: Cache lookups remain fast as the table grows to tens of thousands of rows, expired entries are evicted automatically, and WAL files do not grow unbounded during sustained batch runs
**Depends on**: Phase 5
**Requirements**: PERF-04, PERF-05, PERF-06
**Success Criteria** (what must be TRUE):
  1. Running `EXPLAIN QUERY PLAN` on the cache lookup query shows index usage (not "SCAN TABLE cache") — verified after the composite index on (provider, enrichment_type, query_hash, expires_at) is created
  2. After a batch run that fills the cache beyond its size bound, a subsequent cache inspection shows expired entries have been removed and total row count is within configured limits
  3. Running a large batch (500+ rows) and inspecting the WAL file size shows it does not grow continuously — WAL checkpoint is triggered between chunks and the file stays bounded
  4. Cache-hit rate is measurable in the Streamlit analytics page — returning results for previously enriched contacts without consuming provider credits
**Plans**: TBD

Plans:
- [ ] 06-01: Add composite indexes to cache table on (provider, enrichment_type, query_hash, expires_at)
- [ ] 06-02: Implement automatic cache eviction — remove expired entries and enforce row-count cap per pass
- [ ] 06-03: Add WAL checkpoint management between batch chunks in waterfall.py

### Phase 7: Campaign State Management
**Goal**: Every campaign row has an individual status, batches can be paused and resumed without reprocessing completed rows, and the system recovers gracefully from mid-batch crashes
**Depends on**: Phase 6
**Requirements**: STATE-02, STATE-03, STATE-04
**Success Criteria** (what must be TRUE):
  1. The Streamlit campaign view shows per-row status (pending / processing / complete / failed) that updates in real time during a batch run — not just an aggregate count
  2. Clicking "Pause" on a running campaign in the Streamlit UI causes the batch loop to stop after completing the current row — no rows are left in "processing" state
  3. Clicking "Resume" on a paused campaign restarts enrichment from the first pending or failed row — already-completed rows are not re-enriched and no credits are re-consumed
  4. Killing the application mid-batch and restarting, then resuming the campaign, processes only the rows that were not previously completed — no duplicate enrichment occurs
**Plans**: TBD

Plans:
- [ ] 07-01: Add campaign_rows table with individual row status tracking (pending, processing, complete, failed)
- [ ] 07-02: Implement pause flag on campaigns — batch loop checks between rows and halts when paused
- [ ] 07-03: Implement resume logic — query for pending/failed rows and continue from checkpoint position

### Phase 8: New Capabilities
**Goal**: The platform eliminates duplicate enrichment spend across campaigns, provides a complete per-call audit trail, enables data-driven waterfall optimization via A/B testing, and stores email patterns without duplicates
**Depends on**: Phase 7
**Requirements**: CAP-01, CAP-02, CAP-03, CAP-04
**Success Criteria** (what must be TRUE):
  1. Starting enrichment for a contact that was already enriched in a different campaign returns the cached result immediately — no waterfall API calls are made and no additional credits are consumed
  2. After any enrichment run, the audit trail table contains one row per provider API call with timestamp, campaign_id, row_id, provider, response_status, email_found, credits_consumed, duration_ms, and error_type populated
  3. Enabling A/B testing mode runs the alternative waterfall configuration in shadow mode alongside production — the production output is unaffected, and hit rate comparison results are visible in the Streamlit analytics page
  4. The email pattern store contains no duplicate patterns per domain — adding a pattern that already exists for a domain updates the existing record rather than inserting a duplicate
**Plans**: TBD

Plans:
- [ ] 08-01: Implement cross-campaign contact deduplication — global contacts lookup by (domain + name) or email before waterfall dispatch
- [ ] 08-02: Implement audit trail — append-only action_logs table with AuditLogger writing inside the enrichment transaction
- [ ] 08-03: Implement provider A/B testing framework — shadow mode runs alternative waterfall config in parallel without affecting production output
- [ ] 08-04: Add pattern deduplication — deduplicate stored patterns, no duplicate patterns per domain

### Phase 9: Testing & Quality
**Goal**: All critical code paths have test coverage — retry logic is consistent across providers, CLI commands are integration tested, waterfall edge cases are covered, malformed responses are handled, and concurrent DB access is verified
**Depends on**: Phase 8
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05
**Success Criteria** (what must be TRUE):
  1. All 4 providers use tenacity with exponential backoff for retry logic — no ad-hoc retry loops remain; a simulated transient 500 error triggers automatic retry with delay before returning failure
  2. Running the CLI test suite executes `enrich`, `search`, `verify`, and `stats` commands against a test database and verifies correct output — no command is tested only manually
  3. The test suite includes scenarios for: all providers failing on a single row, a mid-cascade timeout, and budget exhaustion mid-batch — each scenario produces the expected graceful outcome
  4. The test suite includes provider-specific tests for malformed API responses (missing fields, wrong types, empty arrays) — each produces a `ProviderResult(success=False)` and not an unhandled exception
  5. A concurrent access test spins two simultaneous batch enrichment jobs against the same database and verifies no data corruption, deadlocks, or lost writes occur
**Plans**: TBD

Plans:
- [ ] 09-01: Standardize retry logic across all 4 providers using tenacity with exponential backoff
- [ ] 09-02: Write integration tests for CLI commands (enrich, search, verify, stats)
- [ ] 09-03: Write tests for waterfall edge cases (all providers fail, mid-cascade timeout, budget exhaustion mid-batch)
- [ ] 09-04: Write tests for malformed API response handling across all 4 providers
- [ ] 09-05: Write tests for concurrent database access under batch enrichment load

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Foundation | 3/3 | Complete | 2026-03-04 |
| 2. Exception & Response Hardening | 2/2 | Complete | 2026-03-04 |
| 3. Data Layer Hardening | 2/2 | Complete | 2026-03-04 |
| 4. Operational Hardening | 3/3 | Complete | 2026-03-04 |
| 5. I/O & Concurrency Performance | 0/3 | Not started | - |
| 6. Cache & Database Performance | 0/3 | Not started | - |
| 7. Campaign State Management | 0/3 | Not started | - |
| 8. New Capabilities | 0/4 | Not started | - |
| 9. Testing & Quality | 0/5 | Not started | - |
