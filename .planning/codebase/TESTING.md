# Testing

## Framework & Setup

- **Framework:** pytest 8.0+ with pytest-asyncio 0.23+
- **Location:** `tests/` directory
- **Naming:** `test_*.py` files, `Test*` classes, `test_*` methods
- **Run:** `pytest` from project root

## Test Files

| File | Lines | Coverage Area |
|---|---|---|
| `tests/test_classifier.py` | 176 | Route classification by field signals |
| `tests/test_confidence.py` | 178 | Multi-factor confidence scoring |
| `tests/test_database.py` | 195 | SQLite CRUD, caching, credit tracking |
| `tests/test_io.py` | 104 | CSV/Excel import/export |
| `tests/test_models.py` | 165 | Pydantic model validation |
| `tests/test_pattern_engine.py` | 191 | Email pattern discovery/matching |
| `tests/test_providers.py` | 252 | Provider API integration (mocked) |
| `tests/test_waterfall.py` | 96 | Waterfall orchestration flow |
| **Total** | **1,357** | |

## Test Structure

### Class-Based Organization
```python
class TestCompany:
    def test_domain_normalization(self):
        company = Company(domain="WWW.Example.COM")
        assert company.domain == "example.com"

    def test_employee_count_validation(self):
        ...

class TestPerson:
    def test_email_normalization(self):
        ...
```

### Fixtures
```python
@pytest.fixture
def db(tmp_path):
    """Fresh isolated database per test."""
    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    database.initialize()
    yield database
    database.close()

@pytest.fixture
def settings():
    """Default test settings."""
    return Settings(
        waterfall_order=["apollo", "icypeas"],
        cache_ttl_days=1,
    )
```

## Mocking Patterns

### Provider Mocking
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_apollo_find_email():
    provider = ApolloProvider(api_key="test-key")
    provider._request = AsyncMock(return_value={
        "person": {"email": "john@example.com"},
    })
    result = await provider.find_email("John", "Doe", "example.com")
    assert result.success
    assert result.email == "john@example.com"
```

### Database Mocking
- Uses `tmp_path` fixture for isolated SQLite files
- Each test gets a fresh database instance
- No shared state between tests

## Test Patterns

### Arrange-Act-Assert
```python
def test_confidence_cross_provider_bonus(self):
    # Arrange
    result = EnrichmentResult(
        email="test@example.com",
        providers=["apollo", "findymail"],
    )
    # Act
    score = calculate_confidence(result)
    # Assert
    assert score > 80  # Cross-provider agreement bonus
```

### Floating-Point Comparisons
```python
assert confidence == pytest.approx(0.85, abs=0.01)
```

### Async Tests
```python
@pytest.mark.asyncio
async def test_waterfall_cascade():
    """Test that waterfall tries next provider on failure."""
    ...
```

## Coverage Gaps

### Not Tested
- CLI commands (no integration tests for `cli/main.py`)
- Streamlit UI pages
- Concurrent database access under load
- Real MX/SMTP email verification
- Waterfall edge cases: all providers fail, mid-cascade timeout, budget exhaustion
- Malformed API response handling
- Provider rate limiting behavior

### Improvement Opportunities
- Add integration tests for CLI commands using Click's test runner
- Add property-based tests for model validation (hypothesis)
- Add stress tests for concurrent database writes
- Mock at HTTP transport level instead of method level for more realistic tests
