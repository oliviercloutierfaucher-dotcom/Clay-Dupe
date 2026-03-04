# Pitfalls Research

**Domain:** Python async B2B enrichment pipeline — hardening, performance, and scaling improvements
**Researched:** 2026-03-04
**Confidence:** HIGH (grounded in known codebase issues documented in CONCERNS.md, verified against Python async/SQLite/httpx official sources)

---

## Critical Pitfalls

### Pitfall 1: Bare Exception Refactor That Still Swallows Errors

**What goes wrong:**
Developers replace `except Exception` with named exception types but keep the same silent failure pattern inside the handler — catching `httpx.HTTPStatusError` and logging nothing, or catching `KeyError` and returning `None` without any record of the failure. The refactor looks complete but debugging is just as hard as before.

**Why it happens:**
The mechanical change (specific type) is easy. The behavioral change (what to do when caught) requires understanding each failure mode. Teams tackle the type narrowing without auditing the handler bodies.

**How to avoid:**
Each exception handler must do at least one of: log with full context (provider name, input, response snippet), re-raise, or return a typed `ProviderResult` with `success=False` and a reason field. No handler should be a silent `pass` or a bare `return None`. After refactoring, grep for `except` clauses and confirm every one emits a log line or raises.

**Warning signs:**
- Provider waterfall reports zero errors in logs during a batch that returned low hit rates
- A budget is consumed but campaign shows no failed rows — errors are being caught and treated as clean misses
- Tests pass but manual testing of a bad API key silently returns no results instead of raising

**Phase to address:**
Security and hardening phase — must be the first phase since silent failures corrupt all downstream data quality work.

---

### Pitfall 2: Non-Atomic Budget Check + Deduction Race Condition

**What goes wrong:**
The budget check ("is $X remaining?") and the credit deduction ("subtract $X") are separate SQLite write operations. Under concurrent enrichment — two Streamlit sessions running batch jobs simultaneously — both sessions can pass the budget check before either deducts. Credits are spent twice and the budget limit is violated.

**Why it happens:**
SQLite WAL mode allows concurrent reads, so both sessions read the same budget row simultaneously. The writes succeed because SQLite serializes them, but by then both have already decided to proceed.

**How to avoid:**
Wrap budget check and deduction in a single `BEGIN IMMEDIATE` transaction. SQLite `BEGIN IMMEDIATE` acquires a reserved lock at transaction start, blocking other writers from reading stale budget state. This is the correct primitive for this use case — not application-level locking. Verify with a concurrent test that spins two batch jobs against a budget limit.

**Warning signs:**
- Budget overage in credit usage reports (spent more than the configured limit)
- Discrepancy between `credits_used` column and actual provider billing
- Race condition only appears when two Streamlit tabs run enrichment simultaneously

**Phase to address:**
Security and hardening phase — budget integrity is a correctness requirement, not a performance optimization.

---

### Pitfall 3: Non-Atomic Campaign State Leaving Orphaned Rows on Crash

**What goes wrong:**
Campaign progress, credit usage, and cache writes are three separate DB operations. If the process crashes between the first and third write — which is likely during a 500-row batch — the campaign shows partial state that cannot be cleanly resumed. Some rows appear "enriched" (cache has result) but the campaign row still shows "pending". Resuming re-enriches and double-spends credits.

**Why it happens:**
Developers add features incrementally. The cache write, the campaign row update, and the credit deduction were each added at different times without grouping them into a single transaction. It works in normal operation but the crash window between operations is a real production risk.

**How to avoid:**
Wrap the post-enrichment state update (cache write + campaign row update + credit deduction) in a single `BEGIN` / `COMMIT` transaction. If any step fails the transaction rolls back and the row remains "pending" — safe to retry. Add a database-level test that kills the process mid-batch and verifies no orphaned state.

**Warning signs:**
- Campaign shows "In Progress" after process restart with no active workers
- Cache hit returns a result but campaign row shows the contact as unenriched
- Credit usage counter diverges from campaign result counts over time

**Phase to address:**
Security and hardening phase — data integrity before performance work, so that chunked batch processing builds on a reliable state model.

---

### Pitfall 4: asyncio.gather() Loading Entire Batch Into Memory Before Processing

**What goes wrong:**
Implementing chunked batch processing by calling `asyncio.gather(*[enrich(row) for row in all_rows])` on the full CSV. Even with a semaphore controlling concurrency, `asyncio.gather()` materializes the entire coroutine list upfront. A 2,000-row import creates 2,000 coroutine objects simultaneously. Memory pressure spikes and the benefit of "chunking" is lost.

**Why it happens:**
`asyncio.gather()` with a semaphore is the standard concurrency-limiting pattern and it looks correct. The memory issue is non-obvious because the semaphore limits active I/O but not coroutine instantiation.

**How to avoid:**
Process rows in explicit chunks (`itertools.islice` or list slicing into groups of N). Within each chunk use `asyncio.gather()`. Between chunks, await completion before creating the next chunk. Alternatively, use a queue-based producer/consumer pattern where the producer feeds rows lazily. For this codebase the chunk-per-N approach is simpler and matches the existing row-processing model.

**Warning signs:**
- Memory usage during batch enrichment grows linearly with CSV size regardless of concurrency limit
- Process is killed by the OS (OOM) on large imports
- Profiling shows thousands of coroutine objects created before any complete

**Phase to address:**
Performance and scaling phase — after hardening is complete, chunked processing should be the first performance improvement since it unblocks large CSV support.

---

### Pitfall 5: httpx.AsyncClient Recreated Per Provider Instance

**What goes wrong:**
Each `AsyncClient` instantiation creates a new connection pool. If the waterfall instantiates providers fresh per enrichment row (or per session), the TLS handshake overhead accumulates and connection pooling never benefits the workload. At batch scale, each row pays the full connection establishment cost for every provider.

**Why it happens:**
The natural object-oriented pattern is to construct a provider with its credentials and an internal client. When providers are short-lived (per-request objects), the client dies with them. The code looks clean but connection reuse never happens.

**How to avoid:**
Share a single `httpx.AsyncClient` per provider across all enrichment operations, or use a single application-level client passed to all providers. The client should be created once at application startup and closed at shutdown. Use `httpx.Limits` to configure `max_keepalive_connections` appropriate to concurrent provider calls (suggested: `max_keepalive_connections=10, max_connections=20` per provider). Monitor for `PoolTimeout` after extended operation — this signals pool exhaustion and may require periodic client refresh.

**Warning signs:**
- HTTP request latency does not decrease after the first request to a provider
- Profiling shows TLS handshake time on every single API call
- `PoolTimeout` errors appear after hours of batch operation

**Phase to address:**
Performance and scaling phase — connection pooling should be established during the HTTP client sharing work before adaptive concurrency is added on top.

---

### Pitfall 6: Fixed Concurrency Limits Causing Either 429 Storms or Artificial Slowdowns

**What goes wrong:**
Hardcoded semaphore values (e.g., `asyncio.Semaphore(5)`) are set conservatively to avoid rate limiting. In practice, providers have different limits and the same value both over-throttles permissive providers (Apollo allows higher throughput) and under-throttles restrictive ones (Icypeas has tighter limits). This results in wasted throughput on fast providers and 429 errors on slow ones when the limit is miscalibrated.

**Why it happens:**
Fixed concurrency limits are set once at development time and never revisited. Rate limit responses from providers (`HTTP 429`) are caught by the circuit breaker but the learning — "back off to N concurrent requests" — never feeds back into the semaphore value.

**How to avoid:**
Implement per-provider concurrency limits, not a single global limit. When a provider returns a 429, reduce its semaphore count by 1 (down to a minimum of 1). When a configurable time window passes without errors, increment back up. This is adaptive concurrency, not full feedback control — start simple. Store the current limit per provider in a runtime dict, not the database. Reset to defaults on application restart.

**Warning signs:**
- One provider consistently produces 429 errors while others are idle
- Campaign throughput is bottlenecked on the slowest provider even when faster providers could handle more work
- Logs show all 429 errors coming from the same provider across multiple batch runs

**Phase to address:**
Performance and scaling phase — implement after connection pooling is stable, since the adaptive limit needs reliable connections to behave correctly.

---

### Pitfall 7: SQLite WAL File Growing Unboundedly Under Sustained Reads

**What goes wrong:**
SQLite WAL mode allows concurrent reads during writes, but the WAL file is only checkpointed (flushed back to the main DB file) when no readers are active. During extended batch enrichment — which continuously reads campaign rows and cache — the WAL file never gets a clean checkpoint window. The WAL file grows unboundedly, degrading all query performance and inflating database file size.

**Why it happens:**
WAL mode is correctly enabled (the codebase has it) but checkpoint management is left to SQLite defaults (`wal_autocheckpoint = 1000 pages`). Under sustained concurrent read/write workloads, the autocheckpoint is starved because readers always hold open transactions.

**How to avoid:**
Schedule explicit `PRAGMA wal_checkpoint(TRUNCATE)` calls between batch chunks (not mid-chunk). This is the correct time to checkpoint: no active row processing, brief window with no readers. Also set `PRAGMA wal_autocheckpoint = 100` to checkpoint more aggressively. Add monitoring of WAL file size (poll the `.wal` file size) and log a warning when it exceeds a threshold.

**Warning signs:**
- SQLite `.wal` file growing to hundreds of MB during batch processing
- Query times increasing over the course of a long batch run
- Performance is good after fresh start but degrades within minutes of batch enrichment

**Phase to address:**
Performance and scaling phase — during the SQLite optimization work, alongside index additions.

---

### Pitfall 8: Cache Index Absent, Making TTL Queries Full Table Scans

**What goes wrong:**
The cache table is queried by `(provider, input_hash)` or `(provider, domain, email)` on every enrichment step. Without an index on these columns, SQLite performs a full table scan. At 10,000 cached results this is imperceptible. At 100,000+ entries (realistic after months of operation) every waterfall step's cache check degrades from microseconds to tens of milliseconds, stacking latency across 4 providers per row.

**Why it happens:**
Cache tables are designed for fast reads but the index is an afterthought. During initial development with small datasets the query is fast enough that the problem is invisible.

**How to avoid:**
Add a composite index on `(provider, cache_key)` at schema creation time, not after the fact. Also add an index on `expires_at` for TTL eviction queries. Run `EXPLAIN QUERY PLAN` on the cache lookup query and verify it says "USING INDEX" not "SCAN TABLE". Add a schema migration if the table already exists in production without the index.

**Warning signs:**
- `EXPLAIN QUERY PLAN SELECT * FROM cache WHERE provider = ? AND cache_key = ?` shows "SCAN TABLE cache"
- Cache lookup times increase linearly as the cache table grows
- SQLite profiling shows cache queries taking longer than actual API calls

**Phase to address:**
Performance and scaling phase — index the cache table before implementing automatic cache eviction, since eviction queries also need the `expires_at` index.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `except Exception: return None` in providers | Keeps waterfall moving on any error | Silent data loss; impossible to distinguish provider timeout from auth failure from network error | Never — always log or return typed failure result |
| Single global semaphore across all providers | Simple implementation | One slow provider throttles all providers; 429 errors from tight providers drag down permissive ones | Only in initial MVP before provider-specific limits are added |
| Per-row `httpx.AsyncClient` creation | No state to manage | TLS handshake overhead on every call; no connection reuse; PoolTimeout risk at scale | Never for batch operations |
| String-formatted SQL queries | Slightly faster to write | SQL injection vulnerability on any user-controlled input reaching queries | Never — parameterized queries have identical performance |
| Separate DB writes for cache + campaign + credit | Simpler per-feature implementation | Crash between writes leaves inconsistent state requiring manual cleanup | Never where atomicity matters — use transactions |
| Full CSV in `asyncio.gather()` | Simpler code | OOM crash on large imports; no partial progress | Only for CSVs provably under 50 rows |
| No WAL checkpoint management | Zero configuration overhead | WAL file grows to GB range under sustained load | Never in production with sustained batch workloads |

---

## Integration Gotchas

Common mistakes when connecting to external API providers.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Apollo.io | Catching `HTTP 429` as a generic error and immediately retrying, triggering more 429s | Implement exponential backoff with jitter; reduce concurrency semaphore count on 429 |
| Findymail / Icypeas / ContactOut | Direct dict access `response["email"]` without `.get()` | Use `response.get("email")` with explicit fallback; log unexpected response shapes |
| All providers | Creating a new `httpx.AsyncClient` per enrichment call | Share one long-lived `AsyncClient` per provider; close it at application shutdown |
| All providers | Treating `HTTP 200 with empty results` the same as `HTTP 200 with results` | Explicitly check result payload is non-empty before caching and marking as success |
| All providers | No timeout on slow API responses | Set `httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)` — enrichment APIs can take 10-30s |
| ContactOut | Using LinkedIn URL directly without validating format | Validate LinkedIn URL format before passing to ContactOut; invalid URLs waste credits |
| SMTP verification | No rate limiting per domain | Track verification attempts per domain per hour; skip further attempts after 3 failures (spam detection risk) |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unindexed cache table | Cache lookups slower than API calls after DB grows | Add composite index on `(provider, cache_key)` at schema creation | ~10,000 cache rows (~weeks of operation) |
| `asyncio.gather()` on full CSV | OOM kill on large imports | Process in explicit chunks of 50-100 rows | ~500 rows |
| Fixed concurrency limit across providers | 429 storms or underutilization | Per-provider semaphores with adaptive adjustment | First day of production batch runs |
| Unbounded WAL file growth | Query times degrade during long batch | `PRAGMA wal_checkpoint(TRUNCATE)` between chunks | ~1 hour of sustained batch enrichment |
| Unshared HTTP clients | Each API call includes TLS handshake time | Single long-lived `AsyncClient` per provider | Every call at any scale — overhead is constant but cumulative |
| No deduplication before enrichment | Same contact enriched across campaigns, credits wasted | Cross-campaign dedup check before waterfall entry point | First time two campaigns share a contact list |
| Unbounded pattern engine queries | Memory spike on domains with many learned patterns | Paginate pattern queries; cap patterns per domain | Domains with >100 learned email patterns |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| String-formatted SQL in `database.py` | SQL injection if any user-controlled string (company name, domain, email from import) reaches a query | Replace all string-formatted queries with parameterized queries; audit entire `database.py` |
| No API key rotation mechanism | Single leaked key compromises all enrichment budget with no recovery path | Add key rotation support in settings; track key age; log key usage anomalies |
| SMTP probing without per-domain rate limiting | SMTP verification triggers spam detection on target domains, poisoning future deliverability checks | Rate limit SMTP probes to max 3 per domain per hour; add exponential backoff after rejection |
| Cache stores raw email addresses without access control | Any user of the shared Streamlit instance can view enrichment results for all campaigns | Acceptable for internal team tool; re-evaluate if access broadens beyond trusted team |
| No schema migration tracking | Ad-hoc schema changes break existing databases silently | Use a schema version table; run migrations programmatically at startup; never alter schema inline |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No pause/resume for batch enrichment | Network interruption or accidental close loses all progress; user must restart the entire campaign | Implement campaign checkpoint every N rows; resume from last checkpoint on restart |
| Silent enrichment failures treated as "not found" | User assumes no email exists for a contact when actually a provider API key expired or rate limit hit | Distinguish between "no result found" and "provider error" in campaign results; show error counts separately |
| No progress indicator during large batch | User clicks Enrich and sees nothing for minutes; may click again creating duplicate campaigns | Show row-by-row progress with provider name and status; update every 5-10 rows |
| Budget exhaustion discovered after the batch | Credits consumed before user knows budget was hit | Check budget estimate before starting batch; warn if batch may exceed remaining budget |
| Duplicate patterns for same domain | Pattern confidence scores become unreliable; conflicting patterns produce inconsistent email generation | Deduplicate patterns on write; use upsert semantics in `pattern_engine.py` |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Exception handling refactor:** Looks done when exception types are narrowed. Verify each handler body — does it log with context? Does it return a typed failure or raise? Silent handlers with specific types are just as bad as bare except.
- [ ] **SQLite parameterized queries:** Looks done when obvious string concatenation is replaced. Verify with `grep -n "%" database.py` and `grep -n "f\"" database.py` — format strings in SQL are the same risk as `%` concatenation.
- [ ] **Connection pooling:** Looks done when `AsyncClient` is moved to class level. Verify client is created once at application start, not once per class instantiation (if the class is instantiated per-request, moving to class level doesn't help).
- [ ] **Cache indexing:** Looks done when `CREATE INDEX` is added to schema. Verify the index is actually used — run `EXPLAIN QUERY PLAN` on the cache lookup query and confirm it says "USING INDEX".
- [ ] **Batch chunking:** Looks done when rows are sliced into groups. Verify memory profile — chunking the coroutine list but passing all chunks to `asyncio.gather()` immediately doesn't help. Chunks must be awaited sequentially.
- [ ] **Budget atomicity:** Looks done when budget check is near deduction code. Verify they share a single `BEGIN IMMEDIATE` transaction — proximity in code is not the same as atomicity.
- [ ] **WAL checkpoint management:** Looks done when `PRAGMA journal_mode=WAL` is set. Verify WAL file size doesn't grow during batch runs — WAL mode without checkpoint management is incomplete.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Silent exceptions masked real errors, corrupt campaign state | HIGH | Audit all campaign rows for inconsistent state (enriched in cache but pending in campaign); re-run affected rows; add retrospective logging |
| Budget race condition overspent limits | MEDIUM | Identify affected time window from credit logs; calculate overages; set budget to 0 temporarily; add transaction fix before re-enabling |
| Non-atomic crash left orphaned rows | MEDIUM | Run reconciliation query: find rows where cache has result but campaign row is "pending"; mark as complete or re-queue; then add transaction fix |
| WAL file grown to GB | LOW | Run `PRAGMA wal_checkpoint(TRUNCATE)` manually via sqlite3 CLI; restart application; add checkpoint scheduling going forward |
| Cache table missing index (existing production DB) | LOW | Run `CREATE INDEX IF NOT EXISTS` — safe on existing data; SQLite builds index online; no downtime required |
| httpx PoolTimeout after hours of operation | LOW | Restart the Streamlit server to reset client pool; implement client refresh logic to prevent recurrence |
| Pattern duplicates causing conflicting matches | MEDIUM | Run dedup query on `pattern_engine` table grouping by `(domain, pattern)`; keep highest-confidence entry; add upsert on write |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Bare exception refactor still swallowing errors | Phase 1: Security & Hardening | Grep for handlers without log calls; trigger known error conditions and confirm logs appear |
| Non-atomic budget check + deduction | Phase 1: Security & Hardening | Concurrent test: two sessions against same budget limit; verify no overage |
| Non-atomic campaign state on crash | Phase 1: Security & Hardening | Kill process mid-batch; verify no orphaned rows; resume from checkpoint cleanly |
| SQL injection in database.py | Phase 1: Security & Hardening | Audit with grep; send malicious input through all query paths in tests |
| gather() loading full batch into memory | Phase 2: Performance & Scaling | Memory profiling during 500-row import; confirm flat memory profile during chunked processing |
| Unshared httpx.AsyncClient | Phase 2: Performance & Scaling | Profiling shows TLS handshake eliminated after first request per provider |
| Fixed concurrency causing 429 storms | Phase 2: Performance & Scaling | Simulate provider rate limiting; verify adaptive semaphore backs off correctly |
| WAL file unbounded growth | Phase 2: Performance & Scaling | Monitor WAL file size during 1-hour batch; verify checkpoint scheduling keeps it bounded |
| Cache table missing index | Phase 2: Performance & Scaling | EXPLAIN QUERY PLAN confirms index usage; cache lookup time constant as table grows |
| No deduplication before enrichment | Phase 3: New Capabilities | Run two campaigns with shared contacts; confirm second campaign skips already-enriched contacts |
| SMTP probing triggers spam detection | Phase 1: Security & Hardening | Rate limiter test: 4th probe to same domain in 1 hour is blocked |
| Pattern duplicates | Phase 3: New Capabilities | Insert duplicate pattern; verify upsert replaces rather than duplicates |

---

## Sources

- Python asyncio official documentation: https://docs.python.org/3/library/asyncio-dev.html
- PEP 760 — No More Bare Excepts: https://peps.python.org/pep-0760/
- SQLite WAL mode official documentation: https://sqlite.org/wal.html
- SQLite performance tuning (phiresky): https://phiresky.github.io/blog/2020/sqlite-performance-tuning/
- SQLite concurrent writes and "database is locked": https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/
- httpx async support and connection pooling: https://www.python-httpx.org/async/
- httpx resource limits: https://www.python-httpx.org/advanced/resource-limits/
- asyncio concurrency limiting patterns: https://death.andgravity.com/limit-concurrency
- B2B data enrichment mistakes: https://www.slashexperts.com/post/b2b-data-enrichment-mistakes-that-cost-companies-10k-monthly-and-how-to-fix-them
- Known codebase issues: .planning/codebase/CONCERNS.md (HIGH confidence — direct codebase analysis)

---
*Pitfalls research for: Python async B2B enrichment pipeline (Clay-Dupe)*
*Researched: 2026-03-04*
