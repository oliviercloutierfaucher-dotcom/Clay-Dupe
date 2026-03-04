# Architecture Research

**Domain:** B2B enrichment pipeline — hardening, performance, and scaling improvements
**Researched:** 2026-03-04
**Confidence:** HIGH (derived from direct codebase analysis of existing `.planning/codebase/ARCHITECTURE.md` and `CONCERNS.md`)

## Standard Architecture

### System Overview

The existing system is a 5-layer waterfall enrichment pipeline. The milestone improvements layer onto this existing structure — they do not reshape it. Each improvement category maps to a specific layer.

```
┌──────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                            │
│   ┌──────────────────┐          ┌──────────────────┐            │
│   │   CLI (Typer)    │          │  Web UI (Streamlit)│           │
│   │  enrich, search  │          │  enrich, results  │           │
│   │  verify, stats   │          │  analytics, dash  │           │
│   └────────┬─────────┘          └────────┬──────────┘           │
├────────────┴────────────────────────────┴────────────────────────┤
│                  ENRICHMENT PIPELINE LAYER                       │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │               WaterfallOrchestrator                      │   │
│   │  RouteCategory classifier → provider sequence builder   │   │
│   │  Async semaphore (concurrency) → row chunking [NEW]     │   │
│   │  Campaign pause/resume state machine [NEW]              │   │
│   └───────────────────────┬─────────────────────────────────┘   │
├───────────────────────────┴──────────────────────────────────────┤
│                 QUALITY & COST CONTROL LAYER                     │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│   │CircuitBreaker│  │BudgetManager │  │CacheManager [+evict] │  │
│   │per provider  │  │daily/monthly │  │TTL + active eviction │  │
│   └──────────────┘  └──────────────┘  └──────────────────────┘  │
│   ┌──────────────┐  ┌──────────────┐                            │
│   │EmailVerifier │  │RateLimiter   │                            │
│   │DNS/SMTP      │  │+domain-level │                            │
│   │+rate limit   │  │rate limit    │                            │
│   └──────────────┘  └──────────────┘                            │
├──────────────────────────────────────────────────────────────────┤
│                   API PROVIDER LAYER                             │
│   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐  │
│   │  Apollo    │ │ Findymail  │ │  Icypeas   │ │ ContactOut │  │
│   │[hardened]  │ │[hardened]  │ │[hardened]  │ │[hardened]  │  │
│   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘  │
│         └──────────────┴──────────────┴──────────────┘          │
│                    Shared httpx pool [NEW]                       │
├──────────────────────────────────────────────────────────────────┤
│                    DATA ACCESS LAYER                             │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │         Database (SQLite WAL mode)                        │  │
│   │  [parameterized queries] [cache indexes] [audit trail]   │  │
│   │  tables: companies, people, campaigns, campaign_rows,    │  │
│   │          enrichment_results, cache, credit_usage,        │  │
│   │          action_logs [new], api_key_rotations [new]      │  │
│   └──────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│                    CONFIGURATION LAYER                           │
│   settings.py — ProviderConfig, ICPPresets, API keys            │
│   [+ key rotation state, adaptive concurrency config]           │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Milestone Changes |
|-----------|---------------|-------------------|
| WaterfallOrchestrator | Coordinate single-row and batch enrichment | Add chunking strategy, adaptive concurrency, pause/resume |
| RouteCategory | Classify input rows to enrichment path | No change — classification is sound |
| BaseProvider / each provider | Abstract HTTP calls to external APIs | Harden: typed exceptions, input validation, `.get()` fallbacks |
| Shared httpx pool | HTTP connection management | New: replace per-provider clients with shared pool |
| CacheManager | TTL-based result caching | Add active eviction job and SQLite indexes on lookup columns |
| BudgetManager | Daily/monthly spend enforcement | Make budget check + credit deduction atomic |
| CircuitBreaker | Provider failure detection | No change — existing implementation is sound |
| EmailVerifier | DNS/SMTP email verification | Add per-domain rate limiting |
| Database | SQLite WAL persistence | Parameterize all queries; add audit_log table; add cache indexes |
| Settings | Configuration loading | Add key rotation config and adaptive concurrency thresholds |

## Recommended Project Structure

The existing directory structure is retained. Improvements inject into existing files and add focused new modules:

```
project/
├── providers/
│   ├── base.py              # [harden] add InputValidator helper, typed exceptions
│   ├── apollo.py            # [harden] specific exceptions, .get() fallbacks, validated inputs
│   ├── findymail.py         # [harden] same pattern as apollo
│   ├── icypeas.py           # [harden] same pattern as apollo
│   ├── contactout.py        # [harden] same pattern as apollo
│   └── http_pool.py         # [NEW] shared httpx AsyncClient factory + lifecycle
│
├── enrichment/
│   ├── waterfall.py         # [perf] chunking, adaptive concurrency, pause/resume
│   ├── router.py            # no change
│   ├── classifier.py        # no change
│   └── pattern_engine.py    # [fix] dedup patterns per domain
│
├── quality/
│   ├── verification.py      # [harden] per-domain rate limiting on SMTP probing
│   ├── confidence.py        # no change
│   └── circuit_breaker.py   # no change
│
├── cost/
│   ├── budget.py            # [harden] atomic budget check+deduct; A/B test hooks
│   ├── tracker.py           # [harden] audit trail writes
│   └── cache.py             # [scale] active eviction + index enforcement
│
├── data/
│   └── database.py          # [harden] parameterized queries; audit_log table; cache indexes
│
└── config/
    └── settings.py          # [new] key rotation config, adaptive concurrency thresholds
```

### Structure Rationale

- **providers/http_pool.py:** Isolated module for shared client lifecycle avoids changing provider constructor signatures significantly. Pool is initialized once at app startup and injected.
- **cost/cache.py:** Active eviction logic belongs here rather than `data/database.py` — it is a policy decision, not a storage concern.
- **data/database.py:** All parameterization and schema changes land here; audit_log table created alongside existing schema init.
- **No new top-level folders:** This milestone is an improvement pass, not a structural reorganization. Keeping changes inside existing module boundaries minimizes regression risk.

## Architectural Patterns

### Pattern 1: Layered Hardening (Providers)

**What:** Apply a uniform defensive pattern inside each provider method: validate input → call API with specific typed exception handling → parse response with `.get()` fallbacks → return ProviderResponse.

**When to use:** Every provider method that accepts user-influenced data and calls an external API.

**Trade-offs:** Small boilerplate increase per method in exchange for eliminated silent failures and debuggable error traces.

**Example:**
```python
# Before (fragile)
async def find_email(self, first_name: str, last_name: str, domain: str) -> ProviderResponse:
    try:
        resp = await self.client.post("/find", json={"first": first_name, "domain": domain})
        return ProviderResponse(email=resp.json()["email"], found=True)
    except Exception as e:
        logger.error(f"find_email failed: {e}")
        return ProviderResponse(found=False)

# After (hardened)
async def find_email(self, first_name: str, last_name: str, domain: str) -> ProviderResponse:
    domain = InputValidator.validate_domain(domain)      # raises ValueError on bad input
    first_name = InputValidator.sanitize_name(first_name)
    try:
        resp = await self.client.post("/find", json={"first": first_name, "domain": domain})
        resp.raise_for_status()
        data = resp.json()
        return ProviderResponse(
            email=data.get("email"),
            found=bool(data.get("email")),
        )
    except httpx.TimeoutException as e:
        logger.warning("find_email timeout for %s: %s", domain, e)
        return ProviderResponse(found=False, error=str(e))
    except httpx.HTTPStatusError as e:
        logger.warning("find_email HTTP %s for %s", e.response.status_code, domain)
        return ProviderResponse(found=False, error=str(e))
    except ValueError as e:
        logger.error("find_email invalid input: %s", e)
        return ProviderResponse(found=False, error=str(e))
```

### Pattern 2: Chunk-and-Semaphore Batch Processing

**What:** Split large row lists into fixed-size chunks. Process one chunk at a time. Within each chunk, apply the existing asyncio.Semaphore to bound concurrency. Yield progress between chunks.

**When to use:** Batch enrichment for any input exceeding a configurable threshold (e.g., 100 rows).

**Trade-offs:** Slightly higher total latency for small batches; dramatically lower memory pressure and more responsive pause/resume for large batches (500+ rows).

**Example:**
```python
CHUNK_SIZE = 100  # configurable via Settings

async def enrich_batch(self, rows: list[InputRow], campaign_id: int) -> list[EnrichmentResult]:
    results = []
    chunks = [rows[i:i+CHUNK_SIZE] for i in range(0, len(rows), CHUNK_SIZE)]
    for chunk_idx, chunk in enumerate(chunks):
        if await self._is_paused(campaign_id):
            await self._wait_for_resume(campaign_id)
        chunk_results = await self._process_chunk(chunk, campaign_id)
        results.extend(chunk_results)
        await self._checkpoint_campaign(campaign_id, processed=len(results))
    return results
```

### Pattern 3: Shared HTTP Connection Pool

**What:** A single `httpx.AsyncClient` (or a small pool) created at application startup, shared across all provider instances. Each provider receives the client via constructor injection.

**When to use:** Any async provider making repeated outbound HTTP calls to the same or different hosts.

**Trade-offs:** Requires coordinated lifecycle management (startup/shutdown). Reduces TCP handshake overhead and avoids file-descriptor exhaustion on large batches.

**Example:**
```python
# http_pool.py
_shared_client: httpx.AsyncClient | None = None

def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _shared_client

async def close_shared_client() -> None:
    global _shared_client
    if _shared_client:
        await _shared_client.aclose()
        _shared_client = None
```

### Pattern 4: Active Cache Eviction (Background Job)

**What:** A periodic coroutine (or triggered on-demand before batch start) that DELETEs rows from the `cache` table where `expires_at < now()` AND optionally where total row count exceeds a configurable maximum (LRU eviction by `last_accessed`).

**When to use:** Long-running deployments where cache table would otherwise grow unboundedly.

**Trade-offs:** Requires a scheduled trigger (background asyncio task or pre-batch hook). Adds write contention to SQLite during eviction windows — mitigated by running eviction during low-activity periods or with a row-limit cap per eviction pass.

### Pattern 5: Parameterized Query Enforcement

**What:** All `database.py` queries use `?` placeholders with parameter tuples. No string formatting of user-controlled values into SQL strings.

**When to use:** Every query. No exceptions.

**Trade-offs:** Slightly more verbose query construction. Eliminates SQL injection surface completely.

## Data Flow

### Single-Row Enrichment (with hardening applied)

```
User input (CSV row or UI form)
    ↓
[InputValidator] — validate domain, sanitize names
    ↓
[CacheManager.lookup()] — parameterized query on indexed columns
    ↓ (cache miss)
[RouteClassifier] — determine RouteCategory
    ↓
[WaterfallOrchestrator] — build provider sequence
    ↓
For each provider step:
    [BudgetManager.check()] — atomic budget gate
    [CircuitBreaker.is_open()] — skip if tripped
    [RateLimiter.acquire()] — sliding window slot
    [ProviderN.find_email()] — hardened: validated inputs, typed exceptions, .get() fallbacks
    ↓ (on success)
    [CacheManager.store()] — write result with TTL
    [Database.upsert_person()] — parameterized write
    [AuditLogger.record()] — write action_log row
    [BudgetManager.deduct()] — atomic: same txn as record
    ↓
[EnrichmentResult] → returned to caller
```

### Batch Enrichment (with chunking applied)

```
Campaign rows (N rows, potentially 500+)
    ↓
[CacheEviction.evict_expired()] — pre-batch cleanup pass
    ↓
[Chunker] — split into CHUNK_SIZE groups
    ↓ (for each chunk)
[PauseCheck] — check campaign_state before each chunk
    ↓
[asyncio.Semaphore(adaptive_limit)] — bound concurrency per chunk
    ↓ (concurrent within semaphore)
[enrich_single(row)] — full single-row flow per row
    ↓
[Checkpoint] — persist chunk completion to campaign_rows
    ↓
Accumulate results → Campaign marked complete
```

### Key Data Flows

1. **Hardening flow:** User input → InputValidator → provider → typed exception boundary → ProviderResponse. Validation errors short-circuit before any API call, saving credits.

2. **Cache eviction flow:** Background task or pre-batch trigger → DELETE expired rows → if row count > max_rows, DELETE oldest by last_accessed → commit. Runs in its own transaction outside of enrichment path.

3. **Audit trail flow:** Every successful API call → AuditLogger writes (campaign_id, provider, method, credits_used, timestamp, row_id) to `action_logs`. Happens inside the same DB transaction as credit deduction for consistency.

4. **Pause/resume flow:** Campaign state stored in `campaigns` table (RUNNING / PAUSED / COMPLETE). Between chunks, orchestrator checks state. UI writes PAUSED; orchestrator reads it on next chunk boundary and suspends. Resume writes RUNNING; orchestrator resumes on next polling cycle.

## Scaling Considerations

This is a self-hosted, team-size tool. The relevant scale is 1-5 concurrent users and batch sizes up to ~5,000 rows. PostgreSQL migration is explicitly out of scope.

| Concern | Current | After Milestone |
|---------|---------|----------------|
| Batch memory | Full row list in memory | Chunked: CHUNK_SIZE rows at a time |
| Cache table size | Unbounded growth | Bounded by eviction policy + index |
| HTTP connections | N providers × M batch workers | Shared pool: bounded by pool limits |
| SQLite write contention | Unmitigated on concurrent writes | Improved: audit + budget deductions in single transactions |
| Concurrency limits | Hardcoded semaphore(5) | Adaptive: configurable per-provider rate limits |

### Scaling Priorities

1. **First bottleneck (already present):** Cache table full-scan on lookup as row count grows. Fix: add index on `(provider, enrichment_type, query_hash, expires_at)`. This is the highest-leverage single change.

2. **Second bottleneck:** Memory pressure on large CSVs. Fix: row chunking prevents full dataset materialization.

3. **Third bottleneck:** SQLite write lock contention with multiple Streamlit users. Mitigation within scope: fewer, larger transactions (batch audit writes per chunk rather than per row). Full fix (PostgreSQL) is explicitly out of scope.

## Anti-Patterns

### Anti-Pattern 1: Catching `Exception` Broadly in Providers

**What people do:** `except Exception as e: logger.error(e); return ProviderResponse(found=False)`

**Why it's wrong:** Swallows programming errors (AttributeError, TypeError) alongside expected network errors. Makes debugging silent data loss nearly impossible. Circuit breaker may not trip because the exception never propagates.

**Do this instead:** Catch `httpx.TimeoutException`, `httpx.HTTPStatusError`, `httpx.RequestError` explicitly. Let `ValueError` (from input validation) propagate or catch separately. Let unexpected exceptions propagate to the waterfall's top-level handler so they are visible.

### Anti-Pattern 2: String-Formatted SQL

**What people do:** `cursor.execute(f"SELECT * FROM cache WHERE key = '{key}'")`

**Why it's wrong:** SQL injection if `key` contains user-controlled data. Also prevents SQLite query plan caching.

**Do this instead:** `cursor.execute("SELECT * FROM cache WHERE key = ?", (key,))`

### Anti-Pattern 3: Per-Instance HTTP Clients

**What people do:** Each `ApolloProvider.__init__()` creates `self.client = httpx.AsyncClient()`.

**Why it's wrong:** With a semaphore(5) and 4 providers, up to 20 simultaneous `AsyncClient` instances can exist. Each maintains its own connection pool. File descriptors are wasted; connections cannot be reused across providers for the same host.

**Do this instead:** Pass a shared `httpx.AsyncClient` from a module-level factory. Provider constructors accept the client as a parameter.

### Anti-Pattern 4: Non-Atomic Budget Checks

**What people do:** `if budget_ok: call_api(); deduct_budget()` — check and deduction are separate operations.

**Why it's wrong:** Under concurrent enrichment (semaphore(5)), two workers can both pass the budget check before either has deducted, resulting in overspend.

**Do this instead:** Use a threading lock or asyncio lock around the check-and-deduct pair. Alternatively, deduct optimistically before the call and refund on failure.

### Anti-Pattern 5: Unbounded Batch Processing

**What people do:** `await asyncio.gather(*[enrich_single(row) for row in all_rows])`

**Why it's wrong:** Even with a semaphore, materializing 5,000 coroutine objects simultaneously consumes memory. No opportunity to pause mid-batch. No checkpointing on failure.

**Do this instead:** Chunk into groups of CHUNK_SIZE (e.g., 100). Process chunks sequentially; parallelize within chunks via semaphore. Checkpoint campaign state between chunks.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Apollo.io | REST via shared httpx client | Rate limit: varies by plan; circuit breaker guards |
| Findymail | REST via shared httpx client | Has bulk endpoint — Icypeas uses it, Apollo does not |
| Icypeas | REST via shared httpx client | Bulk operations available |
| ContactOut | REST via shared httpx client | LinkedIn-based; slower responses (10-30s) — pool timeout must accommodate |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| WaterfallOrchestrator ↔ Providers | Direct async method calls | After milestone: providers receive shared httpx client; no other interface change |
| WaterfallOrchestrator ↔ CacheManager | Direct method calls | Cache lookup before provider dispatch; write after success |
| WaterfallOrchestrator ↔ BudgetManager | Direct method calls | Must become atomic check+deduct; use asyncio.Lock |
| Providers ↔ InputValidator | Direct function calls | New boundary: validator called at top of every provider method |
| CacheManager ↔ Database | Direct SQL via Database class | After milestone: eviction runs as separate scheduled coroutine |
| AuditLogger ↔ Database | Direct SQL writes | New boundary: every enrichment event writes to action_logs within same transaction as credit_usage |
| WaterfallOrchestrator ↔ Campaign state | Database reads/writes | Pause/resume state: polled between chunks |

## Build Order Implications

The improvements have clear dependency ordering:

**Phase 1 — Hardening (no dependencies on other milestone work)**
- Parameterize all SQL queries in `data/database.py` (security; unblocks trust in data layer for audit trail)
- Add `InputValidator` to `providers/base.py`
- Apply typed exceptions + `.get()` fallbacks to all 4 providers
- No other component changes required

**Phase 2 — Performance (depends on Phase 1 having stable providers)**
- Create `providers/http_pool.py` shared client
- Inject shared client into all 4 providers (requires hardened providers from Phase 1)
- Add adaptive concurrency configuration to `settings.py`
- Update `WaterfallOrchestrator` concurrency to use adaptive limits

**Phase 3 — Scaling (depends on Phase 2 for stable orchestrator base)**
- Add SQLite indexes on cache table (`data/database.py`)
- Add active eviction to `cost/cache.py`
- Add row chunking + checkpointing to `WaterfallOrchestrator`
- Add pause/resume state machine to `WaterfallOrchestrator` + `campaigns` table

**Phase 4 — New Capabilities (depends on Phase 3 for stable batch infrastructure)**
- Audit trail: `action_logs` table + `AuditLogger` (requires hardened DB writes from Phase 1)
- Cross-campaign deduplication (requires stable campaign state from Phase 3)
- Provider A/B testing (requires stable audit trail from this phase)
- API key rotation (requires stable settings infrastructure)
- Per-domain email verification rate limiting

**Why this order:** Security defects (SQL injection, bare exceptions) represent live production risk and must be fixed before building on top of the affected components. Connection pooling depends on stable providers. Chunking/scaling depends on stable concurrency. New capabilities (audit, deduplication, A/B) depend on the entire hardened + scaled foundation.

## Sources

- `.planning/codebase/ARCHITECTURE.md` — direct codebase analysis (HIGH confidence)
- `.planning/codebase/CONCERNS.md` — documented defects and their locations (HIGH confidence)
- `.planning/PROJECT.md` — milestone scope and constraints (HIGH confidence)

---
*Architecture research for: Clay-Dupe B2B enrichment pipeline hardening, performance, and scaling milestone*
*Researched: 2026-03-04*
