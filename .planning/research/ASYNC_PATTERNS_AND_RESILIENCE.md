# Async Patterns & Resilience for API-Heavy Applications

> Deep research for Clay-Dupe's enrichment engine — hundreds of concurrent API calls across multiple providers (Apollo, Icypeas, Findymail, Datagma, ContactOut).

**Date:** 2026-03-08
**Status:** Research Complete

---

## Table of Contents

1. [Async Patterns for API Orchestration](#1-async-patterns-for-api-orchestration)
2. [Resilience Patterns](#2-resilience-patterns)
3. [Error Handling Architecture](#3-error-handling-architecture)
4. [Polling Pattern](#4-polling-pattern)
5. [Background Task Management in Streamlit](#5-background-task-management-in-streamlit)
6. [Rate Limiting Deep Dive](#6-rate-limiting-deep-dive)
7. [Memory Management](#7-memory-management)
8. [Recommended Architecture for Clay-Dupe](#8-recommended-architecture-for-clay-dupe)

---

## 1. Async Patterns for API Orchestration

### 1.1 asyncio.Semaphore vs aiometer vs Custom Rate Limiting

**When to use each:**

| Tool | Best For | Limitation |
|------|----------|------------|
| `asyncio.Semaphore` | Limiting **concurrent requests** (e.g., max 10 in-flight) | No time-based rate limiting |
| `aiometer` | Precise **requests-per-second** limits (e.g., 10 req/s) | Less flexible for per-provider config |
| Custom (token bucket) | Complex multi-provider limits with adaptive behavior | More code to maintain |

**asyncio.Semaphore** — controls how many coroutines can run concurrently:

```python
semaphore = asyncio.Semaphore(10)  # max 10 concurrent

async def rate_limited_call(url: str):
    async with semaphore:
        return await client.get(url)
```

**aiometer** — enforces strict temporal rate limits:

```python
import aiometer

results = await aiometer.run_on_each(
    enrich_contact,
    contacts,
    max_at_once=10,          # concurrency limit
    max_per_second=5,        # rate limit
)
```

**Recommendation for Clay-Dupe:** Use `asyncio.Semaphore` per provider for concurrency control, combined with a custom token bucket for time-based rate limiting. aiometer is excellent for simpler cases but lacks the per-provider granularity we need.

### 1.2 Per-Provider Concurrency Limits

Each provider has different capacity. Implement isolated semaphores:

```python
from dataclasses import dataclass

@dataclass
class ProviderLimits:
    semaphore: asyncio.Semaphore
    requests_per_minute: int
    rate_limiter: "TokenBucket"

class ProviderPool:
    def __init__(self):
        self.providers = {
            "apollo": ProviderLimits(
                semaphore=asyncio.Semaphore(10),
                requests_per_minute=50,   # free plan: 50/min, paid: 200/min
                rate_limiter=TokenBucket(rate=50/60, capacity=10),
            ),
            "findymail": ProviderLimits(
                semaphore=asyncio.Semaphore(20),
                requests_per_minute=300,  # 300 concurrent, no daily limit
                rate_limiter=TokenBucket(rate=300/60, capacity=50),
            ),
            "icypeas": ProviderLimits(
                semaphore=asyncio.Semaphore(5),
                requests_per_minute=60,
                rate_limiter=TokenBucket(rate=1, capacity=5),
            ),
            "datagma": ProviderLimits(
                semaphore=asyncio.Semaphore(5),
                requests_per_minute=60,
                rate_limiter=TokenBucket(rate=1, capacity=5),
            ),
        }

    async def call(self, provider: str, coro_fn, *args):
        limits = self.providers[provider]
        await limits.rate_limiter.acquire()
        async with limits.semaphore:
            return await coro_fn(*args)
```

### 1.3 Adaptive Concurrency (AIMD-style)

Reduce concurrency on 429s, increase on success — inspired by TCP congestion control (Additive Increase, Multiplicative Decrease):

```python
class AdaptiveSemaphore:
    """Semaphore that adjusts its limit based on success/failure signals."""

    def __init__(self, initial: int = 10, min_limit: int = 1, max_limit: int = 50):
        self._limit = initial
        self._min = min_limit
        self._max = max_limit
        self._semaphore = asyncio.Semaphore(initial)
        self._successes_since_last_increase = 0
        self._increase_threshold = 10  # increase after N consecutive successes
        self._lock = asyncio.Lock()

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()

    async def record_success(self):
        async with self._lock:
            self._successes_since_last_increase += 1
            if self._successes_since_last_increase >= self._increase_threshold:
                if self._limit < self._max:
                    self._limit += 1
                    self._semaphore.release()  # add one more permit
                self._successes_since_last_increase = 0

    async def record_rate_limit(self):
        """Called on 429 — halve the concurrency."""
        async with self._lock:
            new_limit = max(self._min, self._limit // 2)
            reduction = self._limit - new_limit
            self._limit = new_limit
            # Consume permits to reduce effective concurrency
            for _ in range(reduction):
                try:
                    self._semaphore.acquire_nowait()
                except:
                    break
            self._successes_since_last_increase = 0
```

### 1.4 asyncio.gather vs asyncio.TaskGroup — Error Handling

**Critical differences for our use case:**

| Feature | `asyncio.gather` | `asyncio.TaskGroup` (3.11+) |
|---------|-------------------|----------------------------|
| On first error | Continues (with `return_exceptions=True`) or cancels all | Cancels all remaining tasks |
| Error collection | Returns exceptions mixed with results | Raises `ExceptionGroup` |
| Error handling syntax | Manual isinstance checks | `except*` syntax |
| Structured concurrency | No | Yes |
| Task lifecycle | Manual | Automatic cleanup |

**`asyncio.gather` with `return_exceptions=True`** — best for waterfall where we want all providers to attempt:

```python
results = await asyncio.gather(
    apollo_enrich(contact),
    findymail_enrich(contact),
    icypeas_enrich(contact),
    return_exceptions=True,
)
# results = [ApolloResult(...), FindymailError(...), IcypeasResult(...)]
for result in results:
    if isinstance(result, Exception):
        log_error(result)
    else:
        process_result(result)
```

**`asyncio.TaskGroup`** — best when ANY failure should abort the batch:

```python
async with asyncio.TaskGroup() as tg:
    task1 = tg.create_task(validate_api_keys())
    task2 = tg.create_task(load_campaign_data())
    task3 = tg.create_task(check_provider_health())
# If any fails, all are cancelled and ExceptionGroup is raised

# Handle with except* (Python 3.11+):
try:
    async with asyncio.TaskGroup() as tg:
        ...
except* ValueError as eg:
    for exc in eg.exceptions:
        handle_validation_error(exc)
except* ConnectionError as eg:
    for exc in eg.exceptions:
        handle_connection_error(exc)
```

**Recommendation for Clay-Dupe:**
- **Waterfall enrichment (per contact):** Use `asyncio.gather(return_exceptions=True)` — we want to try all providers even if one fails.
- **Campaign setup/teardown:** Use `TaskGroup` — if health checks fail, abort everything.
- **Batch processing:** Use `TaskGroup` for the outer loop, `gather` for individual contacts.

### 1.5 Cancel In-Flight Requests (Waterfall Short-Circuit)

When the waterfall finds an email from Provider A, cancel pending requests to Providers B, C, D:

```python
async def waterfall_enrich(contact: dict, providers: list[str]) -> EnrichResult:
    """Try providers in order. Cancel remaining on first success."""
    result = EnrichResult(contact=contact)

    for provider in providers:
        try:
            async with asyncio.timeout(15):  # per-provider timeout
                data = await call_provider(provider, contact)
                if data and data.email:
                    result.email = data.email
                    result.source = provider
                    return result  # short-circuit: skip remaining providers
                # No result — try next provider
        except asyncio.TimeoutError:
            result.add_error(provider, "timeout")
        except ProviderError as e:
            result.add_error(provider, str(e))

    return result  # no provider found an email
```

For **parallel** waterfall (try all simultaneously, take first success):

```python
async def parallel_waterfall(contact: dict, providers: list[str]) -> EnrichResult:
    """Fire all providers in parallel, take first valid result."""
    tasks = {}
    result_event = asyncio.Event()
    final_result = EnrichResult(contact=contact)

    async def try_provider(provider: str):
        try:
            data = await call_provider(provider, contact)
            if data and data.email:
                final_result.email = data.email
                final_result.source = provider
                result_event.set()
        except Exception as e:
            final_result.add_error(provider, str(e))

    async with asyncio.TaskGroup() as tg:
        provider_tasks = [tg.create_task(try_provider(p)) for p in providers]

        # Wait for either: first result found, or all tasks done
        waiter = tg.create_task(result_event.wait())

    # TaskGroup exits when all tasks complete OR when event is set
    # Cancel remaining tasks on short-circuit
    for task in provider_tasks:
        if not task.done():
            task.cancel()

    return final_result
```

**Better approach using `asyncio.wait`:**

```python
async def parallel_waterfall_v2(contact: dict, providers: list[str]) -> EnrichResult:
    tasks = {
        asyncio.create_task(call_provider(p, contact)): p
        for p in providers
    }
    result = EnrichResult(contact=contact)

    pending = set(tasks.keys())
    while pending:
        done, pending = await asyncio.wait(
            pending,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            provider = tasks[task]
            try:
                data = task.result()
                if data and data.email:
                    # Found it — cancel all remaining
                    for p in pending:
                        p.cancel()
                    result.email = data.email
                    result.source = provider
                    return result
            except Exception as e:
                result.add_error(provider, str(e))

    return result  # none succeeded
```

### 1.6 Timeouts — asyncio.timeout vs asyncio.wait_for

**`asyncio.timeout` (3.11+)** — preferred, faster (no new task created):

```python
# Per-request timeout
async with asyncio.timeout(10):
    response = await client.get(url)

# Nested timeouts (inner must be <= outer)
async with asyncio.timeout(60):         # total waterfall timeout
    for provider in providers:
        async with asyncio.timeout(15):  # per-provider timeout
            data = await call_provider(provider, contact)
```

**`asyncio.wait_for`** — creates a new task, useful when you need the task handle:

```python
try:
    result = await asyncio.wait_for(
        long_running_enrichment(),
        timeout=30.0,
    )
except asyncio.TimeoutError:
    logger.warning("Enrichment timed out after 30s")
```

**Timeout cascade for Clay-Dupe:**

```
Campaign timeout:     3600s (1 hour)
  └─ Batch timeout:    300s (5 minutes per batch of 100)
     └─ Row timeout:    60s (per contact, all providers)
        └─ Provider:    15s (single API call)
           └─ HTTP:     10s (network request)
```

```python
# Implementation with httpx timeouts + asyncio timeouts
client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=5.0,    # TCP connect
        read=10.0,      # waiting for response
        write=5.0,      # sending request
        pool=10.0,      # waiting for connection from pool
    )
)

async def enrich_row(contact, providers):
    async with asyncio.timeout(60):          # row-level timeout
        return await waterfall_enrich(contact, providers)

async def enrich_batch(contacts, providers):
    async with asyncio.timeout(300):         # batch-level timeout
        return await asyncio.gather(
            *(enrich_row(c, providers) for c in contacts),
            return_exceptions=True,
        )
```

### 1.7 Avoiding Connection Leaks with httpx.AsyncClient

**Rule #1: Always use context manager:**

```python
# CORRECT — connections auto-cleaned
async with httpx.AsyncClient() as client:
    response = await client.get(url)

# WRONG — connection leak risk
client = httpx.AsyncClient()
response = await client.get(url)
# forgot await client.aclose()
```

**Rule #2: One client per provider, reuse across requests:**

```python
class ProviderClient:
    """Manages httpx client lifecycle for a provider."""

    def __init__(self, base_url: str, api_key: str):
        self._client: httpx.AsyncClient | None = None
        self._base_url = base_url
        self._api_key = api_key

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30,
            ),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def get(self, path: str, **kwargs):
        return await self._client.get(path, **kwargs)
```

**Rule #3: Close streaming responses:**

```python
async with client.stream("GET", url) as response:
    async for chunk in response.aiter_bytes():
        process(chunk)
# Response automatically closed by context manager
```

### 1.8 Connection Pooling — httpx Configuration

```python
# Optimal httpx client configuration for API-heavy app
client = httpx.AsyncClient(
    # Connection pool settings
    limits=httpx.Limits(
        max_connections=100,          # total connections across all hosts
        max_keepalive_connections=20, # idle connections to keep alive
        keepalive_expiry=30,          # seconds before idle connection closes
    ),

    # Timeout settings
    timeout=httpx.Timeout(
        connect=5.0,
        read=10.0,
        write=5.0,
        pool=10.0,  # how long to wait for a connection from the pool
    ),

    # HTTP/2 multiplexing (multiple requests over single connection)
    http2=True,  # requires `httpx[http2]` / `h2` package

    # Transport-level settings
    transport=httpx.AsyncHTTPTransport(
        retries=0,  # we handle retries ourselves with tenacity
    ),
)
```

**HTTP/2 multiplexing benefits:**
- Multiple streams over a single TCP connection
- Header compression (HPACK)
- Eliminates head-of-line blocking at HTTP level
- Fewer TCP connections = fewer TLS handshakes

**Caveat:** Not all provider APIs support HTTP/2. Test each provider:
```python
response = await client.get("https://api.apollo.io/health")
print(response.http_version)  # "HTTP/2" or "HTTP/1.1"
```

---

## 2. Resilience Patterns

### 2.1 Circuit Breaker Pattern — Detailed Implementation

**States:**
```
CLOSED ──(failure threshold reached)──> OPEN
OPEN ──(recovery timeout elapsed)──> HALF_OPEN
HALF_OPEN ──(probe succeeds)──> CLOSED
HALF_OPEN ──(probe fails)──> OPEN
```

**Custom implementation for Clay-Dupe (no external dependency):**

```python
import time
import asyncio
from enum import Enum
from dataclasses import dataclass, field

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0

class CircuitBreaker:
    """Per-provider circuit breaker with async support."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,         # consecutive failures to trip
        recovery_timeout: float = 60.0,      # seconds before trying again
        half_open_max_calls: int = 3,         # test calls in half-open
        error_rate_threshold: float = 0.5,    # alternative: 50% error rate
        error_rate_window: int = 20,          # over last N calls
    ):
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.error_rate_threshold = error_rate_threshold
        self.error_rate_window = error_rate_window
        self._stats = CircuitStats()
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        self._recent_results: list[bool] = []  # True=success, False=failure

    @property
    def is_available(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._stats.last_failure_time
            if elapsed >= self.recovery_timeout:
                return True  # will transition to HALF_OPEN
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max_calls
        return False

    async def call(self, coro):
        """Execute coroutine through the circuit breaker."""
        async with self._lock:
            if not self.is_available:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Recovery in {self._time_until_recovery():.0f}s"
                )
            if self.state == CircuitState.OPEN:
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0

        try:
            result = await coro
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure(e)
            raise

    async def _record_success(self):
        async with self._lock:
            self._stats.successes += 1
            self._stats.consecutive_failures = 0
            self._recent_results.append(True)
            self._trim_results()

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                if self._half_open_calls >= self.half_open_max_calls:
                    self.state = CircuitState.CLOSED
                    self._half_open_calls = 0

    async def _record_failure(self, error: Exception):
        async with self._lock:
            self._stats.failures += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.monotonic()
            self._recent_results.append(False)
            self._trim_results()

            should_trip = (
                self._stats.consecutive_failures >= self.failure_threshold
                or self._error_rate() >= self.error_rate_threshold
            )

            if self.state == CircuitState.HALF_OPEN or (
                self.state == CircuitState.CLOSED and should_trip
            ):
                self.state = CircuitState.OPEN

    def _error_rate(self) -> float:
        if len(self._recent_results) < self.error_rate_window // 2:
            return 0.0  # not enough data
        failures = sum(1 for r in self._recent_results if not r)
        return failures / len(self._recent_results)

    def _trim_results(self):
        while len(self._recent_results) > self.error_rate_window:
            self._recent_results.pop(0)

    def _time_until_recovery(self) -> float:
        elapsed = time.monotonic() - self._stats.last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    def to_dict(self) -> dict:
        """Serialize state for persistence."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self._stats.failures,
            "successes": self._stats.successes,
            "consecutive_failures": self._stats.consecutive_failures,
            "last_failure_time": self._stats.last_failure_time,
        }

    @classmethod
    def from_dict(cls, data: dict, **kwargs) -> "CircuitBreaker":
        """Restore from persisted state."""
        cb = cls(name=data["name"], **kwargs)
        cb.state = CircuitState(data["state"])
        cb._stats.failures = data["failures"]
        cb._stats.successes = data["successes"]
        cb._stats.consecutive_failures = data["consecutive_failures"]
        cb._stats.last_failure_time = data["last_failure_time"]
        return cb
```

**When to trip — two complementary strategies:**

1. **Consecutive failures** (simpler, faster reaction): Trip after 5 consecutive failures. Best for detecting hard outages (provider is completely down).
2. **Error rate threshold** (smoother, avoids false positives): Trip when error rate exceeds 50% over the last 20 calls. Best for detecting degraded service.

**Recovery strategy — exponential backoff on repeated trips:**

```python
class ExponentialRecoveryBreaker(CircuitBreaker):
    def __init__(self, *args, base_timeout: float = 30.0, max_timeout: float = 600.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_timeout = base_timeout
        self._max_timeout = max_timeout
        self._trip_count = 0

    async def _record_failure(self, error):
        was_closed = self.state == CircuitState.CLOSED
        await super()._record_failure(error)
        if was_closed and self.state == CircuitState.OPEN:
            self._trip_count += 1
            self.recovery_timeout = min(
                self._base_timeout * (2 ** (self._trip_count - 1)),
                self._max_timeout,
            )
```

**Persisting state across restarts** — SQLite (no Redis dependency):

```python
import json
import sqlite3

class CircuitBreakerStore:
    def __init__(self, db_path: str = "enrichment.db"):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_breaker_state (
                    provider TEXT PRIMARY KEY,
                    state_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save(self, breaker: CircuitBreaker):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO circuit_breaker_state (provider, state_json) VALUES (?, ?)",
                (breaker.name, json.dumps(breaker.to_dict())),
            )

    def load(self, provider: str, **kwargs) -> CircuitBreaker | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT state_json FROM circuit_breaker_state WHERE provider = ?",
                (provider,),
            ).fetchone()
            if row:
                return CircuitBreaker.from_dict(json.loads(row[0]), **kwargs)
        return None
```

### 2.2 Retry with Backoff — Tenacity Best Practices

```python
from tenacity import (
    retry,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)
import logging

logger = logging.getLogger(__name__)

# Which errors to retry:
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,      # network timeouts
    httpx.ConnectError,          # connection refused
    httpx.ReadError,             # connection reset
    httpx.PoolTimeout,           # connection pool exhausted
)

# Status codes to retry:
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# NEVER retry:
# - 400 Bad Request (our fault)
# - 401 Unauthorized (bad API key)
# - 403 Forbidden (no access)
# - 404 Not Found (contact doesn't exist)
# - 422 Unprocessable Entity (bad data)

class RetryableHTTPError(Exception):
    def __init__(self, status_code: int, retry_after: float | None = None):
        self.status_code = status_code
        self.retry_after = retry_after

def check_response(response: httpx.Response):
    """Raise retryable or permanent error based on status code."""
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise RetryableHTTPError(
            429,
            retry_after=float(retry_after) if retry_after else None,
        )
    if response.status_code in RETRYABLE_STATUS_CODES:
        raise RetryableHTTPError(response.status_code)
    if response.status_code >= 400:
        raise PermanentProviderError(
            f"HTTP {response.status_code}: {response.text[:200]}"
        )

@retry(
    retry=retry_if_exception_type((RetryableHTTPError, *RETRYABLE_EXCEPTIONS)),
    wait=wait_exponential_jitter(
        initial=1,     # first retry after ~1s
        max=60,        # cap at 60s
        jitter=5,      # add 0-5s random jitter
    ),
    stop=(
        stop_after_attempt(5) |    # max 5 attempts
        stop_after_delay(120)       # or 2 minutes total
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def resilient_api_call(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    check_response(response)
    return response
```

**Combining tenacity with circuit breaker:**

```python
async def call_provider(provider: str, contact: dict) -> EnrichResult:
    breaker = circuit_breakers[provider]

    # Circuit breaker wraps the retryable call
    return await breaker.call(
        resilient_api_call(
            clients[provider],
            "POST",
            "/enrich",
            json=contact,
        )
    )
    # Flow: request → tenacity retries (handles transient) → circuit breaker (handles persistent)
    # If retries exhausted → circuit breaker records failure → may trip open
```

### 2.3 Bulkhead Pattern — Provider Isolation

Each provider gets its own isolated resources so a failing provider cannot consume resources meant for others:

```python
class ProviderBulkhead:
    """Isolates each provider with its own resource limits."""

    def __init__(self, provider: str, max_concurrent: int, max_queue: int = 100):
        self.provider = provider
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_size = 0
        self._max_queue = max_queue
        self._active = 0
        self._rejected = 0

    async def execute(self, coro):
        if self._queue_size >= self._max_queue:
            self._rejected += 1
            raise BulkheadFullError(
                f"Provider '{self.provider}' bulkhead full: "
                f"{self._active} active, {self._queue_size} queued"
            )

        self._queue_size += 1
        try:
            async with self._semaphore:
                self._active += 1
                self._queue_size -= 1
                try:
                    return await coro
                finally:
                    self._active -= 1
        except Exception:
            self._queue_size -= 1
            raise

    @property
    def stats(self) -> dict:
        return {
            "provider": self.provider,
            "active": self._active,
            "queued": self._queue_size,
            "rejected": self._rejected,
        }

# Setup
bulkheads = {
    "apollo":    ProviderBulkhead("apollo", max_concurrent=10, max_queue=200),
    "findymail": ProviderBulkhead("findymail", max_concurrent=20, max_queue=100),
    "icypeas":   ProviderBulkhead("icypeas", max_concurrent=5, max_queue=50),
    "datagma":   ProviderBulkhead("datagma", max_concurrent=5, max_queue=50),
}
```

### 2.4 Timeout Cascade

```
Campaign Level:        3600s (1 hour)
├── Batch Level:        300s (5 minutes per chunk of 100 contacts)
│   ├── Row Level:       60s (per contact, full waterfall)
│   │   ├── Provider:    15s (single provider attempt)
│   │   │   └── HTTP:    10s (network I/O via httpx timeout)
│   │   └── Provider:    15s
│   └── Row Level:       60s
└── Batch Level:        300s
```

Implementation:

```python
@dataclass
class TimeoutConfig:
    campaign: float = 3600.0
    batch: float = 300.0
    row: float = 60.0
    provider: float = 15.0
    http_connect: float = 5.0
    http_read: float = 10.0

async def run_campaign(campaign, config: TimeoutConfig = TimeoutConfig()):
    batches = chunk(campaign.contacts, size=100)

    try:
        async with asyncio.timeout(config.campaign):
            for batch in batches:
                try:
                    async with asyncio.timeout(config.batch):
                        results = await asyncio.gather(
                            *(enrich_row(c, config) for c in batch),
                            return_exceptions=True,
                        )
                        await save_results(results)
                except asyncio.TimeoutError:
                    logger.error(f"Batch timed out after {config.batch}s")
                    await save_partial_results(batch)
    except asyncio.TimeoutError:
        logger.error(f"Campaign timed out after {config.campaign}s")
```

### 2.5 Dead Letter Queue

For permanently failed enrichment rows — store them for manual review or future retry:

```python
class DeadLetterQueue:
    """SQLite-backed DLQ for permanently failed enrichment rows."""

    def __init__(self, db_path: str = "enrichment.db"):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    contact_data TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    provider TEXT,
                    attempts INTEGER DEFAULT 0,
                    first_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    status TEXT DEFAULT 'pending'  -- pending, retrying, resolved, abandoned
                )
            """)

    async def enqueue(
        self,
        campaign_id: str,
        contact: dict,
        error: Exception,
        provider: str | None = None,
        attempts: int = 0,
    ):
        await asyncio.to_thread(
            self._insert,
            campaign_id,
            json.dumps(contact),
            type(error).__name__,
            str(error)[:1000],
            provider,
            attempts,
        )

    def _insert(self, campaign_id, contact_data, error_type, error_msg, provider, attempts):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO dead_letter_queue
                   (campaign_id, contact_data, error_type, error_message, provider, attempts)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (campaign_id, contact_data, error_type, error_msg, provider, attempts),
            )

    async def get_retryable(self, campaign_id: str, max_items: int = 50) -> list[dict]:
        """Get items that might succeed on retry (transient errors)."""
        rows = await asyncio.to_thread(self._query_retryable, campaign_id, max_items)
        return rows

    async def mark_resolved(self, item_id: int):
        await asyncio.to_thread(self._update_status, item_id, "resolved")

    async def mark_abandoned(self, item_id: int):
        await asyncio.to_thread(self._update_status, item_id, "abandoned")
```

**Classification of failures:**

| Error Type | Retryable? | Action |
|-----------|-----------|---------|
| Network timeout | Yes | DLQ → auto-retry after cooldown |
| 429 Rate Limited | Yes | DLQ → retry with backoff |
| 500/502/503 Server Error | Yes | DLQ → retry with backoff |
| 401 Unauthorized | No | DLQ → alert user (bad API key) |
| 404 Not Found | No | Mark as "no data available" |
| 422 Validation Error | No | DLQ → review contact data |
| Circuit Breaker Open | Yes | DLQ → retry when circuit closes |

---

## 3. Error Handling Architecture

### 3.1 Exception Hierarchy

```python
# exceptions.py

class EnrichmentError(Exception):
    """Base exception for all enrichment errors."""
    pass

# --- Provider Errors ---

class ProviderError(EnrichmentError):
    """Base for all provider-related errors."""
    def __init__(self, provider: str, message: str, original: Exception | None = None):
        self.provider = provider
        self.original = original
        super().__init__(f"[{provider}] {message}")

class ProviderAuthError(ProviderError):
    """Invalid or expired API key. Non-retryable."""
    pass

class ProviderRateLimitError(ProviderError):
    """429 Too Many Requests. Retryable with backoff."""
    def __init__(self, provider: str, retry_after: float | None = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(provider, f"Rate limited (retry after {retry_after}s)", **kwargs)

class ProviderTimeoutError(ProviderError):
    """Request or response timed out. Retryable."""
    pass

class ProviderNotFoundError(ProviderError):
    """Contact/company not found by provider. Non-retryable for this contact."""
    pass

class ProviderServerError(ProviderError):
    """5xx error from provider. Retryable."""
    pass

class ProviderDataError(ProviderError):
    """Provider returned unparseable or invalid data. Non-retryable."""
    pass

# --- Circuit Breaker Errors ---

class CircuitBreakerOpenError(EnrichmentError):
    """Circuit breaker is open — provider temporarily unavailable."""
    def __init__(self, provider: str, recovery_in: float):
        self.provider = provider
        self.recovery_in = recovery_in
        super().__init__(f"Circuit open for '{provider}', recovery in {recovery_in:.0f}s")

# --- Bulkhead Errors ---

class BulkheadFullError(EnrichmentError):
    """Provider bulkhead is at capacity."""
    pass

# --- Campaign Errors ---

class CampaignError(EnrichmentError):
    """Base for campaign-level errors."""
    pass

class CampaignCancelledError(CampaignError):
    """User cancelled the campaign."""
    pass

class CampaignTimeoutError(CampaignError):
    """Campaign exceeded its time budget."""
    pass

# --- Waterfall Errors ---

class WaterfallExhaustedError(EnrichmentError):
    """All providers tried, none returned data."""
    def __init__(self, contact_id: str, errors: dict[str, str]):
        self.contact_id = contact_id
        self.provider_errors = errors
        providers = ", ".join(errors.keys())
        super().__init__(f"All providers exhausted for {contact_id}: {providers}")
```

**When to raise vs return error objects:**

```python
# RAISE — for hard failures that should stop processing this item
raise ProviderAuthError("apollo", "Invalid API key")

# RETURN — for soft failures in the waterfall (try next provider)
@dataclass
class ProviderResult:
    success: bool
    provider: str
    data: dict | None = None
    error: str | None = None
    error_type: str | None = None  # "rate_limit", "not_found", "timeout", etc.
```

**Rule of thumb:**
- **Raise** when the error should propagate up (auth errors, campaign cancellation)
- **Return error objects** when the error is expected and the caller decides what to do (waterfall logic, partial failures)

### 3.2 Surfacing Async Errors to Streamlit UI

Streamlit runs synchronously on the main thread. Background async tasks must communicate via thread-safe shared state:

```python
import threading
from dataclasses import dataclass, field
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class EnrichmentProgress:
    """Thread-safe progress state shared between async engine and Streamlit UI."""
    status: TaskStatus = TaskStatus.PENDING
    total_rows: int = 0
    processed_rows: int = 0
    successful: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)
    current_provider: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def add_error(self, error: dict):
        with self._lock:
            self.errors.append(error)
            if len(self.errors) > 100:  # cap to prevent memory issues
                self.errors = self.errors[-100:]

    @property
    def progress_pct(self) -> float:
        with self._lock:
            if self.total_rows == 0:
                return 0.0
            return self.processed_rows / self.total_rows

    def snapshot(self) -> dict:
        """Thread-safe snapshot for UI rendering."""
        with self._lock:
            return {
                "status": self.status.value,
                "total": self.total_rows,
                "processed": self.processed_rows,
                "successful": self.successful,
                "failed": self.failed,
                "progress": self.progress_pct,
                "errors": list(self.errors[-10:]),  # last 10 errors
                "current_provider": self.current_provider,
            }

# In Streamlit:
def render_progress():
    progress = st.session_state.get("enrichment_progress")
    if not progress:
        return

    snap = progress.snapshot()
    st.progress(snap["progress"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Processed", f"{snap['processed']}/{snap['total']}")
    col2.metric("Success", snap["successful"])
    col3.metric("Failed", snap["failed"])

    if snap["errors"]:
        with st.expander(f"Recent Errors ({len(snap['errors'])})"):
            for err in snap["errors"]:
                st.error(f"[{err['provider']}] {err['message']}")

    # Auto-rerun to update progress
    if snap["status"] == "running":
        time.sleep(1)
        st.rerun()
```

### 3.3 Structured Error Logging

```python
import structlog

logger = structlog.get_logger()

async def enrich_with_logging(provider: str, contact: dict, campaign_id: str):
    log = logger.bind(
        provider=provider,
        contact_id=contact.get("id"),
        campaign_id=campaign_id,
        email=contact.get("email", "unknown"),
    )

    try:
        result = await call_provider(provider, contact)
        log.info("enrichment_success", fields_found=list(result.keys()))
        return result
    except ProviderRateLimitError as e:
        log.warning("enrichment_rate_limited", retry_after=e.retry_after)
        raise
    except ProviderNotFoundError:
        log.info("enrichment_not_found")  # expected, not an error
        return None
    except ProviderError as e:
        log.error("enrichment_failed", error_type=type(e).__name__, error=str(e))
        raise
```

### 3.4 Error Aggregation for Reporting

```python
from collections import defaultdict, Counter

class ErrorAggregator:
    """Collects and summarizes errors across a campaign run."""

    def __init__(self):
        self._errors: list[dict] = []
        self._lock = threading.Lock()

    def record(self, provider: str, error_type: str, message: str, contact_id: str = ""):
        with self._lock:
            self._errors.append({
                "provider": provider,
                "error_type": error_type,
                "message": message,
                "contact_id": contact_id,
                "timestamp": time.time(),
            })

    def summary(self) -> dict:
        with self._lock:
            by_provider = defaultdict(lambda: Counter())
            for e in self._errors:
                by_provider[e["provider"]][e["error_type"]] += 1

            return {
                "total_errors": len(self._errors),
                "by_provider": {
                    provider: dict(counts)
                    for provider, counts in by_provider.items()
                },
                "error_rate_by_provider": {
                    provider: {
                        etype: count
                        for etype, count in counts.items()
                    }
                    for provider, counts in by_provider.items()
                },
                "most_common": Counter(
                    e["error_type"] for e in self._errors
                ).most_common(5),
            }
```

---

## 4. Polling Pattern (Icypeas bulk, ContactOut batch)

### 4.1 Safe Polling with Max Timeout

```python
async def poll_bulk_result(
    client: httpx.AsyncClient,
    job_id: str,
    max_timeout: float = 300.0,       # 5 minutes max
    initial_interval: float = 2.0,     # start checking every 2s
    max_interval: float = 30.0,        # cap at 30s between checks
    backoff_factor: float = 1.5,       # multiply interval by 1.5 each time
) -> dict:
    """Poll a bulk enrichment job with exponential backoff."""

    start = time.monotonic()
    interval = initial_interval
    attempt = 0

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= max_timeout:
            raise ProviderTimeoutError(
                "icypeas",
                f"Bulk job {job_id} not complete after {max_timeout}s"
            )

        response = await client.get(f"/bulk/{job_id}/status")
        data = response.json()
        status = data.get("status")

        if status == "completed":
            return data.get("results", {})
        elif status == "failed":
            raise ProviderServerError("icypeas", f"Bulk job {job_id} failed: {data}")
        elif status == "partial":
            # Some results ready, some still processing
            logger.info(f"Bulk job {job_id}: {data.get('progress', '?')}% complete")

        # Wait with exponential backoff
        jitter = random.uniform(0, interval * 0.1)  # 10% jitter
        wait_time = min(interval + jitter, max_timeout - elapsed)
        if wait_time <= 0:
            break
        await asyncio.sleep(wait_time)
        interval = min(interval * backoff_factor, max_interval)
        attempt += 1

    raise ProviderTimeoutError("icypeas", f"Polling exhausted for job {job_id}")
```

### 4.2 Cancellable Polling

```python
async def cancellable_poll(
    client: httpx.AsyncClient,
    job_id: str,
    cancel_event: asyncio.Event,
    **kwargs,
) -> dict | None:
    """Poll with support for user cancellation."""

    start = time.monotonic()
    interval = kwargs.get("initial_interval", 2.0)
    max_timeout = kwargs.get("max_timeout", 300.0)
    max_interval = kwargs.get("max_interval", 30.0)

    while True:
        if cancel_event.is_set():
            logger.info(f"Polling cancelled for job {job_id}")
            # Optionally cancel the remote job too
            await client.delete(f"/bulk/{job_id}")
            return None

        elapsed = time.monotonic() - start
        if elapsed >= max_timeout:
            raise ProviderTimeoutError("icypeas", f"Timeout after {max_timeout}s")

        response = await client.get(f"/bulk/{job_id}/status")
        data = response.json()

        if data["status"] == "completed":
            return data["results"]
        if data["status"] == "failed":
            raise ProviderServerError("icypeas", f"Job failed: {data}")

        # Wait, but check cancel_event periodically
        try:
            await asyncio.wait_for(
                cancel_event.wait(),
                timeout=min(interval, max_timeout - elapsed),
            )
            # If we get here, cancel was requested
            return None
        except asyncio.TimeoutError:
            # Normal — just means we should check status again
            interval = min(interval * 1.5, max_interval)
```

### 4.3 Handling Partial Results

```python
async def poll_with_partial_results(
    client: httpx.AsyncClient,
    job_id: str,
    on_partial: callable,  # callback for partial results
    max_timeout: float = 300.0,
) -> dict:
    """Poll and stream partial results as they become available."""

    seen_ids = set()
    interval = 2.0

    async with asyncio.timeout(max_timeout):
        while True:
            response = await client.get(f"/bulk/{job_id}")
            data = response.json()

            # Process any new results
            for item in data.get("results", []):
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    await on_partial(item)  # save to DB immediately

            if data["status"] == "completed":
                return {
                    "total": len(seen_ids),
                    "results": data["results"],
                }

            progress = len(seen_ids) / max(data.get("total", 1), 1) * 100
            logger.info(f"Job {job_id}: {progress:.0f}% ({len(seen_ids)} items)")

            await asyncio.sleep(interval)
            interval = min(interval * 1.3, 30.0)
```

### 4.4 asyncio.Event for Signaling

```python
class BulkJobManager:
    """Manages multiple bulk jobs with completion signaling."""

    def __init__(self):
        self._jobs: dict[str, asyncio.Event] = {}
        self._results: dict[str, dict] = {}

    def register_job(self, job_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._jobs[job_id] = event
        return event

    async def wait_for_job(self, job_id: str, timeout: float = 300.0) -> dict:
        event = self._jobs.get(job_id)
        if not event:
            raise ValueError(f"Unknown job: {job_id}")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._results[job_id]
        except asyncio.TimeoutError:
            raise ProviderTimeoutError("bulk", f"Job {job_id} timed out")

    async def poll_loop(self, client: httpx.AsyncClient, job_id: str):
        """Background polling task that signals completion via Event."""
        interval = 2.0
        while True:
            response = await client.get(f"/bulk/{job_id}/status")
            data = response.json()

            if data["status"] == "completed":
                self._results[job_id] = data["results"]
                self._jobs[job_id].set()  # signal completion
                return
            elif data["status"] == "failed":
                self._results[job_id] = {"error": data}
                self._jobs[job_id].set()
                return

            await asyncio.sleep(interval)
            interval = min(interval * 1.5, 30.0)
```

---

## 5. Background Task Management in Streamlit

### 5.1 Recommended Architecture: Thread + asyncio Event Loop

Streamlit does not natively support asyncio. The proven pattern is running an asyncio event loop in a daemon thread:

```python
import threading
import asyncio

class EnrichmentEngine:
    """Runs async enrichment in a background thread with its own event loop."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._cancel_event = asyncio.Event()

    def start(self, campaign, progress: EnrichmentProgress):
        """Start enrichment in a background thread."""
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(campaign, progress),
            daemon=True,  # dies when main thread dies
        )
        self._thread.start()

    def _run_loop(self, campaign, progress: EnrichmentProgress):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(
                self._run_campaign(campaign, progress)
            )
        except Exception as e:
            progress.update(status=TaskStatus.FAILED)
            progress.add_error({"provider": "engine", "message": str(e)})
        finally:
            self._loop.close()

    async def _run_campaign(self, campaign, progress: EnrichmentProgress):
        progress.update(status=TaskStatus.RUNNING, total_rows=len(campaign.contacts))

        async with httpx.AsyncClient() as client:
            for i, batch in enumerate(chunk(campaign.contacts, 100)):
                if self._cancel_event.is_set():
                    progress.update(status=TaskStatus.CANCELLED)
                    return

                results = await asyncio.gather(
                    *(self._enrich_one(client, c, progress) for c in batch),
                    return_exceptions=True,
                )
                await self._save_batch(results)

        progress.update(status=TaskStatus.COMPLETED)

    def cancel(self):
        """Thread-safe cancellation from Streamlit UI."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._cancel_event.set)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
```

**Streamlit integration:**

```python
# In enrich.py page
def start_enrichment(campaign):
    engine = EnrichmentEngine()
    progress = EnrichmentProgress()
    st.session_state["engine"] = engine
    st.session_state["progress"] = progress
    engine.start(campaign, progress)

def cancel_enrichment():
    engine = st.session_state.get("engine")
    if engine:
        engine.cancel()

# UI
if st.button("Start Enrichment"):
    start_enrichment(campaign)
    st.rerun()

if st.button("Cancel"):
    cancel_enrichment()

progress = st.session_state.get("progress")
if progress and progress.status == TaskStatus.RUNNING:
    render_progress()
```

### 5.2 Handling Session Disconnect

Streamlit sessions can disconnect during long-running tasks. Key strategies:

**1. Daemon thread continues regardless:**
The background thread is a daemon thread — it continues running even if the Streamlit session disconnects. When the user reconnects, they can check the progress object (stored in session state or a global registry).

**2. Global task registry (survives session restarts):**

```python
# Singleton task registry — persists across Streamlit reruns
_task_registry: dict[str, EnrichmentEngine] = {}
_registry_lock = threading.Lock()

def register_task(campaign_id: str, engine: EnrichmentEngine):
    with _registry_lock:
        _task_registry[campaign_id] = engine

def get_task(campaign_id: str) -> EnrichmentEngine | None:
    with _registry_lock:
        return _task_registry.get(campaign_id)
```

### 5.3 Checkpoint/Restart for Interrupted Campaigns

```python
class CampaignCheckpointer:
    """Persists campaign progress to SQLite for crash recovery."""

    def __init__(self, db_path: str = "enrichment.db"):
        self.db_path = db_path

    async def save_checkpoint(self, campaign_id: str, last_processed_idx: int, results: list):
        await asyncio.to_thread(
            self._save,
            campaign_id,
            last_processed_idx,
            json.dumps([r.to_dict() for r in results]),
        )

    def _save(self, campaign_id, idx, results_json):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO campaign_checkpoints
                   (campaign_id, last_processed_idx, results_json, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
                (campaign_id, idx, results_json),
            )

    def load_checkpoint(self, campaign_id: str) -> tuple[int, list] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_processed_idx, results_json FROM campaign_checkpoints WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if row:
                return row[0], json.loads(row[1])
        return None

    async def resume_campaign(self, campaign):
        checkpoint = self.load_checkpoint(campaign.id)
        if checkpoint:
            start_idx, prior_results = checkpoint
            logger.info(f"Resuming campaign {campaign.id} from row {start_idx}")
            remaining_contacts = campaign.contacts[start_idx + 1:]
            return start_idx + 1, prior_results
        return 0, []
```

---

## 6. Rate Limiting Deep Dive

### 6.1 Token Bucket Algorithm

```python
import asyncio
import time

class TokenBucket:
    """Async token bucket rate limiter.

    rate: tokens added per second (e.g., 50/60 for 50 requests/minute)
    capacity: max burst size
    """

    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1):
        """Wait until enough tokens are available."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return

            # Not enough tokens — calculate wait time
            wait = (tokens - self._tokens) / self.rate
            await asyncio.sleep(wait)

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.capacity,
            self._tokens + elapsed * self.rate,
        )
        self._last_refill = now

    @property
    def available(self) -> float:
        return self._tokens
```

### 6.2 Sliding Window Rate Limiter

```python
from collections import deque

class SlidingWindowRateLimiter:
    """Sliding window counter — smoother than fixed window.

    max_requests: maximum requests allowed in the window
    window_seconds: window duration
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available."""
        while True:
            async with self._lock:
                now = time.monotonic()
                # Remove expired timestamps
                cutoff = now - self.window_seconds
                while self._timestamps and self._timestamps[0] < cutoff:
                    self._timestamps.popleft()

                if len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    return

            # Window full — wait until the oldest request expires
            wait = self._timestamps[0] + self.window_seconds - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait + 0.01)  # small buffer

    @property
    def remaining(self) -> int:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        active = sum(1 for t in self._timestamps if t >= cutoff)
        return max(0, self.max_requests - active)
```

### 6.3 Provider-Specific Rate Limits

| Provider | Rate Limit | Type | Implementation |
|----------|-----------|------|----------------|
| **Apollo** (Free) | 50 req/min, 600 req/day | Rolling window | `SlidingWindowRateLimiter(50, 60)` + daily counter |
| **Apollo** (Paid) | 200 req/min, 2000 req/day | Rolling window | `SlidingWindowRateLimiter(200, 60)` + daily counter |
| **Findymail** | 300 concurrent, no daily cap | Concurrency | `asyncio.Semaphore(300)` |
| **Icypeas** | See API docs | Per-endpoint | `TokenBucket(rate=TBD, capacity=TBD)` |
| **Datagma** | See API docs | Per-endpoint | `TokenBucket(rate=TBD, capacity=TBD)` |

### 6.4 Global Rate Limiting Across Providers

```python
class GlobalRateLimiter:
    """Coordinates rate limiting across all providers to prevent resource exhaustion."""

    def __init__(self, max_total_concurrent: int = 50, max_total_per_second: float = 20.0):
        self._global_semaphore = asyncio.Semaphore(max_total_concurrent)
        self._global_bucket = TokenBucket(rate=max_total_per_second, capacity=max_total_concurrent)
        self._provider_limiters: dict[str, TokenBucket] = {}

    def register_provider(self, name: str, rate: float, capacity: int):
        self._provider_limiters[name] = TokenBucket(rate=rate, capacity=capacity)

    async def acquire(self, provider: str):
        """Acquire both global and provider-specific rate limit slots."""
        await self._global_bucket.acquire()
        async with self._global_semaphore:
            provider_limiter = self._provider_limiters.get(provider)
            if provider_limiter:
                await provider_limiter.acquire()

    async def execute(self, provider: str, coro):
        await self.acquire(provider)
        return await coro
```

### 6.5 Handling 429 Responses

```python
async def handle_rate_limit(response: httpx.Response, provider: str):
    """Parse and respect Retry-After headers."""

    if response.status_code != 429:
        return

    # Parse Retry-After header (seconds or HTTP-date)
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            wait = float(retry_after)
        except ValueError:
            # HTTP-date format: parse and calculate delta
            from email.utils import parsedate_to_datetime
            retry_date = parsedate_to_datetime(retry_after)
            wait = (retry_date - datetime.now(timezone.utc)).total_seconds()
            wait = max(0, wait)
    else:
        wait = 60.0  # default fallback

    # Also check provider-specific headers
    # Apollo: X-RateLimit-Remaining, X-RateLimit-Reset
    remaining = response.headers.get("X-RateLimit-Remaining")
    reset_at = response.headers.get("X-RateLimit-Reset")

    logger.warning(
        f"Rate limited by {provider}: wait {wait}s, "
        f"remaining={remaining}, reset={reset_at}"
    )

    raise ProviderRateLimitError(provider, retry_after=wait)
```

---

## 7. Memory Management

### 7.1 Processing 10K+ Rows Without OOM

**Principle:** Never hold all rows + all results in memory simultaneously. Stream results to database as they complete.

```python
async def process_large_campaign(
    campaign_id: str,
    db: Database,
    batch_size: int = 100,
):
    """Process large campaigns in memory-efficient chunks."""

    total = await db.count_contacts(campaign_id)
    offset = 0

    while offset < total:
        # Load only one batch at a time
        batch = await db.get_contacts(campaign_id, limit=batch_size, offset=offset)

        results = await asyncio.gather(
            *(enrich_contact(c) for c in batch),
            return_exceptions=True,
        )

        # Write results to DB immediately — don't accumulate
        await db.save_results(campaign_id, results)

        # Let GC clean up the batch
        del batch, results

        offset += batch_size

        # Yield control to prevent event loop starvation
        await asyncio.sleep(0)
```

### 7.2 Streaming Results to Database

```python
class ResultStreamer:
    """Writes enrichment results to SQLite as they arrive, not in bulk."""

    def __init__(self, db_path: str, campaign_id: str):
        self.db_path = db_path
        self.campaign_id = campaign_id
        self._batch_buffer: list[dict] = []
        self._buffer_size = 50  # flush every 50 results
        self._lock = asyncio.Lock()

    async def add_result(self, result: dict):
        async with self._lock:
            self._batch_buffer.append(result)
            if len(self._batch_buffer) >= self._buffer_size:
                await self._flush()

    async def _flush(self):
        if not self._batch_buffer:
            return
        batch = self._batch_buffer[:]
        self._batch_buffer.clear()
        await asyncio.to_thread(self._write_batch, batch)

    def _write_batch(self, batch: list[dict]):
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO enrichment_results
                   (campaign_id, contact_id, data_json, provider, created_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [
                    (self.campaign_id, r["contact_id"], json.dumps(r["data"]), r["provider"])
                    for r in batch
                ],
            )

    async def close(self):
        """Flush remaining buffer on shutdown."""
        async with self._lock:
            await self._flush()
```

### 7.3 Chunking Large Batches

```python
from typing import TypeVar, Iterator

T = TypeVar("T")

def chunk(items: list[T], size: int) -> Iterator[list[T]]:
    """Split a list into fixed-size chunks."""
    for i in range(0, len(items), size):
        yield items[i : i + size]

# Optimal batch sizes by provider:
BATCH_SIZES = {
    "apollo": 100,       # Apollo supports bulk enrich of up to 100
    "icypeas": 50,       # Icypeas bulk endpoint
    "findymail": 200,    # Findymail has high concurrency
    "datagma": 50,       # Conservative
    "default": 100,
}
```

### 7.4 asyncio and Garbage Collection

```python
# Avoid keeping references to completed tasks
async def process_without_accumulating():
    """Process contacts without holding references to completed tasks."""

    # BAD — accumulates all task objects in memory
    # all_tasks = [asyncio.create_task(enrich(c)) for c in contacts]
    # results = await asyncio.gather(*all_tasks)

    # GOOD — process in chunks, discard references
    for batch in chunk(contacts, 100):
        tasks = [asyncio.create_task(enrich(c)) for c in batch]
        results = await asyncio.gather(*tasks)
        await save_results(results)
        # tasks and results go out of scope → eligible for GC

    # ALSO GOOD — use asyncio.as_completed for streaming
    tasks = [asyncio.create_task(enrich(c)) for c in contacts]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        await save_single_result(result)
        # Each result is saved and can be GC'd
```

---

## 8. Recommended Architecture for Clay-Dupe

### Full Resilience Stack (per request flow)

```
Request Flow:
  Contact → GlobalRateLimiter → ProviderBulkhead → CircuitBreaker → Tenacity Retry → httpx call
                                                                                         │
  Result  ← ResultStreamer    ← ErrorAggregator  ← Result/Error  ← Response Parser  ←───┘
```

### Component Summary

| Component | Library/Pattern | Purpose |
|-----------|----------------|---------|
| Concurrency control | `asyncio.Semaphore` per provider | Limit in-flight requests |
| Rate limiting | Custom `TokenBucket` + `SlidingWindow` | Respect API rate limits |
| Adaptive concurrency | Custom AIMD semaphore | Auto-adjust on 429/success |
| Circuit breaker | Custom (see 2.1) | Stop calling dead providers |
| Retry | `tenacity` | Handle transient errors |
| Bulkhead | `asyncio.Semaphore` per provider | Isolate provider failures |
| Timeouts | `asyncio.timeout` (nested) | Prevent hung requests |
| Connection pooling | `httpx.AsyncClient` with limits | Efficient HTTP connections |
| Error hierarchy | Custom exception classes | Clean error propagation |
| Dead letter queue | SQLite table | Handle permanent failures |
| Background tasks | `threading.Thread` + `asyncio` loop | Non-blocking Streamlit |
| Progress tracking | Thread-safe `EnrichmentProgress` | UI updates |
| Checkpointing | SQLite persistence | Crash recovery |
| Memory management | Batch + stream to DB | Handle 10K+ rows |
| Polling | Exponential backoff + `asyncio.Event` | Bulk API results |

### Key Dependencies

```
httpx[http2]     # HTTP client with HTTP/2, connection pooling
tenacity         # Retry with backoff
structlog        # Structured logging
```

No external circuit breaker or rate limiter library needed — custom implementations give us exactly the behavior we need with zero unnecessary dependencies.

---

## Sources

- [Limit concurrency with semaphore in Python asyncio](https://rednafi.com/python/limit-concurrency-with-semaphore/)
- [How to Rate Limit Async Requests in Python](https://scrapfly.io/blog/posts/how-to-rate-limit-asynchronous-python-requests)
- [How to Handle Concurrent OpenAI API Calls with Rate Limiting](https://villoro.com/blog/async-openai-calls-rate-limiter/)
- [Coroutines and Tasks — Python 3.14 documentation](https://docs.python.org/3/library/asyncio-task.html)
- [Why Taskgroup and Timeout Are so Crucial in Python 3.11 Asyncio](https://www.dataleadsfuture.com/why-taskgroup-and-timeout-are-so-crucial-in-python-3-11-asyncio/)
- [Python 3.11 Preview: Task and Exception Groups — Real Python](https://realpython.com/python311-exception-groups/)
- [aiobreaker — Python Circuit Breaker](https://github.com/arlyon/aiobreaker)
- [pybreaker — Circuit Breaker Pattern](https://github.com/danielfm/pybreaker)
- [Tenacity Documentation](https://tenacity.readthedocs.io/)
- [OpenAI Cookbook: How to Handle Rate Limits](https://cookbook.openai.com/examples/how_to_handle_rate_limits)
- [httpx Resource Limits](https://www.python-httpx.org/advanced/resource-limits/)
- [httpx Async Support](https://www.python-httpx.org/async/)
- [httpx Timeouts](https://www.python-httpx.org/advanced/timeouts/)
- [Asyncio Task Cancellation Best Practices — Super Fast Python](https://superfastpython.com/asyncio-task-cancellation-best-practices/)
- [asyncio.timeout() To Wait and Cancel Tasks — Super Fast Python](https://superfastpython.com/asyncio-timeout/)
- [How to Implement Bulkhead Pattern in Python](https://oneuptime.com/blog/post/2026-01-25-bulkhead-pattern-python/view)
- [Structuring exceptions in Python like a PRO](https://guicommits.com/how-to-structure-exception-in-python-like-a-pro/)
- [Threading in Streamlit — Streamlit Docs](https://docs.streamlit.io/develop/concepts/design/multithreading)
- [How to Run a Background Task in Streamlit](https://discuss.streamlit.io/t/how-to-run-a-background-task-in-streamlit-and-notify-the-ui-when-it-finishes/95033)
- [Streamlit Session Recovery — GitHub Issue](https://github.com/streamlit/streamlit/issues/9031)
- [Token Bucket Rate Limiting in Python](https://oneuptime.com/blog/post/2026-01-22-token-bucket-rate-limiting-python/view)
- [Apollo API Rate Limits](https://docs.apollo.io/reference/rate-limits)
- [Icypeas Rate Limits](https://api-doc.icypeas.com/how-works/rate_limits/)
- [Building a Robust Redis Client: Async Redis + Tenacity + Circuit Breaker](https://dev.to/akarshan/building-a-robust-redis-client-with-retry-logic-in-python-jeg)
- [Resilient APIs: Retry Logic, Circuit Breakers, and Fallback Mechanisms](https://medium.com/@fahimad/resilient-apis-retry-logic-circuit-breakers-and-fallback-mechanisms-cfd37f523f43)
- [Dead Letter Queues in Python](https://oneuptime.com/blog/post/2026-01-24-dead-letter-queues-python/view)
- [How to Handle Dead Letter Queues in Python](https://oneuptime.com/blog/post/2026-01-24-dead-letter-queues-python/view)
- [Waiting in asyncio — Hynek Schlawack](https://hynek.me/articles/waiting-in-asyncio/)
