# Requirements: Clay-Dupe Hardening & Scaling Milestone

**Defined:** 2026-03-04
**Core Value:** Reliably find verified contact emails by cascading through multiple providers in cost-optimized order, with full cost tracking and caching to prevent wasted credits.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Security & Hardening

- [ ] **SEC-01**: All provider exception handling uses specific exception types (httpx.TimeoutException, httpx.HTTPStatusError, KeyError, ValueError) instead of bare `except Exception`
- [ ] **SEC-02**: All database queries use parameterized queries — no string formatting/interpolation in SQL statements
- [ ] **SEC-03**: Provider method inputs (domain, email, name, LinkedIn URL) are validated and sanitized before API calls
- [ ] **SEC-04**: All JSON response parsing uses `.get()` with fallback defaults — no direct dictionary key access on API responses
- [ ] **SEC-05**: API keys can be rotated without restarting the application
- [ ] **SEC-06**: Email verification (SMTP probing) is rate-limited per target domain to avoid triggering spam detection

### State Management & Atomicity

- [ ] **STATE-01**: Budget check, credit deduction, result write, and campaign row status update happen within a single database transaction
- [ ] **STATE-02**: Campaign rows track individual status (pending, processing, complete, failed) for checkpoint-per-row progress
- [ ] **STATE-03**: Campaign supports pause flag — batch loop checks between rows and stops processing when paused
- [ ] **STATE-04**: Resume queries for pending/failed rows and continues enrichment from checkpoint position

### Performance & Scaling

- [ ] **PERF-01**: Batch enrichment processes rows in chunks (configurable chunk size, default ~100) instead of spawning all coroutines at once
- [ ] **PERF-02**: HTTP client is shared across provider instances via connection pool singleton (not per-provider clients)
- [ ] **PERF-03**: Concurrency limits adapt based on provider rate limit responses (429 status, Retry-After headers)
- [ ] **PERF-04**: Cache table has indexes on (provider, enrichment_type, query_hash, expires_at) for efficient lookups
- [ ] **PERF-05**: Automatic cache eviction removes expired entries and enforces size bounds
- [ ] **PERF-06**: WAL checkpoint management runs between batch chunks to prevent unbounded WAL file growth

### New Capabilities

- [ ] **CAP-01**: Cross-campaign contact deduplication — lookup by normalized (domain + name) or email before waterfall dispatch
- [ ] **CAP-02**: Audit trail logs every provider API call with: timestamp, campaign_id, row_id, provider, input_hash, response_status, email_found, credits_consumed, duration_ms, error_type
- [ ] **CAP-03**: Provider A/B testing framework — shadow mode runs alternative waterfall config in parallel, compares hit rates without affecting production output
- [ ] **CAP-04**: Pattern engine deduplicates stored patterns — no duplicate patterns per domain

### Testing & Quality

- [ ] **TEST-01**: Retry logic standardized across all providers using tenacity with exponential backoff
- [ ] **TEST-02**: Integration tests for CLI commands (enrich, search, verify, stats)
- [ ] **TEST-03**: Tests for waterfall edge cases (all providers fail, mid-cascade timeout, budget exhaustion mid-batch)
- [ ] **TEST-04**: Tests for malformed API response handling across all providers
- [ ] **TEST-05**: Tests for concurrent database access under batch enrichment load
- [ ] **TEST-06**: Python version pinned to >= 3.11

### Infrastructure

- [ ] **INFRA-01**: Async database access via aiosqlite replaces synchronous sqlite3 calls
- [ ] **INFRA-02**: Rate-limited concurrency via aiometer replaces bare asyncio.Semaphore for batch processing

## v2 Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Analytics & Reporting

- **ANLYT-01**: Row-level confidence aggregation across providers for analytics dashboards
- **ANLYT-02**: Scheduled/recurring campaign runs with job scheduler
- **ANLYT-03**: Provider cost comparison reports over time

### Operational

- **OPS-01**: Multi-tenant isolation (if shared across teams)
- **OPS-02**: Streamlit UI automated tests

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| PostgreSQL migration | SQLite sufficient for team-size workloads after indexing improvements; adds ops complexity |
| OAuth/SSO authentication | Internal team tool on local network; API keys in .env sufficient |
| Additional provider integrations | 4 providers covers market well; validate utilization via A/B testing first |
| Mobile app | Enrichment is a desktop batch operation; Streamlit via browser sufficient |
| AI-generated email personalization | Out of scope for enrichment tool; route to sequencer for personalization |
| Predictive enrichment / intent signals | Requires streaming infrastructure; 10x current platform scope |
| Real-time multi-user collaboration | SQLite WAL handles reads; serialize large batch jobs operationally |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 2 | Pending |
| SEC-02 | Phase 3 | Pending |
| SEC-03 | Phase 3 | Pending |
| SEC-04 | Phase 2 | Pending |
| SEC-05 | Phase 4 | Pending |
| SEC-06 | Phase 4 | Pending |
| STATE-01 | Phase 4 | Pending |
| STATE-02 | Phase 7 | Pending |
| STATE-03 | Phase 7 | Pending |
| STATE-04 | Phase 7 | Pending |
| PERF-01 | Phase 5 | Pending |
| PERF-02 | Phase 5 | Pending |
| PERF-03 | Phase 5 | Pending |
| PERF-04 | Phase 6 | Pending |
| PERF-05 | Phase 6 | Pending |
| PERF-06 | Phase 6 | Pending |
| CAP-01 | Phase 8 | Pending |
| CAP-02 | Phase 8 | Pending |
| CAP-03 | Phase 8 | Pending |
| CAP-04 | Phase 8 | Pending |
| TEST-01 | Phase 9 | Pending |
| TEST-02 | Phase 9 | Pending |
| TEST-03 | Phase 9 | Pending |
| TEST-04 | Phase 9 | Pending |
| TEST-05 | Phase 9 | Pending |
| TEST-06 | Phase 1 | Pending |
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0

---
*Requirements defined: 2026-03-04*
*Last updated: 2026-03-04 after roadmap creation — all 28 requirements mapped*
