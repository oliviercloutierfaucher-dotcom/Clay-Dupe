# Stack Research

**Domain:** Python async data enrichment pipeline — hardening and scaling
**Researched:** 2026-03-04
**Confidence:** HIGH (versions verified via PyPI; patterns verified via official docs and multiple credible sources)

---

## Context

This is a subsequent-milestone research file. The existing stack (Python 3.x, httpx 0.27+, Pydantic v2, SQLite WAL, Streamlit, Typer, pytest 8.0+, pytest-asyncio 0.23+) is already deployed. This document covers only the **additions and changes** needed to harden, optimize, and scale that platform. Do not re-evaluate the base stack.

Known pain points driving this research (from CONCERNS.md):
- Sequential batch processing — no chunking, fixed concurrency
- Each provider creates its own httpx client — no connection reuse across instances
- SQL injection risk in `data/database.py` via string-formatted queries
- Bare `except Exception` across all providers — silent error swallowing
- Unindexed cache table — slow lookups as data grows
- No structured retry with backoff — inconsistent across providers
- No async-aware SQLite access — potential blocking on event loop
- Test gaps: concurrent DB access, malformed API responses, waterfall edge cases

---

## Recommended Stack

### Core Additions: Async Batch Processing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `aiometer` | 1.0.0 | Per-provider concurrency + rate limiting | Provides `max_at_once` (concurrency cap) and `max_per_second` (rate cap) simultaneously. The only stdlib-free library that handles both axes of throttling in one call — `asyncio.Semaphore` alone cannot rate-limit per second. Uses GCRA algorithm, not leaky bucket, so bursts are handled correctly. Production-stable since April 2025. |
| `asyncio.TaskGroup` | stdlib (Python 3.11+) | Structured concurrency for batch chunks | Replaces `asyncio.gather()` for chunk-level orchestration. Guarantees all tasks are cancelled on any exception — no orphaned tasks silently running after a crash. Required for the pause/resume feature since task groups have clean cancellation semantics. |
| `asyncio.Semaphore` | stdlib | Per-provider guard inside waterfall | Use in combination with `aiometer` when you need a simple cap without rate-limiting (e.g., capping concurrent DB writes). Zero dependency, zero overhead. |

**Chunking pattern (for 500+ row CSVs):**
Use `asyncio.TaskGroup` to process rows in chunks of 50-100. Each chunk processes concurrently via `aiometer.amap()`. This keeps memory bounded and allows campaign pause/resume by tracking the last committed chunk index.

### Core Additions: HTTP Connection Pooling

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `httpx.AsyncClient` (shared singleton) | 0.27+ (already installed) | Single shared client across all provider instances | The existing code creates one client per provider instance with no reuse. httpx connection pools are per-client — each new client starts a cold pool. A single shared `AsyncClient` passed at construction time (or via app-level singleton) keeps the pool warm across providers. Official httpx docs explicitly state: "make sure you're not instantiating multiple client instances — have a single scoped client." |

**Configuration for this workload:**
```python
limits = httpx.Limits(
    max_connections=40,        # 4 providers × ~10 concurrent requests each
    max_keepalive_connections=20,  # Keep half warm between bursts
    keepalive_expiry=30.0,     # Provider APIs respond within 30s
)
timeout = httpx.Timeout(
    connect=10.0,
    read=45.0,   # Icypeas/ContactOut can take 30+ seconds
    write=10.0,
    pool=5.0,
)
```

Set `semaphore_limit ≤ max_connections` always. The current default of `max_concurrent_requests=5` is safe with these limits.

### Core Additions: Retry Logic

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `tenacity` | 9.1.4 | Consistent async retry with backoff across all providers | The existing codebase has inconsistent retry logic — some providers retry 429s, others raise immediately. Tenacity provides `@retry` decorator with `AsyncRetrying` support, exponential backoff (`wait_exponential`), per-exception retry conditions (`retry_if_exception_type`), and stop strategies. Replaces ad-hoc retry loops in all 4 providers with one consistent pattern. Version 9.1.4 released February 2026, requires Python 3.10+. |

**Usage for provider methods:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    reraise=True,
)
async def _fetch_with_retry(self, url: str) -> dict:
    ...
```

### Core Additions: SQLite Optimization

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `aiosqlite` | 0.22.1 | Async bridge for SQLite | The existing `data/database.py` uses the synchronous `sqlite3` stdlib module. Calling synchronous SQLite from an async context blocks the event loop for the duration of every query — a write under load pauses ALL concurrent enrichments. `aiosqlite` wraps sqlite3 in a dedicated thread per connection, making all operations awaitable. Released December 2025, Python 3.9+. |

**SQLite PRAGMA configuration to add at connection open:**
```python
await db.execute("PRAGMA journal_mode = WAL")
await db.execute("PRAGMA synchronous = NORMAL")   # Safe with WAL; much faster than FULL
await db.execute("PRAGMA temp_store = MEMORY")
await db.execute("PRAGMA mmap_size = 268435456")  # 256 MB memory-mapped I/O
await db.execute("PRAGMA cache_size = -32768")     # 32 MB page cache
await db.execute("PRAGMA foreign_keys = ON")
await db.execute("PRAGMA optimize = 0x10002")      # Update query planner stats on open
```

**Indexes to add (addresses CONCERNS.md: "Unindexed Cache"):**
```sql
-- Cache table: primary lookup pattern is (provider, cache_key, expires_at)
CREATE INDEX IF NOT EXISTS idx_cache_lookup
    ON cache(provider, cache_key, expires_at);

-- Campaign rows: frequent filter by campaign + status
CREATE INDEX IF NOT EXISTS idx_campaign_rows_status
    ON campaign_rows(campaign_id, status);

-- Enrichment results: lookups by person/company
CREATE INDEX IF NOT EXISTS idx_enrichment_results_person
    ON enrichment_results(person_id, created_at DESC);

-- Credit usage: daily budget checks
CREATE INDEX IF NOT EXISTS idx_credit_usage_provider_date
    ON credit_usage(provider, usage_date);
```

Run `PRAGMA optimize` before each connection close (long-lived connections: run every hour).

### Core Additions: Security Hardening

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `pydantic` v2 validators | 2.0+ (already installed) | Input sanitization at provider method boundaries | Already in the stack. The gap is that provider methods accept raw strings without going through Pydantic models. Add `@field_validator` on domain, email, and LinkedIn URL fields with regex constraints. Pydantic v2's Rust-backed validation runs in microseconds — no performance concern. Avoids adding a new dependency for what the existing stack already handles. |
| Parameterized queries (stdlib `sqlite3`) | stdlib | Eliminate SQL injection in `database.py` | The fix is a code pattern, not a library. All string-formatted SQL (`f"SELECT ... WHERE x = '{val}'"`) must become `cursor.execute("SELECT ... WHERE x = ?", (val,))`. The `aiosqlite` migration enforces this review pass naturally. No new dependency needed. |

**Do NOT use** `bleach` or `validators` (PyPI) for this workload — they are designed for HTML sanitization and generic URL checking respectively. Pydantic v2 field validators with `pattern=` regex constraints are faster, already-integrated, and composable with the existing data models.

### Core Additions: Testing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `pytest-asyncio` | 1.3.0 | Async test runner | Already in the stack at 0.23+. Upgrade to 1.3.0 — the 1.0 release (May 2025) removed the deprecated `event_loop` fixture that caused session-scoped async fixture failures. Set `asyncio_mode = "auto"` in `pytest.ini` to eliminate per-test `@pytest.mark.asyncio` boilerplate. Required for testing `aiosqlite` concurrent access properly. |
| `respx` | 0.22.0 | Mock httpx in tests | The only mocking library built specifically for httpx's async client. Provides `@respx.mock` decorator and `respx_mock` pytest fixture. Enables testing provider error handling (429, 500, malformed JSON) without real API calls. Requires httpx 0.25+, compatible with current 0.27+. |
| `pytest-mock` | 3.x (already typical) | General mocking via `mocker` fixture | Use alongside respx for non-HTTP mocking (database, circuit breaker state, time). Standard pytest plugin, no conflicts with respx or pytest-asyncio 1.3.0. |

**Testing patterns needed for this milestone:**

1. **Concurrent DB access tests** — use `asyncio.TaskGroup` to spawn 10 concurrent writes, assert no `OperationalError: database is locked`. Validates WAL mode + aiosqlite are working.
2. **Malformed API response tests** — use `respx` to return truncated JSON (`{"email": null}`, missing keys). Validates `.get()` fallback fixes in providers.
3. **Waterfall edge cases** — mock all providers to raise `httpx.HTTPStatusError(429)`. Validate circuit breaker opens and waterfall terminates gracefully.
4. **Batch chunking tests** — enrich 150 fake rows, assert credit usage matches expected provider call counts. Validates chunking + deduplication.

---

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `loguru` | 0.7+ | Structured async-safe logging | Add for the audit trail feature. `enqueue=True` makes it non-blocking in async context. Simpler API than `structlog`. Use for the new `audit_log` table supplement — emit structured JSON logs alongside DB writes for debugging. Optional if the team finds stdlib `logging` sufficient. |

---

## Installation

```bash
# New additions for this milestone
pip install aiometer==1.0.0
pip install tenacity==9.1.4
pip install aiosqlite==0.22.1
pip install respx==0.22.0

# Upgrade existing (breaking changes in pytest-asyncio)
pip install --upgrade pytest-asyncio==1.3.0
```

**No changes needed to:** httpx, pydantic, pytest, pandas, Typer, Streamlit, rapidfuzz, dnspython.

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `aiometer` | `asyncio.Semaphore` alone | Semaphore caps concurrency but cannot enforce `max_per_second`. Provider APIs enforce per-second rate limits (Apollo: 50/sec). Without per-second control, bursts hit 429s even under the concurrency cap. |
| `aiometer` | `aiohttp` + custom limiter | Already using httpx; switching HTTP clients to get rate limiting is unnecessary churn. aiometer works with any async callable, including httpx. |
| `tenacity` | Custom retry loops | Existing ad-hoc retries are inconsistent (some providers retry, others don't). tenacity standardizes the pattern with zero boilerplate and `AsyncRetrying` support. |
| `aiosqlite` | `sqlite3` in `asyncio.run_in_executor` | `run_in_executor` wrapping sqlite3 works but requires manual thread management and doesn't provide async context managers. aiosqlite is the canonical solution — same API surface, awaitable. |
| `respx` | `pytest_httpx` | Both mock httpx. respx has more active maintenance (0.22.0 Dec 2024) and better pattern matching for URL-specific response configuration across multiple providers. |
| `pydantic` validators | `bleach`, `validators` | bleach is for HTML sanitization (irrelevant here). The `validators` PyPI package is a thin wrapper with no async integration. Pydantic field validators are already in the stack — using them avoids adding dependencies for functionality that already exists. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `aiohttp` for providers | Existing providers use httpx. Mixing clients means two connection pools, two timeout configurations, and inconsistent error types. | Stay on `httpx.AsyncClient` — fix the unshared client problem by making it a singleton |
| `asyncpg` / PostgreSQL | Out of scope per PROJECT.md. SQLite with WAL + indexes + aiosqlite handles the team-size workload. Adding Postgres adds a server dependency that contradicts self-hosted constraints. | `aiosqlite` + SQLite PRAGMA tuning |
| `celery` / `rq` / task queues | Heavyweight — requires Redis/RabbitMQ broker, adds infrastructure. Waterfall enrichment is CPU-light and I/O-bound; asyncio concurrency is sufficient. | `asyncio.TaskGroup` + `aiometer` |
| `anyio` (as primary async runtime) | AnyIO conflicts with pytest-asyncio 1.3.0 when both are in auto mode. Only add AnyIO if the codebase targets Trio compatibility, which it does not. | `asyncio` stdlib + `pytest-asyncio` |
| `hypothesis` | Property-based testing is valuable but the immediate gaps are integration tests (real provider mocking, concurrent DB access). Hypothesis adds complexity before the basics are covered. | `respx` + targeted parametrize tests for edge cases |

---

## Stack Patterns by Variant

**If batch size is under 100 rows:**
- Use `asyncio.Semaphore(5)` directly — no need for aiometer's per-second limiting at this scale.
- Because rate limit budgets won't be reached in a single batch.

**If batch size is over 500 rows:**
- Use `aiometer.amap()` with `max_at_once=5, max_per_second=3` per provider.
- Chunk into 50-row groups with `asyncio.TaskGroup`, commit chunk results before starting next.
- Because this enables pause/resume (resume from last committed chunk index) and prevents memory pressure from holding all results in RAM.

**If concurrent Streamlit users are a concern:**
- Set `PRAGMA wal_autocheckpoint = 1000` (already default) and monitor WAL file size.
- Run WAL checkpoint in a background thread on a separate connection to avoid blocking writes.
- Because WAL checkpoint stalls can cause brief write latency spikes under concurrent load.

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `pytest-asyncio 1.3.0` | `pytest 8.0+` | Confirmed compatible. The 1.0 release dropped `event_loop` fixture — existing tests using it must migrate to `loop_scope`. |
| `pytest-asyncio 1.3.0` | `respx 0.22.0` | No known conflicts. Both work with standard async fixtures. |
| `aiosqlite 0.22.1` | `sqlite3` stdlib | aiosqlite is a wrapper — it uses the same SQLite binary as stdlib. All PRAGMA settings apply equally. |
| `aiometer 1.0.0` | `httpx 0.27+` | aiometer is HTTP-client agnostic — wraps any async callable. No direct dependency. |
| `tenacity 9.1.4` | Python 3.10+ | Requires Python 3.10+. Verify the project has a Python version lock >= 3.10 (currently "Python 3.x" — this needs pinning). |

**Action required:** The codebase has no explicit Python version lock (`requirements.txt` and no `pyproject.toml` version specifier found). Pin to `python_requires >= "3.11"` to unlock `asyncio.TaskGroup` without a backport.

---

## Sources

- [httpx Resource Limits — official docs](https://www.python-httpx.org/advanced/resource-limits/) — connection pool configuration, HIGH confidence
- [httpx Async Support — official docs](https://www.python-httpx.org/async/) — singleton client pattern, HIGH confidence
- [aiometer PyPI](https://pypi.org/project/aiometer/) — version 1.0.0, April 2025, HIGH confidence
- [aiometer GitHub](https://github.com/florimondmanca/aiometer) — GCRA algorithm, max_at_once + max_per_second, HIGH confidence
- [tenacity PyPI](https://pypi.org/project/tenacity/) — version 9.1.4, February 2026, HIGH confidence
- [aiosqlite PyPI](https://pypi.org/project/aiosqlite/) — version 0.22.1, December 2025, HIGH confidence
- [respx GitHub](https://github.com/lundberg/respx) — version 0.22.0, December 2024, HIGH confidence
- [pytest-asyncio PyPI](https://pypi.org/project/pytest-asyncio/) — version 1.3.0, November 2025, HIGH confidence
- [pytest-asyncio 1.0 migration guide](https://pytest-asyncio.readthedocs.io/en/latest/how-to-guides/migrate_from_0_23.html) — event_loop removal, HIGH confidence
- [SQLite PRAGMA tuning — phiresky blog](https://phiresky.github.io/blog/2020/sqlite-performance-tuning/) — PRAGMA settings, MEDIUM confidence (content is from 2020 but PRAGMAs are stable across SQLite versions)
- [SQLite recommended PRAGMAs — High Performance SQLite](https://highperformancesqlite.com/articles/sqlite-recommended-pragmas) — production settings, MEDIUM confidence
- [Forward Email SQLite production config](https://forwardemail.net/en/blog/docs/sqlite-performance-optimization-pragma-chacha20-production-guide) — real-world production PRAGMA settings, MEDIUM confidence

---

*Stack research for: Python async enrichment pipeline hardening and scaling*
*Researched: 2026-03-04*
