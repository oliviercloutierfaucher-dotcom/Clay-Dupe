"""Circuit breaker and rate limiting for providers."""

import asyncio
import time
from enum import Enum
from typing import Optional

from config.settings import ProviderName


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider circuit breaker."""

    def __init__(
        self,
        provider: ProviderName,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 3,
    ):
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def state(self) -> CircuitState:
        # If OPEN, check if recovery timeout has elapsed -> transition to HALF_OPEN
        if self._state == CircuitState.OPEN and self._last_failure_time:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._success_count = 0
        return self._state

    def can_execute(self) -> bool:
        """Check if we can make a request."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        elif state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.half_open_max
        else:  # OPEN
            return False

    def record_success(self):
        """Record successful API call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= 2:
                # Transition back to CLOSED
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._half_open_calls = 0
        else:
            self._failure_count = 0  # Reset consecutive failures

    def record_failure(self, error_code: Optional[int] = None):
        """Record failed API call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_error = f"HTTP {error_code}" if error_code else "Unknown error"

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open -> back to OPEN with longer timeout
            self._state = CircuitState.OPEN
            self.recovery_timeout = min(self.recovery_timeout * 1.5, 300.0)
            self._half_open_calls = 0
            self._success_count = 0
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            # 429 errors get longer recovery timeout
            if error_code == 429:
                self.recovery_timeout = min(self.recovery_timeout * 2, 300.0)

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1

    def get_status(self) -> dict:
        return {
            "provider": self.provider.value,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "recovery_timeout": self.recovery_timeout,
            "last_error": self._last_error,
        }


class SlidingWindowRateLimiter:
    """Rate limiter using sliding window algorithm."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available. Call before each API request."""
        while True:
            async with self._lock:
                now = time.monotonic()
                # Remove timestamps outside the window
                self._timestamps = [
                    t for t in self._timestamps if now - t < self.window_seconds
                ]
                if len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    return
            # Wait a bit before retrying
            await asyncio.sleep(self.window_seconds / self.max_requests)

    @property
    def available(self) -> int:
        now = time.monotonic()
        active = [t for t in self._timestamps if now - t < self.window_seconds]
        return max(0, self.max_requests - len(active))


class ConcurrencySemaphore:
    """Semaphore-based limiter for concurrent requests."""

    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, *args):
        self._semaphore.release()

    async def acquire(self):
        """Acquire a slot (for use without context manager)."""
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()

    @property
    def available(self) -> int:
        return self._semaphore._value


def create_rate_limiters() -> dict:
    """Create rate limiters for all providers."""
    return {
        ProviderName.APOLLO: SlidingWindowRateLimiter(50, 60),  # 50/min
        ProviderName.FINDYMAIL: ConcurrencySemaphore(300),  # 300 concurrent
        ProviderName.ICYPEAS: SlidingWindowRateLimiter(10, 1),  # 10/sec
        ProviderName.CONTACTOUT: SlidingWindowRateLimiter(30, 60),  # 30/min
    }


def create_circuit_breakers() -> dict[ProviderName, CircuitBreaker]:
    """Create circuit breakers for all providers."""
    return {
        ProviderName.APOLLO: CircuitBreaker(
            ProviderName.APOLLO, recovery_timeout=60
        ),
        ProviderName.FINDYMAIL: CircuitBreaker(
            ProviderName.FINDYMAIL, recovery_timeout=30
        ),
        ProviderName.ICYPEAS: CircuitBreaker(
            ProviderName.ICYPEAS, recovery_timeout=60
        ),
        ProviderName.CONTACTOUT: CircuitBreaker(
            ProviderName.CONTACTOUT, recovery_timeout=60
        ),
    }
