# Enrichment Provider API Specifications

Comprehensive, implementation-ready API specifications for all 4 enrichment providers.

---

## 1. Apollo.io

### Base URL
```
https://api.apollo.io/api/v1
```

### Authentication
```
Headers:
  Content-Type: application/json
  Cache-Control: no-cache
  X-Api-Key: <YOUR_API_KEY>
```
- API key obtained from https://app.apollo.io/#/settings/api
- Some endpoints require a "master" API key (e.g., people search). Create via Apollo Developer Portal.
- A missing/invalid key returns `401`. Insufficient permissions (non-master key) returns `403`.

### Rate Limits (Fixed-Window Strategy)

| Plan | Per Minute | Per Day |
|------|-----------|---------|
| Free | 50 | 600 |
| Basic/Pro | 200 | 2,000 |
| Custom | Higher (negotiated) | Higher |

- Bulk endpoints are throttled to **50% of per-minute** limit of their single counterparts (but 100% of hourly/daily).
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` (on 429).
- Check your exact limits: `GET /api/v1/rate_limits`

### Error Codes

| Code | Meaning | Retry? |
|------|---------|--------|
| 200 | Success (may still have no data — check response body) | N/A |
| 401 | Unauthorized — invalid/missing API key | No |
| 403 | Forbidden — need master API key or insufficient plan | No |
| 404 | Endpoint not found | No |
| 422 | Validation error — bad request data. Response body has field-level errors. | No (fix request) |
| 429 | Rate limited. Respect `Retry-After` header. | Yes (exponential backoff: 1s, 2s, 4s, 8s) |

### Credits

- **People Search** (`mixed_people/search`): **FREE** — no credits consumed. Does NOT return emails/phones.
- **People Enrichment** (`people/match`): Costs 1 export credit per person enriched.
- **Organization Enrichment** (`organizations/enrich`): Costs 1 export credit.
- **Waterfall enrichment** (via `run_waterfall_email`/`run_waterfall_phone`): Additional credits based on which third-party source returns data.
- **Mobile phone reveal**: Costs 1 mobile credit.
- Credits do NOT roll over between billing cycles.

---

### Endpoint: People Search

```
POST /api/v1/mixed_people/search
```

**Purpose:** Find people matching filters. Returns IDs and basic profile data. Does NOT return emails or phone numbers. Use the IDs with `people/match` or `people/bulk_match` to get contact info.

**Requires:** Master API key.

**Credits:** FREE (no credits consumed).

#### Request Body

```json
{
  "person_titles": ["CEO", "CTO", "VP Engineering"],      // string[] — job title filter
  "person_locations": ["California, US", "New York, US"],  // string[] — location filter
  "person_seniorities": ["c_suite", "vp", "director"],    // string[] — seniority levels
  "q_organization_domains_list": ["example.com"],          // string[] — filter by company domain
  "organization_locations": ["United States"],             // string[] — company HQ location
  "organization_num_employees_ranges": ["11,50", "51,200"],// string[] — employee count ranges
  "organization_ids": ["5f5e2..."],                        // string[] — Apollo org IDs
  "include_similar_titles": true,                          // boolean — include title variants
  "page": 1,                                               // int — page number (default: 1)
  "per_page": 25                                           // int — results per page (max: 100, default: 25)
}
```

All parameters are **optional** but you should provide at least one filter.

#### Response Body

```json
{
  "breadcrumbs": [...],
  "partial_results_only": false,
  "disable_eu_prospecting": false,
  "partial_results_limit": 10000,
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total_entries": 1234,
    "total_pages": 50
  },
  "people": [
    {
      "id": "6081c....",
      "first_name": "John",
      "last_name": "Doe",
      "name": "John Doe",
      "linkedin_url": "https://www.linkedin.com/in/johndoe",
      "title": "CEO",
      "headline": "CEO at Acme Corp",
      "photo_url": "https://...",
      "city": "San Francisco",
      "state": "California",
      "country": "United States",
      "organization_id": "5f5e2...",
      "organization": {
        "id": "5f5e2...",
        "name": "Acme Corp",
        "website_url": "https://acme.com",
        "primary_domain": "acme.com",
        "industry": "Information Technology",
        "estimated_num_employees": 150,
        "short_description": "...",
        "logo_url": "https://..."
      },
      "has_email": true,           // boolean — indicates email is available via enrichment
      "has_direct_phone": false,
      "seniority": "c_suite",
      "departments": ["c_suite"]
    }
  ]
}
```

#### Pagination
- Max 100 per page, up to 500 pages = **50,000 record display limit**.
- Add more filters to narrow results if you hit the limit.

#### "Nothing found" response
Returns `200` with `"people": []` and `"total_entries": 0`.

---

### Endpoint: People Enrichment (Single)

```
POST /api/v1/people/match
```

**Purpose:** Enrich a single person — get email, phone, full profile from identifying info.

**Credits:** 1 export credit per enriched person.

#### Request Body

```json
{
  "first_name": "John",                    // string — optional but recommended
  "last_name": "Doe",                      // string — optional but recommended
  "email": "john@acme.com",                // string — optional (best identifier)
  "organization_name": "Acme Corp",        // string — optional
  "domain": "acme.com",                    // string — optional (company domain)
  "id": "6081c...",                         // string — Apollo person ID (from search)
  "linkedin_url": "https://linkedin.com/in/johndoe", // string — optional
  "reveal_personal_emails": true,          // boolean — default false
  "reveal_phone_number": true,             // boolean — default false
  "run_waterfall_email": false,            // boolean — async waterfall enrichment
  "run_waterfall_phone": false,            // boolean — async waterfall enrichment
  "webhook_url": "https://your.webhook/..."// string — for async waterfall results
}
```

- Provide as many identifying fields as possible for best match accuracy.
- At minimum, provide `email` OR (`first_name` + `last_name` + (`domain` OR `organization_name`)).
- If only general info is provided, may return 200 with no match.

#### Response Body

```json
{
  "person": {
    "id": "6081c...",
    "first_name": "John",
    "last_name": "Doe",
    "name": "John Doe",
    "linkedin_url": "https://www.linkedin.com/in/johndoe",
    "title": "CEO",
    "headline": "CEO at Acme Corp",
    "photo_url": "https://...",
    "email": "john@acme.com",
    "email_status": "verified",            // "verified" | "guessed" | "unavailable" | null
    "personal_emails": ["john.doe@gmail.com"],
    "phones": [
      {
        "raw_number": "+14155551234",
        "sanitized_number": "+14155551234",
        "type": "mobile",
        "position": 0
      }
    ],
    "city": "San Francisco",
    "state": "California",
    "country": "United States",
    "organization_id": "5f5e2...",
    "organization": {
      "id": "5f5e2...",
      "name": "Acme Corp",
      "website_url": "https://acme.com",
      "primary_domain": "acme.com",
      "industry": "Information Technology",
      "estimated_num_employees": 150,
      "founded_year": 2015,
      "linkedin_url": "https://www.linkedin.com/company/acme",
      "phone": "+14155550000",
      "raw_address": "123 Main St, San Francisco, CA",
      "city": "San Francisco",
      "state": "California",
      "country": "United States"
    },
    "employment_history": [
      {
        "id": "...",
        "organization_name": "Acme Corp",
        "title": "CEO",
        "start_date": "2020-01-01",
        "end_date": null,
        "current": true
      }
    ],
    "departments": ["c_suite"],
    "seniority": "c_suite"
  },
  "status": "enrichment_complete"
}
```

#### "Nothing found" response
Returns `200` with `"person": null` or `"person": {}` with empty fields. No credits consumed if no match.

#### Waterfall Enrichment (Async)
When `run_waterfall_email: true` or `run_waterfall_phone: true`:
- Synchronous response returns demographic/firmographic data immediately.
- Emails/phones from waterfall sources are delivered **asynchronously** to the `webhook_url`.
- Webhook payload contains the enriched person data.

---

### Endpoint: Bulk People Enrichment

```
POST /api/v1/people/bulk_match
```

**Purpose:** Enrich up to **10 people** in a single API call.

**Credits:** 1 export credit per person enriched (same as single).

**Rate limit:** 50% of per-minute limit of single endpoint.

#### Request Body

```json
{
  "details": [
    {
      "first_name": "John",
      "last_name": "Doe",
      "domain": "acme.com"
    },
    {
      "id": "6081c..."
    },
    {
      "email": "jane@example.com"
    }
  ],
  "reveal_personal_emails": true,   // boolean — applies to ALL entries
  "reveal_phone_number": true       // boolean — applies to ALL entries
}
```

- `details[]`: Array of up to **10** person objects. Each object accepts the same fields as single `people/match`.
- Global params (`reveal_personal_emails`, etc.) apply to all entries.

#### Response Body

```json
{
  "status": "success",
  "matches": [
    {
      "person": { /* same schema as single endpoint */ },
      "status": "enrichment_complete"
    },
    {
      "person": null,
      "status": "no_match"
    }
  ]
}
```

---

### Endpoint: Organization Enrichment

```
GET /api/v1/organizations/enrich?domain=acme.com
```

**Purpose:** Get company details from a domain.

**Credits:** 1 export credit.

#### Request Parameters (Query String)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | Yes | Company domain (e.g., `acme.com`) |

#### Response Body

```json
{
  "organization": {
    "id": "5f5e2...",
    "name": "Acme Corp",
    "website_url": "https://acme.com",
    "primary_domain": "acme.com",
    "industry": "Information Technology",
    "raw_address": "123 Main St, San Francisco, CA 94105",
    "city": "San Francisco",
    "state": "California",
    "country": "United States",
    "phone": "+14155550000",
    "linkedin_url": "https://www.linkedin.com/company/acme",
    "logo_url": "https://...",
    "estimated_num_employees": 150,
    "founded_year": 2015,
    "short_description": "Acme Corp builds widgets...",
    "annual_revenue": 15000000,
    "annual_revenue_printed": "$15M",
    "total_funding": 5000000,
    "total_funding_printed": "$5M",
    "latest_funding_round_date": "2023-06-15",
    "latest_funding_stage": "Series A",
    "technologies": ["Python", "AWS", "React"],
    "keywords": ["SaaS", "Enterprise Software"],
    "seo_description": "...",
    "suborganizations": [],
    "num_suborganizations": 0,
    "publicly_traded_symbol": null,
    "publicly_traded_exchange": null
  }
}
```

#### "Nothing found" response
Returns `200` with `"organization": null`.

---

### Gotchas & Undocumented Behaviors (Apollo)

1. **People Search does NOT return emails** — you MUST follow up with enrichment.
2. **Master API key** required for search endpoints. Regular API keys get `403`.
3. **50,000 record cap** on search — use filters to stay under.
4. **Credits expire monthly** — no rollover.
5. **Bulk endpoint has 50% per-minute rate limit** of single.
6. **Waterfall is async-only** — must use webhook_url. No polling mechanism.
7. **Parameters can be passed as query string OR request body** — use body (raw JSON, not form-data).

---

## 2. Findymail

### Base URL
```
https://app.findymail.com/api
```

### Authentication
```
Headers:
  Authorization: Bearer <YOUR_API_KEY>
  Content-Type: application/json
  Accept: application/json
```
- API key from https://app.findymail.com/settings/api

### Rate Limits
- **300 concurrent requests** (no per-minute/hourly/daily cap documented).
- No hard daily limit — practically unlimited if you have credits.

### Credits

| Action | Credits |
|--------|---------|
| Email found (search/name, search/linkedin, search/domain) | 1 credit |
| Email NOT found | 0 credits (no charge) |
| Phone found | 10 credits |
| Phone NOT found | 0 credits |
| Email verification | 1 credit |
| Reverse email lookup (without profile) | 1 credit |
| Reverse email lookup (with profile enrichment) | 2 credits |
| Company info | 1 credit |
| Employee search | 1 credit per contact found |

### Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success (email found or verification complete) |
| 200 + empty/null email | Email not found (no error, just no result) |
| 401 | Unauthorized — invalid/missing Bearer token |
| 404 | Endpoint not found |
| 422 | Validation error — missing required fields |
| 429 | Rate limit exceeded (unlikely given 300 concurrent limit, but possible) |

---

### Endpoint: Search by Name (Email Finder)

```
POST /api/search/name
```

**Purpose:** Find a verified email from a person's name and company domain.

**Credits:** 1 credit on success, 0 on failure.

#### Request Body

```json
{
  "name": "John Doe",              // string — REQUIRED — full name
  "domain": "acme.com"             // string — REQUIRED — company domain
}
```

Note: Uses `name` (full name as single string), NOT separate `first_name`/`last_name`.

#### Response Body (Success)

```json
{
  "email": "john.doe@acme.com",
  "domain": "acme.com",
  "name": "John Doe",
  "company": "Acme Corp"
}
```

#### Response Body (Not Found)

```json
{
  "email": null,
  "domain": "acme.com",
  "name": "John Doe"
}
```

Returns `200` with `"email": null`. No credit consumed.

---

### Endpoint: Search by LinkedIn URL

```
POST /api/search/linkedin
```

**Purpose:** Find a verified email from a LinkedIn profile URL.

**Credits:** 1 credit on success, 0 on failure.

#### Request Body

```json
{
  "linkedin_url": "https://www.linkedin.com/in/johndoe"  // string — REQUIRED
}
```

#### Response Body

Same structure as search/name response.

---

### Endpoint: Search by Domain

```
POST /api/search/domain
```

**Purpose:** Find all emails associated with a domain.

**Credits:** 1 credit per email found.

#### Request Body

```json
{
  "domain": "acme.com"            // string — REQUIRED
}
```

#### Response Body

```json
{
  "domain": "acme.com",
  "contacts": [
    {
      "email": "john.doe@acme.com",
      "name": "John Doe",
      "position": "CEO"
    },
    {
      "email": "jane.smith@acme.com",
      "name": "Jane Smith",
      "position": "CTO"
    }
  ]
}
```

---

### Endpoint: Verify Email

```
POST /api/verify
```

**Purpose:** Verify deliverability of an email address.

**Credits:** 1 credit.

#### Request Body

```json
{
  "email": "john.doe@acme.com"    // string — REQUIRED
}
```

#### Response Body

```json
{
  "email": "john.doe@acme.com",
  "status": "valid",              // "valid" | "invalid" | "catch_all" | "unknown"
  "provider": "Google"            // email provider name
}
```

---

### Endpoint: Reverse Email Search

```
POST /api/search/reverse-email
```

**Purpose:** Get LinkedIn profile data from an email address.

**Credits:** 1 credit (without profile), 2 credits (with profile enrichment).

#### Request Body

```json
{
  "email": "john.doe@acme.com",   // string — REQUIRED
  "with_profile": true             // boolean — optional, default false
}
```

#### Response Body (with_profile: true)

```json
{
  "email": "john.doe@acme.com",
  "fullName": "John Doe",
  "headline": "CEO at Acme Corp",
  "jobTitle": "CEO",
  "companyName": "Acme Corp",
  "linkedin_url": "https://www.linkedin.com/in/johndoe"
}
```

---

### Endpoint: Phone Finder

```
POST /api/search/phone
```

**Purpose:** Find phone number from LinkedIn profile.

**Credits:** 10 credits on success, 0 on failure. GDPR compliant (excludes EU).

#### Request Body

```json
{
  "linkedin_url": "https://www.linkedin.com/in/johndoe"  // string — REQUIRED
}
```

---

### Endpoint: Check Credits

```
GET /api/credits
```

**Purpose:** Check remaining credit balance.

**Credits:** Free.

#### Response Body

```json
{
  "credits": 4523
}
```

---

### Gotchas & Undocumented Behaviors (Findymail)

1. **No batch/bulk endpoint** — all calls are single-record. For bulk, parallelize (up to 300 concurrent).
2. **Synchronous API** — response returns immediately with the result. No polling needed.
3. **Bounce guarantee** — <5% bounce rate. If exceeded, contact support for credit refund.
4. **`name` field is FULL NAME** — not separate first/last. Pass "John Doe" not {"first_name": "John", "last_name": "Doe"}.
5. **Only charged on success** — zero cost for misses. This is critical for waterfall economics.
6. **Catch-all handling** — Findymail validates catch-all emails that other tools mark as "unknown".
7. **Webhook support mentioned** in marketing but the core search endpoints are synchronous. Webhooks may be for integrations/automation platforms only.

---

## 3. Icypeas

### Base URL
```
https://app.icypeas.com/api
```

### Authentication
```
Headers:
  Authorization: <YOUR_API_KEY>
  Content-Type: application/json
```
- API key from https://app.icypeas.com/api-key
- Note: NO "Bearer" prefix — just the raw API key in the Authorization header.

### Rate Limits

| Route | Limit |
|-------|-------|
| Single email search (`/email-search`) | 10 requests/second |
| Sync email search (`/sync/email-search`) | 10 requests/second |
| Bulk search (`/bulk`) | 1 request/second |
| Result retrieval (`/bulk-single-searchs/read`) | Rate limited (exact number undisclosed) |
| All other routes | Rate limited |

- Exceeding limits returns `429`.

### Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success (check `status` field — may be "NOT_FOUND") |
| 401 | Authentication failed — invalid API key |
| 429 | Rate limit exceeded |

### Credits
- 1 credit per verified email found.
- No charge when email is not found.
- Cheapest per-credit cost of all 4 providers.

---

### Endpoint: Synchronous Email Search (RECOMMENDED)

```
POST /api/sync/email-search
```

**Purpose:** Find an email address synchronously — response includes the result immediately.

**Credits:** 1 credit per email found.

#### Request Body

```json
{
  "firstname": "John",            // string — at least one of firstname/lastname required
  "lastname": "Doe",              // string — at least one of firstname/lastname required
  "domainOrCompany": "acme.com"   // string — REQUIRED — domain or company name
}
```

- `firstname` and `lastname`: At least ONE is required. The other can be empty string `""`.
- `domainOrCompany`: Required. Can be a domain (e.g., "acme.com") or company name (e.g., "Acme Corp").

#### Response Body (Success — Email Found)

```json
{
  "success": true,
  "status": "FOUND",
  "emails": [
    {
      "certainty": "ULTRA_SURE",       // "ULTRA_SURE" | "SURE" | "PROBABLE" | other
      "email": "john.doe@acme.com",
      "mxProvider": "Google",          // "Google" | "Microsoft" | "Other" | etc.
      "mxRecords": ["google.com"]
    }
  ],
  "searchId": "4f3Ai5YBhGZBKOhxEm3s"
}
```

#### Response Body (Not Found)

```json
{
  "success": true,
  "status": "NOT_FOUND",
  "emails": [],
  "searchId": "..."
}
```

Note: Returns `200` with `"status": "NOT_FOUND"` and empty `emails` array. No credit consumed.

#### Certainty Levels
- `ULTRA_SURE` — verified, highest confidence
- `SURE` — high confidence
- `PROBABLE` — likely correct but not verified

---

### Endpoint: Asynchronous Email Search

```
POST /api/email-search
```

**Purpose:** Start an async email search. Returns an ID; poll for results.

#### Request Body

```json
{
  "firstname": "John",
  "lastname": "Doe",
  "domainOrCompany": "acme.com",
  "webhookUrl": "https://your.server/webhook",  // string — optional
  "customId": "your-tracking-id"                  // string — optional
}
```

#### Response Body (Immediate)

```json
{
  "success": true,
  "item": {
    "status": "NONE",            // "NONE" = still processing
    "_id": "p_gfS5EB4liCGm90KDFC"
  }
}
```

Then retrieve results via `/api/bulk-single-searchs/read` (see below).

---

### Endpoint: Bulk Search (up to 5,000 rows)

```
POST /api/bulk
```

**Purpose:** Start a bulk search for up to 5,000 email addresses. ASYNC — results retrieved via polling or webhook.

**Rate limit:** 1 request/second.

#### Request Body

```json
{
  "name": "My batch search 2024-01-15",    // string — name for this bulk search
  "task": "email-search",                    // string — REQUIRED: "email-search" | "domain-search" | "email-verification"
  "data": [                                  // array — REQUIRED: max 5,000 rows
    ["John", "Doe", "acme.com"],            // [firstname, lastname, domainOrCompany]
    ["Jane", "", "example.com"],            // lastname can be empty
    ["", "Smith", "Acme Corp"]              // firstname can be empty
  ],
  "webhookUrl": "https://your.server/row-webhook",           // string — optional — called per ROW
  "webhookUrlBulk": "https://your.server/bulk-webhook",       // string — optional — called when ALL rows done
  "includeResultsInWebhook": false,                            // boolean — optional — include full results in bulk webhook
  "externalIds": ["id1", "id2", "id3"]                        // string[] — optional — your tracking IDs, must match data length
}
```

**Data format by task type:**
- `email-search`: `[firstname, lastname, domainOrCompany]` — 3 items per row
- `email-verification`: `[email]` — 1 item per row
- `domain-search`: `[domain]` — 1 item per row

**Limits:** Max **5,000 items** per bulk search.

#### Response Body

```json
{
  "success": true,
  "item": {
    "_id": "bulk_abc123...",       // bulk search ID — use with result retrieval
    "status": "PENDING"
  }
}
```

#### Webhook Behavior

**Per-row webhook** (`webhookUrl`): Called each time a single row finishes processing. Payload contains that row's result.

**Bulk-complete webhook** (`webhookUrlBulk`): Called when ALL rows are done. Contains statistics only (not results), UNLESS `includeResultsInWebhook: true`.

**Warning:** If `includeResultsInWebhook: true` and >1,000 items, ensure your webhook server can handle large POST payloads.

---

### Endpoint: Retrieve Search Results

```
POST /api/bulk-single-searchs/read
```

**Purpose:** Retrieve results from single or bulk searches. This is the polling endpoint.

#### Request Body — Single Search Result

```json
{
  "id": "p_gfS5EB4liCGm90KDFC"    // string — the _id from the search response
}
```

#### Request Body — Bulk Search Results

```json
{
  "file": "bulk_abc123...",         // string — the bulk _id
  "mode": "bulk",                   // string — REQUIRED for bulk results
  "limit": 100,                     // int — max 100 (default: 10)
  "next": true                      // boolean — true = next page, false = previous page
}
```

#### Response Body

```json
{
  "success": true,
  "items": [
    {
      "_id": "...",
      "status": "DEBITED",          // "DEBITED" = found + charged | "NOT_FOUND" | "NONE" (still processing)
      "firstname": "John",
      "lastname": "Doe",
      "emails": [
        {
          "certainty": "ULTRA_SURE",
          "email": "john.doe@acme.com",
          "mxProvider": "Google",
          "mxRecords": ["google.com"]
        }
      ]
    }
  ]
}
```

#### Status Values
- `"NONE"` — Still processing. Poll again after a few seconds.
- `"DEBITED"` — Email found, credit consumed.
- `"NOT_FOUND"` — No email found, no credit consumed.
- `"ERROR"` — Something went wrong.

#### Pagination
- Max **100 results per request**.
- Use `"next": true` / `"next": false` to paginate.
- Results are sorted by creation date.

---

### Endpoint: Email Verification

```
POST /api/email-verification
```

or synchronous:

```
POST /api/sync/email-verification
```

#### Request Body

```json
{
  "email": "john.doe@acme.com"    // string — REQUIRED
}
```

---

### Endpoint: Domain Scan

```
POST /api/domain-scan
```

**Purpose:** Find all role-based email addresses for a domain (e.g., info@, contact@, support@).

#### Request Body

```json
{
  "domainOrCompany": "acme.com"   // string — REQUIRED
}
```

---

### Gotchas & Undocumented Behaviors (Icypeas)

1. **Two modes: sync and async** — Use `/sync/email-search` for real-time waterfall. Use `/email-search` (async) + polling for background jobs.
2. **Bulk is ALWAYS async** — You submit, then poll or use webhooks. No sync bulk.
3. **Result retrieval endpoint is shared** — Both single async and bulk results use `/bulk-single-searchs/read`.
4. **Max 100 results per read request** — For a 5,000-item bulk, you need 50 paginated reads.
5. **`domainOrCompany` accepts both domains AND company names** — Icypeas resolves company names to domains internally.
6. **`customId` uniqueness is YOUR responsibility** — Icypeas does not enforce uniqueness.
7. **No "Bearer" prefix** — Just `Authorization: YOUR_API_KEY`.
8. **Field names are camelCase** — `firstname`, `lastname`, `domainOrCompany` (note: lowercase first letters, camelCase for compound).

---

## 4. ContactOut

### Base URL
```
https://api.contactout.com
```

### Authentication
```
Headers:
  Content-Type: application/json
  Accept: application/json
  token: <YOUR_API_TOKEN>
```
- Note: Uses `token` header (NOT `Authorization`, NOT `Bearer`).
- API key from https://contactout.com/dashboard/api
- Requires Team/API plan for full API access (custom pricing).

### Rate Limits
- Plan-dependent, not publicly documented.
- Team/API plan rate limits are communicated during sales process.
- Standard plans have implicit fair-use caps.

### Credits

| Action | Credits |
|--------|---------|
| Profile found (no contact info requested) | 1 search credit |
| Email found | 1 email credit |
| Phone found | 1 phone credit |
| No match / no data | 0 credits |

**Monthly caps (fair use policy):**
- Email Plan: 2,000 email credits/month
- Email + Phone Plan: 2,000 email + 1,000 phone credits/month
- Team/API: Custom (negotiated)
- Credits do NOT roll over.

### Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request — malformed parameters |
| 401 | Unauthorized — invalid/missing token |
| 404 | Profile not found |
| 429 | Rate limit exceeded |

---

### Endpoint: Single LinkedIn Profile Lookup

```
GET /v1/people/linkedin
```

**Purpose:** Get contact details for a single LinkedIn profile.

**Credits:** 1 search credit + 1 email credit (if found) + 1 phone credit (if found and requested).

#### Request Parameters (Query String)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile` | string | Yes | LinkedIn public profile URL |
| `include_phone` | boolean | No | Include phone numbers (default: false) |
| `email_type` | string | No | `"work"` to get real-time verified work emails (slower) |

#### Example Request
```
GET /v1/people/linkedin?profile=https://www.linkedin.com/in/johndoe&include_phone=true&email_type=work
```

#### Response Body

```json
{
  "status_code": 200,
  "profile": {
    "url": "https://www.linkedin.com/in/johndoe",
    "email": ["john.doe@acme.com", "john.doe@gmail.com"],
    "work_email": ["john.doe@acme.com"],
    "work_email_status": {
      "john.doe@acme.com": "Verified"      // "Verified" | "Unverified"
    },
    "personal_email": ["john.doe@gmail.com"],
    "phone": ["+14155551234"],
    "github": ["johndoe"]
  }
}
```

#### "Nothing found" response

```json
{
  "status_code": 404,
  "message": "Profile not found"
}
```

Or `200` with empty arrays:
```json
{
  "status_code": 200,
  "profile": {
    "url": "https://www.linkedin.com/in/johndoe",
    "email": [],
    "work_email": [],
    "personal_email": [],
    "phone": [],
    "github": []
  }
}
```

---

### Endpoint: Batch LinkedIn Lookup (v2 — Async)

```
POST /v2/people/linkedin/batch
```

**Purpose:** Get contact details for up to **30 LinkedIn profiles** in a single async call.

**Credits:** Same as single — 1 email credit per profile with email, 1 phone credit per profile with phone.

#### Request Body

```json
{
  "profiles": [                                    // string[] — REQUIRED — max 30 URLs
    "https://www.linkedin.com/in/johndoe",
    "https://www.linkedin.com/in/janesmith",
    "https://www.linkedin.com/in/bobwilson"
  ],
  "include_phone": true,                           // boolean — optional (default: false)
  "callback_url": "https://your.server/webhook"    // string — optional — receives results when done
}
```

**Limits:** Max **30 profiles** per request.

#### Response Body (Immediate)

```json
{
  "status": "QUEUED",
  "job_id": "96d1c156-fc66-46ef-b053-be6dbb45cf1f"
}
```

#### Polling for Results

```
GET /v2/people/linkedin/batch/{job_uuid}
```

Headers: Same `token` header.

#### Polling Response (In Progress)

```json
{
  "status": "PROCESSING",
  "job_id": "96d1c156-..."
}
```

#### Polling Response (Complete)

```json
{
  "status": "DONE",
  "job_id": "96d1c156-...",
  "results": [
    {
      "url": "https://www.linkedin.com/in/johndoe",
      "email": ["john.doe@acme.com"],
      "work_email": ["john.doe@acme.com"],
      "work_email_status": { "john.doe@acme.com": "Verified" },
      "personal_email": [],
      "phone": ["+14155551234"],
      "github": []
    },
    {
      "url": "https://www.linkedin.com/in/janesmith",
      "email": [],
      "work_email": [],
      "personal_email": [],
      "phone": [],
      "github": []
    }
  ]
}
```

#### Webhook Callback
If `callback_url` is provided, ContactOut sends a POST request to that URL with the complete results when the job finishes. Payload is same as the polling "Complete" response above.

---

### Endpoint: People Enrichment

```
POST /v1/people/enrich
```

**Purpose:** Enrich a person from multiple data points (flexible — doesn't require LinkedIn URL).

**Credits:** 1 search credit + 1 email/phone credit per found item.

#### Request Body

```json
{
  "first_name": "John",                           // string — optional
  "last_name": "Doe",                             // string — optional
  "email": "john.doe@acme.com",                   // string — optional
  "phone": "+14155551234",                         // string — optional
  "linkedin_url": "https://linkedin.com/in/...",  // string — optional
  "company_name": "Acme Corp",                    // string — optional
  "company_domain": "acme.com",                   // string — optional
  "title": "CEO",                                  // string — optional
  "location": "San Francisco, CA",                 // string — optional
  "include": ["personal_email", "work_email", "phone"],  // string[] — REQUIRED to get contact info
  "output_fields": ["title", "company", "experience"]    // string[] — optional — limit response fields
}
```

- At least one identifying parameter is required.
- `include` parameter is CRITICAL — without it, you only get profile data, NO contact info.
- `include` values: `"personal_email"`, `"work_email"`, `"phone"`

#### Response Body

```json
{
  "profile": {
    "full_name": "John Doe",
    "li_vanity": "johndoe",
    "title": "CEO",
    "headline": "CEO at Acme Corp",
    "company": {
      "name": "Acme Corp",
      "website": "https://acme.com",
      "domain": "acme.com",
      "email_domain": "acme.com",
      "headquarter": "San Francisco, CA",
      "size": "51-200",
      "revenue": "$10M-$50M",
      "industry": "Information Technology"
    },
    "location": "San Francisco, CA",
    "industry": "Information Technology",
    "experience": [
      "CEO at Acme Corp (2020-Present)",
      "VP Engineering at Previous Corp (2017-2020)"
    ],
    "education": [
      "BS Computer Science, Stanford University"
    ],
    "skills": ["Leadership", "Strategy", "Engineering Management"],
    "contact_availability": {
      "personal_email": true,
      "work_email": true,
      "phone": true
    },
    "contact_info": {
      "emails": ["john.doe@acme.com", "johndoe@gmail.com"],
      "personal_emails": ["johndoe@gmail.com"],
      "work_emails": ["john.doe@acme.com"],
      "work_email_status": { "john.doe@acme.com": "Verified" },
      "phones": ["+14155551234"]
    }
  }
}
```

---

### Endpoint: People Search

```
GET /v1/people/search
```

**Purpose:** Search for people across 20+ data points.

**Credits:** 1 search credit per profile returned. 1 email/phone credit if `reveal_info=true`.

#### Request Parameters (Query String)

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Person's name |
| `title` | string | Job title |
| `company_name` | string | Company name |
| `company_domain` | string | Company domain |
| `location` | string | Location |
| `industry` | string | Industry |
| `page` | int | Page number |
| `page_size` | int | Results per page |
| `reveal_info` | boolean | Include contact info (costs extra credits) |
| `data_types` | string | Filter by available data types |

#### Response Body

```json
{
  "metadata": {
    "page": 1,
    "page_size": 10,
    "total_results": 150
  },
  "profiles": {
    "https://linkedin.com/in/johndoe": {
      "full_name": "John Doe",
      "title": "CEO",
      "headline": "CEO at Acme Corp",
      "company": { /* company object */ },
      "contact_availability": {
        "personal_email": true,
        "work_email": true,
        "phone": false
      },
      "contact_info": { /* if reveal_info=true */ }
    }
  }
}
```

---

### Endpoint: Decision Makers

```
GET /v1/company/decision-makers
```

**Purpose:** Get key decision makers at a company.

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `linkedin_url` | string | At least one of these 3 | Company LinkedIn URL |
| `domain` | string | At least one of these 3 | Company domain |
| `name` | string | At least one of these 3 | Company name |

---

### Endpoint: Company Enrichment

```
GET /v1/domain/enrich
```

**Purpose:** Get company profile from domain.

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `domain` | string | Yes | Company domain |

---

### Endpoint: Email Verification

```
GET /v1/email/verify?email=john@acme.com
```

**Purpose:** Verify single email deliverability.

```
POST /v1/email/verify/batch
```

**Purpose:** Verify up to **100 emails** in bulk (async).

#### Batch Request Body

```json
{
  "emails": ["john@acme.com", "jane@acme.com"],
  "callback_url": "https://your.server/webhook"
}
```

Returns a `job_id` for polling. Status: `"QUEUED"` -> `"DONE"`.

---

### Gotchas & Undocumented Behaviors (ContactOut)

1. **`include` parameter is REQUIRED for contact info** — Without it, you only get profile data. This is the most common mistake.
2. **`token` header (not `Authorization`)** — Unique auth format. Easy to miss.
3. **Does NOT support Sales Navigator or Recruiter LinkedIn URLs** — Only public LinkedIn profile URLs (linkedin.com/in/...).
4. **`email_type=work` slows response** — Real-time work email verification adds latency.
5. **v2 batch is async, v1 single is sync** — Different patterns for single vs batch.
6. **Fair use policy caps "unlimited" plans** — 2,000 emails/month and 1,000 phones/month despite "unlimited" marketing.
7. **Profiles keyed by LinkedIn URL in search response** — Not an array; it's an object with URLs as keys.
8. **`work_email_status` is an object, not a string** — Maps email address to verification status.
9. **Batch limited to 30 profiles** — Much smaller than Icypeas' 5,000.
10. **Webhook is optional** — You can poll OR use callback_url. Both work for v2 batch.

---

## Cross-Provider Comparison Matrix

| Feature | Apollo | Findymail | Icypeas | ContactOut |
|---------|--------|-----------|---------|------------|
| **Auth header** | `X-Api-Key` | `Authorization: Bearer` | `Authorization` (no prefix) | `token` |
| **Base URL** | `api.apollo.io/api/v1` | `app.findymail.com/api` | `app.icypeas.com/api` | `api.contactout.com` |
| **Single email lookup** | Sync | Sync | Sync (`/sync/`) or Async | Sync |
| **Batch size** | 10 | None (parallelize) | 5,000 | 30 |
| **Batch mode** | Sync | N/A | Async (webhook + polling) | Async (webhook + polling) |
| **Credit on miss** | Yes (enrichment) | No | No | No |
| **Free search** | Yes (no emails) | No | No | No |
| **Webhook support** | Waterfall only | No* | Yes (per-row + bulk-complete) | Yes (callback_url) |
| **Rate limit** | 50-200/min (plan) | 300 concurrent | 10/sec single, 1/sec bulk | Plan-dependent |
| **Best for** | Initial prospecting | High-accuracy email | Cheap bulk email | LinkedIn-based lookup |

---

## Implementation Notes for Waterfall

### Recommended Call Pattern

```
1. Apollo Search (FREE) -> get person IDs, names, titles, LinkedIn URLs, domains
2. Apollo Enrich (if has_email=true) -> get email directly
   -- if no email --
3. Icypeas Sync Search -> cheapest per-credit
   -- if no email --
4. Findymail Search by Name -> highest accuracy/deliverability
   -- if no email but have LinkedIn URL --
5. ContactOut LinkedIn Lookup -> LinkedIn-based extraction
```

### Key Decision Points

- **Apollo search is free** — always start here to get identifying data.
- **Apollo enrichment charges even on miss** — only call if `has_email: true` from search.
- **Findymail and Icypeas only charge on success** — safe to call speculatively.
- **ContactOut requires LinkedIn URL** — only usable when you have one from Apollo or elsewhere.

### Caching Strategy

All results should be cached by a composite key:
```
cache_key = f"{provider}:{first_name}:{last_name}:{domain}"
```
With a configurable TTL (default 30 days).
