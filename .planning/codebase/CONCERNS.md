# Codebase Concerns

## Tech Debt

### Bare Exception Handling
- Multiple `except Exception` blocks across providers that swallow errors silently
- Files: `providers/apollo.py`, `providers/findymail.py`, `providers/icypeas.py`, `providers/contactout.py`
- Impact: Debugging failures becomes difficult; silent data loss possible

### Missing Input Validation
- Provider methods accept raw strings without sanitization
- Domain inputs not validated before API calls
- Impact: Invalid API calls waste credits

### JSON Response Fragility
- Direct dictionary key access without `.get()` fallbacks in several providers
- Impact: KeyError crashes on unexpected API response formats

### Incomplete Error Recovery
- Rate limit handling exists but retry logic is inconsistent across providers
- Some providers retry, others just raise
- Impact: Intermittent failures during batch processing

### SQL Injection Risk
- Some database queries use string formatting instead of parameterized queries
- File: `data/database.py`
- Impact: Security vulnerability if user input reaches queries

## Known Bugs

### Campaign Row Data Handling
- Campaign processing may not correctly handle rows with missing fields
- Partial enrichment results could be lost on campaign failure

### Cache Hit Logic
- Cache lookup may return stale data past TTL in edge cases
- TTL comparison logic needs verification

### Pattern Duplicates
- Pattern engine may store duplicate patterns for the same domain
- File: `enrichment/pattern_engine.py`
- Impact: Wasted storage, potentially conflicting pattern matches

## Security Concerns

### API Key Storage
- Keys stored in `.env` file with no rotation mechanism
- No encryption at rest for stored API keys
- No key expiry tracking

### SMTP Probing
- Email verification could trigger spam detection systems
- No rate limiting on verification attempts per domain

### SQL Schema
- Database schema created inline without migration tracking
- No protection against schema injection via malformed data

## Performance Bottlenecks

### Batch Operations
- Batch enrichment processes rows sequentially within each provider call
- No connection pooling optimization across batch items
- Impact: Large CSVs (500+ rows) will be slow

### Fixed Concurrency
- Hardcoded concurrency limits don't adapt to provider rate limits
- Impact: Either too aggressive (429 errors) or too conservative (slow)

### Unindexed Cache
- SQLite cache table may lack indexes on frequently queried columns
- Impact: Slow cache lookups as data grows

### Unbounded Pattern Queries
- Pattern engine queries all patterns for a domain without pagination
- Impact: Memory issues with domains that have many learned patterns

## Fragile Areas

### Email Verification Timeouts
- MX record lookups and SMTP connections can hang indefinitely
- No consistent timeout enforcement across verification paths

### Provider Response Duplication
- Multiple providers may return different emails for the same person
- Deduplication logic is minimal — waterfall stops at first hit without cross-validation

### Non-Atomic State Updates
- Campaign progress, credit usage, and cache writes are separate DB operations
- Crash mid-batch could leave inconsistent state

### Budget Transaction Safety
- Budget checks and credit deductions aren't atomic
- Race condition possible in concurrent enrichment

## Scaling Limits

### SQLite Concurrency
- WAL mode helps but SQLite still has write lock contention
- Impact: Multiple Streamlit users doing batch enrichment simultaneously will bottleneck

### Unbounded Cache Growth
- No automatic cache eviction beyond TTL
- Cache table will grow indefinitely
- Impact: Database file size, query performance

### Unsegmented Row Processing
- All rows processed in single batch without chunking strategy
- Impact: Memory pressure on large datasets

### Unshared HTTP Clients
- Each provider creates its own httpx client
- No connection reuse across provider instances

## Dependency Risks

### Pandas Overhead
- Full pandas imported for CSV I/O that could use lighter alternatives
- Impact: Startup time, memory footprint

### Pydantic v2 Breaking Changes
- Using Pydantic v2 which has different API from v1
- Some patterns may mix v1/v2 style

### httpx Timeout Defaults
- Default httpx timeouts may not be appropriate for slow API responses
- Some enrichment APIs can take 10-30 seconds

## Missing Features

### Deduplication
- No cross-campaign deduplication
- Same person enriched multiple times across campaigns wastes credits

### Pause/Resume
- No mechanism to pause and resume batch enrichment
- Network interruption loses progress

### Audit Trail
- Credit usage tracked but no detailed audit log of which API calls were made
- Difficult to dispute provider billing

### A/B Testing
- No mechanism to test waterfall order effectiveness
- Can't compare hit rates of different provider orderings

## Test Coverage Gaps

### CLI Integration Tests
- CLI commands not tested end-to-end
- File: `cli/main.py` has no corresponding integration tests

### Provider Response Mocking
- Tests mock at high level but don't cover edge cases in API response parsing
- Missing tests for malformed API responses

### Concurrent Database Access
- No tests for concurrent read/write scenarios
- SQLite locking behavior untested under load

### Email Verification
- Verification logic not tested with real MX/SMTP scenarios
- Mock-only testing may miss timeout and connection issues

### Waterfall Edge Cases
- Waterfall tests don't cover: all providers failing, mid-waterfall timeout, budget exhaustion mid-cascade
