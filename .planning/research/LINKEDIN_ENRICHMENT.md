# LinkedIn-Based Contact Enrichment — Deep Research Report

> **Date**: 2026-03-08
> **Purpose**: Comprehensive analysis of going from LinkedIn profile URL to enriched contact data (email, phone, company info)

---

## Table of Contents

1. [LinkedIn as a Data Source](#1-linkedin-as-a-data-source)
2. [Provider APIs that Accept LinkedIn URLs](#2-provider-apis-that-accept-linkedin-urls)
3. [LinkedIn URL Formats & Normalization](#3-linkedin-url-formats--normalization)
4. [Practical LinkedIn Enrichment Workflow](#4-practical-linkedin-enrichment-workflow)
5. [Sales Navigator CSV Export](#5-sales-navigator-csv-export)
6. [Recommended Architecture for Our Platform](#6-recommended-architecture-for-our-platform)

---

## 1. LinkedIn as a Data Source

### 1.1 LinkedIn Official API

**Access Model**: LinkedIn only grants API access to approved partners. You must submit details about your product, business model, and use case. The API is designed for marketing, recruiting, and content management — NOT for contact enrichment or lead generation.

**What You CAN Access (with approval)**:
- Community Management API: Post creation (text, images, videos, carousels, polls), comments/reactions on behalf of organizations
- Marketing API: Ad management, campaign analytics, audience targeting
- Profile API (limited): Basic profile of authenticated user only (via OAuth)
- Video analytics for member creator posts (new endpoint, version 202506)

**What You CANNOT Access**:
- Other users' email addresses or phone numbers
- Bulk profile data or search results
- Contact information beyond what the authenticated user shares
- Any data for enrichment/prospecting purposes

**Restrictions**:
- Strict data storage requirements and deletion obligations
- Restricted use cases explicitly prohibit building competitive products, contact databases, or enrichment tools
- Rate limits enforced with 429 errors for exceeding daily call limits
- All usage must comply with LinkedIn Marketing API Program Terms

**Bottom Line**: LinkedIn's official API is useless for contact enrichment. It does not expose the data needed (emails, phones, detailed profiles of third parties).

### 1.2 LinkedIn Sales Navigator API (SNAP)

**What is SNAP**: Sales Navigator Application Platform — the only official way to access Sales Navigator data via API.

**Access Status**: As of August 2025, LinkedIn is NOT accepting new SNAP partners. The application process is paused with no public timeline for reopening.

**What SNAP Provides** (for approved partners):
- Run search queries from your app and sync results
- Auto-enrich CRM records with profile URLs, photos, and LinkedIn URNs
- Match CRM leads to LinkedIn profiles

**What SNAP Does NOT Provide**:
- Raw LinkedIn data extraction
- Email or phone number enrichment
- Contact data for outbound tools
- Lead scraping capabilities

**Requirements for Access**:
- Rigorous application process with design review
- Must demonstrate direct support for sales, recruiting, or marketing
- Must meet technical compliance, data privacy, and security standards

**Bottom Line**: SNAP is irrelevant for our use case. Even if accepting new partners, it explicitly prohibits the enrichment use case we need.

### 1.3 How Tools Extract Emails from LinkedIn Profiles

Tools like ContactOut, Kaspr, LeadIQ, and Lusha use a combination of approaches:

**Chrome Extension Overlay Method**:
- Browser extension activates when viewing a LinkedIn profile
- Extension reads the profile's public identifier and visible data (name, company, title)
- Data is sent to the provider's backend API
- Backend cross-references against proprietary databases built from:
  - Web scraping of public data sources
  - Data partnerships and licensing agreements
  - User-contributed data (opt-in email sharing)
  - SMTP verification and pattern matching
  - Public records and business registrations

**Technical Approach (Simplified)**:
1. **Profile Identification**: Extract name + company from LinkedIn page DOM or URL
2. **Database Lookup**: Query proprietary database of 300M+ contacts
3. **Email Pattern Matching**: Apply known email patterns for the company domain (e.g., `first.last@company.com`)
4. **SMTP Verification**: Validate candidate emails via SMTP handshake without sending
5. **Confidence Scoring**: Return results with accuracy confidence percentage

**Key Insight**: These tools do NOT extract emails from LinkedIn itself. LinkedIn does not display email addresses on profiles (except to direct connections). Instead, they use the identity signals from LinkedIn (name + company) to look up emails in their own databases.

### 1.4 Legal Landscape of LinkedIn Scraping

#### hiQ Labs v. LinkedIn (Key Precedent)

**Timeline**:
- 2017: hiQ sued LinkedIn after LinkedIn sent cease-and-desist for scraping public profiles
- 2019: Ninth Circuit ruled scraping publicly available data does not violate CFAA
- 2021: Supreme Court vacated and remanded based on Van Buren v. United States
- 2022 (April): Ninth Circuit reaffirmed — CFAA does not apply to public data scraping
- 2022 (November): District Court ruled LinkedIn's Terms of Service prohibiting scraping ARE enforceable as breach of contract
- 2022 (December): Settlement — $500,000 judgment against hiQ

**Key Legal Takeaways**:
1. **CFAA (Computer Fraud and Abuse Act)**: Scraping publicly accessible data does NOT violate the CFAA — confirmed by both Ninth Circuit and informed by Supreme Court's Van Buren ruling
2. **Terms of Service**: However, scraping that violates LinkedIn's ToS CAN be enforced as a breach of contract claim
3. **Practical Implication**: While not criminally illegal, LinkedIn CAN sue scrapers for breach of contract and win

**Current Legal Status**:
- LinkedIn's ToS explicitly prohibit: "automated software, devices, scripts, robots, or other means to access, scrape, crawl, or spider the Services"
- Enforcement focuses on worst offenders (mass scraping, thousands of messages)
- Using third-party enrichment APIs that have their own databases is the legally safe approach

### 1.5 LinkedIn Rate Limits & Anti-Scraping Measures

**Technical Defenses**:
- Rate limiting and IP blocking
- CAPTCHA challenges triggered by suspicious activity
- Advanced anti-bot algorithms detecting non-human patterns
- Account restrictions and bans for detected automation

**Detection Triggers**:
- Actions at superhuman speeds
- Identical message templates sent to hundreds of users
- Systematic profile access patterns suggesting automated collection
- Multiple requests from same IP in short timeframes

**Known Thresholds** (approximate, from community data):
- ~80-100 profile views per day before warnings
- ~2,000 public profiles per day per account (maximum safe scraping)
- Connection requests: 20-25 per day
- Messages: 50-100 per day
- Search result pages: ~25-30 per session

**Mitigation Strategies** (used by scraping tools):
- Residential proxy rotation
- Random delays between actions (human-like timing)
- Session management and cookie persistence
- Spread activity across multiple accounts/IPs

---

## 2. Provider APIs that Accept LinkedIn URLs

### 2.1 Provider Comparison Matrix

| Provider | LinkedIn URL Input | Endpoint | Email | Phone | Cost/Lookup | Free Tier | Rate Limit |
|----------|-------------------|----------|-------|-------|-------------|-----------|------------|
| **Apollo.io** | Yes | `POST /api/v1/people/match` | Yes | Yes | 1 credit (email), 5-8 credits (phone) | 120 credits/mo | 600/hour |
| **ContactOut** | Yes | `GET /v1/linkedin/enrich` | Yes | Yes | 1 email credit + 1 phone credit | 100 credits/mo | Not published |
| **Findymail** | Yes (via name endpoint) | `POST /api/search/name` + phone via `/api/search/phone` | Yes | Yes | 1 credit (email), 10 credits (phone) | 10 credits trial | Not published |
| **Prospeo** | Yes | `POST /enrich-person` | Yes | Yes | 1 credit (email+company), 10 credits (with mobile) | 75 credits/mo | Plan-dependent |
| **Snov.io** | Yes | `POST /v2/li-profiles-by-urls/start` | No (profile only) | No | 1 credit/profile | 50 credits/mo | 60 req/min |
| **RocketReach** | Yes | `GET /api/v2/person/lookup` | Yes | Yes | 1 lookup credit | 5 free lookups | Not published |
| **PeopleDataLabs** | Yes | `GET /v5/person/enrich` | Yes | Yes | $0.20-0.28/credit | 100 req/min (free) | 100-1000 req/min |
| **Datagma** | Yes | `POST /api/ingress/v2/full` | Yes | Yes | 1 credit (email), 30 credits (phone) | 90 emails/year | Not published |
| **Kaspr** | Yes | `POST /profile/linkedin` | Yes | Yes | 1 credit (email), 1 credit (phone) | 5 phone + 5 email/mo | Not published |
| **Icypeas** | Partial (name+domain) | Async API | Yes | No | 1 credit/email | 50 credits | 10 req/sec |
| **Hunter.io** | Yes (handle) | `GET /v2/email-finder` | Yes | Sometimes | 1 credit | 25 searches/mo | 15 req/sec, 500/min |

### 2.2 Detailed Provider Analysis

#### Apollo.io
- **Endpoint**: `POST https://api.apollo.io/api/v1/people/match`
- **LinkedIn Parameter**: `linkedin_url` — e.g., `http://www.linkedin.com/in/tim-zheng-677ba010`
- **Key Parameters**: `reveal_personal_emails`, `reveal_phone_number`, `run_waterfall_email`, `run_waterfall_phone`
- **Returns**: Full profile (name, title, headline, email, email_status, photo, social profiles, location, organization details, employment history, departments, seniority, intent signals)
- **Credit Cost**: 1 credit for email reveal, 5-8 credits for mobile number, waterfall enrichment costs vary by data source that returns data
- **Free Tier**: 120 email credits/month on free plan, 5 mobile credits/month
- **Rate Limit**: 600 requests/hour for people/match endpoint
- **Accuracy**: ~80% email accuracy reported
- **Bulk**: Separate bulk endpoint (`/api/v1/people/bulk_match`) for up to 10 people per call
- **Note**: Apollo removed LinkedIn automation features in January 2026, but API enrichment via LinkedIn URL still works

#### ContactOut
- **Primary Endpoint**: `GET https://api.contactout.com/v1/linkedin/enrich`
- **LinkedIn Parameter**: `profile` — fully formed LinkedIn URL
- **Additional Endpoints**:
  - `GET /v1/people/linkedin` — contact info only
  - `POST /v1/people/linkedin/batch` — bulk (up to 30 URLs)
  - `POST /v2/people/linkedin/batch` — async bulk (up to 1,000 URLs)
  - `GET /v1/people/linkedin/personal_email_status` — check availability (free, no credits)
  - `GET /v1/people/linkedin/work_email_status` — check availability (free, no credits)
  - `GET /v1/people/linkedin/phone_status` — check availability (free, no credits)
- **Returns**: email, work_email, personal_email, phone, full_name, headline, company details, experience, education, skills
- **Credit Cost**: 1 email credit per profile (if email found), 1 phone credit (if phone found and requested)
- **Free Tier**: 100 free credits/month
- **Accuracy**: Database covers 300M+ work emails and 200M+ personal emails
- **Unique Feature**: Free status-check endpoints to verify data availability before consuming credits
- **Rate Limit**: Not publicly documented; fair use caps of ~2,000 emails and 1,000 phones monthly

#### Findymail
- **Email Endpoint**: `POST https://app.findymail.com/api/search/name` (accepts name + domain)
- **Phone Endpoint**: `POST https://app.findymail.com/api/search/phone` (accepts `linkedin_url`)
- **Reverse Email**: `POST /api/search/reverse-email` — find LinkedIn profile from email
- **Company**: Supports LinkedIn URL, domain, or company name for company enrichment
- **Returns**: Verified email address, phone number, name, linkedinUrl, jobTitle, companyName
- **Credit Cost**: 1 credit per email found, 10 credits per phone found, 2 credits for reverse email with profile
- **Free Tier**: 10 finder credits + 10 verification credits on trial
- **Pricing**: $49/mo (Basic), $99/mo (Starter, 5,000 credits), $249/mo (Business, 15,000 credits)
- **Accuracy**: Built-in email verification — only returns verified addresses
- **Note**: LinkedIn URL works as input for Clay integration (2 credits per enriched cell with Clay-managed account)

#### Prospeo
- **Endpoint**: `POST https://api.prospeo.io/enrich-person`
- **LinkedIn Parameter**: `linkedin_url` — e.g., `https://www.linkedin.com/in/john-doe`
- **Key Parameters**: `only_verified_email`, `enrich_mobile`, `only_verified_mobile`
- **Returns**: Full person object + company object (email, mobile, job title, company data)
- **Credit Cost**: 1 credit for email + company enrichment, 10 credits with mobile number
- **Free Tier**: 75 credits/month (API access requires Starter plan at $149/mo minimum)
- **No Charge**: When no results found or duplicate enrichment within account lifetime
- **Accuracy**: High — only verified results returned when using `only_verified_email`
- **Note**: Legacy Email Finder endpoint deprecated March 2026, migrated to enrich-person

#### Snov.io
- **Endpoint**: `POST https://api.snov.io/v2/li-profiles-by-urls/start` (async)
- **Result Retrieval**: `GET https://api.snov.io/v2/li-profiles-by-urls/result?task_hash={hash}`
- **LinkedIn Parameter**: `urls[]` — up to 10 LinkedIn URLs per request
- **Returns**: Full name, first/last name, industry, country, city, job title, company name, company LinkedIn URL, company domain
- **Credit Cost**: 1 credit per LinkedIn profile enriched
- **Free Tier**: 50 credits/month on Trial plan
- **Rate Limit**: 60 requests/minute
- **Limitation**: Returns profile data but NOT email addresses directly via this endpoint. Email finding requires separate Domain Email Search or Email Finder endpoint with name+domain
- **Pricing**: $39/mo (Starter), $99/mo (Pro)

#### RocketReach
- **Endpoint**: `GET https://api.rocketreach.co/api/v2/person/lookup`
- **LinkedIn Parameter**: `linkedin_url` — e.g., `www.linkedin.com/in/jamesgullbrand`
- **Returns**: Profile (id, name, photo, linkedin_url), employment (current_title, current_employer, job_history), education, verified emails (with SMTP validity grades), phone numbers (with type), location, skills
- **Credit Cost**: 1 lookup credit per profile with at least one verified email; re-lookups and updates are free on active plans
- **Free Tier**: 5 free lookups (no credit card required)
- **Pricing**: $399/year Essentials (1,200 lookups, email only), $899/year Pro (3,600 lookups, email+phone), $2,099/year Ultimate (10,000 lookups)
- **Accuracy**: Highly accurate — LinkedIn URL lookups return better results than name-based lookups
- **Bulk**: Separate bulk endpoint for batch requests
- **Overage**: $0.30-0.45 per extra lookup

#### PeopleDataLabs (PDL)
- **Endpoint**: `GET https://api.peopledatalabs.com/v5/person/enrich`
- **LinkedIn Parameter**: `profile` — e.g., `http://linkedin.com/in/seanthorne`
- **Alternative**: `lid` parameter for LinkedIn ID directly
- **Returns**: Full profile — full_name, emails, phone_numbers, experience, education, location, social profiles, job titles, skills, certifications
- **Credit Cost**: 1 credit per successful match (200 response), ~$0.20-0.28 per credit depending on volume
- **Free Tier**: 100 requests/minute for free customers
- **Rate Limit**: 100 req/min (free), 1,000 req/min (paid)
- **Pricing**: Pro plan starts at $98/month (350 person credits), Enterprise from ~$2,500/month (custom/unlimited)
- **Accuracy**: Recommended `min_likelihood >= 6` for best accuracy
- **Bulk**: Separate bulk enrichment endpoint available

#### Datagma
- **Endpoint**: `POST https://gateway.datagma.net/api/ingress/v2/full`
- **LinkedIn Support**: Accepts LinkedIn profile URL as input for person enrichment
- **Returns**: 75 data points per contact including verified emails, mobile phone numbers, company data
- **Credit Cost**: 1 credit = 1 email (includes person + company enrichment), 30 credits = 1 mobile phone number
- **Free Tier**: 90 verified emails + 3 mobile numbers per year, includes API access
- **No Charge**: If no data found — risk-free model
- **Pricing**: $39/mo (Regular, annual), up to $209/mo (Expert, annual)
- **Chrome Extension**: Real-time enrichment on LinkedIn profiles

#### Kaspr
- **Endpoint**: `POST https://api.developers.kaspr.io/profile/linkedin`
- **LinkedIn Parameter**: LinkedIn ID + full name
- **Header Required**: `accept-version: v2.0`
- **Returns**: Name, email (B2B work email, direct email), phone number, job title
- **Credit System**: 4 types (phone, direct email, B2B email, export) — not interchangeable
- **Free Tier**: Unlimited B2B emails, 5 phone credits, 5 direct email credits, 10 export credits/month
- **Pricing**: $49/mo Starter (annual), $79/mo Business (annual)
- **API Access**: Available on Starter and Business plans (upon request)
- **Accuracy**: Database of 500M+ consumer profiles
- **LinkedIn URL Format**: Only compatible with standard LinkedIn profile URL formats

#### Icypeas
- **API Type**: Asynchronous endpoints
- **LinkedIn Support**: Partial — primarily works with name + company domain, not direct LinkedIn URL input via API
- **Returns**: Verified email addresses
- **Credit Cost**: 1 credit per verified email found, no charge if not found
- **Free Tier**: 50 free credits on signup (never expire)
- **Rate Limit**: 10 req/sec (single), 1 req/sec (bulk, up to 5,000 rows)
- **Pricing**: Extremely competitive — down to $0.0039 per email at 1M credits
- **Unique**: Credits never expire, even if you cancel subscription
- **LinkedIn Scraper**: Available via Apify marketplace (separate product)

#### Hunter.io
- **Endpoint**: `GET https://api.hunter.io/v2/email-finder`
- **LinkedIn Parameter**: `linkedin_handle` — standalone alternative to name+domain
- **Returns**: Email address, confidence score (0-100), first/last name, position, company, social profiles, phone (sometimes), verification status, up to 20 public sources
- **Credit Cost**: 1 credit per email found
- **Free Tier**: 25 email searches + 50 verifications per month
- **Rate Limit**: 15 req/sec, 500 req/min (Email Finder); 10 req/sec, 300 req/min (Verifier)
- **Pricing**: $49/mo Starter (2,000 credits), $149/mo Growth (10,000), $299/mo Scale (25,000)
- **Accuracy**: Confidence score system; sources provided for transparency
- **Note**: Also supports enrichment from LinkedIn handle to full company record

---

## 3. LinkedIn URL Formats & Normalization

### 3.1 Valid LinkedIn URL Formats

```
# Standard public profile (current format)
https://www.linkedin.com/in/username
https://linkedin.com/in/username
http://www.linkedin.com/in/username
http://linkedin.com/in/username

# With trailing slash
https://www.linkedin.com/in/username/

# With country subdomain (legacy, redirects)
https://uk.linkedin.com/in/username
https://fr.linkedin.com/in/username
https://de.linkedin.com/in/username

# Legacy /pub format (deprecated, redirects to /in/)
https://www.linkedin.com/pub/first-last/xx/xxx/xxx

# Sales Navigator URLs (NOT public profile URLs)
https://www.linkedin.com/sales/lead/ACwAAA...
https://www.linkedin.com/sales/people/ACwAAA...

# Profile view URLs (temporary, session-based)
https://www.linkedin.com/in/username?miniProfileUrn=...
```

### 3.2 URL Normalization Rules

```
Input normalization steps:
1. Strip protocol variations → always use https://
2. Remove www. prefix → linkedin.com
3. Remove country subdomains → linkedin.com (not uk.linkedin.com)
4. Remove trailing slashes
5. Remove query parameters (?miniProfileUrn=, ?originalSubdomain=, etc.)
6. Remove URL fragments (#)
7. Lowercase the entire URL
8. Extract the public identifier: everything after /in/ before any / or ?

Regex pattern:
  /(?:https?:\/\/)?(?:[\w]+\.)?linkedin\.com\/in\/([\w\-]+)/i

Valid characters in identifier:
  - Letters (a-z)
  - Numbers (0-9)
  - Hyphens (-)
  - NO spaces, underscores, or special symbols
```

### 3.3 Extracting Public Identifier

```javascript
function extractLinkedInId(url) {
  const match = url.match(
    /(?:https?:\/\/)?(?:[\w]+\.)?linkedin\.com\/in\/([\w\-]+)/i
  );
  return match ? match[1].toLowerCase() : null;
}

// Examples:
// "https://www.linkedin.com/in/John-Doe-123" → "john-doe-123"
// "http://uk.linkedin.com/in/jane-smith/"    → "jane-smith"
// "linkedin.com/in/Bob"                       → "bob"
```

### 3.4 Sales Navigator URL Conversion

Sales Navigator URLs use internal URNs (e.g., `ACwAAA...`) that do NOT map directly to public profile identifiers. To convert:
- The Sales Navigator profile page includes a link to the public LinkedIn profile
- Third-party tools like Evaboot can batch-convert Sales Navigator URLs to public LinkedIn URLs
- No official API exists for this conversion

---

## 4. Practical LinkedIn Enrichment Workflow

### 4.1 User Input Scenarios

**Scenario A: User pastes individual LinkedIn URLs**
```
Input: https://www.linkedin.com/in/john-doe-12345
Flow: Normalize URL → Query providers with linkedin_url parameter → Return enriched data
```

**Scenario B: User imports Sales Navigator CSV**
```
Input: CSV file with names, titles, companies, LinkedIn URLs (if exported via third-party tool)
Flow: Parse CSV → Extract LinkedIn URLs + name/company → Batch enrich → Return results
```

**Scenario C: User pastes list of LinkedIn URLs**
```
Input: Bulk list of 10-1000 LinkedIn URLs
Flow: Normalize all URLs → Batch enrich via bulk endpoints → Waterfall unfound records → Return results
```

### 4.2 Optimal Provider Waterfall for LinkedIn-Sourced Contacts

Based on cost, accuracy, LinkedIn URL support, and coverage:

```
LinkedIn URL Enrichment Waterfall (Email Priority):

Layer 1: Apollo.io
  - Why first: Best database coverage (~80% accuracy), native LinkedIn URL support
  - Cost: 1 credit per email (~$0.03-0.04 at scale)
  - Expected hit rate: 60-70%

Layer 2: ContactOut
  - Why second: Specialized in LinkedIn-to-email, 300M+ database
  - Cost: 1 email credit per match
  - Expected incremental: +10-15%

Layer 3: Prospeo
  - Why third: Strong accuracy, only verified results
  - Cost: 1 credit per match, no charge if not found
  - Expected incremental: +5-10%

Layer 4: Hunter.io
  - Why fourth: LinkedIn handle support, confidence scoring, source transparency
  - Cost: 1 credit per match
  - Expected incremental: +3-5%

Layer 5: RocketReach
  - Why last: Higher per-lookup cost but strong accuracy for hard-to-find contacts
  - Cost: 1 lookup credit
  - Expected incremental: +3-5%

Combined expected hit rate: 80-90% for work emails
```

```
Phone Number Waterfall (if needed):

Layer 1: Kaspr (1 credit per phone, good coverage)
Layer 2: Prospeo (10 credits, verified mobile)
Layer 3: Datagma (30 credits per phone, 75 data points)
Layer 4: Apollo.io (5-8 credits per phone, waterfall available)
```

### 4.3 Realistic Hit Rates for LinkedIn URL Enrichment

| Target Segment | Email Hit Rate | Phone Hit Rate |
|---------------|---------------|----------------|
| US-based tech professionals | 75-90% | 40-60% |
| US-based enterprise executives | 70-85% | 35-55% |
| European professionals (GDPR) | 60-75% | 20-35% |
| Small business owners | 55-70% | 30-45% |
| Academic/Government | 50-65% | 15-25% |
| Recently changed jobs (<3 months) | 40-55% | 30-45% |

**Key Factors Affecting Hit Rate**:
- Geographic region (US/UK highest, GDPR regions lower for personal data)
- Industry (tech/SaaS highest, government/nonprofit lowest)
- Seniority level (VP+ slightly lower than IC/Manager)
- Company size (mid-market best coverage, very small/very large more challenging)
- Profile completeness on LinkedIn (more data = better matching)

### 4.4 Cost Optimization Strategies

1. **Check availability before enriching**: ContactOut offers free status-check endpoints to verify data exists before consuming credits
2. **Use free tiers strategically**: Apollo (120/mo), Prospeo (75/mo), Hunter (25/mo), Snov.io (50/mo) = ~270 free lookups/month
3. **Batch when possible**: ContactOut bulk V2 handles 1,000 URLs per call; Apollo bulk handles 10
4. **No-charge-on-miss providers**: Prospeo, Datagma, Icypeas only charge when data is found
5. **Cache results aggressively**: RocketReach re-lookups are free on active plans

---

## 5. Sales Navigator CSV Export

### 5.1 Native Export Limitations

**LinkedIn Sales Navigator does NOT have a native CSV export feature.** There is no "Download to CSV" button within the platform. This is by design — LinkedIn wants to keep data within their ecosystem.

The only built-in data export is through CRM sync (Salesforce, HubSpot) via the SNAP integration, which syncs profile URLs and basic info but NOT email addresses or phone numbers.

### 5.2 Third-Party Export Tools

Users typically export Sales Navigator lists using tools like:

| Tool | Method | Max Leads | Email Enrichment | Pricing |
|------|--------|-----------|-----------------|---------|
| **Evaboot** | Chrome extension | Unlimited | Yes (built-in) | $29-99/mo |
| **PhantomBuster** | Cloud automation | Per phantom limits | Via integrations | $56-128/mo |
| **Dux-Soup** | Chrome extension | Varies | Via integrations | $14.99-55/mo |
| **Skrapp.io** | Chrome extension + API | Varies | Yes (built-in) | $49-199/mo |
| **Linked Helper** | Desktop app | Varies | Via integrations | $15-45/mo |

### 5.3 Typical Exported CSV Fields

When exported via third-party tools (e.g., Evaboot), the CSV typically contains:

```
Core Identity Fields:
- First Name
- Last Name
- Full Name
- LinkedIn URL (public profile URL)
- LinkedIn Sales Navigator URL

Professional Fields:
- Job Title / Headline
- Company Name
- Company LinkedIn URL
- Company Website / Domain
- Industry
- Company Size (employees range)

Location Fields:
- Location (city, state/region)
- Country

Optional Enriched Fields (tool-dependent):
- Email (work email, verified)
- Phone Number
- Seniority Level
- Department / Function
- Years in Current Role
- Years at Company
- Profile Photo URL
```

### 5.4 Importing Sales Navigator Exports

**Recommended Import Flow**:
1. User exports from Sales Navigator via Evaboot/PhantomBuster → gets CSV
2. User uploads CSV to our platform
3. Platform auto-detects columns and maps fields:
   - LinkedIn URL column → primary enrichment key
   - First Name + Last Name + Company → fallback enrichment key
   - Pre-existing email → skip enrichment or verify
4. Platform normalizes LinkedIn URLs
5. Platform runs waterfall enrichment on unmapped/missing contacts
6. Results displayed with match confidence

**Column Detection Heuristics**:
```
LinkedIn URL: column name contains "linkedin", "profile", "url" + value matches linkedin.com pattern
Email: column name contains "email", "mail" + value matches email pattern
First Name: "first", "fname", "given"
Last Name: "last", "lname", "surname", "family"
Company: "company", "organization", "employer"
Title: "title", "position", "role", "job"
```

---

## 6. Recommended Architecture for Our Platform

### 6.1 LinkedIn URL Enrichment Pipeline

```
┌─────────────────────────────────────────────────────┐
│                    User Input                        │
│  (Paste URLs, Upload CSV, Sales Navigator export)    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              URL Normalization Layer                  │
│  - Validate LinkedIn URL format                      │
│  - Extract public identifier                         │
│  - Deduplicate                                       │
│  - Convert Sales Nav URLs if needed                  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Cache Lookup Layer                      │
│  - Check if URL was enriched recently                │
│  - Return cached data if fresh (< 30 days)           │
│  - Skip to enrichment if stale or missing            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           Waterfall Enrichment Engine                 │
│                                                      │
│  Provider 1 (Apollo) ──miss──► Provider 2 (ContactOut)│
│       │                             │                │
│      hit                           hit               │
│       │                             │                │
│       ▼                            miss              │
│    Return                           │                │
│                     Provider 3 (Prospeo) ──miss──►   │
│                          │              Provider 4   │
│                         hit              (Hunter)    │
│                          │                  │        │
│                          ▼                 ...       │
│                       Return                         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Result Aggregation                      │
│  - Merge data from multiple providers                │
│  - Deduplicate emails                                │
│  - Assign confidence scores                          │
│  - Cache results                                     │
└─────────────────────────────────────────────────────┘
```

### 6.2 Priority Providers for LinkedIn URL Input

**Tier 1 — Must Integrate (native LinkedIn URL support, best ROI)**:
1. **Apollo.io** — Best all-around, `linkedin_url` parameter, waterfall built-in
2. **ContactOut** — Purpose-built for LinkedIn enrichment, bulk endpoints, free status checks
3. **Prospeo** — Clean API, `linkedin_url` parameter, no charge on miss

**Tier 2 — Strong Additions**:
4. **Hunter.io** — `linkedin_handle` parameter, confidence scoring, good free tier
5. **RocketReach** — Excellent for LinkedIn lookups, re-lookups free
6. **Kaspr** — Good phone coverage, dedicated LinkedIn endpoint

**Tier 3 — Specialized Use Cases**:
7. **PeopleDataLabs** — Large dataset, `profile` parameter for LinkedIn
8. **Datagma** — 75 data points per contact, risk-free pricing
9. **Findymail** — Strong verification, phone from LinkedIn URL

**Tier 4 — Supplementary**:
10. **Snov.io** — LinkedIn profile data (not email directly), cheap
11. **Icypeas** — Cheapest per-email at scale, but no direct LinkedIn URL input via API

### 6.3 Key Implementation Considerations

1. **LinkedIn URL is the strongest enrichment signal**: When available, always prefer LinkedIn URL over name+company for matching accuracy
2. **Batch processing**: ContactOut (1,000/batch) and Apollo (10/batch) support bulk — use for CSV imports
3. **Async handling**: Snov.io and Findymail use async patterns (submit → poll for results)
4. **Credit conservation**: Use ContactOut's free status-check endpoints before consuming credits on unlikely matches
5. **Phone enrichment is expensive**: 5-30x the cost of email enrichment — only enrich phone when specifically requested
6. **GDPR considerations**: Some providers exclude EU phone numbers (Findymail). Factor geography into provider selection
7. **Data freshness**: People change jobs — enriched data has a ~6-month half-life for accuracy. Implement re-enrichment triggers

---

## Sources

### LinkedIn API & Legal
- [LinkedIn API Guide 2026 — OutX](https://www.outx.ai/blog/linkedin-api-guide)
- [What is LinkedIn API — Evaboot](https://evaboot.com/blog/what-is-linkedin-api)
- [LinkedIn Marketing API Restricted Uses — Microsoft Learn](https://learn.microsoft.com/en-us/linkedin/marketing/restricted-use-cases)
- [Sales Navigator API — Evaboot](https://evaboot.com/blog/linkedin-sales-navigator-api)
- [SNAP Partner Access — LinkedIn Help](https://www.linkedin.com/help/sales-navigator/answer/a526048)
- [hiQ Labs v. LinkedIn — Wikipedia](https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn)
- [Ninth Circuit hiQ Ruling — CalLawyers](https://calawyers.org/privacy-law/ninth-circuit-holds-data-scraping-is-legal-in-hiq-v-linkedin/)
- [hiQ v LinkedIn Settlement — ZwillGen](https://www.zwillgen.com/alternative-data/hiq-v-linkedin-wrapped-up-web-scraping-lessons-learned/)
- [LinkedIn Anti-Scraping 2025 — LeadSourcing](https://leadsourcing.co/linkedin-strategies/linkedin-scraping-in-2025-risks-legalities-and-alternatives/)
- [LinkedIn Limits Guide — MagicPost](https://magicpost.in/blog/linkedin-limitations)

### Provider Documentation
- [Apollo People Enrichment API](https://docs.apollo.io/reference/people-enrichment)
- [Apollo API Pricing](https://docs.apollo.io/docs/api-pricing)
- [ContactOut API Reference](https://api.contactout.com/)
- [Findymail API](https://www.findymail.com/api/)
- [Prospeo Enrich Person API](https://prospeo.io/api-docs/enrich-person)
- [Prospeo Social URL Enrichment](https://prospeo.io/api-docs/social-url-enrichment)
- [Snov.io API](https://snov.io/api)
- [Snov.io LinkedIn Enrichment KB](https://snov.io/knowledgebase/how-to-enrich-your-data-via-snov-io-api/)
- [RocketReach People Lookup API](https://docs.rocketreach.co/reference/people-lookup-api)
- [PeopleDataLabs Person Enrichment](https://docs.peopledatalabs.com/docs/reference-person-enrichment-api)
- [PeopleDataLabs Input Parameters](https://docs.peopledatalabs.com/docs/input-parameters-person-enrichment-api)
- [Datagma API Getting Started](https://datagmaapi.readme.io/reference/getting-started-with-your-api)
- [Kaspr API](https://www.kaspr.io/api)
- [Kaspr API Docs — Stoplight](https://kaspr.stoplight.io/docs/kaspr-api/branches/main/51f7f5ce88a29-get-linked-in-profile)
- [Icypeas](https://www.icypeas.com/)
- [Hunter.io API Documentation](https://hunter.io/api-documentation)
- [Hunter LinkedIn Handle Support](https://hunter.io/changelog/linkedin-handle-support-new-api-endpoints-2/)

### Pricing
- [Apollo Pricing](https://www.apollo.io/pricing)
- [ContactOut Pricing](https://contactout.com/pricing)
- [Findymail Pricing](https://www.findymail.com/pricing/)
- [Prospeo Pricing](https://prospeo.io/pricing)
- [Snov.io Pricing](https://snov.io/pricing)
- [RocketReach Pricing](https://rocketreach.co/pricing)
- [PeopleDataLabs Pricing](https://www.peopledatalabs.com/pricing/person)
- [Datagma Pricing](https://datagma.com/pricing/)
- [Kaspr Pricing](https://www.kaspr.io/pricing)
- [Icypeas Pricing](https://www.icypeas.com/pricing)
- [Hunter.io Pricing](https://hunter.io/pricing)

### Waterfall & Comparison
- [Waterfall Enrichment Guide 2025 — LeadDelta](https://leaddelta.com/waterfall-enrichment/)
- [Waterfall Enrichment Comparison — Persana](https://persana.ai/blogs/waterfall-enrichment-comparison)
- [Best Waterfall Enrichment Tools — Surfe](https://www.surfe.com/blog/4-best-waterfall-enrichment-tools/)
- [Best Data Enrichment APIs 2025 — CUFinder](https://cufinder.io/blog/best-data-enrichment-apis/)

### Sales Navigator Export
- [Export Leads from Sales Navigator — Skrapp](https://skrapp.io/blog/export-leads-from-sales-navigator/)
- [Export Sales Navigator Lists — Surfe](https://www.surfe.com/blog/how-to-export-sales-navigator-lists-to-a-csv-file/)
- [Export Sales Navigator to Excel — Evaboot](https://evaboot.com/blog/export-leads-linkedin-sales-navigator)
- [Sales Navigator Lead List Export — Kaspr](https://www.kaspr.io/blog/sales-navigator-lead-list-export)
