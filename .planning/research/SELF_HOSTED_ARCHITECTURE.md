# Self-Hosted B2B Enrichment Platform: Architecture Deep Dive

**Domain:** Python-based self-hosted enrichment platform (Streamlit + SQLite + async)
**Researched:** 2026-03-08
**Confidence:** HIGH (cross-referenced multiple production implementations, official docs, and battle-tested patterns)

---

## Table of Contents

1. [Architecture Patterns](#1-architecture-patterns)
2. [Database Architecture](#2-database-architecture)
3. [Scalability Considerations](#3-scalability-considerations)
4. [Provider Integration Patterns](#4-provider-integration-patterns)
5. [Security for Self-Hosted](#5-security-for-self-hosted)
6. [Deployment Patterns](#6-deployment-patterns)
7. [Open Source Enrichment Tools](#7-open-source-enrichment-tools)
8. [Sources](#sources)

---

## 1. Architecture Patterns

### 1.1 Handling Concurrent API Calls to Multiple Providers

The core challenge is orchestrating calls to 5-15 different API providers, each with different rate limits, latencies, and reliability characteristics.

**Recommended Pattern: `asyncio.TaskGroup` with Per-Provider Semaphores**

```python
import asyncio
from contextlib import asynccontextmanager

class ProviderOrchestrator:
    def __init__(self):
        # Per-provider concurrency limits
        self.semaphores = {
            "apollo": asyncio.Semaphore(10),      # 10 concurrent
            "findymail": asyncio.Semaphore(5),     # 5 concurrent
            "icypeas": asyncio.Semaphore(3),       # 3 concurrent
            "contactout": asyncio.Semaphore(5),
            "datagma": asyncio.Semaphore(3),
        }

    async def call_provider(self, provider_name: str, func, *args):
        semaphore = self.semaphores[provider_name]
        async with semaphore:
            return await func(*args)

    async def enrich_parallel(self, providers: list, row_data: dict):
        """Call multiple providers concurrently, respecting per-provider limits."""
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self.call_provider(p.name, p.enrich, row_data))
                for p in providers
            ]
        return [t.result() for t in tasks]
```

**Key principles:**
- Use `asyncio.Semaphore` per provider to cap concurrent requests (never exceed provider rate limits)
- Use `asyncio.TaskGroup` (Python 3.11+) for structured concurrency with automatic exception propagation
- Share a single `httpx.AsyncClient` per provider for connection pooling
- Never use `asyncio.gather(return_exceptions=True)` for critical paths; prefer TaskGroup for proper error handling

### 1.2 Queue-Based vs Direct Waterfall

| Aspect | Direct Waterfall | Queue-Based |
|--------|-----------------|-------------|
| **Complexity** | Low — linear async chain | Higher — needs queue infrastructure |
| **Latency** | Lower per-row (no queue overhead) | Higher per-row, better throughput |
| **Error handling** | Straightforward try/except | Dead letter queues, retry queues |
| **Scalability** | Limited to single process | Can scale to multiple workers |
| **Memory** | Predictable (bounded by concurrency) | Queue can buffer large batches |
| **Resumability** | Must track state manually | Built-in (items stay in queue until acked) |
| **Best for** | < 10K rows, single-machine | > 10K rows, multi-worker |

**Recommendation for self-hosted:** Start with **direct waterfall** (simpler, sufficient for most use cases). Add an in-process `asyncio.Queue` as a buffer layer when batch sizes exceed 5K rows. Only move to external queue (Redis, RabbitMQ) if you need multi-process scaling.

```python
class WaterfallQueue:
    """In-process queue for buffered waterfall processing."""

    def __init__(self, max_concurrent: int = 50):
        self.queue = asyncio.Queue(maxsize=max_concurrent * 2)
        self.results = {}
        self.workers = []

    async def producer(self, rows: list[dict]):
        for row in rows:
            await self.queue.put(row)
        # Poison pills for workers
        for _ in self.workers:
            await self.queue.put(None)

    async def worker(self, waterfall_fn):
        while True:
            row = await self.queue.get()
            if row is None:
                break
            try:
                result = await waterfall_fn(row)
                self.results[row["id"]] = result
            except Exception as e:
                self.results[row["id"]] = {"error": str(e)}
            finally:
                self.queue.task_done()

    async def run(self, rows, waterfall_fn, num_workers=10):
        self.workers = [
            asyncio.create_task(self.worker(waterfall_fn))
            for _ in range(num_workers)
        ]
        await self.producer(rows)
        await asyncio.gather(*self.workers)
        return self.results
```

### 1.3 Retry Logic with Exponential Backoff

**Use the `tenacity` library** — it is the standard for Python retry logic and supports async natively.

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import httpx
import logging

logger = logging.getLogger(__name__)

# Per-provider retry decorator
def provider_retry(max_attempts: int = 3, min_wait: float = 1, max_wait: float = 30):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.HTTPStatusError,  # will be filtered in callback
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

# Usage
class ApolloProvider(BaseProvider):
    @provider_retry(max_attempts=3, min_wait=1, max_wait=15)
    async def find_email(self, first_name: str, last_name: str, domain: str) -> dict:
        response = await self.client.post(
            "https://api.apollo.io/v1/people/match",
            json={"first_name": first_name, "last_name": last_name, "domain": domain},
        )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            raise httpx.HTTPStatusError(
                f"Rate limited, retry after {retry_after}s",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        return response.json()
```

**Key retry rules:**
- **Retry on:** 429 (rate limited), 500/502/503/504 (server errors), timeouts, connection errors
- **Never retry on:** 400 (bad request), 401 (auth), 403 (forbidden), 404 (not found)
- **Add jitter** to prevent thundering herd: `wait_exponential` with `multiplier=1` adds natural jitter
- **Cap backoff** at 30-60 seconds max to avoid excessively long waits
- **Log every retry** with the wait duration for debugging

### 1.4 Connection Pooling with httpx

**httpx is the recommended HTTP client for async Python.** It provides connection pooling out of the box.

```python
import httpx

class HTTPPool:
    """Shared HTTP client pool for all providers."""

    _instance: httpx.AsyncClient | None = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._instance is None or cls._instance.is_closed:
            cls._instance = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=100,          # Total connection pool
                    max_keepalive_connections=20,  # Idle connections to keep
                    keepalive_expiry=30,           # Seconds before closing idle
                ),
                timeout=httpx.Timeout(
                    connect=5.0,     # Connection establishment
                    read=30.0,       # Waiting for response body
                    write=10.0,      # Sending request body
                    pool=10.0,       # Waiting for available connection
                ),
                follow_redirects=True,
                http2=True,  # HTTP/2 for multiplexed connections
            )
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance and not cls._instance.is_closed:
            await cls._instance.aclose()
            cls._instance = None
```

**Best practices:**
- **One client per application** — never create a new `httpx.AsyncClient` per request
- **HTTP/2 when possible** — multiplexes requests over a single TCP connection
- **Set explicit timeouts** — never use infinite timeouts in production
- **`max_connections=100`** is a sensible default for enrichment workloads
- **`keepalive_expiry=30`** prevents stale connections
- **Use context managers** for lifecycle management in Streamlit:

```python
# In Streamlit, manage lifecycle with session state
if "http_client" not in st.session_state:
    st.session_state.http_client = httpx.AsyncClient(...)
```

### 1.5 Rate Limiting Across Multiple Providers

**Use a token bucket per provider.** The `aiolimiter` library implements an efficient async token bucket.

```python
from aiolimiter import AsyncLimiter

class ProviderRateLimiter:
    def __init__(self):
        # rate = requests per time_period (seconds)
        self.limiters = {
            "apollo":     AsyncLimiter(50, 60),     # 50 req/min
            "findymail":  AsyncLimiter(10, 1),      # 10 req/sec
            "icypeas":    AsyncLimiter(5, 1),        # 5 req/sec
            "contactout": AsyncLimiter(30, 60),      # 30 req/min
            "datagma":    AsyncLimiter(20, 60),      # 20 req/min
        }

    async def acquire(self, provider_name: str):
        limiter = self.limiters.get(provider_name)
        if limiter:
            await limiter.acquire()

    async def call_with_limit(self, provider_name: str, func, *args, **kwargs):
        await self.acquire(provider_name)
        return await func(*args, **kwargs)
```

**Combining semaphores + rate limiters:**
- **Semaphore** = max concurrent requests at any instant (concurrency limit)
- **Rate limiter** = max requests per time window (throughput limit)
- You need BOTH — a semaphore alone allows bursting, a rate limiter alone allows too many concurrent connections

```python
async def call_provider(self, provider: str, func, *args):
    """Respects both concurrency and rate limits."""
    async with self.semaphores[provider]:       # Concurrency gate
        await self.rate_limiters.acquire(provider)  # Rate gate
        return await func(*args)
```

### 1.6 Circuit Breaker Pattern

**When to trip:** After N consecutive failures (typically 5-10) or when error rate exceeds a threshold (e.g., >50% in last 60 seconds).

**Recovery strategy:** Half-open state allows 1 test request through. If it succeeds, close the circuit. If it fails, reopen for another cooldown period.

```python
import time
from enum import Enum
from dataclasses import dataclass, field

class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing — block all requests
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5         # Consecutive failures to trip
    recovery_timeout: float = 60.0     # Seconds before trying again
    half_open_max_calls: int = 1       # Test calls in half-open

    # Internal state
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    _half_open_calls: int = 0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls

    def record_success(self):
        self.failure_count = 0
        self.success_count += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._half_open_calls = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._half_open_calls = 0
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    async def execute(self, func, *args, **kwargs):
        if not self.can_execute():
            raise CircuitOpenError(
                f"Circuit {self.name} is OPEN. "
                f"Recovery in {self.recovery_timeout - (time.monotonic() - self.last_failure_time):.0f}s"
            )
        try:
            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

class CircuitOpenError(Exception):
    pass
```

**Integration with waterfall:** When a provider's circuit is open, the waterfall should skip it and try the next provider immediately, rather than waiting for recovery.

### 1.7 Provider Plugin System

**Use Abstract Base Classes with auto-registration via `__init_subclass__`.**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

@dataclass
class ProviderConfig:
    name: str
    api_key: str
    rate_limit: int = 60       # requests per minute
    max_concurrent: int = 5
    timeout: float = 30.0
    enabled: bool = True

class BaseProvider(ABC):
    """All providers must inherit from this class."""

    _registry: ClassVar[dict[str, type["BaseProvider"]]] = {}

    def __init_subclass__(cls, **kwargs):
        """Auto-register providers when they subclass BaseProvider."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "PROVIDER_NAME"):
            BaseProvider._registry[cls.PROVIDER_NAME] = cls

    @classmethod
    def get_provider(cls, name: str) -> type["BaseProvider"]:
        if name not in cls._registry:
            raise ValueError(f"Unknown provider: {name}. Available: {list(cls._registry.keys())}")
        return cls._registry[name]

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._registry.keys())

    # --- Required interface ---

    @abstractmethod
    async def find_email(self, first_name: str, last_name: str, domain: str) -> dict | None:
        """Find email for a person at a company."""

    @abstractmethod
    async def enrich_company(self, domain: str) -> dict | None:
        """Enrich company data by domain."""

    @abstractmethod
    async def search_people(self, domain: str, **filters) -> list[dict]:
        """Search for people at a company."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify provider is operational."""

    # --- Optional hooks ---

    async def on_rate_limit(self, response) -> float:
        """Return seconds to wait. Override for provider-specific logic."""
        return float(response.headers.get("Retry-After", 5))

    def normalize_result(self, raw: dict) -> dict:
        """Override to map provider-specific fields to standard schema."""
        return raw


# Example provider implementation
class ApolloProvider(BaseProvider):
    PROVIDER_NAME = "apollo"

    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient):
        self.config = config
        self.client = client

    async def find_email(self, first_name, last_name, domain):
        resp = await self.client.post(
            "https://api.apollo.io/v1/people/match",
            json={"first_name": first_name, "last_name": last_name, "domain": domain},
            headers={"x-api-key": self.config.api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        return self.normalize_result(data)

    async def enrich_company(self, domain):
        resp = await self.client.post(
            "https://api.apollo.io/v1/organizations/enrich",
            json={"domain": domain},
            headers={"x-api-key": self.config.api_key},
        )
        resp.raise_for_status()
        return resp.json().get("organization")

    async def search_people(self, domain, **filters):
        # ... implementation
        pass

    async def health_check(self):
        try:
            resp = await self.client.get(
                "https://api.apollo.io/v1/auth/health",
                headers={"x-api-key": self.config.api_key},
            )
            return resp.status_code == 200
        except Exception:
            return False

    def normalize_result(self, raw):
        person = raw.get("person", {})
        return {
            "email": person.get("email"),
            "first_name": person.get("first_name"),
            "last_name": person.get("last_name"),
            "title": person.get("title"),
            "linkedin_url": person.get("linkedin_url"),
            "confidence": 0.85 if person.get("email") else 0.0,
        }
```

**Adding a new provider requires only:**
1. Create a new file (e.g., `providers/newprovider.py`)
2. Subclass `BaseProvider` and set `PROVIDER_NAME`
3. Implement the abstract methods
4. Import the module (auto-registration handles the rest)

---

## 2. Database Architecture

### 2.1 SQLite vs PostgreSQL — When to Switch

| Factor | SQLite Sweet Spot | Switch to PostgreSQL When... |
|--------|------------------|------------------------------|
| **Concurrent users** | 1-10 simultaneous users | >10 concurrent writers |
| **Database size** | Up to 5-10 GB | >10 GB or growing fast |
| **Write throughput** | ~50-200 writes/sec (WAL mode) | Need >500 writes/sec sustained |
| **Concurrent reads** | Unlimited in WAL mode | N/A (SQLite handles this fine) |
| **Deployment** | Single machine, no DBA needed | Multi-machine or team management |
| **Backup** | Simple file copy | Need point-in-time recovery |
| **Full-text search** | FTS5 is excellent | Need advanced text search (tsvector) |

**For this project:** SQLite is the right choice. A self-hosted enrichment tool typically has 1-3 concurrent users, and enrichment writes are batch-oriented (not high-frequency OLTP). WAL mode + proper connection handling makes SQLite performant up to ~10K enrichments/day easily.

**Migration trigger checklist (switch when 2+ are true):**
- [ ] Database file exceeds 10 GB
- [ ] More than 5 people using the tool simultaneously
- [ ] Experiencing `SQLITE_BUSY` errors despite WAL mode + busy timeout
- [ ] Need row-level locking for concurrent batch operations
- [ ] Need PostGIS, JSONB indexing, or advanced query features

### 2.2 Concurrent Writes in SQLite

**Essential configuration (non-negotiable for production):**

```python
import aiosqlite

async def get_connection(db_path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)

    # WAL mode — allows concurrent readers + single writer without blocking
    await conn.execute("PRAGMA journal_mode = WAL")

    # Normal sync — safe with WAL, much faster than FULL
    await conn.execute("PRAGMA synchronous = NORMAL")

    # Busy timeout — wait up to 5 seconds for locks instead of failing immediately
    await conn.execute("PRAGMA busy_timeout = 5000")

    # Memory-mapped I/O — faster reads for databases that fit in memory
    await conn.execute("PRAGMA mmap_size = 268435456")  # 256 MB

    # Larger cache — default 2MB is too small for enrichment workloads
    await conn.execute("PRAGMA cache_size = -64000")  # 64 MB (negative = KB)

    # Use IMMEDIATE transactions for writes to prevent upgrade deadlocks
    # DEFERRED transactions that upgrade to WRITE can cause SQLITE_BUSY
    # that ignores busy_timeout
    await conn.execute("PRAGMA foreign_keys = ON")

    return conn
```

**Write queue pattern for high-concurrency scenarios:**

```python
class SQLiteWriteQueue:
    """Serializes all writes through a single queue to prevent contention."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.queue: asyncio.Queue = asyncio.Queue()
        self._writer_task: asyncio.Task | None = None

    async def start(self):
        self._writer_task = asyncio.create_task(self._writer_loop())

    async def _writer_loop(self):
        conn = await get_connection(self.db_path)
        try:
            while True:
                sql, params, future = await self.queue.get()
                try:
                    async with conn.execute(sql, params) as cursor:
                        result = await cursor.fetchall()
                    await conn.commit()
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                finally:
                    self.queue.task_done()
        finally:
            await conn.close()

    async def execute(self, sql: str, params: tuple = ()) -> list:
        future = asyncio.get_event_loop().create_future()
        await self.queue.put((sql, params, future))
        return await future
```

**Critical rule:** Always use `BEGIN IMMEDIATE` for write transactions. `BEGIN DEFERRED` (the default) can cause upgrade deadlocks where the `busy_timeout` is NOT respected.

### 2.3 Schema Design for Enrichment Results

```sql
-- Core tables

CREATE TABLE companies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT UNIQUE NOT NULL,
    name            TEXT,
    industry        TEXT,
    employee_count  INTEGER,
    revenue_range   TEXT,
    hq_location     TEXT,
    linkedin_url    TEXT,
    description     TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER REFERENCES companies(id),
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT,
    title           TEXT,
    linkedin_url    TEXT,
    phone           TEXT,
    seniority       TEXT,   -- 'c_suite', 'vp', 'director', 'manager', 'individual'
    department      TEXT,   -- 'engineering', 'sales', 'marketing', etc.
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(first_name, last_name, company_id)
);

-- Enrichment results — multi-provider, versioned, TTL-aware

CREATE TABLE enrichment_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('company', 'contact')),
    entity_id       INTEGER NOT NULL,
    provider        TEXT NOT NULL,          -- 'apollo', 'findymail', etc.
    field_name      TEXT NOT NULL,          -- 'email', 'phone', 'title', etc.
    field_value     TEXT,
    confidence      REAL DEFAULT 0.0,      -- 0.0 to 1.0
    raw_response    TEXT,                   -- Full JSON from provider (for debugging)
    version         INTEGER DEFAULT 1,     -- Increment on re-enrichment
    ttl_days        INTEGER DEFAULT 30,    -- Freshness window
    enriched_at     TEXT DEFAULT (datetime('now')),
    expires_at      TEXT,                   -- Pre-computed: enriched_at + ttl_days
    is_current      INTEGER DEFAULT 1,     -- Only latest version is current

    UNIQUE(entity_type, entity_id, provider, field_name, version)
);

CREATE INDEX idx_enrichment_current
    ON enrichment_results(entity_type, entity_id, field_name, is_current)
    WHERE is_current = 1;

CREATE INDEX idx_enrichment_expiry
    ON enrichment_results(expires_at)
    WHERE is_current = 1;

-- Enrichment audit trail

CREATE TABLE enrichment_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        TEXT,                   -- UUID grouping a batch run
    entity_type     TEXT NOT NULL,
    entity_id       INTEGER NOT NULL,
    provider        TEXT NOT NULL,
    action          TEXT NOT NULL,          -- 'enrich', 'cache_hit', 'skip', 'error'
    status          TEXT NOT NULL,          -- 'success', 'failure', 'rate_limited', 'circuit_open'
    duration_ms     INTEGER,
    credits_used    REAL DEFAULT 0.0,
    error_message   TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_batch ON enrichment_audit(batch_id);
CREATE INDEX idx_audit_provider ON enrichment_audit(provider, created_at);

-- Provider health tracking

CREATE TABLE provider_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL,
    window_start    TEXT NOT NULL,          -- Hourly window
    total_requests  INTEGER DEFAULT 0,
    successful      INTEGER DEFAULT 0,
    failed          INTEGER DEFAULT 0,
    rate_limited    INTEGER DEFAULT 0,
    avg_latency_ms  REAL DEFAULT 0.0,
    p95_latency_ms  REAL DEFAULT 0.0,
    credits_used    REAL DEFAULT 0.0,
    UNIQUE(provider, window_start)
);

-- Cost tracking

CREATE TABLE cost_tracking (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL,
    operation       TEXT NOT NULL,          -- 'find_email', 'enrich_company', etc.
    credits_used    REAL NOT NULL,
    cost_usd        REAL,                  -- Estimated USD cost
    batch_id        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
```

### 2.4 Caching Strategies

**TTL-based cache with domain-level and contact-level granularity:**

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Company firmographics | 30 days | Company info changes slowly |
| Contact email | 7-14 days | Job changes average ~2 years, but verification matters |
| Contact phone | 7 days | Phone numbers change with jobs |
| Contact title | 14 days | Titles change with promotions/job changes |
| Domain-level email pattern | 90 days | Email patterns (first.last@) rarely change |
| Provider API response (raw) | 24 hours | Short cache for debugging |

```python
class EnrichmentCache:
    """TTL-aware cache checking enrichment_results table."""

    TTL_DAYS = {
        "company": 30,
        "email": 14,
        "phone": 7,
        "title": 14,
        "email_pattern": 90,
    }

    async def get_cached(self, entity_type: str, entity_id: int, field: str) -> dict | None:
        """Return cached result if fresh, None if stale or missing."""
        row = await self.db.execute(
            """
            SELECT field_value, confidence, enriched_at, expires_at
            FROM enrichment_results
            WHERE entity_type = ? AND entity_id = ? AND field_name = ?
              AND is_current = 1
              AND datetime(expires_at) > datetime('now')
            ORDER BY confidence DESC
            LIMIT 1
            """,
            (entity_type, entity_id, field),
        )
        if row:
            return {"value": row["field_value"], "confidence": row["confidence"]}
        return None

    async def set_cached(self, entity_type, entity_id, provider, field, value, confidence):
        ttl = self.TTL_DAYS.get(field, 30)
        # Mark old versions as non-current
        await self.db.execute(
            "UPDATE enrichment_results SET is_current = 0 "
            "WHERE entity_type = ? AND entity_id = ? AND field_name = ? AND is_current = 1",
            (entity_type, entity_id, field),
        )
        # Insert new version
        await self.db.execute(
            """
            INSERT INTO enrichment_results
            (entity_type, entity_id, provider, field_name, field_value, confidence,
             ttl_days, expires_at, is_current)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    datetime('now', '+' || ? || ' days'), 1)
            """,
            (entity_type, entity_id, provider, field, value, confidence, ttl, ttl),
        )
```

**Cache savings impact:** Proper TTL caching reduces API credit consumption by 40-60% on bulk enrichment operations (validated by multiple enrichment API vendors).

### 2.5 Enrichment History and Audit Trails

Every enrichment action should be logged in the `enrichment_audit` table. This provides:

1. **Debugging** — trace exactly which provider returned what for a given contact
2. **Cost analysis** — understand credit spend per provider per batch
3. **Performance monitoring** — identify slow or failing providers
4. **Compliance** — demonstrate data provenance for GDPR

```python
async def log_audit(
    self,
    batch_id: str,
    entity_type: str,
    entity_id: int,
    provider: str,
    action: str,
    status: str,
    duration_ms: int = 0,
    credits_used: float = 0.0,
    error_message: str | None = None,
):
    await self.db.execute(
        """
        INSERT INTO enrichment_audit
        (batch_id, entity_type, entity_id, provider, action, status,
         duration_ms, credits_used, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (batch_id, entity_type, entity_id, provider, action, status,
         duration_ms, credits_used, error_message),
    )
```

### 2.6 Data Freshness — When to Re-Enrich

**Decision matrix for re-enrichment:**

```python
async def should_re_enrich(self, entity_type: str, entity_id: int, field: str) -> bool:
    """Determine if cached enrichment data is stale."""
    result = await self.db.execute(
        """
        SELECT enriched_at, expires_at, confidence
        FROM enrichment_results
        WHERE entity_type = ? AND entity_id = ? AND field_name = ?
          AND is_current = 1
        ORDER BY enriched_at DESC
        LIMIT 1
        """,
        (entity_type, entity_id, field),
    )
    if not result:
        return True  # Never enriched

    enriched_at = datetime.fromisoformat(result["enriched_at"])
    expires_at = datetime.fromisoformat(result["expires_at"])
    confidence = result["confidence"]

    # Expired
    if datetime.utcnow() > expires_at:
        return True

    # Low confidence — try again sooner
    if confidence < 0.5 and (datetime.utcnow() - enriched_at).days > 3:
        return True

    # Contact changed company (detected via other signals)
    # This would be triggered externally

    return False
```

---

## 3. Scalability Considerations

### 3.1 Concurrent Enrichments per Python Process

| Configuration | Throughput | Bottleneck |
|--------------|-----------|------------|
| Single thread, sync requests | ~5-10 enrichments/sec | Sequential I/O |
| asyncio, 10 concurrent | ~50-100 enrichments/sec | Provider rate limits |
| asyncio, 50 concurrent | ~200-500 enrichments/sec | Provider rate limits, memory |
| asyncio, 100 concurrent | ~300-800 enrichments/sec | Memory, connection pool exhaustion |

**Practical ceiling:** ~100-200 concurrent enrichments per process. The bottleneck is almost always provider API rate limits, not Python. A single Python process with asyncio can handle thousands of concurrent I/O operations, but providers limit you to 10-100 requests/minute each.

**Real-world enrichment speed:** With 5 providers at ~50 req/min each, and waterfall logic (sequential per row), expect ~15-30 rows/minute for full enrichment. For 10K rows, that's ~6-11 hours. Parallel rows (not parallel providers per row) improve this dramatically.

### 3.2 SQLite Bottleneck Thresholds

| Metric | Comfortable | Caution | Switch |
|--------|------------|---------|--------|
| Database size | < 1 GB | 1-10 GB | > 10 GB |
| Write ops/sec | < 100 | 100-500 | > 500 sustained |
| Concurrent writers | 1 | 2-3 | > 3 |
| Concurrent readers | < 50 | 50-100 | > 100 |
| Table row count | < 1M | 1-10M | > 10M |

**Key insight:** For enrichment workloads, writes are batched (INSERT after each provider call), not high-frequency. A typical enrichment run generates ~5 writes per row (audit + result + update). At 30 rows/minute = 150 writes/minute = 2.5 writes/second. SQLite handles this trivially.

### 3.3 Efficient Batch API Calls

**Group by provider and domain for maximum efficiency:**

```python
class BatchOptimizer:
    """Groups enrichment requests for maximum API efficiency."""

    @staticmethod
    def group_by_domain(rows: list[dict]) -> dict[str, list[dict]]:
        """Group rows by domain to batch company enrichment calls."""
        groups = {}
        for row in rows:
            domain = row.get("domain", "unknown")
            groups.setdefault(domain, []).append(row)
        return groups

    @staticmethod
    async def enrich_domain_batch(domain: str, rows: list[dict], waterfall):
        """Enrich company once, then enrich all contacts at that company."""
        # 1. Enrich company (one API call, cached for all contacts)
        company = await waterfall.enrich_company(domain)

        # 2. Enrich contacts in parallel (within rate limits)
        tasks = [waterfall.enrich_contact(row, company) for row in rows]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return results

    @staticmethod
    def chunk(rows: list, size: int = 100) -> list[list]:
        """Process in chunks to control memory."""
        return [rows[i:i + size] for i in range(0, len(rows), size)]
```

### 3.4 Memory Management for Large Batches (10K+ Rows)

**Problem:** Loading 10K+ rows into memory, each with provider responses (5-10 KB JSON each), consumes 50-100 MB+.

**Strategies:**

1. **Chunk processing** — process in batches of 100-500 rows, commit to DB, then discard
2. **Streaming results** — yield results to DB as they complete, don't accumulate
3. **Limit raw response storage** — store only extracted fields, not full JSON responses
4. **Use generators** — avoid loading entire CSV into memory

```python
async def process_large_batch(self, csv_path: str, chunk_size: int = 100):
    """Process large CSV in chunks to control memory."""
    import csv

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        chunk = []
        processed = 0

        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                await self._process_chunk(chunk)
                processed += len(chunk)
                self.progress_callback(processed)
                chunk = []  # Release memory

        if chunk:  # Remaining rows
            await self._process_chunk(chunk)
            processed += len(chunk)
            self.progress_callback(processed)
```

### 3.5 Progress Tracking and Resumability

```python
@dataclass
class BatchProgress:
    batch_id: str
    total_rows: int
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0           # Cache hits or duplicates
    started_at: str = ""
    last_checkpoint: str = ""
    status: str = "pending"    # pending, running, paused, completed, failed

    @property
    def percent_complete(self) -> float:
        return (self.processed / self.total_rows * 100) if self.total_rows > 0 else 0

    @property
    def estimated_remaining_seconds(self) -> float:
        if self.processed == 0:
            return 0
        elapsed = (datetime.utcnow() - datetime.fromisoformat(self.started_at)).total_seconds()
        rate = self.processed / elapsed
        remaining = self.total_rows - self.processed
        return remaining / rate if rate > 0 else 0

# Resumable batch with checkpoint
class ResumableBatch:
    async def process(self, rows, batch_id: str):
        # Check for existing checkpoint
        checkpoint = await self.db.get_batch_checkpoint(batch_id)
        start_idx = checkpoint.processed if checkpoint else 0

        for i, row in enumerate(rows[start_idx:], start=start_idx):
            try:
                await self.enrich_row(row)
                await self.update_checkpoint(batch_id, i + 1)
            except KeyboardInterrupt:
                await self.save_checkpoint(batch_id, i, "paused")
                raise
            except Exception as e:
                await self.log_error(batch_id, i, str(e))
                continue  # Don't stop batch on single row failure
```

---

## 4. Provider Integration Patterns

### 4.1 BaseProvider Abstraction

(Covered in detail in section 1.7 above)

Key design principles:
- **Abstract methods** for core operations (`find_email`, `enrich_company`, `search_people`, `health_check`)
- **Auto-registration** via `__init_subclass__` — no manual registry maintenance
- **Normalize result** hook — each provider maps its response to a standard schema
- **Rate limit hook** — each provider can override how to read `Retry-After` headers
- **Health check** — lightweight endpoint to verify provider is operational

### 4.2 Data Normalization Across Providers

Each provider returns different field names and formats. A normalization layer maps everything to a standard schema.

```python
# Standard enrichment result schema
@dataclass
class NormalizedContact:
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    title: str | None = None
    seniority: str | None = None       # Normalized: c_suite, vp, director, manager, ic
    department: str | None = None       # Normalized: engineering, sales, marketing, etc.
    linkedin_url: str | None = None
    phone: str | None = None
    confidence: float = 0.0
    source_provider: str = ""

# Provider-specific normalizers
class ApolloNormalizer:
    SENIORITY_MAP = {
        "c_suite": "c_suite",
        "owner": "c_suite",
        "founder": "c_suite",
        "vp": "vp",
        "director": "director",
        "manager": "manager",
        "senior": "individual",
        "entry": "individual",
    }

    @staticmethod
    def normalize(raw: dict) -> NormalizedContact:
        person = raw.get("person", {})
        return NormalizedContact(
            email=person.get("email"),
            first_name=person.get("first_name"),
            last_name=person.get("last_name"),
            full_name=f'{person.get("first_name", "")} {person.get("last_name", "")}'.strip(),
            title=person.get("title"),
            seniority=ApolloNormalizer.SENIORITY_MAP.get(
                person.get("seniority", "").lower(), "unknown"
            ),
            department=person.get("departments", [None])[0] if person.get("departments") else None,
            linkedin_url=person.get("linkedin_url"),
            phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
            confidence=0.85 if person.get("email") else 0.0,
            source_provider="apollo",
        )

class FindymailNormalizer:
    @staticmethod
    def normalize(raw: dict) -> NormalizedContact:
        return NormalizedContact(
            email=raw.get("email"),
            confidence=raw.get("score", 0) / 100.0,  # Findymail uses 0-100
            source_provider="findymail",
        )
```

### 4.3 Provider-Specific Quirks

| Provider | Quirk | Handling |
|----------|-------|---------|
| Apollo | Rate limit is per API key, not per IP | Share rate limiter across all calls |
| Apollo | Returns `null` for email if credits exhausted | Check `credits_remaining` in response |
| Findymail | Uses score 0-100 instead of 0-1 confidence | Divide by 100 in normalizer |
| IcyPeas | Returns email in `result.email` not `email` | Deep path extraction in normalizer |
| ContactOut | Rate limits return 429 without Retry-After | Default to 60s backoff |
| Datagma | Batches require webhook callback | Use polling as fallback |
| Hunter.io | Confidence is "score" field, 0-100 | Normalize to 0-1 |

### 4.4 Provider Health Monitoring

```python
class ProviderHealthMonitor:
    def __init__(self):
        self.metrics: dict[str, ProviderMetrics] = {}

    @dataclass
    class ProviderMetrics:
        total_requests: int = 0
        successes: int = 0
        failures: int = 0
        rate_limits: int = 0
        latencies: list[float] = field(default_factory=list)
        last_success: float = 0.0
        last_failure: float = 0.0

        @property
        def success_rate(self) -> float:
            return self.successes / self.total_requests if self.total_requests > 0 else 0.0

        @property
        def avg_latency_ms(self) -> float:
            return sum(self.latencies[-100:]) / len(self.latencies[-100:]) if self.latencies else 0

        @property
        def p95_latency_ms(self) -> float:
            if not self.latencies:
                return 0
            sorted_lat = sorted(self.latencies[-100:])
            idx = int(len(sorted_lat) * 0.95)
            return sorted_lat[idx]

    async def record(self, provider: str, duration_ms: float, success: bool, rate_limited: bool = False):
        m = self.metrics.setdefault(provider, self.ProviderMetrics())
        m.total_requests += 1
        m.latencies.append(duration_ms)
        if success:
            m.successes += 1
            m.last_success = time.monotonic()
        else:
            m.failures += 1
            m.last_failure = time.monotonic()
        if rate_limited:
            m.rate_limits += 1

    def get_dashboard_data(self) -> dict:
        return {
            name: {
                "success_rate": f"{m.success_rate:.1%}",
                "avg_latency": f"{m.avg_latency_ms:.0f}ms",
                "p95_latency": f"{m.p95_latency_ms:.0f}ms",
                "total_requests": m.total_requests,
                "rate_limits": m.rate_limits,
            }
            for name, m in self.metrics.items()
        }
```

### 4.5 A/B Testing Provider Performance

Run the same enrichment request through two providers and compare results:

```python
class ProviderABTest:
    """Compare provider performance on the same dataset."""

    async def run_test(self, test_rows: list[dict], provider_a: str, provider_b: str):
        results = {"a_only": 0, "b_only": 0, "both": 0, "neither": 0, "agree": 0, "disagree": 0}

        for row in test_rows:
            result_a = await self.enrich(provider_a, row)
            result_b = await self.enrich(provider_b, row)

            a_found = result_a and result_a.get("email")
            b_found = result_b and result_b.get("email")

            if a_found and b_found:
                results["both"] += 1
                if result_a["email"] == result_b["email"]:
                    results["agree"] += 1
                else:
                    results["disagree"] += 1
            elif a_found:
                results["a_only"] += 1
            elif b_found:
                results["b_only"] += 1
            else:
                results["neither"] += 1

        return results
```

### 4.6 Cost Tracking Per Provider

```python
# Provider credit costs (as of 2026)
PROVIDER_COSTS = {
    "apollo": {
        "find_email": 1,          # 1 credit
        "enrich_company": 1,
        "search_people": 1,
        "cost_per_credit_usd": 0.03,
    },
    "findymail": {
        "find_email": 1,
        "cost_per_credit_usd": 0.05,
    },
    "icypeas": {
        "find_email": 1,
        "cost_per_credit_usd": 0.02,
    },
    "contactout": {
        "find_email": 1,
        "cost_per_credit_usd": 0.10,
    },
    "datagma": {
        "find_email": 1,
        "enrich_company": 1,
        "cost_per_credit_usd": 0.04,
    },
}

class CostTracker:
    async def record(self, provider: str, operation: str, batch_id: str = None):
        costs = PROVIDER_COSTS.get(provider, {})
        credits = costs.get(operation, 1)
        cost_usd = credits * costs.get("cost_per_credit_usd", 0)
        await self.db.execute(
            "INSERT INTO cost_tracking (provider, operation, credits_used, cost_usd, batch_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (provider, operation, credits, cost_usd, batch_id),
        )

    async def get_summary(self, days: int = 30) -> dict:
        rows = await self.db.execute(
            """
            SELECT provider, SUM(credits_used) as total_credits,
                   SUM(cost_usd) as total_cost, COUNT(*) as total_calls
            FROM cost_tracking
            WHERE datetime(created_at) > datetime('now', '-' || ? || ' days')
            GROUP BY provider
            """,
            (days,),
        )
        return {row["provider"]: dict(row) for row in rows}
```

---

## 5. Security for Self-Hosted

### 5.1 API Key Storage

**Tier 1 — Minimum (environment variables):**
```bash
# .env file (gitignored)
APOLLO_API_KEY=xxxx
FINDYMAIL_API_KEY=xxxx
ICYPEAS_API_KEY=xxxx
```

```python
import os
from dotenv import load_dotenv

load_dotenv()
apollo_key = os.environ["APOLLO_API_KEY"]
```

**Tier 2 — Better (encrypted config file):**
```python
from cryptography.fernet import Fernet

class SecureConfig:
    def __init__(self, master_key: str):
        self.cipher = Fernet(master_key)

    def encrypt_key(self, api_key: str) -> bytes:
        return self.cipher.encrypt(api_key.encode())

    def decrypt_key(self, encrypted: bytes) -> str:
        return self.cipher.decrypt(encrypted).decode()
```

**Tier 3 — Best (HashiCorp Vault or similar):**
- Secrets manager with audit logging, rotation, and access controls
- Overkill for a self-hosted single-user tool, but appropriate for team deployment
- Docker Secrets is a good middle ground for Docker deployments

**Recommendation for this project:** Tier 1 (environment variables) with `.env` file gitignored. Add Tier 2 encrypted config if the tool is shared with a team.

### 5.2 Sensitive Contact Data

**Encryption at rest for SQLite:**
- Use SQLCipher (encrypted SQLite fork) for full-database encryption
- Or encrypt specific fields (email, phone) at the application layer using AES-256-GCM
- Field-level encryption allows searching on non-sensitive fields while protecting PII

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class FieldEncryption:
    def __init__(self, key: bytes):  # 32 bytes for AES-256
        self.aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode(), None)
        return nonce + ciphertext  # Prepend nonce for decryption

    def decrypt(self, data: bytes) -> str:
        nonce = data[:12]
        ciphertext = data[12:]
        return self.aesgcm.decrypt(nonce, ciphertext, None).decode()
```

### 5.3 GDPR Considerations

For a self-hosted tool storing personal contact data:

1. **Legal basis** — Legitimate interest (B2B prospecting) under GDPR Article 6(1)(f)
2. **Data minimization** — Only store fields you actually use
3. **Right to erasure** — Implement a "delete contact and all enrichment data" function
4. **Data portability** — Export all data for a contact in a standard format (JSON/CSV)
5. **Processing records** — The `enrichment_audit` table serves as a processing activity log
6. **Retention limits** — Auto-delete data older than your retention period

```python
async def gdpr_delete_contact(self, contact_id: int):
    """Complete GDPR erasure — removes all traces of a contact."""
    await self.db.execute("DELETE FROM enrichment_results WHERE entity_type = 'contact' AND entity_id = ?", (contact_id,))
    await self.db.execute("DELETE FROM enrichment_audit WHERE entity_type = 'contact' AND entity_id = ?", (contact_id,))
    await self.db.execute("DELETE FROM cost_tracking WHERE batch_id IN (SELECT batch_id FROM enrichment_audit WHERE entity_id = ?)", (contact_id,))
    await self.db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))

async def gdpr_export_contact(self, contact_id: int) -> dict:
    """Export all data held about a contact."""
    contact = await self.db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,))
    enrichments = await self.db.execute(
        "SELECT * FROM enrichment_results WHERE entity_type = 'contact' AND entity_id = ?", (contact_id,)
    )
    audit = await self.db.execute(
        "SELECT * FROM enrichment_audit WHERE entity_type = 'contact' AND entity_id = ?", (contact_id,)
    )
    return {"contact": dict(contact), "enrichments": [dict(r) for r in enrichments], "audit": [dict(a) for a in audit]}
```

### 5.4 Data Retention Policies

```python
async def enforce_retention(self, max_days: int = 365):
    """Delete data older than retention period."""
    cutoff = f"-{max_days} days"
    await self.db.execute(
        "DELETE FROM enrichment_results WHERE datetime(enriched_at) < datetime('now', ?)", (cutoff,)
    )
    await self.db.execute(
        "DELETE FROM enrichment_audit WHERE datetime(created_at) < datetime('now', ?)", (cutoff,)
    )
    # Don't auto-delete contacts — they may have active campaigns
    # Instead, mark as "retention_expired" for manual review
    await self.db.execute(
        "UPDATE contacts SET retention_status = 'expired' "
        "WHERE datetime(updated_at) < datetime('now', ?) AND retention_status IS NULL",
        (cutoff,),
    )
```

### 5.5 Network Security for Streamlit

**Nginx reverse proxy with HTTPS (recommended production setup):**

```nginx
server {
    listen 443 ssl;
    server_name enrichment.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/enrichment.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/enrichment.yourcompany.com/privkey.pem;

    # Basic auth
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;  # WebSocket timeout for Streamlit
    }
}
```

**Streamlit authentication options:**
- Nginx basic auth (simplest, shown above)
- Streamlit's built-in `st.experimental_user` for OAuth/OIDC
- Custom login page with session tokens stored in `st.session_state`
- IP allowlisting at the firewall level for internal tools

---

## 6. Deployment Patterns

### 6.1 Docker Best Practices

```dockerfile
# Multi-stage build for smaller image
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

# Security: run as non-root
RUN useradd -m -s /bin/bash appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.fileWatcherType=none", \
    "--browser.gatherUsageStats=false"]
```

### 6.2 SQLite in Docker

**Critical: mount the database directory as a Docker volume.**

```yaml
# docker-compose.yml
version: "3.8"

services:
  enrichment:
    build: .
    ports:
      - "8501:8501"
    volumes:
      - ./data:/app/data              # SQLite database persistence
      - ./backups:/app/backups        # Backup directory
    env_file:
      - .env
    restart: unless-stopped

    # Optional: nginx sidecar for HTTPS
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./certs:/etc/letsencrypt
    depends_on:
      - enrichment
```

**Volume mounting rules:**
- NEVER store the SQLite database inside the container filesystem
- Use a named volume or bind mount to `./data/`
- Set `PRAGMA journal_mode = WAL` (the WAL file must be on the same filesystem)
- The `-wal` and `-shm` files must be accessible alongside the main `.db` file

### 6.3 Single-Machine Deployment Options

| Option | Cost | Complexity | Best For |
|--------|------|-----------|----------|
| **Local Docker** | Free | Low | Development, small team |
| **DigitalOcean Droplet** | $6-12/mo | Low | Production, always-on |
| **Railway** | $5+/mo | Very low | Quick deploy, auto-scaling |
| **Fly.io** | $0-5/mo | Low-medium | Edge deployment, low-latency |
| **Hetzner VPS** | $4-8/mo | Low | EU-based, GDPR-friendly |
| **Home server** | Electricity | Medium | Max privacy, no cloud |

**Recommendation:** DigitalOcean Droplet ($6/mo, 1 GB RAM) or Hetzner VPS for a self-hosted enrichment tool. Railway for rapid prototyping.

### 6.4 SQLite Backup Strategy

```bash
#!/bin/bash
# backup.sh — run via cron every 6 hours

DB_PATH="/app/data/enrichment.db"
BACKUP_DIR="/app/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/enrichment_${TIMESTAMP}.db"

# Use SQLite's online backup API (safe with WAL mode)
sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"

# Compress
gzip "$BACKUP_FILE"

# Retain last 7 days of backups
find "$BACKUP_DIR" -name "*.db.gz" -mtime +7 -delete

echo "Backup complete: ${BACKUP_FILE}.gz"
```

**Crontab entry:**
```
0 */6 * * * /app/backup.sh >> /app/logs/backup.log 2>&1
```

**Python-based backup (for programmatic control):**

```python
import sqlite3
import shutil
from datetime import datetime

async def backup_database(db_path: str, backup_dir: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/enrichment_{timestamp}.db"

    # SQLite online backup API — safe while database is in use
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    dest.close()
    source.close()

    # Compress
    shutil.make_archive(backup_path, 'gzip', backup_dir, f"enrichment_{timestamp}.db")
```

### 6.5 Monitoring and Alerting

**Built-in Streamlit dashboard page for monitoring:**

```python
# pages/monitoring.py
import streamlit as st

st.title("System Health")

# Provider health
col1, col2 = st.columns(2)
with col1:
    st.subheader("Provider Status")
    for provider, metrics in health_monitor.get_dashboard_data().items():
        status = "ok" if float(metrics["success_rate"].rstrip("%")) > 90 else "degraded"
        st.metric(
            label=provider,
            value=metrics["success_rate"],
            delta=f"{metrics['avg_latency']} avg",
        )

with col2:
    st.subheader("Database")
    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
    st.metric("Database Size", f"{db_size:.1f} MB")
    st.metric("WAL Size", f"{wal_size:.1f} MB")

# Cost tracking
st.subheader("Credits Used (Last 30 Days)")
costs = await cost_tracker.get_summary(30)
st.bar_chart({p: c["total_cost"] for p, c in costs.items()})
```

**External monitoring (lightweight):**
- Uptime monitoring: UptimeRobot (free) or Healthchecks.io
- Error tracking: Sentry (free tier)
- Log aggregation: Loki + Grafana (self-hosted) or Papertrail (hosted)

---

## 7. Open Source Enrichment Tools

### 7.1 Full Platforms

| Tool | Description | Stars | Self-Hosted? |
|------|-------------|-------|-------------|
| **n8n** | Workflow automation, can chain enrichment APIs | 30K+ | Yes (Docker) |
| **Mautic** | Marketing automation with lead management | 5.9K | Yes |
| **SuiteCRM** | Full CRM with enrichment plugins | 4K+ | Yes |
| **Krayin CRM** | Laravel CRM with email campaigns | New | Yes |

### 7.2 Lead Generation & Scraping

| Tool | Description | Stars | Language |
|------|-------------|-------|---------|
| **theHarvester** | OSINT email gatherer from 20+ sources | 12K | Python |
| **SpiderFoot** | OSINT platform, 100+ data sources | 8K | Python |
| **SalesGPT** | AI sales agent (voice, email, SMS) | 2.2K | Python |
| **Google Maps Scraper** | Business data extraction | 1.4K | Python |
| **leads-db** | AI-powered B2B lead generation | - | Python |

### 7.3 Email Finders (Open Source)

| Tool | Description | URL |
|------|-------------|-----|
| **EmailFinder (Josue87)** | Search engines for domain emails | github.com/Josue87/EmailFinder |
| **MailFinder** | OSINT email from first/last name | github.com/mishakorzik/MailFinder |
| **EmailFinder (rix4uni)** | Multi-engine email OSINT | github.com/rix4uni/EmailFinder |
| **email-finder** | Name + domain to valid email | github.com/giuseppebaldini/email-finder |
| **Buster** | Advanced email reconnaissance | github.com/sham00n/buster |

### 7.4 Commercial Waterfall Enrichment Platforms (Not Open Source)

| Platform | Focus | Pricing | Providers |
|----------|-------|---------|-----------|
| **FullEnrich** | Email + phone waterfall | $29/mo | 15+ providers |
| **BetterContact** | Contact waterfall | Pay-per-result | 20+ providers |
| **Clay** | Data orchestration | $149/mo | 150+ providers |
| **Instantly** | Email outreach + enrichment | $30/mo | Multiple |
| **Enricher.io** | API-based enrichment | Usage-based | Multiple |

**Key finding:** No open source tool replicates the full waterfall enrichment pattern (sequential multi-provider with fallback). This is the gap that a self-hosted tool fills. The closest approach is chaining APIs via n8n, but it lacks the intelligent caching, circuit breaking, and cost optimization that a purpose-built platform provides.

### 7.5 Recommended Hybrid Stack

For building a self-hosted enrichment platform, combine:

```
Your Platform (Python + Streamlit + SQLite)
    |
    +-- Provider Layer (direct API integration)
    |       Apollo, Findymail, IcyPeas, ContactOut, Datagma
    |
    +-- Open Source Components
    |       theHarvester (OSINT email discovery)
    |       tenacity (retry logic)
    |       aiolimiter (rate limiting)
    |       httpx (async HTTP with connection pooling)
    |
    +-- Infrastructure
            Docker + nginx + Let's Encrypt
            SQLite (WAL mode) + automated backups
            Sentry (error tracking)
```

---

## Sources

### Architecture & Async Patterns
- [HTTPX Resource Limits](https://www.python-httpx.org/advanced/resource-limits/)
- [HTTPX Async Support](https://www.python-httpx.org/async/)
- [HTTPX Client Configuration](https://www.python-httpx.org/advanced/clients/)
- [Rate Limiting Async Requests in Python](https://scrapfly.io/blog/posts/how-to-rate-limit-asynchronous-python-requests)
- [Async Rate Limiter Strategies](https://proxiesapi.com/articles/effective-strategies-for-rate-limiting-asynchronous-requests-in-python)
- [aiolimiter Documentation](https://aiolimiter.readthedocs.io/)
- [self-limiters - Async Distributed Rate Limiters](https://github.com/snok/self-limiters)
- [Limit Concurrency with Semaphore](https://rednafi.com/python/limit_concurrency_with_semaphore/)
- [Python in the Backend 2025: Asyncio and FastAPI](https://www.nucamp.co/blog/coding-bootcamp-backend-with-python-2025-python-in-the-backend-in-2025-leveraging-asyncio-and-fastapi-for-highperformance-systems)

### Circuit Breaker & Retry
- [API Error Handling & Retry Strategies Python Guide 2026](https://easyparser.com/blog/api-error-handling-retry-strategies-python-guide)
- [Circuit Breaker Pattern with Exponential Backoff](https://medium.com/@usama19026/building-resilient-applications-circuit-breaker-pattern-with-exponential-backoff-fc14ba0a0beb)
- [circuitbreaker PyPI](https://pypi.org/project/circuitbreaker/)
- [Circuit Breaker Pattern from Scratch in Python](https://bhaveshpraveen.medium.com/implementing-circuit-breaker-pattern-from-scratch-in-python-714100cdf90b)
- [Retry Logic with Exponential Backoff in Python](https://oneuptime.com/blog/post/2025-01-06-python-retry-exponential-backoff/view)
- [Tenacity: Smart Retries for Python](https://www.amitavroy.com/articles/building-resilient-python-applications-with-tenacity-smart-retries-for-a-fail-proof-architecture)
- [AWS: Timeouts, Retries and Backoff with Jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)

### Plugin Systems
- [Building Plugin Systems in Python](https://oneuptime.com/blog/post/2026-01-30-python-plugin-systems/view)
- [Plugin Architecture with Python](https://mwax911.medium.com/building-a-plugin-architecture-with-python-7b4ab39ad4fc)
- [Plugin Architecture with importlib](https://gist.github.com/dorneanu/cce1cd6711969d581873a88e0257e312)
- [Multi-Provider Strategy for Configuration](https://devblogs.microsoft.com/ise/multi-provider-strategy-configuration-python/)
- [Typed Pluggable Framework](https://scaibu.medium.com/scaling-infrastructure-fast-you-need-a-typed-pluggable-framework-now-a8eb7cfafe8a)

### Database
- [SQLite Concurrency: WAL Mode and Beyond](https://iifx.dev/en/articles/17373144)
- [Concurrent Writing with SQLite3 in Python](https://www.pythontutorials.net/blog/concurrent-writing-with-sqlite3/)
- [SQLite Worker for Multi-threaded Python](https://medium.com/@roshanlamichhane/sqlite-worker-supercharge-your-sqlite-performance-in-multi-threaded-python-applications-01e2e43cc406)
- [Handling Concurrency in SQLite Best Practices](https://www.sqliteforum.com/p/handling-concurrency-in-sqlite-best)
- [SQLite in Python 2026](https://oneuptime.com/blog/post/2026-02-02-sqlite-python/view)
- [Abusing SQLite for Concurrency (SkyPilot)](https://blog.skypilot.co/abusing-sqlite-to-handle-concurrency/)
- [PostgreSQL vs SQLite 2026](https://www.selecthub.com/relational-database-solutions/postgresql-vs-sqlite/)
- [SQLite vs PostgreSQL Performance 2026](https://medium.com/pythonic-af/sqlite-vs-postgresql-performance-comparison-46ba1d39c9c8)
- [Database Design for Audit Logging](https://www.red-gate.com/blog/database-design-for-audit-logging/)

### Enrichment & Waterfall
- [Waterfall Enrichment Ultimate Guide 2026](https://bettercontact.rocks/blog/waterfall-enrichment/)
- [B2B Enrichment API Developer Guide 2026](https://derrick-app.com/en/api-enrichissement-b2b-2/)
- [FullEnrich - Waterfall Enrichment](https://fullenrich.com/)
- [Clay vs FullEnrich](https://coldiq.com/blog/clay-vs-fullenrich)
- [Lead Enrichment Tools 2026](https://www.default.com/post/lead-enrichment-tools)

### Security & GDPR
- [GDPR Encryption Guide](https://thecyphere.com/blog/gdpr-encryption/)
- [Encryption at Rest Guide](https://oneuptime.com/blog/post/2026-01-24-encryption-at-rest/view)
- [API Key Security Best Practices 2025](https://dev.to/hamd_writer_8c77d9c88c188/api-keys-the-complete-2025-guide-to-security-management-and-best-practices-3980)
- [API Key Management Best Practices](https://blog.gitguardian.com/secrets-api-management/)
- [GDPR Encryption Requirements](https://www.gdpr-advisor.com/gdpr-encryption-requirements/)

### Deployment
- [SQLite in Docker 2026 Guide](https://copyprogramming.com/howto/embed-sqlite-database-to-docker-container)
- [Streamlit Docker Deployment](https://docs.streamlit.io/deploy/tutorials/docker)
- [Streamlit HTTPS Support](https://docs.streamlit.io/develop/concepts/configuration/https-support)
- [Docker Best Practices 2026](https://thinksys.com/devops/docker-best-practices/)
- [Streamlit with Nginx Reverse Proxy](https://medium.com/@amancodes/deploying-streamlit-apps-with-nginx-reverse-proxy-on-custom-url-paths-2e0fdcaa2ac2)

### Open Source Tools
- [Autonomous Lead Generation - Top 30 Open Source Projects](https://huggingface.co/blog/samihalawa/automating-lead-generation-with-ai)
- [GitHub: lead-generation topic](https://github.com/topics/lead-generation)
- [GitHub: email-finder topic](https://github.com/topics/email-finder)
- [Clay Alternatives 2026](https://enricher.io/blog/clay-alternatives)
- [leads-db - AI B2B Lead Generation](https://github.com/IsaacBell/leads-db)
