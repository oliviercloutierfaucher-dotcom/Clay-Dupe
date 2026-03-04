# Project Research Summary

**Project:** Clay-Dupe — B2B Waterfall Enrichment Platform
**Domain:** Python async data enrichment pipeline — hardening, performance, and scaling
**Researched:** 2026-03-04
**Confidence:** HIGH

## Executive Summary

This is a subsequent milestone for a functioning self-hosted B2B waterfall enrichment platform. The core pipeline (4-provider cascade, budget limits, circuit breakers, SQLite persistence, Streamlit UI, CSV import/export) is already deployed. The research consensus is unambiguous: the platform has correctness defects that must be fixed before any performance or capability work is layered on top. Specifically, non-atomic state writes, bare exception swallowing, and SQL injection vulnerabilities are live production risks that corrupt data quality and credit tracking. These are not technical debt to schedule later — they are blocking issues because new features (pause/resume, cross-campaign dedup) directly depend on a reliable state model.

The recommended approach is a strict four-phase build order derived from dependency analysis: (1) security and hardening — fix the foundation so all upstream work is trustworthy; (2) performance and scaling — shared HTTP connection pool, SQLite indexing and WAL management, and chunked async batch processing; (3) new capabilities — audit trail, pause/resume, cross-campaign deduplication; (4) differentiators — provider A/B testing framework and adaptive concurrency. This order is non-negotiable: audit trails require parameterized queries, pause/resume requires atomic state updates, A/B testing requires a stable audit trail. Skipping phases or reordering creates compound risk.

The primary risks are implementation completeness traps: changes that appear done but leave the core problem intact. Exception handlers narrowed to specific types but still silent, connection pool code moved to class level but still per-instantiation, batch chunking code that sequences chunks but materializes all coroutine objects immediately — each of these is a documented failure mode. The prevention strategy is explicit verification gates per phase, not code review alone.

---

## Key Findings

### Recommended Stack

The existing stack (Python 3.x, httpx 0.27+, Pydantic v2, SQLite WAL, Streamlit, pytest 8.0+, pytest-asyncio 0.23+) remains unchanged. Four targeted additions address the documented pain points without architectural disruption.

**Core technologies (new additions only):**
- `aiometer 1.0.0`: per-provider concurrency + per-second rate limiting — the only stdlib-free library that handles both axes simultaneously; `asyncio.Semaphore` alone cannot enforce per-second limits, which is what provider APIs enforce
- `tenacity 9.1.4`: consistent async retry with exponential backoff across all 4 providers — replaces ad-hoc inconsistent retry loops that currently exist in some providers but not others
- `aiosqlite 0.22.1`: async bridge for SQLite — the existing `sqlite3` usage blocks the event loop on every query during concurrent enrichment; this is the canonical fix, not `run_in_executor` wrapping
- `respx 0.22.0`: httpx-specific mock library for tests — enables testing provider error handling (429, 500, malformed JSON) and concurrent DB access without real API calls
- `pytest-asyncio 1.3.0` (upgrade from 0.23+): session-scoped fixture fix; required for correct aiosqlite concurrent access testing

**Critical action required:** Pin Python to `>= 3.11` to unlock `asyncio.TaskGroup` without a backport. The codebase currently has no explicit Python version lock — this must be added before any async refactoring.

See `.planning/research/STACK.md` for full installation instructions, version compatibility matrix, and alternatives considered.

### Expected Features

The four milestone capabilities (pause/resume, cross-campaign dedup, audit trail, provider A/B testing) all have direct feature dependencies that dictate build order.

**Must have in this milestone (P1 — correctness and named scope):**
- Atomic state updates — foundational; pause/resume and dedup both have race conditions without this
- Pause and resume batch enrichment — checkpoint-per-row model with campaign-level pause flag
- Cross-campaign contact deduplication — global contacts lookup before waterfall dispatch; requires atomic writes
- Audit trail (per-enrichment-call log) — append-only `action_logs` table; also the data source for A/B analysis
- Input validation before API calls — Pydantic v2 field validators on domain/email/LinkedIn URL fields; prevents credit waste on invalid inputs
- Chunked async batch processing — explicit chunk iteration, not `asyncio.gather()` on full CSV; required for 500+ row support
- Cache indexing and active eviction — prevents performance degradation as the cache table grows over months

**Should have after P1 validates (P2 — differentiators):**
- Provider A/B testing framework — requires stable audit trail; shadow-run or split-group mode; statistical significance gating
- Adaptive concurrency limits — per-provider semaphores that back off on 429 and recover over time
- API key rotation without restart — low complexity; add after core changes settle
- Per-domain SMTP verification rate limiting — cap probing at 3 attempts per domain per hour

**Defer (P3 — out of this milestone):**
- Row-level confidence aggregation across providers — needs audit data to accumulate first
- Scheduled/recurring campaign runs — requires job scheduler; scope creep risk
- Multi-tenant isolation — only relevant if the tool is shared across teams

**Anti-features confirmed out of scope:** PostgreSQL migration (no gain at team scale after proper indexing), OAuth/SSO (internal team tool), AI email personalization (wrong tool), additional provider integrations (use A/B testing to validate existing providers first).

See `.planning/research/FEATURES.md` for full competitor analysis and feature dependency graph.

### Architecture Approach

The existing 5-layer architecture (Presentation, Enrichment Pipeline, Quality and Cost Control, API Providers, Data Access) is sound and is not being restructured. All milestone changes inject into existing files and add focused new modules within the existing directory structure. No new top-level folders are required — this minimizes regression risk.

**Key architectural changes per layer:**
1. `providers/http_pool.py` (NEW) — shared `httpx.AsyncClient` singleton; injected into all 4 providers at construction; lifecycle managed at app startup/shutdown
2. `providers/base.py` + each provider (HARDEN) — `InputValidator` helper at method entry; typed exception boundaries (`httpx.TimeoutException`, `httpx.HTTPStatusError`, `httpx.RequestError`); `.get()` fallbacks on all response parsing
3. `enrichment/waterfall.py` (PERF + SCALE) — chunk iteration (not `gather()`), adaptive concurrency per provider, pause/resume state machine polling campaign table between chunks
4. `data/database.py` (HARDEN) — parameterized queries throughout; `action_logs` table (audit trail); composite indexes on cache, campaign_rows, enrichment_results, credit_usage
5. `cost/budget.py` (HARDEN) — atomic `BEGIN IMMEDIATE` transaction wrapping budget check and credit deduction
6. `cost/cache.py` (SCALE) — active eviction coroutine; runs pre-batch or on schedule; bounded by row-count cap per pass
7. `cost/tracker.py` (HARDEN) — audit trail writes inside same transaction as credit deduction

**Build order is strictly dependency-ordered:** SQL injection and bare exceptions must be fixed before building the audit trail on top. Shared HTTP pool requires stable providers. Chunked batch processing requires stable concurrency management. Pause/resume requires chunked batch. A/B testing requires stable audit trail.

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, per-pattern code examples, and integration point table.

### Critical Pitfalls

1. **Exception refactor that still swallows errors** — Narrowing exception types while keeping silent handler bodies is the most common failure mode in this refactor. Every handler must either log with context (provider name, input, response snippet), re-raise, or return a typed `ProviderResult(success=False, reason=...)`. Grep for `except` clauses after refactoring and verify each emits a log line.

2. **Non-atomic budget check and deduction** — Under concurrent enrichment, two Streamlit sessions can both pass the budget check before either deducts. The fix is `BEGIN IMMEDIATE` transaction (not application-level locking) — WAL mode concurrent reads make read-check followed by separate write inherently racy. Verify with a concurrent test that spins two batch jobs against the same budget limit.

3. **Non-atomic campaign state on crash** — Cache write, campaign row update, and credit deduction are three separate DB operations. Crash between them leaves orphaned rows that appear enriched in cache but pending in the campaign, causing double-spend on resume. Wrap all three in a single `BEGIN / COMMIT` transaction.

4. **asyncio.gather() materializing full batch** — Even with a semaphore, calling `gather(*[enrich(row) for row in all_rows])` creates all coroutine objects upfront. 2,000 rows = 2,000 simultaneous coroutine objects. The fix is sequential iteration over explicit chunks, with `gather()` only within each chunk.

5. **Completion traps** — Changes that appear done but are not: connection pool moved to class level but class is instantiated per-request; cache index added but `EXPLAIN QUERY PLAN` still shows full scan; WAL mode enabled but no checkpoint scheduling; budget check adjacent to deduction in code but not inside a shared transaction. Each of these requires explicit verification, not just code review.

See `.planning/research/PITFALLS.md` for full technical debt table, integration gotchas per provider, and recovery strategies.

---

## Implications for Roadmap

Research strongly supports a 4-phase build order. This is not a preference — it is derived from hard dependencies between components.

### Phase 1: Security and Hardening

**Rationale:** Three of the eight documented CONCERNS.md issues are live correctness defects (SQL injection, bare exceptions, non-atomic writes) that corrupt the data quality and credit tracking that all other features rely on. No new feature should be built on top of a broken state model. This phase has no dependencies on other milestone work — it is pure surgical fixes to existing code.

**Delivers:** A trustworthy data layer and provider layer. Parameterized queries eliminate SQL injection. Typed exceptions make failure modes visible. Atomic transactions prevent orphaned rows and budget overruns.

**Addresses (from FEATURES.md P1):**
- Atomic state updates
- Input validation before API calls (Pydantic field validators)

**Avoids (from PITFALLS.md):**
- Bare exception refactor that still swallows errors (Pitfall 1)
- Non-atomic budget check race condition (Pitfall 2)
- Non-atomic campaign state on crash (Pitfall 3)
- SQL injection in database.py (Security section)
- SMTP verification spam detection (per-domain rate limiting added here)

**Research flag:** Standard patterns — no additional research needed. Parameterized SQL, typed exceptions, `BEGIN IMMEDIATE` transactions, and Pydantic validators are well-documented.

---

### Phase 2: Performance and Scaling

**Rationale:** After Phase 1 establishes a reliable foundation, the next bottlenecks are I/O and memory. Unshared HTTP clients pay TLS handshake on every call. The cache table will become a full-scan bottleneck at ~10,000 rows. Unmanaged WAL files degrade performance under sustained batch loads. These are all independent fixes that can land together.

**Delivers:** Faster per-request latency (connection reuse), bounded memory on large CSVs (chunked batch), stable query performance as the cache grows (indexes + eviction), and controlled provider throughput (per-provider semaphores replacing global hardcoded limit).

**Addresses (from FEATURES.md P1):**
- Chunked async batch processing
- Cache indexing and automatic eviction

**Uses (from STACK.md):**
- `aiometer 1.0.0` for per-provider concurrency + per-second rate limiting
- `aiosqlite 0.22.1` for non-blocking SQLite from async context
- SQLite PRAGMA tuning (WAL + synchronous = NORMAL + mmap + cache_size)
- `providers/http_pool.py` shared client pattern

**Avoids (from PITFALLS.md):**
- asyncio.gather() materializing full batch (Pitfall 4)
- Per-instance httpx.AsyncClient (Pitfall 5)
- Fixed concurrency causing 429 storms (Pitfall 6)
- WAL file unbounded growth (Pitfall 7)
- Cache table missing index (Pitfall 8)

**Research flag:** Standard patterns — chunking, connection pooling, and SQLite indexing are well-documented. No additional research needed.

---

### Phase 3: New Capabilities

**Rationale:** Pause/resume, cross-campaign dedup, and audit trail all depend on the atomic state foundation from Phase 1 and the chunked batch infrastructure from Phase 2. They cannot be built correctly before those phases complete. This phase delivers the four capabilities named as Active in PROJECT.md.

**Delivers:** Full pause/resume with checkpoint-per-row semantics. Cross-campaign deduplication that prevents double-spend on shared contacts. Per-call audit trail that is the data source for billing disputes and A/B analysis. Together these make the platform operationally mature.

**Addresses (from FEATURES.md P1):**
- Pause and resume batch enrichment
- Cross-campaign contact deduplication
- Audit trail (per-enrichment-call log)

**Implements (from ARCHITECTURE.md):**
- `action_logs` table with AuditLogger writing inside same transaction as credit deduction
- Campaign pause/resume state machine in WaterfallOrchestrator polling between chunks
- Global contacts dedup check before waterfall entry point, with atomic write on match

**Avoids (from PITFALLS.md):**
- No deduplication leading to double-spend (Performance Traps table)
- Pattern duplicates causing conflicting confidence scores (Pattern Deduplication)

**Research flag:** Pause/resume and dedup patterns are well-documented (job queue checkpointing, CRM dedup literature — HIGH confidence per FEATURES.md). Provider A/B testing shadow-run mode has less public documentation — if A/B analysis is moved to this phase, mark for deeper research.

---

### Phase 4: Differentiators

**Rationale:** Provider A/B testing is the highest-value differentiator but requires a stable audit trail to be meaningful. Without accurate per-call logs, there is no data to analyze. This phase also adds the remaining P2 items (adaptive concurrency, API key rotation) that enhance the platform but are not required for correctness.

**Delivers:** Data-driven waterfall ordering via real per-provider hit rate analysis for the team's specific ICP. Adaptive concurrency that learns from live 429 signals rather than static configuration. API key rotation without service restart.

**Addresses (from FEATURES.md P2):**
- Provider A/B testing framework (shadow mode or split-group mode)
- Adaptive concurrency limits (per-provider semaphore with backoff and recovery)
- API key rotation without restart

**Uses (from STACK.md):**
- `tenacity 9.1.4` for consistent async retry; adaptive concurrency feedback loop built on top

**Research flag:** Provider A/B testing for data quality pipelines has limited public documentation (MEDIUM confidence per FEATURES.md). Specifically: statistical significance thresholds for hit rate comparison and shadow-run implementation pattern in a waterfall context need deeper research during planning for this phase.

---

### Phase Ordering Rationale

- **Correctness before performance:** SQL injection and non-atomic writes are live defects; performance work built on a broken data layer compounds the defects
- **Foundation before features:** Pause/resume and dedup both have race conditions that only disappear after Phase 1's atomic transactions are in place
- **Infrastructure before analytics:** A/B testing is meaningless without the audit trail data it analyzes; the audit trail is meaningless if the credit deductions it records are non-atomic
- **No phase can be skipped or reordered:** Each phase's deliverables are explicit prerequisites for the next phase's correctness — this is not a preference, it is a dependency graph

### Research Flags

Phases needing deeper research during planning:
- **Phase 4 (Provider A/B Testing):** Shadow-run implementation pattern in a waterfall enrichment context has limited public documentation. Needs research into: statistical significance thresholds, shadow-run vs. split-group tradeoffs, result comparison methodology. FEATURES.md rates this MEDIUM confidence.

Phases with standard, well-documented patterns (skip research-phase):
- **Phase 1 (Security and Hardening):** Parameterized SQL, typed exception handling, `BEGIN IMMEDIATE` atomicity, and Pydantic validators are well-documented. HIGH confidence.
- **Phase 2 (Performance and Scaling):** Connection pooling, asyncio chunking, SQLite indexing, and WAL checkpoint management are well-documented. HIGH confidence.
- **Phase 3 (New Capabilities):** Checkpoint-based pause/resume and CRM dedup patterns are well-documented. HIGH confidence except for any A/B components if they slip into this phase.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via PyPI; patterns verified via official httpx, asyncio, and aiosqlite docs; alternatives explicitly evaluated |
| Features | MEDIUM | Table stakes and P1 features verified against competitor analysis and CRM dedup literature; provider A/B testing shadow-run patterns have limited public precedent in waterfall enrichment context |
| Architecture | HIGH | Derived from direct codebase analysis of existing ARCHITECTURE.md and CONCERNS.md; not inferred from generic patterns |
| Pitfalls | HIGH | All 8 critical pitfalls grounded in documented CONCERNS.md issues; verified against Python async/SQLite/httpx official sources |

**Overall confidence:** HIGH

### Gaps to Address

- **Python version lock:** The codebase has no explicit `python_requires` specifier. Must pin to `>= 3.11` before Phase 2 to enable `asyncio.TaskGroup` without a backport. This is a blocking action item before implementation begins.
- **Provider A/B testing implementation pattern:** MEDIUM confidence only. Shadow-run mode for waterfall enrichment is not a well-documented pattern. When Phase 4 is planned, run a targeted research pass on: (a) shadow-run vs. split-group methodology, (b) minimum sample size for statistical significance on hit rates, (c) how to surface results in the Streamlit UI without overwhelming the user.
- **Schema migration tracking:** PITFALLS.md flags the absence of schema migration tracking as a security mistake. The proposed `action_logs` and index additions in Phase 1-3 will need a migration path for existing deployed databases. A schema version table and programmatic migration at startup should be added — this is not currently in scope but should be flagged during Phase 1 planning.
- **Adaptive concurrency calibration:** STACK.md suggests `max_concurrent_requests=5` is safe with the recommended pool limits, but per-provider calibration values are not specified. Phase 4 planning should include a research pass on documented rate limits for Apollo, Findymail, Icypeas, and ContactOut to set sensible adaptive concurrency starting values.

---

## Sources

### Primary (HIGH confidence)
- `.planning/codebase/ARCHITECTURE.md` — direct codebase analysis; component responsibilities and existing patterns
- `.planning/codebase/CONCERNS.md` — documented defects with file locations; primary driver for Phase 1 scope
- `.planning/PROJECT.md` — milestone scope, constraints, and Active feature list
- [httpx official docs — Resource Limits](https://www.python-httpx.org/advanced/resource-limits/) — connection pool configuration
- [httpx official docs — Async Support](https://www.python-httpx.org/async/) — shared client singleton pattern
- [aiometer PyPI](https://pypi.org/project/aiometer/) — version 1.0.0, April 2025; GCRA rate limiting
- [tenacity PyPI](https://pypi.org/project/tenacity/) — version 9.1.4, February 2026; AsyncRetrying support
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) — version 0.22.1, December 2025
- [respx GitHub](https://github.com/lundberg/respx) — version 0.22.0; httpx-specific mocking
- [pytest-asyncio PyPI](https://pypi.org/project/pytest-asyncio/) — version 1.3.0; event_loop fixture removal migration
- [SQLite WAL mode official docs](https://sqlite.org/wal.html) — checkpoint behavior under concurrent load
- [Python asyncio official docs](https://docs.python.org/3/library/asyncio-dev.html) — TaskGroup, Semaphore
- [PEP 760](https://peps.python.org/pep-0760/) — No More Bare Excepts rationale

### Secondary (MEDIUM confidence)
- [SQLite performance tuning — phiresky](https://phiresky.github.io/blog/2020/sqlite-performance-tuning/) — PRAGMA settings (2020, but PRAGMAs are stable)
- [Forward Email SQLite production config](https://forwardemail.net/en/blog/docs/sqlite-performance-optimization-pragma-chacha20-production-guide) — production PRAGMA validation
- [SQLite concurrent writes — tenthousandmeters](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — WAL locking behavior
- [FullEnrich waterfall enrichment guide](https://fullenrich.com/blog/waterfall-enrichment) — industry feature expectations
- [Clay review 2026 — Hackceleration](https://hackceleration.com/clay-review/) — competitor feature analysis
- [CRM dedup guide 2025 — RTDynamic](https://www.rtdynamic.com/blog/crm-deduplication-guide-2025/) — dedup pattern validation
- [Checkpoint recovery for long-running transformations — Dev3lop](https://dev3lop.com/checkpoint-based-recovery-for-long-running-data-transformations/) — pause/resume pattern validation
- [asyncio concurrency limiting patterns — death.andgravity.com](https://death.andgravity.com/limit-concurrency) — batch processing patterns

### Tertiary (LOW confidence — needs validation)
- Provider A/B testing shadow-run in waterfall enrichment context — no direct public documentation found; pattern inferred from general A/B testing and shadow deployment literature

---
*Research completed: 2026-03-04*
*Ready for roadmap: yes*
