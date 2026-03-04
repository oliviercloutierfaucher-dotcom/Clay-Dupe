# Codebase Conventions

## Language & Runtime

- **Python 3.9+** with `from __future__ import annotations` for forward references
- **Async/await** throughout providers and enrichment engine via `asyncio` + `httpx.AsyncClient`
- **Type hints** on all function signatures: `Optional[str]`, `list[str]`, `dict[str, Any]`

## Import Organization

```python
# 1. Standard library
from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

# 2. Third-party
import httpx
from pydantic import BaseModel, field_validator

# 3. Local imports
from data.models import Person, Company
from providers.base import BaseProvider

# 4. Type-checking only (avoid circular imports)
if TYPE_CHECKING:
    from enrichment.waterfall import WaterfallOrchestrator
```

## Pydantic v2 Patterns

### Model Definition
```python
class Company(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str | None = None
    name: str | None = None
    industry: str | None = None
    employee_count: int | None = None

    @field_validator("domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: str | None) -> str | None:
        if v:
            return v.lower().strip().removeprefix("www.")
        return v
```

### Validators
- `@field_validator` for single field normalization (domain, email, country)
- `@model_validator` for cross-field validation
- `mode="before"` for pre-processing raw input

## Provider Pattern

All 4 providers follow the same structure:

```python
class ApolloProvider(BaseProvider):
    BASE_URL = "https://api.apollo.io/v1"

    async def find_email(self, first_name, last_name, domain, **kwargs) -> ProviderResponse:
        # 1. Build request payload
        # 2. Make HTTP call with error handling
        # 3. Parse response into ProviderResponse
        # 4. Return with confidence score

    async def _request(self, method, endpoint, **kwargs) -> dict:
        # Centralized HTTP with rate limit handling
        ...
```

### ProviderResponse
```python
@dataclass
class ProviderResponse:
    success: bool
    email: str | None = None
    confidence: float = 0.0
    credits_used: int = 0
    raw_data: dict = field(default_factory=dict)
    provider: str = ""
```

## Error Handling

### Provider Errors
```python
try:
    response = await self._request("POST", "/endpoint", json=payload)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 429:
        # Rate limited — check Retry-After header
        ...
    elif e.response.status_code in (401, 403):
        # Auth failure
        ...
    return ProviderResponse(success=False, provider=self.name)
except Exception:
    logger.exception("Unexpected error in %s", self.name)
    return ProviderResponse(success=False, provider=self.name)
```

### Pattern: Return error objects, don't raise
- Providers return `ProviderResponse(success=False)` on failure
- Waterfall checks `.success` and cascades to next provider
- Exceptions are caught and logged, never propagated to caller

## Logging

```python
logger = logging.getLogger(__name__)

# Usage throughout:
logger.debug("Cache hit for %s", key)
logger.info("Enrichment complete: %d/%d found", found, total)
logger.warning("Rate limited by %s, retrying in %ds", provider, delay)
logger.exception("Failed to enrich %s")  # includes traceback
```

- Standard Python `logging` module (no custom logger)
- Logger per module via `__name__`
- Use `%s` formatting (not f-strings) in log calls for lazy evaluation

## Async Patterns

### HTTP Client Lifecycle
```python
class BaseProvider:
    async def __aenter__(self):
        self._client = httpx.AsyncClient(http2=True, timeout=30.0)
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()
```

### Concurrent Operations
```python
# Batch processing with semaphore
sem = asyncio.Semaphore(10)
async def limited_call(item):
    async with sem:
        return await provider.find_email(...)

results = await asyncio.gather(*[limited_call(item) for item in items])
```

## Database Patterns

### SQLite with WAL Mode
```python
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
conn.row_factory = sqlite3.Row
```

### CRUD Pattern
```python
def save_result(self, result: EnrichmentResult) -> None:
    self.conn.execute(
        "INSERT OR REPLACE INTO results (...) VALUES (?, ?, ?)",
        (result.email, result.provider, result.confidence)
    )
    self.conn.commit()
```

## Configuration

### Environment Variables
- API keys: `APOLLO_API_KEY`, `FINDYMAIL_API_KEY`, `ICYPEAS_API_KEY`, `CONTACTOUT_API_KEY`
- Waterfall order: `WATERFALL_ORDER=apollo,icypeas,findymail,contactout`
- Cache TTL: `CACHE_TTL_DAYS=30`
- Loaded via `python-dotenv` in `config/settings.py`

### Pydantic Settings
```python
class Settings(BaseModel):
    waterfall_order: list[str] = ["apollo", "icypeas", "findymail", "contactout"]
    cache_ttl_days: int = 30
    providers: dict[str, ProviderConfig] = {}
```

## CSV/Excel I/O

### Column Mapping
- Auto-detect columns using `rapidfuzz` fuzzy matching
- Maps common variations: "First Name", "first_name", "firstName" → `first_name`
- Normalizes data on import (strip whitespace, lowercase emails/domains)

### Export Format
- Results exported with enrichment metadata (provider, confidence, timestamp)
- Excel export includes formatting via `openpyxl`
