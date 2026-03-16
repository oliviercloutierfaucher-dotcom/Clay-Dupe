# Free B2B Enrichment API Providers — Research Report

**Date**: 2026-03-08
**Purpose**: Evaluate free tiers, endpoints, data fields, rate limits, and gotchas for B2B enrichment APIs

---

## Table of Contents

1. [Hunter.io](#1-hunterio)
2. [Snov.io](#2-snovio)
3. [PeopleDataLabs](#3-peopledatalabs)
4. [RocketReach](#4-rocketreach)
5. [Prospeo](#5-prospeo)
6. [Dropcontact](#6-dropcontact)
7. [Apollo.io](#7-apolloio-bonus)
8. [Tomba.io](#8-tombaio-bonus)
9. [Proxycurl](#9-proxycurl-bonus)
10. [LinkedIn URL Enrichment](#10-linkedin-url-enrichment)
11. [Comparison Matrix](#11-comparison-matrix)

---

## 1. Hunter.io

**API Docs**: https://hunter.io/api-documentation/v2

### Free Tier
- **25 searches/month** (Domain Search)
- **50 verifications/month** (Email Verifier)
- 1 connected email account
- API access included on free tier

### Key Endpoints

| Endpoint | Description | Credit Cost |
|----------|-------------|-------------|
| `GET /domain-search` | Find emails associated with a domain | 1 credit per 1-10 emails returned |
| `GET /email-finder` | Find email for a person (name + domain) | 1 credit |
| `GET /email-verifier` | Verify a single email address | 0.5 credit |
| `GET /email-count` | Count emails for a domain (free) | 0 credits |
| `GET /account` | Account info (free) | 0 credits |

### Data Fields Returned

**Email Finder response**:
- `email`, `first_name`, `last_name`
- `score` (confidence 0-100)
- `domain`, `position` (job title)
- `twitter`, `linkedin_url`, `phone_number`
- `company`
- `sources[]` — array of web sources where email was found
- `verification.status` — verified/unverified
- `type` — "personal" or "generic" (role-based like info@)

**Domain Search response**:
- Organization data (name, domain)
- Array of emails with person data (name, position, department, type, confidence, sources)
- Up to 100 emails per request

### Rate Limits
- Email Finder & Domain Search: **15 req/sec**, **500 req/min**
- Email Verifier: **10 req/sec**, **300 req/min**
- Discover API: **5 req/sec**, **50 req/min**

### Python Library
- **PyHunter** — community wrapper (`pip install pyhunter`)
- GitHub: https://github.com/VonStruddle/PyHunter
- Supports all v2 endpoints, `raw=True` for full response

### Authentication
- **API Key** — passed as `api_key` query parameter

### Gotchas
- Free tier is very limited (25 searches)
- Domain Search credits scale: 1 credit = up to 10 results
- No bulk endpoints on free tier
- Phone numbers are sparse — not Hunter's strength
- Email type classification ("personal" vs "generic") is useful for filtering

---

## 2. Snov.io

**API Docs**: https://snov.io/api

### Free Tier
- **50-150 credits/month** (sources vary; latest info says 150 monthly credits)
- 100 unique recipients for email campaigns
- 1 mailbox warm-up slot
- **API access may require demo booking on free plan** (significant limitation)

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `/v1/get-domain-emails-with-info` | Domain Search — find emails for a domain |
| `/v1/get-emails-from-names` | Email Finder — find email from name + domain |
| `/v1/get-emails-verification-status` | Check email verification status |
| `/v1/add-prospect-to-list` | Add prospect to a list |
| `/v1/prospect-list` | Manage prospect lists |
| `/v1/get-prospect-by-email` | Get prospect profile by email |

### Data Fields Returned
- Email address and verification status (valid/green, unknown/yellow)
- First name, last name
- Company name, domain
- Job title, industry
- Social profiles
- Custom fields (user-defined)

### Rate Limits
- **60 requests/minute** across all endpoints

### Python Library
- **python-snovio** — community wrapper
- GitHub: https://github.com/miguelcdpmarques/python-snovio
- Initialize with user_id + secret, or directly with access_token

### Authentication
- **OAuth2-style**: First call `/v1/oauth/access_token` with client_id and client_secret
- Returns `access_token` valid for **3600 seconds** (1 hour)
- Use as Bearer token in subsequent requests
- Must refresh token every hour

### Gotchas
- **API access may not be available on free plan** without contacting sales
- Token expires every hour — need refresh logic
- Async pattern: some endpoints return `task_hash`, need second call to get results
- Bulk operations may be restricted to premium plans
- Credit system is confusing — different actions cost different credits

---

## 3. PeopleDataLabs

**API Docs**: https://docs.peopledatalabs.com

### Free Tier
- **100 person/company lookups/month** (production)
- **25 IP lookups/month**
- **Sandbox API**: Unlimited synthetic data for testing (5 calls/min)
- No credit card required

### Key Endpoints

| Endpoint | Description | Free Rate Limit |
|----------|-------------|-----------------|
| `GET /v5/person/enrich` | Person enrichment | 100/min |
| `GET /v5/company/enrich` | Company enrichment | 10/min |
| `POST /v5/person/bulk` | Bulk person enrichment | Limited |
| `GET /v5/person/search` | Person search (SQL-like) | Limited |
| `GET /v5/person/identify` | Identify from partial data | Limited |
| `GET /v5/skill/enrich` | Skill enrichment | 100/min |
| Sandbox variants | Same endpoints, synthetic data | 5/min |

### Data Fields Returned

**Person Enrichment** (nearly 3 billion profiles):
- `full_name`, `first_name`, `last_name`, `gender`
- `birth_date`, `birth_year`
- `emails[]` — array of email addresses
- `phone_numbers[]`
- `linkedin_url`, `facebook_url`, `twitter_url`, `github_url`
- `job_title`, `job_company_name`, `job_company_website`
- `job_company_industry`, `job_company_size`
- `location_name`, `location_country`, `location_region`, `location_city`
- `skills[]`, `interests[]`
- `education[]` — schools, degrees, fields of study
- `experience[]` — full work history
- `certifications[]`

**Company Enrichment**:
- `name`, `display_name`, `size`, `industry`
- `website`, `linkedin_url`
- `location` (HQ address)
- `founded`, `type` (public/private)
- `employee_count`, `tags[]`
- `naics[]`, `sic[]` (industry codes)

### Rate Limits
- Free: Person 100/min, Company 10/min, Sandbox 5/min
- Paid: 1,000-5,000/min depending on endpoint

### Python Library
- **Official SDK**: `pip install peopledatalabs`
- GitHub: https://github.com/peopledatalabs/peopledatalabs-python
- Well-maintained, supports all endpoints
- Usage: `PDLPY(api_key="...").person.enrichment(name="...", profile="linkedin.com/...")`

### Authentication
- **API Key** — passed as `X-Api-Key` header

### Gotchas
- **100 lookups/month is very generous** for testing but tight for production
- Sandbox returns synthetic/fake data — good for dev, useless for real enrichment
- Company enrichment rate limit is only 10/min on free (very restrictive)
- Data is US-heavy; international coverage varies
- No email verification built-in — emails may bounce
- **Best free tier for data richness** — most fields per record

---

## 4. RocketReach

**API Docs**: https://rocketreach.co/api/v1/docs/

### Free Tier
- **5 free lookups/month** — extremely limited
- No credit card required
- **API access only on Ultimate plan ($209/month)** or Enterprise

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v2/api/search` | Search for people |
| `GET /v2/api/lookupProfile` | Lookup person profile |
| `GET /v2/api/lookupCompany` | Lookup company |
| `POST /v2/api/bulkLookup` | Bulk lookups |

### Data Fields Returned
- Personal and professional emails
- Mobile and direct phone numbers
- Job title, company, location
- Social profiles (LinkedIn, Twitter, etc.)
- Technographics (company tech stack)

### Rate Limits
- Rate limits apply; 429 errors returned when exceeded
- Check `Retry-After` header for wait time
- Specific limits not publicly documented

### Python Library
- **Official SDK**: `pip install rocketreach`
- GitHub: https://github.com/rocketreach/rocketreach_python
- PyPI: https://pypi.org/project/rocketreach/

### Authentication
- **API Key** — passed as `Api-Key` header

### Gotchas
- **Essentially no free tier** — 5 lookups is just a trial
- **API requires Ultimate plan at $209/month** — most expensive option
- Overage costs: $0.30-$0.45 per additional lookup
- Not viable for a free/low-cost enrichment pipeline
- Best data quality for phone numbers, but premium pricing

---

## 5. Prospeo

**API Docs**: https://prospeo.io/api-docs

### Free Tier
- **75 emails/month** (free plan)
- **100 Chrome extension credits/month**
- No credit card required

### Key Endpoints (New API — post March 2026 migration)

| Endpoint | Description | Credits |
|----------|-------------|---------|
| `POST /enrich-person` | Full person enrichment (email + phone + profile) | 1 credit |
| `POST /bulk-enrich-person` | Batch up to 50 persons | 1 credit/person |
| `POST /enrich-company` | Company enrichment (50+ fields) | 1 credit |
| `POST /bulk-enrich-company` | Batch up to 50 companies | 1 credit/company |
| `POST /search-person` | Search 200M+ contacts, 30+ filters | Variable |
| `POST /search-company` | Search 30M+ companies | Variable |

**Legacy Endpoints (deprecated March 2026)**:
- `/email-finder` — Find email from name + company
- `/mobile-finder` — Find mobile number
- `/email-verifier` — Verify email address
- `/domain-search` — Find emails for a domain

### Data Fields Returned

**Enrich Person**:
- Verified email address
- Mobile phone number
- Full professional profile data
- Company information for current employer
- Null for unavailable fields

**Enrich Company** (50+ fields):
- Company name, domain, description
- Industry, size, founded date
- Technologies used
- Funding data
- Location

### Rate Limits
- Divided into 2 categories (specific values not publicly documented)
- 429 error when exceeded

### Python Library
- **No official SDK** — REST API with Python `requests` examples in docs
- Simple header-based auth makes it easy to wrap

### Authentication
- **API Key** — passed as `X-KEY` header
- 401 returned for invalid key

### Gotchas
- **API was completely revamped** — old endpoints deprecated March 2026
- Must migrate to new endpoints
- ~$0.01/email, 10 credits per mobile number on paid plans
- 75 free emails is decent for testing
- **Supports LinkedIn URL as input** for person enrichment
- Good accuracy (>95% email find rate claimed)

---

## 6. Dropcontact

**API Docs**: https://developer.dropcontact.com/

### Free Tier
- **Free trial available** — specific credit count unclear
- No permanent free tier documented
- Paid plans start at **EUR 24/month** (500 credits)

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /batch` (or `/all`) | Submit batch of up to 250 contacts |
| `GET /batch/{request_id}` | Retrieve enrichment results |

### Data Fields Returned
- Civility (Mr/Ms)
- First name, last name, full name
- Email address (found or verified)
- Email validity status
- Company name, domain
- Job title
- Phone number
- LinkedIn URL
- SIREN/SIRET (French company IDs)
- Company size, industry

### Rate Limits
- **60 requests/minute**
- Max **250 contacts per batch request**
- Each contact must be < 15 KB

### Python Library
- **No official SDK** — REST API only
- Simple to wrap with `requests`

### Authentication
- **API Key** — passed as `X-Access-Token` header

### GDPR Approach
- **100% GDPR compliant** — proprietary algorithms
- Data processed exclusively on **EU-based servers**
- **No database** — generates data in real-time
- No reliance on non-compliant third-party providers
- No personal data stored — results are ephemeral
- Pay-on-success: 1 credit = 1 email found/verified (credit back if not found)

### Gotchas
- **No real free tier** — trial only
- Async pattern: POST to submit, poll GET for results
- Webhook callback supported via `custom_callback_url`
- Strongest GDPR story of all providers
- Best for EU-focused teams
- LinkedIn enrichment available on Growth plan only
- **Pay-on-success model** is unique and cost-effective

---

## 7. Apollo.io (Bonus)

**API Docs**: https://docs.apollo.io

### Free Tier
- **10,000 email credits/month** (verified corporate domains)
- **100 email credits/month** (non-verified domains)
- **5 mobile credits/month**
- **10 export credits/month**
- 1 seat included
- Basic API access included

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/people/match` | Person enrichment from email/LinkedIn URL |
| `POST /v1/organizations/enrich` | Company enrichment |
| `POST /v1/mixed_people/search` | Search people database (275M+ contacts) |
| `POST /v1/mixed_companies/search` | Search company database |
| `POST /v1/contacts/create` | Create contact in CRM |

### Data Fields Returned
- Email (personal + professional)
- Phone numbers (direct + mobile)
- Job title, seniority, department
- Company name, domain, size, industry, revenue
- LinkedIn URL, Twitter
- Location (city, state, country)
- Technologies used

### Authentication
- **API Key** — passed as header or query parameter

### Gotchas
- **Best free tier by far** — 10K email credits is extremely generous
- API credit consumption varies by data type and enrichment source
- Waterfall enrichment available (tries multiple sources)
- **Accepts LinkedIn URL as enrichment input**
- Rate limits not clearly documented for free tier
- Some advanced API features restricted to paid plans
- Data quality varies; verification recommended

---

## 8. Tomba.io (Bonus)

**API Docs**: https://tomba.io/api | https://docs.tomba.io

### Free Tier
- **50 searches/month**
- **100 email verifications/month**
- API access on all plans

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /domain-search` | Find emails for a domain |
| `GET /email-finder` | Find email by name + domain |
| `GET /email-verifier` | Verify email address |
| `GET /email-count` | Count emails for domain (free) |
| `GET /account` | Account info |

### Data Fields Returned
- Email address and verification status
- First name, last name
- Job title, department, seniority
- Company info (name, domain)
- Social profiles
- Sources where email was found

### Authentication
- **API Key** — passed as header

### Gotchas
- Very similar to Hunter.io in approach
- API accessible on free plan (unlike some competitors)
- 50 searches is more generous than Hunter's 25
- Less well-known, smaller database than Hunter

---

## 9. Proxycurl (Bonus — LinkedIn-specific)

**API Docs**: https://nubela.co/proxycurl/docs

### Free Tier
- **Limited free credits** for new accounts (amount unclear, reportedly small)
- Pay-as-you-go from $10

### Key Feature
- **Takes LinkedIn URL as input** and returns structured data
- Up to **44 data points per person**, **90 data points with company**
- Legally scrapes LinkedIn public profiles

### Key Endpoints

| Endpoint | Credits | Description |
|----------|---------|-------------|
| `GET /api/v2/linkedin` | 3 credits | Person profile from LinkedIn URL |
| `GET /api/linkedin/company` | 1 credit | Company profile from LinkedIn URL |
| `GET /api/contact-api/personal-email` | 1 credit | Find personal email |
| `GET /api/contact-api/personal-contact` | 1 credit | Find phone number |

### Data Fields (Person)
- Full name, headline, summary
- Current and past experience (title, company, dates)
- Education history
- Skills, certifications
- Location, country
- Profile picture URL
- Connections count
- Languages

### Authentication
- **API Key** — Bearer token in Authorization header

### Gotchas
- **No real free tier** — small trial credits only
- $49/month for 1,000 API calls minimum
- 3 credits per person lookup is expensive
- Credits charged even for empty results
- Best for LinkedIn-URL-first workflows
- **Has official Python SDK**: https://github.com/nubelaco/proxycurl-py-linkedin-profile-scraper

---

## 10. LinkedIn URL Enrichment

### Which Providers Accept LinkedIn URL as Input?

| Provider | LinkedIn URL Input | What You Get |
|----------|-------------------|--------------|
| **Apollo.io** | Yes (people/match endpoint) | Email, phone, title, company |
| **Proxycurl** | Yes (primary use case) | Full profile + work history |
| **Prospeo** | Yes (enrich-person) | Verified email + mobile |
| **PeopleDataLabs** | Yes (profile parameter) | Full enrichment (100+ fields) |
| **ContactOut** | Yes (Chrome extension + API) | Personal email + phone |
| **Dropcontact** | Yes (Growth plan) | Email + company data |
| **Findymail** | Yes | Verified email (>95% accuracy, <2% bounce) |
| **RocketReach** | Yes (lookupProfile) | Email + phone |
| **Snov.io** | Yes (LinkedIn Email Finder) | Email |

### Legal Considerations

1. **LinkedIn TOS**: Scraping violates LinkedIn's Terms of Service, but the 2022 hiQ Labs v. LinkedIn ruling (US) affirmed scraping public data is not illegal under CFAA
2. **GDPR**: For EU contacts, must have legitimate interest or consent. Dropcontact and Findymail are GDPR-compliant by design
3. **Best Practice**: Use providers that aggregate publicly available data rather than scraping LinkedIn directly
4. **Risk Mitigation**: API-based providers (Proxycurl, PDL) are safer than direct scraping tools

### Recommended Approach for Our Platform
- Use **Apollo.io** (free, 10K credits) as primary LinkedIn-URL enrichment
- Fall back to **PeopleDataLabs** (100 free lookups) for deeper data
- Use **Hunter.io/Prospeo** for email-specific verification
- **Waterfall pattern**: Try Apollo first -> PDL -> Prospeo -> Hunter

---

## 11. Comparison Matrix

### Free Tier Credits

| Provider | Free Credits/Month | API on Free? | Best For |
|----------|-------------------|--------------|----------|
| **Apollo.io** | 10,000 email credits | Yes (basic) | Volume email finding |
| **PeopleDataLabs** | 100 lookups + sandbox | Yes | Rich data fields |
| **Prospeo** | 75 emails | Yes | Email + mobile |
| **Tomba.io** | 50 searches + 100 verifications | Yes | Email finding |
| **Hunter.io** | 25 searches + 50 verifications | Yes | Email verification |
| **Snov.io** | 50-150 credits | Maybe (demo required) | Outreach integration |
| **RocketReach** | 5 lookups | No (Ultimate only) | Not viable for free |
| **Dropcontact** | Trial only | Yes (on paid) | GDPR compliance |
| **Proxycurl** | Tiny trial | No | LinkedIn profiles |

### Data Field Coverage

| Field | Hunter | Snov | PDL | Rocket | Prospeo | Drop | Apollo | Tomba |
|-------|--------|------|-----|--------|---------|------|--------|-------|
| Email | Y | Y | Y | Y | Y | Y | Y | Y |
| Phone | Sparse | N | Y | Y | Y | Y | Y | N |
| Title | Y | Y | Y | Y | Y | Y | Y | Y |
| Company | Y | Y | Y | Y | Y | Y | Y | Y |
| LinkedIn | Y | N | Y | Y | Y | Y | Y | N |
| Location | N | N | Y | Y | Y | N | Y | N |
| Work History | N | N | Y | Y | N | N | Y | N |
| Education | N | N | Y | N | N | N | N | N |
| Tech Stack | N | N | N | Y | Y | N | Y | N |

### Authentication Summary

| Provider | Auth Method | Token Refresh? |
|----------|------------|----------------|
| Hunter.io | API Key (query param) | No |
| Snov.io | OAuth2 (client_id/secret) | Every 1 hour |
| PeopleDataLabs | API Key (X-Api-Key header) | No |
| RocketReach | API Key (Api-Key header) | No |
| Prospeo | API Key (X-KEY header) | No |
| Dropcontact | API Key (X-Access-Token header) | No |
| Apollo.io | API Key (header/query) | No |
| Tomba.io | API Key (header) | No |
| Proxycurl | Bearer token | No |

### Python SDK Availability

| Provider | Official SDK | Community Wrapper | Package |
|----------|-------------|-------------------|---------|
| PeopleDataLabs | Yes | - | `peopledatalabs` |
| RocketReach | Yes | - | `rocketreach` |
| Proxycurl | Yes | - | `proxycurl-py` |
| Hunter.io | No | PyHunter | `pyhunter` |
| Snov.io | No | python-snovio | `python-snovio` |
| Prospeo | No | - | REST only |
| Dropcontact | No | - | REST only |
| Apollo.io | No | - | REST only |
| Tomba.io | No | - | REST only |

---

## Recommended Free Stack for Waterfall Enrichment

### Priority Order (maximize free credits):

1. **Apollo.io** — 10,000 credits/month, broadest coverage, LinkedIn URL support
2. **PeopleDataLabs** — 100 lookups/month, richest data per record, official Python SDK
3. **Prospeo** — 75 emails/month, good for email + mobile, LinkedIn URL support
4. **Tomba.io** — 50 searches + 100 verifications, good email accuracy
5. **Hunter.io** — 25 searches + 50 verifications, best for email verification step

### Total Free Monthly Capacity:
- ~10,250 email lookups (Apollo dominates)
- ~100 deep enrichments (PDL)
- ~75 mobile number lookups (Prospeo)
- ~150 email verifications (Hunter + Tomba)

### Architecture Recommendation:
```
Input (name, company, LinkedIn URL, email)
    |
    v
[Apollo.io] — Try first (10K credits, accepts LinkedIn URL)
    |  (miss?)
    v
[PeopleDataLabs] — Deep enrichment fallback (100/month)
    |  (miss?)
    v
[Prospeo] — Email + mobile specialist (75/month)
    |  (miss?)
    v
[Hunter.io] — Email verification final step (50/month)
```

---

## Sources

- [Hunter.io API Reference V2](https://hunter.io/api-documentation/v2)
- [Hunter.io Rate Limits](https://help.hunter.io/en/articles/1971004-is-there-a-request-per-second-limit)
- [Snov.io API Documentation](https://snov.io/api)
- [Snov.io Pricing & Limits](https://snov.io/knowledgebase/plans-and-limits-update/)
- [PeopleDataLabs Usage Limits](https://docs.peopledatalabs.com/docs/usage-limits)
- [PeopleDataLabs Sandbox APIs](https://docs.peopledatalabs.com/docs/sandbox-apis)
- [PeopleDataLabs Plan Types](https://support.peopledatalabs.com/hc/en-us/articles/27546010665115-Plan-types-Free-Pro-and-Enterprise)
- [PeopleDataLabs Python SDK](https://github.com/peopledatalabs/peopledatalabs-python)
- [RocketReach API Docs](https://docs.rocketreach.co/reference/rocketreach-api)
- [RocketReach Python SDK](https://github.com/rocketreach/rocketreach_python)
- [RocketReach Pricing](https://rocketreach.co/pricing)
- [Prospeo API Documentation](https://prospeo.io/api-docs)
- [Prospeo Rate Limits](https://prospeo.io/api-docs/rate-limits)
- [Prospeo Pricing](https://prospeo.io/pricing)
- [Dropcontact API](https://developer.dropcontact.com/)
- [Dropcontact Pricing](https://www.dropcontact.com/pricing)
- [Apollo.io API Pricing](https://docs.apollo.io/docs/api-pricing)
- [Apollo.io Pricing](https://www.apollo.io/pricing)
- [Tomba.io Pricing](https://tomba.io/pricing)
- [Tomba.io API Docs](https://docs.tomba.io/features)
- [Proxycurl Docs](https://nubela.co/proxycurl/docs)
- [Proxycurl Python SDK](https://github.com/nubelaco/proxycurl-py-linkedin-profile-scraper)
- [PyHunter GitHub](https://github.com/VonStruddle/PyHunter)
- [python-snovio GitHub](https://github.com/miguelcdpmarques/python-snovio)
