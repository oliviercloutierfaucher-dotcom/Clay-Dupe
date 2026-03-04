# Clay-Dupe: Self-Hosted B2B Enrichment Platform

## Overview

A self-hosted alternative to Clay for B2B data enrichment. Focused on finding emails, domains, and LinkedIn URLs for niche businesses (A&D, medical device, niche industrial) with 1-15M EBITDA, 10-100 employees in US, UK, and Canada.

**Tech Stack:** Python + FastAPI (backend) + Streamlit (team web UI) + CLI
**APIs:** Apollo, Findymail, Icypeas, ContactOut (waterfall enrichment)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    INTERFACES                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Streamlit UI │  │  CLI Tool   │  │  CSV Import  │ │
│  │ (team use)   │  │ (batch ops) │  │  /Export     │ │
│  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘ │
│         └─────────────┬───┘─────────────────┘        │
│                       ▼                              │
│  ┌────────────────────────────────────────────────┐  │
│  │            ENRICHMENT ENGINE                    │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │         Waterfall Orchestrator            │  │  │
│  │  │  (cascades through providers until hit)   │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │  ┌──────────┐┌──────────┐┌────────┐┌────────┐ │  │
│  │  │ Apollo   ││Findymail ││Icypeas ││Contact │ │  │
│  │  │ Provider ││ Provider ││Provider││  Out   │ │  │
│  │  └──────────┘└──────────┘└────────┘└────────┘ │  │
│  └────────────────────────────────────────────────┘  │
│                       ▼                              │
│  ┌────────────────────────────────────────────────┐  │
│  │              DATA LAYER                         │  │
│  │  SQLite DB (results cache + history)            │  │
│  │  CSV/Excel export                               │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## API Integration Map

### 1. Apollo.io
- **Use for:** Company search, people search, email finding, company enrichment
- **Key endpoints:**
  - `POST /v1/mixed_people/search` — Find people by company, title, location, employee count
  - `POST /v1/mixed_companies/search` — Find companies by industry, size, revenue
  - `POST /v1/people/match` — Enrich a person (get email from name + company)
  - `POST /v1/people/bulk_match` — Bulk enrich up to 10 people per call
  - `POST /v1/organizations/enrich` — Get company details from domain
- **Auth:** API key in header (`X-Api-Key` or `api_key` parameter)
- **Rate limits:** 50/min, 100/hour, 300/day (varies by plan)
- **Credits:** People search is free; enrichment costs credits
- **Best for:** Initial prospecting — finding target companies and people that match your ICP

### 2. Findymail
- **Use for:** Email finding + verification (highest deliverability)
- **Key endpoints:**
  - `POST /api/search/name` — Find email from first name, last name, domain
  - `POST /api/verify/single` — Verify a single email
  - `POST /api/search/domain` — Find all emails for a domain
- **Auth:** API key in `Authorization: Bearer <key>` header
- **Rate limits:** 300 concurrent requests, no daily cap
- **Credits:** 1 credit per email found, 10 per phone. Only charged on success.
- **Best for:** Second pass in waterfall — high accuracy email finding (98%+ valid, <5% bounce)

### 3. Icypeas
- **Use for:** Cheap email discovery + bulk operations
- **Key endpoints:**
  - `POST /api/email-search/single` — Find email from name + domain
  - `POST /api/email-search/bulk` — Bulk search up to 5,000 rows
  - `POST /api/email-verification` — Verify email
  - `POST /api/people-scraper` — Get job titles, company info
- **Auth:** API key in `Authorization` header
- **Rate limits:** 10 req/sec (single), 1 req/sec (bulk)
- **Credits:** 1 credit per verified email. Cheapest provider.
- **Best for:** Third pass in waterfall — catches what others miss, great for bulk

### 4. ContactOut
- **Use for:** LinkedIn-based email extraction
- **Key endpoints:**
  - `POST /v1/people/lookup` — Get email/phone from LinkedIn URL
  - `POST /v1/people/batch` — Batch lookup up to 30 LinkedIn profiles
  - `GET /v1/people/search` — Search by name + company
- **Auth:** API key in header
- **Rate limits:** Plan-dependent
- **Credits:** 1 credit per email, 1 credit per phone
- **Best for:** When you have LinkedIn URLs — highest hit rate for LinkedIn-sourced contacts

---

## Waterfall Enrichment Strategy

The core value prop — cascade through providers to maximize find rate while minimizing cost.

### Email Finding Waterfall (ordered by cost-effectiveness):

```
Input: first_name, last_name, domain (or company_name)
                    │
                    ▼
        ┌───────────────────┐
Step 1  │    Apollo.io       │  Free people search, credits for enrichment
        │  (broadest data)   │  Returns email? ──YES──► Done ✓
        └────────┬──────────┘
                 │ NO
                 ▼
        ┌───────────────────┐
Step 2  │    Icypeas         │  Cheapest per-credit cost
        │  (cost-effective)  │  Returns email? ──YES──► Done ✓
        └────────┬──────────┘
                 │ NO
                 ▼
        ┌───────────────────┐
Step 3  │   Findymail        │  Highest accuracy/deliverability
        │  (high accuracy)   │  Returns email? ──YES──► Done ✓
        └────────┬──────────┘
                 │ NO
                 ▼
        ┌───────────────────┐
Step 4  │   ContactOut       │  LinkedIn-based (requires LinkedIn URL)
        │  (LinkedIn data)   │  Returns email? ──YES──► Done ✓
        └────────┬──────────┘
                 │ NO
                 ▼
            Mark as "not found"
```

### Domain Finding Waterfall:
```
Input: company_name
    │
    ▼
1. Apollo organization search → domain
2. Clearbit Name-to-Domain API (free, 50k/mo) → domain
3. Google search fallback (programmatic)
```

### LinkedIn URL Finding:
```
Input: first_name, last_name, company
    │
    ▼
1. Apollo people search → linkedin_url
2. ContactOut people search → linkedin_url
3. Google search: "{name} {company} site:linkedin.com/in"
```

---

## Project Structure

```
Clay-Dupe/
├── README.md
├── PLAN.md
├── requirements.txt
├── .env.example              # Template for API keys
├── .gitignore
│
├── config/
│   └── settings.py           # App config, API key loading, waterfall order
│
├── providers/                 # API provider integrations
│   ├── __init__.py
│   ├── base.py               # Base provider class (interface)
│   ├── apollo.py             # Apollo.io integration
│   ├── findymail.py          # Findymail integration
│   ├── icypeas.py            # Icypeas integration
│   └── contactout.py         # ContactOut integration
│
├── enrichment/                # Core enrichment logic
│   ├── __init__.py
│   ├── waterfall.py          # Waterfall orchestrator
│   ├── email_finder.py       # Email finding pipeline
│   ├── domain_finder.py      # Domain lookup pipeline
│   ├── linkedin_finder.py    # LinkedIn URL pipeline
│   └── company_enricher.py   # Company data enrichment
│
├── data/                      # Data handling
│   ├── __init__.py
│   ├── models.py             # Data models (Company, Person, EnrichmentResult)
│   ├── database.py           # SQLite cache/history
│   └── io.py                 # CSV/Excel import/export
│
├── ui/                        # Streamlit web interface
│   ├── app.py                # Main Streamlit app
│   ├── pages/
│   │   ├── search.py         # Company/people search page
│   │   ├── enrich.py         # Enrichment page (upload + enrich)
│   │   ├── results.py        # Results browser + export
│   │   └── settings.py       # API key management + waterfall config
│   └── components/
│       └── data_table.py     # Interactive data table component
│
├── cli/                       # Command-line interface
│   ├── __init__.py
│   └── main.py               # CLI entry point (click/typer)
│
└── tests/
    ├── test_providers.py
    ├── test_waterfall.py
    └── test_enrichment.py
```

---

## Implementation Phases

### Phase 1: Foundation (Core Infrastructure)
1. Project scaffolding (requirements.txt, .env, .gitignore, config)
2. Data models (Company, Person, EnrichmentResult)
3. Base provider interface
4. SQLite cache layer (avoid duplicate API calls, save money)

### Phase 2: API Providers
5. Apollo.io provider (company search, people search, email enrichment)
6. Findymail provider (email finder, verifier)
7. Icypeas provider (email finder, bulk search)
8. ContactOut provider (LinkedIn-based lookup)

### Phase 3: Enrichment Engine
9. Waterfall orchestrator (cascade through providers)
10. Email finding pipeline
11. Domain finding pipeline
12. LinkedIn URL finding pipeline
13. Company enrichment pipeline

### Phase 4: Interfaces
14. CLI tool (CSV input → enriched CSV output)
15. Streamlit UI — Search page (find companies matching ICP)
16. Streamlit UI — Enrich page (upload CSV, run enrichment)
17. Streamlit UI — Results page (browse, filter, export)
18. Streamlit UI — Settings page (API keys, waterfall config)

### Phase 5: ICP-Specific Features
19. ICP filter presets (A&D, medical device, niche industrial)
20. EBITDA/employee count filtering via Apollo
21. Geography filtering (US, UK, Canada)
22. Saved searches and templates

---

## API Keys Required

| Provider   | Get API key at                          | Estimated cost          |
|------------|----------------------------------------|-------------------------|
| Apollo.io  | https://app.apollo.io/#/settings/api   | Free tier available     |
| Findymail  | https://app.findymail.com/settings/api | From $41/mo (1k credits)|
| Icypeas    | https://app.icypeas.com/api-key        | Cheapest per credit     |
| ContactOut | https://contactout.com/dashboard/api   | From $99/year           |

### .env file format:
```
APOLLO_API_KEY=your_apollo_key_here
FINDYMAIL_API_KEY=your_findymail_key_here
ICYPEAS_API_KEY=your_icypeas_key_here
CONTACTOUT_API_KEY=your_contactout_key_here

# Optional: for domain finding
CLEARBIT_API_KEY=your_clearbit_key_here

# Waterfall order (customize priority)
WATERFALL_ORDER=apollo,icypeas,findymail,contactout

# Cache settings
CACHE_TTL_DAYS=30
```

---

## Key Design Decisions

1. **SQLite cache** — Every API result is cached locally. If you look up the same person twice, you don't burn credits. Cache TTL is configurable (default 30 days).

2. **Waterfall order is configurable** — Default: Apollo → Icypeas → Findymail → ContactOut. But you can reorder based on your credit balances and hit rates.

3. **Pay-on-success tracking** — Dashboard shows credits consumed per provider, hit rates, and cost per successful lookup. This lets you optimize which providers to prioritize.

4. **Batch processing** — Upload a CSV of 500+ companies, walk away, come back to enriched results. Uses async processing with progress tracking.

5. **Team access** — Streamlit runs on a local network. Multiple team members can use it simultaneously. No per-seat fees.

6. **ICP presets** — Pre-configured filters for your target market (A&D, medical device, niche industrial; 1-15M EBITDA; 10-100 employees; US/UK/Canada).

---

## Cost Comparison vs Clay

| | Clay | Clay-Dupe |
|---|---|---|
| Monthly subscription | $149-$800+/mo | $0 |
| Per-credit markup | Clay adds margin on top of provider costs | Direct API costs only |
| Email enrichment | ~$0.05-0.10/lookup via Clay | ~$0.01-0.03/lookup direct |
| Hosting | Cloud (their servers) | Self-hosted (your machine) |
| Customization | Limited to Clay's UI | Fully customizable |
| Waterfall control | Clay decides order | You decide order |
