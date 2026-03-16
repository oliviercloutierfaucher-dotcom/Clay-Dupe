# Salesforce API Patterns & Security Research

> Deep research for Clay-Dupe Phase 11 (Salesforce Integration)
> Focus: SOQL injection remediation, simple-salesforce best practices, caching strategy

---

## Table of Contents

1. [simple-salesforce Library Reference](#1-simple-salesforce-library-reference)
2. [SOQL Injection & Security](#2-soql-injection--security)
3. [Our Vulnerability Analysis](#3-our-vulnerability-analysis)
4. [Salesforce Data Model](#4-salesforce-data-model)
5. [API Limits](#5-api-limits)
6. [Caching Strategy](#6-caching-strategy)
7. [Testing Salesforce Integration](#7-testing-salesforce-integration)
8. [Implementation Recommendations](#8-implementation-recommendations)

---

## 1. simple-salesforce Library Reference

### 1.1 Authentication Methods

**simple-salesforce** (v1.12.9, Python 3.9-3.13) supports four authentication flows:

#### Username / Password / Security Token

```python
from simple_salesforce import Salesforce

sf = Salesforce(
    username='user@example.com',
    password='password',
    security_token='token',          # from Profile -> Reset Security Token
    domain='login',                  # 'login' (prod) or 'test' (sandbox)
)
```

#### IP-Whitelist with Organization ID

```python
sf = Salesforce(
    username='user@example.com',
    password='password',
    organizationId='OrgId',          # no security_token needed
)
```

#### JWT Bearer Token (server-to-server, recommended for production)

```python
sf = Salesforce(
    username='user@example.com',
    consumer_key='XYZ',
    privatekey_file='filename.key',  # or privatekey='key-string'
)
```

#### Connected App (OAuth 2.0 client credentials)

```python
sf = Salesforce(
    username='user@example.com',
    password='password',
    consumer_key='consumer_key',
    consumer_secret='consumer_secret',
)

# Or domain-based (no username/password):
sf = Salesforce(
    consumer_key='sfdc_client_id',
    consumer_secret='sfdc_client_secret',
    domain='organization.my',        # your My Domain
)
```

#### Direct Session ID

```python
sf = Salesforce(
    instance='na1.salesforce.com',   # or instance_url='https://na1.salesforce.com'
    session_id='existing_access_token',
)
```

### 1.2 Constructor Parameters (Complete)

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | str | Salesforce username |
| `password` | str | Password |
| `security_token` | str | Security token (from profile settings) |
| `session_id` | str | Pre-existing access token |
| `instance` | str | Domain only, e.g. `na1.salesforce.com` |
| `instance_url` | str | Full URL, e.g. `https://na1.salesforce.com` |
| `organizationId` | str | Org ID for IP-whitelist auth |
| `version` | str | API version, default `'59.0'` |
| `proxies` | dict | `{"http": "...", "https": "..."}` |
| `session` | requests.Session | Custom session for specialized handling |
| `client_id` | str | App identifier, appears as `simple-salesforce/MyApp` |
| `domain` | str | `'login'` (prod), `'test'` (sandbox), or My Domain |
| `consumer_key` | str | Connected App consumer key |
| `consumer_secret` | str | Connected App consumer secret |
| `privatekey_file` | str | Path to private key file for JWT |
| `privatekey` | str | Private key string for JWT |
| `parse_float` | callable | Custom float parser for JSON |
| `object_pairs_hook` | callable | JSON object pairs hook (default: OrderedDict) |

**Note on timeout**: The constructor does not have a built-in `timeout` parameter in the
current stable release. Timeout can be configured via a custom `requests.Session`:

```python
import requests

session = requests.Session()
session.timeout = 30  # seconds

sf = Salesforce(
    username='user@example.com',
    password='password',
    security_token='token',
    session=session,
)
```

### 1.3 SOQL Query Methods

#### `sf.query(soql)` -- Single Page

Returns first page of results (up to 2,000 records). If more exist, response
includes `nextRecordsUrl`.

```python
result = sf.query("SELECT Id, Email FROM Contact WHERE LastName = 'Jones'")
# result = {"totalSize": 5, "done": True, "records": [...]}
```

#### `sf.query_more(identifier, identifier_is_url=False)` -- Pagination

```python
# By record ID:
sf.query_more("01gD0000002HU6KIAW-2000")

# By full URL:
sf.query_more("/services/data/v59.0/query/01gD0000002HU6KIAW-2000", True)
```

#### `sf.query_all(soql)` -- All Results Materialized

Fetches ALL pages and returns them in a single dict. **Warning**: materializes
entire result set into memory.

```python
result = sf.query_all("SELECT Id, Email FROM Contact WHERE LastName = 'Jones'")
# All records in result["records"], regardless of pagination
```

#### `sf.query_all_iter(soql)` -- Lazy Iterator (Recommended for Large Sets)

Returns an iterator -- processes one record at a time without loading all into memory.

```python
for record in sf.query_all_iter("SELECT Id, Name FROM Account"):
    process(record)
```

### 1.4 Record Management (CRUD)

```python
# Create
sf.Contact.create({'LastName': 'Smith', 'Email': 'smith@example.com'})

# Read
contact = sf.Contact.get('003e0000003GuNXAA0')

# Read by external ID
contact = sf.Contact.get_by_custom_id('My_Custom_ID__c', '22')

# Update
sf.Contact.update('003e0000003GuNXAA0', {'LastName': 'Jones'})

# Delete
sf.Contact.delete('003e0000003GuNXAA0')

# Upsert (by external ID)
sf.Contact.upsert('customExtIdField__c/11999', {'LastName': 'Smith'})

# Deleted records (last 10 days)
sf.Contact.deleted(start_datetime, end_datetime)

# Updated records (last 10 days)
sf.Contact.updated(start_datetime, end_datetime)
```

### 1.5 Bulk API

#### Bulk 1.0

```python
sf.bulk.Account.insert([{"Name": "Acme"}, {"Name": "Beta"}])
sf.bulk.Account.update([{"Id": "001...", "Name": "Updated"}])
sf.bulk.Account.upsert([...], "External_Id__c")
sf.bulk.Account.delete([{"Id": "001..."}])
sf.bulk.Account.query("SELECT Id, Name FROM Account")
```

#### Bulk 2.0

```python
sf.bulk2.Account.insert([{"Name": "Acme"}])
sf.bulk2.Account.update([{"Id": "001...", "Name": "Updated"}])
sf.bulk2.Account.upsert([...], "External_Id__c")
sf.bulk2.Account.delete([{"Id": "001..."}])
sf.bulk2.Account.query("SELECT Id, Name FROM Account")
```

Bulk 2.0 supports `max_records`, `column_delimiter`, `line_ending` parameters.
Default wait timeout: 86,400 seconds (24 hours).

### 1.6 Error Handling -- Exception Hierarchy

```
SalesforceError (base)
  |-- SalesforceMoreThanOneRecord     (300 - multiple external ID matches)
  |-- SalesforceMalformedRequest      (400 - bad JSON/XML or invalid SOQL)
  |-- SalesforceExpiredSession         (401 - token expired or invalid)
  |-- SalesforceRefusedRequest         (403 - insufficient permissions)
  |-- SalesforceResourceNotFound       (404 - bad URI or sharing issue)
  |-- SalesforceGeneralError           (any other status code)
  |-- SalesforceAuthenticationFailed   (login failure - special constructor)
```

All exceptions carry: `url`, `status`, `resource_name`, `content`.

`SalesforceAuthenticationFailed` has a special constructor:
```python
SalesforceAuthenticationFailed(code, auth_message)
# code: str|int|None, auth_message: str
```

#### Recommended Error Handling Pattern

```python
from simple_salesforce.exceptions import (
    SalesforceAuthenticationFailed,
    SalesforceExpiredSession,
    SalesforceMalformedRequest,
    SalesforceRefusedRequest,
    SalesforceGeneralError,
)

try:
    result = sf.query(soql)
except SalesforceExpiredSession:
    # Re-authenticate and retry
    sf = Salesforce(...)  # fresh connection
    result = sf.query(soql)
except SalesforceMalformedRequest as e:
    # Bad SOQL syntax or invalid field
    logger.error("SOQL error: %s", e.content)
except SalesforceRefusedRequest as e:
    # Permission denied -- check user profile
    logger.error("Permission denied: %s", e.content)
except SalesforceAuthenticationFailed as e:
    # Credentials invalid
    logger.error("Auth failed: %s", e.auth_message)
```

### 1.7 Connection Management

- simple-salesforce uses `requests.Session` internally (one per Salesforce instance)
- Session is reusable across multiple API calls
- No built-in connection pooling -- one HTTP session per `Salesforce()` object
- For session expiry: catch `SalesforceExpiredSession`, re-instantiate, retry
- Custom session allows: SSL certs, retries (via `urllib3.Retry`), timeouts, proxies

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503])
session.mount("https://", HTTPAdapter(max_retries=retry))

sf = Salesforce(
    username='...', password='...', security_token='...',
    session=session,
)
```

---

## 2. SOQL Injection & Security

### 2.1 Can SOQL Be Injected?

**Yes.** SOQL injection is a real and documented attack vector. While SOQL is more
limited than SQL (no INSERT/UPDATE/DELETE, no UNION, no subqueries in WHERE), an
attacker can still:

1. **Exfiltrate unauthorized data** by modifying WHERE clauses
2. **Bypass access controls** by removing or changing filters
3. **Access hidden fields** by injecting additional field names

#### Classic SOQL Injection Example

Vulnerable code (Apex, but same pattern applies to Python):
```
String query = "SELECT Id, Name FROM Account WHERE Name = '" + userInput + "'";
```

Attack payload:
```
' OR Name != '
```

Resulting SOQL:
```sql
SELECT Id, Name FROM Account WHERE Name = '' OR Name != ''
-- Returns ALL accounts
```

More sophisticated attack:
```
%' AND Performance_Rating__c < 2 AND Name LIKE '%
```

This lets an attacker query fields they were not supposed to see.

### 2.2 Attack Surface in Our Context

In our `providers/salesforce.py`, the attack surface is:

1. **Phase 1 (IN clause)**: Domain strings are interpolated directly into SOQL
   ```python
   in_clause = ", ".join(f"'{d}'" for d in chunk)
   soql = f"... WHERE Unique_Domain__c IN ({in_clause})"
   ```
   A domain like `acme.com' OR Name != '` would break out of the string.

2. **Phase 2 (LIKE clause)**: Even worse -- no escaping at all
   ```python
   like_clauses = " OR ".join(f"Website LIKE '%{d}%'" for d in chunk)
   ```
   A domain like `%' OR Id != '` would return all accounts.

### 2.3 Prevention: `format_soql()` (THE Answer for Python)

simple-salesforce provides `format_soql()` -- a parameterized query builder that
properly escapes all SOQL special characters.

```python
from simple_salesforce.format import format_soql
```

#### How It Works Internally

The `format.py` source reveals the exact escaping logic:

```python
# Characters that get escaped in SOQL strings:
soql_escapes = str.maketrans({
    '\\': '\\\\',    # backslash
    '\'': '\\\'',    # single quote (THE critical one)
    '"': '\\"',      # double quote
    '\n': '\\n',     # newline
    '\r': '\\r',     # carriage return
    '\t': '\\t',     # tab
    '\b': '\\b',     # backspace
    '\f': '\\f',     # form feed
})

# Additional escapes for LIKE expressions:
soql_like_escapes = str.maketrans({
    '%': '\\%',      # percent wildcard
    '_': '\\_',      # underscore wildcard
})
```

#### `quote_soql_value(value)` -- Type-Aware Quoting

```python
quote_soql_value("O'Brien")      # => "'O\\'Brien'"
quote_soql_value(42)              # => "42"
quote_soql_value(True)            # => "true"
quote_soql_value(None)            # => "null"
quote_soql_value(["a", "b"])      # => "('a','b')"  -- for IN clauses!
quote_soql_value(datetime(...))   # => ISO 8601 format
quote_soql_value(date(...))       # => ISO 8601 format
```

#### Usage Patterns

```python
# Positional parameters:
format_soql("SELECT Id FROM Account WHERE Name = {}", "O'Brien")
# => "SELECT Id FROM Account WHERE Name = 'O\\'Brien'"

# Named parameters:
format_soql(
    "SELECT Id FROM Contact WHERE LastName = {name}",
    name="Jones"
)

# List/IN clause (automatic parentheses + quoting):
format_soql(
    "SELECT Id FROM Account WHERE Unique_Domain__c IN {}",
    ["acme.com", "beta.com"]
)
# => "SELECT Id FROM Account WHERE Unique_Domain__c IN ('acme.com','beta.com')"

# :literal modifier -- SKIP escaping (use for field names, operators):
format_soql(
    "SELECT Id FROM {:literal} WHERE Name = {}",
    "Account", "Acme"
)

# :like modifier -- escape LIKE wildcards in user input while preserving %:
format_soql(
    "SELECT Id FROM Account WHERE Website LIKE '%{:like}%'",
    "acme.com"
)
# Escapes %, _, \, ' in the user value but preserves the surrounding %
```

### 2.4 The `:like` Modifier Deep Dive

This is critical for our Website LIKE queries. The `:like` modifier:

1. Applies standard SOQL string escaping (single quotes, backslashes, etc.)
2. **Additionally** escapes `%` and `_` in the user's input so they are treated as
   literal characters, not SOQL wildcards
3. Does NOT add surrounding quotes -- you must provide them in the format string

```python
# User input: "acme.com"
format_soql("Website LIKE '%{:like}%'", "acme.com")
# => "Website LIKE '%acme.com%'"

# Malicious input: "acme%' OR Id != '"
format_soql("Website LIKE '%{:like}%'", "acme%' OR Id != '")
# => "Website LIKE '%acme\\%\\' OR Id != \\'%'"
# The ' is escaped, the % in the input is escaped -- injection blocked
```

### 2.5 Manual Escaping (When format_soql Is Insufficient)

If you need to build dynamic SOQL outside of format_soql, use the translation tables
directly:

```python
from simple_salesforce.format import soql_escapes, soql_like_escapes

# For string values in WHERE X = 'value':
safe_value = user_input.translate(soql_escapes)
soql = f"SELECT Id FROM Account WHERE Name = '{safe_value}'"

# For LIKE patterns:
safe_pattern = user_input.translate(soql_escapes).translate(soql_like_escapes)
soql = f"SELECT Id FROM Account WHERE Website LIKE '%{safe_pattern}%'"
```

**However, `format_soql` is always preferred** -- it handles type coercion, list
formatting, and edge cases that manual escaping misses.

### 2.6 SOQL vs SQL Injection -- Key Differences

| Aspect | SQL Injection | SOQL Injection |
|--------|--------------|----------------|
| INSERT/UPDATE/DELETE | Possible | NOT possible (SOQL is read-only) |
| UNION attacks | Possible | NOT possible (no UNION in SOQL) |
| Subquery in WHERE | Possible | NOT possible |
| Data exfiltration | Full database | Only objects user has access to |
| Field access | Any column | Only fields in user's profile |
| Drop table | Possible | NOT possible |
| Severity | Critical | Medium-High (data leak, not destruction) |

**Key takeaway**: SOQL injection cannot destroy data, but it CAN leak data the user
should not see (e.g., querying all accounts when they should only see filtered results).

---

## 3. Our Vulnerability Analysis

### 3.1 Current Vulnerable Code (`providers/salesforce.py`)

#### Vulnerability #1: IN Clause (Line 124)

```python
# VULNERABLE -- direct string interpolation
in_clause = ", ".join(f"'{d}'" for d in chunk)
soql = (
    f"SELECT Id, Name, Unique_Domain__c, Website "
    f"FROM Account "
    f"WHERE Unique_Domain__c IN ({in_clause})"
)
```

**Attack vector**: A domain value like `acme.com' OR Name LIKE '%` would break out
of the IN clause and query arbitrary data.

**Risk level**: Medium -- domains come from our CSV upload, not direct user typing,
but defense in depth requires fixing this.

#### Vulnerability #2: LIKE Clause (Lines 147-149)

```python
# VULNERABLE -- direct string interpolation in LIKE
like_clauses = " OR ".join(
    f"Website LIKE '%{d}%'" for d in chunk
)
```

**Attack vector**: A domain value like `%' OR Id != '` would return all accounts.

**Risk level**: Medium -- same as above, but LIKE queries are more commonly targeted.

### 3.2 Fixed Code

```python
from simple_salesforce.format import format_soql

def _do_check_domains(self, domains: list[str]) -> dict[str, dict]:
    sf = self._connect()
    instance_url = sf.sf_instance
    results: dict[str, dict] = {}
    unmatched = set(domains)

    # Phase 1: Unique_Domain__c exact match (IN clause)
    for chunk in _chunked(domains, BATCH_SIZE):
        soql = format_soql(
            "SELECT Id, Name, Unique_Domain__c, Website "
            "FROM Account "
            "WHERE Unique_Domain__c IN {}",
            chunk,  # format_soql handles list -> ('val1','val2') with escaping
        )
        response = sf.query_all(soql)
        for record in response.get("records", []):
            unique_domain = record.get("Unique_Domain__c")
            if unique_domain:
                nd = _normalize_domain(unique_domain)
                if nd in unmatched:
                    results[nd] = {
                        "sf_account_id": record["Id"],
                        "sf_account_name": record["Name"],
                        "sf_instance_url": instance_url,
                    }
                    unmatched.discard(nd)

    # Phase 2: Website LIKE fallback (safe escaping)
    if unmatched:
        unmatched_list = list(unmatched)
        for chunk in _chunked(unmatched_list, BATCH_SIZE):
            # Build LIKE clauses with proper escaping
            like_parts = []
            for d in chunk:
                safe_clause = format_soql(
                    "Website LIKE '%{:like}%'", d
                )
                like_parts.append(safe_clause)
            where_clause = " OR ".join(like_parts)

            soql = (
                f"SELECT Id, Name, Website "
                f"FROM Account "
                f"WHERE {where_clause}"
            )
            response = sf.query_all(soql)
            # ... same record processing as before
```

---

## 4. Salesforce Data Model

### 4.1 Account Object

| Field | API Name | Type | Notes |
|-------|----------|------|-------|
| Account ID | `Id` | ID (18 char) | Auto-generated, unique |
| Account Name | `Name` | String (255) | Required |
| Website | `Website` | URL (255) | Free-text, no standard format |
| Industry | `Industry` | Picklist | Standard values |
| Phone | `Phone` | Phone | |
| Type | `Type` | Picklist | Customer, Partner, Prospect, etc. |
| Description | `Description` | TextArea | |
| BillingCity | `BillingCity` | String | |
| NumberOfEmployees | `NumberOfEmployees` | Integer | |
| AnnualRevenue | `AnnualRevenue` | Currency | |

**Website field format**: There is NO standard format. You will see all of these:
- `https://www.acme.com`
- `http://acme.com`
- `www.acme.com`
- `acme.com`
- `acme.com/`
- `https://acme.com/en/`

This is why our `_normalize_domain()` function is essential, and why LIKE queries
are needed as a fallback.

**Custom fields** (like our `Unique_Domain__c`): Created by admins, end with `__c`.
This is the most reliable way to do domain matching -- a normalized, deduplicated
domain field.

### 4.2 Contact Object

| Field | API Name | Type | Notes |
|-------|----------|------|-------|
| Contact ID | `Id` | ID | |
| First Name | `FirstName` | String | |
| Last Name | `LastName` | String | Required |
| Email | `Email` | Email | Standard email field |
| Account | `AccountId` | Reference | Links to Account |
| Phone | `Phone` | Phone | |
| Title | `Title` | String | Job title |
| Department | `Department` | String | |

**Querying Contacts by Email**:
```python
# Exact match
format_soql("SELECT Id, FirstName, LastName, AccountId FROM Contact WHERE Email = {}", email)

# Domain match (all contacts at a company)
format_soql("SELECT Id, Email, AccountId FROM Contact WHERE Email LIKE '%{:like}'", "@acme.com")
```

### 4.3 Lead Object

Leads are separate from Contacts -- they represent unqualified prospects. Key differences:

- Leads are NOT linked to an Account (they have `Company` as a text field)
- When qualified, a Lead is "converted" into a Contact + Account (+ optionally Opportunity)
- After conversion, the Lead record is marked as converted and largely read-only

For our use case: we primarily care about Account + Contact. Leads are relevant only if
we want to check "does this person already exist as a Lead?"

### 4.4 Domain Matching Strategies

#### Strategy 1: Custom Field `Unique_Domain__c` (Best)

- Admin creates a custom text field on Account
- Populated by automation (Flow, Apex trigger, or our tool)
- Always normalized (lowercase, no protocol, no www)
- Enables exact-match queries (fast, no LIKE needed)

```python
format_soql(
    "SELECT Id, Name FROM Account WHERE Unique_Domain__c IN {}",
    ["acme.com", "beta.com"]
)
```

#### Strategy 2: Website LIKE Query (Fallback)

- Works with standard Website field, no custom fields needed
- Slower (LIKE scans don't use indexes efficiently)
- Requires careful normalization on the result side

```python
format_soql(
    "SELECT Id, Name, Website FROM Account WHERE Website LIKE '%{:like}%'",
    "acme.com"
)
```

#### Strategy 3: SOSL Search (For fuzzy matching)

```python
sf.search("FIND {acme.com} IN ALL FIELDS RETURNING Account(Id, Name, Website)")
```

SOSL is tokenized search -- faster than LIKE but less precise.

### 4.5 Salesforce Duplicate Detection

Salesforce has built-in duplicate management:

- **Matching Rules**: Define which fields to compare and how (exact, fuzzy, etc.)
  - Standard Account Matching Rule: Account Name + Billing Address (fuzzy)
  - Standard Contact Matching Rule: First Name + Last Name + Email (exact)
  - Standard Lead Matching Rule: First Name + Last Name + Email + Company (exact)
- **Duplicate Rules**: Define what happens when a duplicate is found (alert, block, report)
- Can have up to 5 active duplicate rules per object, 3 matching rules per duplicate rule

For our use case: we do our own matching (by domain), so we don't rely on Salesforce's
duplicate rules. But we should be aware they exist -- an admin might have them configured,
and our creates/updates might trigger duplicate alerts.

---

## 5. API Limits

### 5.1 Daily API Request Limits (Rolling 24-Hour Window)

| Edition | Base Limit | Per User License | Typical Total |
|---------|-----------|-----------------|---------------|
| Developer | 15,000 | -- | 15,000 |
| Professional | 15,000 | +1,000/license | ~25,000 (10 users) |
| Enterprise | 100,000 | +1,000/license | ~150,000 (50 users) |
| Unlimited | Unlimited | -- | Unlimited |

**Important**: This is a SOFT limit. Salesforce does not immediately block orgs that
temporarily exceed limits, but sustained overage will result in `REQUEST_LIMIT_EXCEEDED`
errors. The daily limit counts ALL API types: REST, SOAP, Bulk, Connect.

### 5.2 SOQL Query Limits

| Limit | Value | Notes |
|-------|-------|-------|
| Max records per query | 2,000 (per page) | Use `query_all` for auto-pagination |
| Max total records | 50,000 | Per transaction in Apex; via REST API, pagination handles this |
| Max SOQL query length | 100,000 characters | Rarely a concern |
| Max IN clause values | ~200 (practical) | Our BATCH_SIZE=150 is safe |
| SOQL timeout | 120 seconds | Server-side; long-running queries time out |

### 5.3 Bulk API Limits

| Limit | Value |
|-------|-------|
| Max batches per day | 15,000 |
| Max records per batch | 10,000 |
| Max batch size | 10 MB |
| Max concurrent jobs | 5 per org |
| Max query timeout | 2 minutes per batch |

### 5.4 Rate Limiting Best Practices

```python
# Check remaining API calls:
result = sf.limits()
# Returns: {"DailyApiRequests": {"Max": 100000, "Remaining": 95000}, ...}

# Our batch approach is efficient:
# - 300 domains = 2 SOQL queries (150 per chunk) for IN clause
# - Plus 2 SOQL queries for LIKE fallback (worst case)
# - Total: ~4 API calls per 300 domains
# - Even at 1000 enrichment runs/day: ~4000 calls = well within limits
```

### 5.5 Monitoring API Usage

```python
# Programmatic check:
limits = sf.limits()
daily = limits['DailyApiRequests']
print(f"Used: {daily['Max'] - daily['Remaining']} / {daily['Max']}")

# Also available in Salesforce UI:
# Setup -> Company Information -> API Requests, Last 24 Hours
```

---

## 6. Caching Strategy

### 6.1 How Often Does Salesforce Data Change?

- **Account records**: Relatively stable. New accounts added daily/weekly.
  Website/domain fields rarely change for existing accounts.
- **Contact records**: More volatile. New contacts added frequently.
- **Reasonable cache TTL for domain lookups**: 1-4 hours for active usage,
  24 hours for batch processing runs.

### 6.2 Recommended Caching Architecture

```python
# Two-level cache for domain lookups:

# Level 1: In-memory (per session, clears on restart)
# - TTL: 1 hour
# - Purpose: Avoid redundant queries within a single enrichment run
# - Implementation: dict with timestamp

# Level 2: SQLite (persistent, survives restarts)
# - TTL: 24 hours (configurable)
# - Purpose: Avoid querying Salesforce for domains we checked recently
# - Implementation: sf_cache_checked_at timestamp in companies table
```

#### Implementation Pattern

```python
from datetime import datetime, timedelta

CACHE_TTL = timedelta(hours=24)

class SalesforceClient:
    def __init__(self, ...):
        self._domain_cache: dict[str, dict | None] = {}
        self._cache_timestamps: dict[str, datetime] = {}

    def check_domain_cached(self, domain: str) -> dict | None:
        """Check cache before hitting Salesforce API."""
        norm = _normalize_domain(domain)
        if norm in self._domain_cache:
            if datetime.utcnow() - self._cache_timestamps[norm] < CACHE_TTL:
                return self._domain_cache[norm]
            else:
                del self._domain_cache[norm]
                del self._cache_timestamps[norm]
        return None  # Cache miss

    def _cache_result(self, domain: str, result: dict | None):
        """Cache a domain lookup result (including negative results)."""
        norm = _normalize_domain(domain)
        self._domain_cache[norm] = result
        self._cache_timestamps[norm] = datetime.utcnow()
```

### 6.3 Incremental Sync with Salesforce

For keeping our local cache in sync with Salesforce changes:

#### Option A: Polling with SystemModstamp (Simple, Recommended)

```python
# Query only accounts modified since last sync
last_sync = get_last_sync_timestamp()
soql = format_soql(
    "SELECT Id, Name, Website, Unique_Domain__c, SystemModstamp "
    "FROM Account "
    "WHERE SystemModstamp > {}",
    last_sync,
)
for record in sf.query_all_iter(soql):
    update_local_cache(record)
save_last_sync_timestamp(datetime.utcnow())
```

#### Option B: Change Data Capture (Real-Time, Complex)

Salesforce Change Data Capture (CDC) publishes events when records change:

- Events retained for 3 days
- Uses CometD or Pub/Sub API for subscription
- Requires additional Salesforce configuration
- Overkill for our use case -- we don't need real-time sync

**Recommendation**: Use polling with SystemModstamp. Run it as a background task
every 1-4 hours. This is simple, reliable, and well within API limits.

### 6.4 Cache Invalidation Strategies

- **Time-based**: Simple TTL (recommended, 24h default)
- **On-demand**: User clicks "Refresh Salesforce Data" in UI
- **Startup**: Clear cache on application restart (in-memory cache does this naturally)
- **Negative caching**: Cache "domain NOT in Salesforce" results too, with shorter TTL
  (1 hour) to detect newly-added accounts faster

---

## 7. Testing Salesforce Integration

### 7.1 Salesforce Developer Edition (Free)

- Sign up at https://developer.salesforce.com/signup
- Full-featured org with 15,000 API calls/day
- Includes all standard objects (Account, Contact, Lead, Opportunity)
- Can create custom fields (like `Unique_Domain__c`)
- Persists data indefinitely (but Salesforce may deactivate inactive orgs after 1 year)

### 7.2 Sandbox Environments

- Available on Enterprise, Unlimited, Performance editions
- Types: Developer Sandbox (free), Partial Copy, Full Copy
- Sandbox domain: use `domain='test'` in simple-salesforce
- Username convention: `user@example.com.sandboxname`

```python
sf = Salesforce(
    username='user@example.com.mysandbox',
    password='password',
    security_token='token',
    domain='test',
)
```

### 7.3 Mocking simple-salesforce in Pytest

Our existing tests already follow good patterns. Here is the recommended approach:

```python
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

class TestSalesforceClient:

    @patch("providers.salesforce.Salesforce")
    def test_domain_check(self, MockSF):
        """Test domain checking with mocked Salesforce."""
        # Set up mock
        mock_sf = MagicMock()
        type(mock_sf).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        mock_sf.query_all.return_value = {
            "records": [{
                "Id": "001ABC",
                "Name": "Acme Inc",
                "Unique_Domain__c": "acme.com",
                "Website": "https://acme.com",
            }]
        }
        MockSF.return_value = mock_sf

        # Test
        client = SalesforceClient("user", "pass", "token")
        result = client.check_domains_batch(["acme.com"])

        # Assert
        assert "acme.com" in result
        assert result["acme.com"]["sf_account_id"] == "001ABC"

        # Verify the SOQL query was safe (inspect call args)
        actual_soql = mock_sf.query_all.call_args[0][0]
        assert "'" not in actual_soql.replace("\\'", "")  # no unescaped quotes

    @patch("providers.salesforce.Salesforce")
    def test_soql_injection_prevented(self, MockSF):
        """Verify malicious domain names are properly escaped."""
        mock_sf = MagicMock()
        type(mock_sf).sf_instance = PropertyMock(return_value="na1.salesforce.com")
        mock_sf.query_all.return_value = {"records": []}
        MockSF.return_value = mock_sf

        client = SalesforceClient("user", "pass", "token")
        # Attempt injection via domain name
        malicious = "acme.com' OR Name != '"
        client.check_domains_batch([malicious])

        # Verify the query was escaped
        actual_soql = mock_sf.query_all.call_args[0][0]
        # The malicious single quote should be escaped
        assert "OR Name" not in actual_soql
```

### 7.4 Testing SOQL Escaping Directly

```python
from simple_salesforce.format import format_soql

def test_format_soql_escapes_single_quotes():
    result = format_soql("SELECT Id FROM Account WHERE Name = {}", "O'Brien")
    assert result == "SELECT Id FROM Account WHERE Name = 'O\\'Brien'"

def test_format_soql_escapes_injection_attempt():
    result = format_soql("SELECT Id FROM Account WHERE Name = {}", "' OR '1'='1")
    assert "OR" not in result.split("'")[0]  # OR is inside the escaped string

def test_format_soql_list_escaping():
    result = format_soql(
        "SELECT Id FROM Account WHERE Domain__c IN {}",
        ["acme.com", "O'Brien.com"]
    )
    assert "O\\'Brien.com" in result

def test_format_soql_like_escaping():
    result = format_soql(
        "SELECT Id FROM Account WHERE Website LIKE '%{:like}%'",
        "acme%attack"
    )
    assert "\\%" in result  # % in input is escaped

def test_format_soql_like_preserves_wildcards():
    result = format_soql(
        "SELECT Id FROM Account WHERE Website LIKE '%{:like}%'",
        "acme.com"
    )
    # The surrounding % should remain, the input should be clean
    assert result.startswith("SELECT Id FROM Account WHERE Website LIKE '%acme.com%'")
```

### 7.5 Integration Test Setup

For actual end-to-end testing against a Salesforce org:

```python
import os
import pytest

@pytest.fixture
def sf_client():
    """Create a real Salesforce client for integration tests.
    Skip if credentials not configured.
    """
    username = os.environ.get("SF_TEST_USERNAME")
    password = os.environ.get("SF_TEST_PASSWORD")
    token = os.environ.get("SF_TEST_TOKEN")

    if not all([username, password, token]):
        pytest.skip("Salesforce test credentials not configured")

    return SalesforceClient(username, password, token)

@pytest.mark.integration
def test_real_health_check(sf_client):
    result = sf_client.health_check()
    assert result["connected"] is True
    assert result["org_name"]  # non-empty

@pytest.mark.integration
def test_real_domain_check(sf_client):
    # Assumes test org has an account with acme.com
    result = sf_client.check_domains_batch(["acme.com"])
    # May or may not find it -- just verify no errors
    assert isinstance(result, dict)
```

---

## 8. Implementation Recommendations

### 8.1 Priority Fixes (Security -- Do First)

1. **Replace all string interpolation in SOQL with `format_soql()`**
   - IN clause: Use list parameter (automatic `('val1','val2')` formatting)
   - LIKE clause: Use `:like` modifier
   - This is a 10-line change that eliminates the injection vulnerability

2. **Add SOQL injection tests**
   - Test with `'`, `%`, `_`, `\`, and known injection payloads
   - Verify escaped output in mock call args

### 8.2 Reliability Improvements

3. **Add timeout via custom session**
   ```python
   session = requests.Session()
   session.timeout = 30
   ```

4. **Add retry logic with backoff**
   ```python
   retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503])
   ```

5. **Check API limits before batch operations**
   ```python
   limits = sf.limits()
   remaining = limits['DailyApiRequests']['Remaining']
   if remaining < 100:
       raise SalesforceAPILimitWarning(f"Only {remaining} API calls remaining")
   ```

### 8.3 Performance Improvements

6. **Implement domain cache** (in-memory + SQLite)
   - Skip Salesforce API calls for recently-checked domains
   - Cache negative results too (shorter TTL)

7. **Use `query_all_iter` instead of `query_all`** for large result sets
   - Avoids materializing entire result set in memory

8. **Consider Bulk API for large batches** (>1000 domains)
   - Single API call instead of many chunked queries

### 8.4 Authentication Upgrade Path

9. **Move from username/password to JWT** for production
   - More secure (no password in config)
   - Supports automated token refresh
   - Standard for server-to-server integrations

---

## Sources

- [simple-salesforce PyPI](https://pypi.org/project/simple-salesforce/)
- [simple-salesforce GitHub](https://github.com/simple-salesforce/simple-salesforce)
- [simple-salesforce Documentation](https://simple-salesforce.readthedocs.io/)
- [simple-salesforce format.py (source)](https://github.com/simple-salesforce/simple-salesforce/blob/master/simple_salesforce/format.py)
- [simple-salesforce exceptions.py (source)](https://github.com/simple-salesforce/simple-salesforce/blob/master/simple_salesforce/exceptions.py)
- [Salesforce Secure Coding Guide - SQL Injection](https://developer.salesforce.com/docs/atlas.en-us.secure_coding_guide.meta/secure_coding_guide/secure_coding_sql_injection.htm)
- [Salesforce Trailhead - Prevent SOQL Injection](https://trailhead.salesforce.com/content/learn/modules/secure-serverside-development/mitigate-soql-injection)
- [Dynamic SOQL Injection Prevention - Apex Hours](https://www.apexhours.com/dynamic-soql-injection-prevention/)
- [Salesforce API Limits Blog](https://developer.salesforce.com/blogs/2024/11/api-limits-and-monitoring-your-api-usage)
- [Salesforce API Rate Limits - Coefficient](https://coefficient.io/salesforce-api/salesforce-api-rate-limits)
- [Salesforce API Request Limits - Developer Docs](https://developer.salesforce.com/docs/atlas.en-us.salesforce_app_limits_cheatsheet.meta/salesforce_app_limits_cheatsheet/salesforce_app_limits_platform_api.htm)
- [Salesforce SOQL/SOSL Limits](https://developer.salesforce.com/docs/atlas.en-us.salesforce_app_limits_cheatsheet.meta/salesforce_app_limits_cheatsheet/salesforce_app_limits_platform_soslsoql.htm)
- [Salesforce Governor Limits](https://www.apexhours.com/governor-limits-in-salesforce/)
- [Salesforce Duplicate Rules](https://help.salesforce.com/s/articleView?id=sales.duplicate_rules_map_of_reference.htm)
- [Salesforce Matching Rules](https://help.salesforce.com/s/articleView?id=sales.matching_rule_map_of_reference.htm)
- [Salesforce Change Data Capture](https://trailhead.salesforce.com/content/learn/modules/change-data-capture/understand-change-data-capture)
- [Salesforce Bulk API 2.0](https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/bulk_api_2_0.htm)
- [Salesforce REST API Limits](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_limits.htm)
