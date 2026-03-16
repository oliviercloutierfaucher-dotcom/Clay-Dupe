# Domain Finding Research: Company Name to Website Domain

> **Last Updated:** 2026-03-08
> **Status:** Comprehensive research complete
> **Purpose:** Map the landscape of techniques and APIs for resolving company names to website domains — the critical first step before email enrichment.

---

## Table of Contents

1. [Why Domain Finding Matters](#1-why-domain-finding-matters)
2. [Search Engine APIs](#2-search-engine-apis)
3. [Dedicated Name-to-Domain APIs](#3-dedicated-name-to-domain-apis)
4. [Sales Intelligence APIs](#4-sales-intelligence-apis)
5. [Data Provider APIs](#5-data-provider-apis)
6. [WHOIS Reverse Lookup](#6-whois-reverse-lookup)
7. [Free and Low-Cost Approaches](#7-free-and-low-cost-approaches)
8. [Domain Validation](#8-domain-validation)
9. [Domain Normalization](#9-domain-normalization)
10. [Name-to-Domain Matching Challenges](#10-name-to-domain-matching-challenges)
11. [Recommended Architecture](#11-recommended-architecture)
12. [Cost Comparison Matrix](#12-cost-comparison-matrix)

---

## 1. Why Domain Finding Matters

Domain finding is the **single most critical step** in the email enrichment pipeline. Without a correct domain:

- **Email waterfall is useless** — patterns like `firstname.lastname@domain.com` require the right domain
- **Wrong domain = wasted API calls** — every downstream enrichment call (Hunter, Apollo, etc.) is burned on incorrect data
- **Garbage in, garbage out** — a wrong domain propagates through the entire pipeline, corrupting contact data
- **Many input lists only have company names** — especially CRM exports, event attendee lists, and manually compiled prospect lists

### The Domain Finding Pipeline Position

```
[Company Name] --> [DOMAIN FINDING] --> [Domain] --> [Email Pattern] --> [Email Waterfall] --> [Verified Email]
                   ^^^^^^^^^^^^^^^^^
                   THIS IS THE BOTTLENECK
```

If domain finding has 80% accuracy, even a perfect email waterfall can only achieve 80% max output quality.

---

## 2. Search Engine APIs

### 2.1 Google Custom Search JSON API

**Status:** Available but closing to new customers. Existing customers must migrate by January 1, 2027.

| Detail | Value |
|--------|-------|
| **Free Tier** | 100 queries/day |
| **Paid Tier** | $5 per 1,000 queries (max 10,000/day) |
| **Cost per Domain** | ~$0.005 (1 query per company) |
| **New Signups** | Closed to new customers |
| **Shutdown Date** | January 1, 2027 |
| **Replacement** | Vertex AI Search (enterprise pricing, no public rates) |

**How to Use for Domain Finding:**
1. Search query: `"Company Name" official website`
2. Parse JSON results — extract URLs from top 10 results
3. Filter out social media, directories, and review sites
4. Score remaining URLs by:
   - Position in search results (lower = better)
   - Domain name similarity to company name
   - Title tag containing company name
   - Absence of path components (root domain preferred)

**Domains to Exclude (Blocklist):**
```
linkedin.com, facebook.com, twitter.com, instagram.com,
crunchbase.com, glassdoor.com, yelp.com, bbb.org,
bloomberg.com, zoominfo.com, dnb.com, indeed.com,
yellowpages.com, manta.com, pitchbook.com, owler.com,
g2.com, trustpilot.com, capterra.com, wikipedia.org
```

**Verdict:** Best accuracy for domain finding but sunsetting. Not viable for new projects.

### 2.2 Serper.dev (Google Search API Alternative)

**Status:** Active, recommended Google Search API replacement.

| Detail | Value |
|--------|-------|
| **Free Tier** | 2,500 searches on signup (expires in 6 months) |
| **Paid Tier** | $50/month for 50,000 searches |
| **Cost per Search** | ~$0.001 at scale |
| **Response Time** | 1-2 seconds average |
| **Output** | Structured JSON (same as Google results) |

**Advantages:**
- Cheapest Google Search proxy available
- Returns structured JSON identical to Google results
- Same filtering/scoring logic as Google Custom Search
- No shutdown date announced
- No credit card required for free tier

**Verdict:** Best replacement for Google Custom Search API. Excellent for domain finding at scale.

### 2.3 Brave Search API

**Status:** Active, independent search index.

| Detail | Value |
|--------|-------|
| **Free Tier** | $5 free credit/month (~1,000 queries) for new users |
| **Legacy Free** | Existing users retain 2,000 queries/month free |
| **Paid Tier** | $5 per 1,000 requests |
| **Cost per Search** | $0.005 |

**Note:** Requires attribution in your project's website/about page to receive free credit.

**Verdict:** Good backup option. Independent index means different results than Google — useful as a secondary signal.

### 2.4 Bing Web Search API

**Status:** DISCONTINUED as of August 11, 2025.

| Detail | Value |
|--------|-------|
| **Status** | Retired — all endpoints dark |
| **Replacement** | Azure AI Agents ($35 per 1,000 queries) |

**Verdict:** Dead. Do not use. Azure AI Agents replacement is 7x more expensive than alternatives.

### 2.5 DuckDuckGo Instant Answer API

**Status:** Active but severely limited for domain finding.

| Detail | Value |
|--------|-------|
| **Free Tier** | Completely free |
| **Rate Limit** | 20 requests/second |
| **Output** | Instant answers only — NOT full search results |

**Critical Limitation:** Does not return full search result URLs. Only returns "instant answer" snippets. This makes it **nearly useless for domain finding** — you need the full search result URLs to extract company domains.

**Verdict:** Not useful for domain finding. The API does not return the data we need.

### 2.6 SerpAPI

**Status:** Active, premium SERP API.

| Detail | Value |
|--------|-------|
| **Free Tier** | 100 searches/month |
| **Developer Tier** | $75/month for 5,000 searches |
| **Cost per Search** | $0.015 (Developer) to $0.005 (Enterprise) |
| **Engines** | 80+ search engines |

**Verdict:** More expensive than Serper.dev for the same functionality. Only justified if you need multi-engine support.

---

## 3. Dedicated Name-to-Domain APIs

### 3.1 Clearbit Name-to-Domain API

**Status:** Free tier sunsetted April 30, 2025. Paid API still available through HubSpot/Clearbit subscription. Transitioning to "Breeze Intelligence."

| Detail | Value |
|--------|-------|
| **Free Tier** | Gone (sunsetted April 30, 2025) |
| **Paid Access** | Requires Clearbit/HubSpot subscription |
| **API Endpoint** | `https://company.clearbit.com/v1/domains/find?name=CompanyName` |
| **Accuracy** | Was considered industry-leading |

**Historical Context:**
- Was the gold standard for name-to-domain resolution
- Acquired by HubSpot in December 2023
- Free tools systematically sunsetted throughout 2025
- Logo API also sunset December 1, 2025
- Now rebranded as "Breeze Intelligence" within HubSpot

**Verdict:** No longer viable unless you already have a HubSpot/Clearbit subscription. Not recommended for new integrations.

### 3.2 FindCompanyDomain.com

**Status:** Active, purpose-built for name-to-domain resolution.

| Detail | Value |
|--------|-------|
| **Free Tier** | 500 credits (no expiration) |
| **Mid Tier** | 10,000 credits for $30 |
| **Enterprise** | 50,000 credits for $150 |
| **Cost per Lookup** | $0.003 at scale |
| **Accuracy Claim** | 98% verified domain matching |

**Technical Approach:**
- Multi-source cross-referencing with intelligent matching
- Handles brand names, holding companies, abbreviations, and rebranded businesses
- Returns official website URL and email structure/pattern
- REST API with bulk upload (10k+ rows)
- CRM and enrichment pipeline integration

**Verdict:** Cheapest dedicated name-to-domain API. Good accuracy claims. Worth testing as primary or secondary source.

### 3.3 EnrichmentAPI.io

**Status:** Active, broader enrichment with name-to-domain capability.

| Detail | Value |
|--------|-------|
| **Free Tier** | 50 free credits |
| **Basic** | $99/month for 25,000 credits |
| **Standard** | $199/month for 65,000 credits |
| **Premium** | $599/month for 300,000 credits |
| **Cost per Lookup** | ~$0.004 (Basic) to $0.002 (Premium) |

**Returns:** Domain, location, phone, industry, social media links.

**Verdict:** More expensive than FindCompanyDomain but returns richer data. Consider if you need industry/location alongside domain.

### 3.4 Marcom Robot (ProspectingAI)

**Status:** Active.

| Detail | Value |
|--------|-------|
| **Cost per Domain** | $0.069 |
| **Plan** | $69/month |

**Verdict:** Too expensive compared to alternatives. No clear advantage.

### 3.5 Hunter.io Domain Search

**Status:** Active. Can search by company name to find domain + emails.

| Detail | Value |
|--------|-------|
| **Free Tier** | 25 searches/month |
| **Paid Plans** | Start at $49/month |
| **Cost per Search** | 1 credit per 10 email results |
| **Rate Limit** | 15 req/sec, 500 req/min |
| **Input** | Company name OR domain |

**Key Detail:** Hunter accepts company name as input (not just domain). If it finds the company, it returns both the domain and associated emails in one call.

**Verdict:** Useful as a two-in-one tool — gets domain AND emails simultaneously. Limited free tier makes it better as a paid enrichment step rather than primary domain finder.

---

## 4. Sales Intelligence APIs

### 4.1 Apollo.io Organization Search

**Status:** Active, comprehensive sales intelligence platform.

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST https://api.apollo.io/api/v1/mixed_companies/search` |
| **Free Plan** | Available (limited credits) |
| **Basic Plan** | $49/user/month |
| **Credit Cost** | 1 credit per enrichment |
| **Display Limit** | 50,000 records (100/page, 500 pages max) |

**Response Data Includes:**
- Company website/domain URL
- LinkedIn and social media URLs
- Industry classification
- Employee count
- Funding information
- Technology stack
- Location data

**How to Use for Domain Finding:**
1. Search by company name using the organization search endpoint
2. Extract `website_url` from the response
3. Normalize the domain (strip protocol, www, path)

**Verdict:** Already integrated in our stack via MCP tools. Can pull domain as part of broader enrichment. Consumes credits though — not ideal for domain-only lookups at scale.

### 4.2 Apollo MCP Tool (Already Available)

We already have `mcp__claude_ai_Apollo_io__apollo_mixed_companies_search` and `mcp__claude_ai_Apollo_io__apollo_organizations_enrich` available. These can be used directly for company name to domain resolution.

---

## 5. Data Provider APIs

### 5.1 PeopleDataLabs Company Search

**Status:** Active.

| Detail | Value |
|--------|-------|
| **Endpoint** | `https://api.peopledatalabs.com/v5/company/search` |
| **Free Tier** | 100 records/month |
| **Pro Plan** | $100/month for 1,000+ records |
| **Cost per Record** | 1 credit per company profile |

**Verdict:** Expensive for domain-only lookups. Better suited when you need comprehensive company data alongside the domain.

### 5.2 Crunchbase API

**Status:** Active with limited free tier.

| Detail | Value |
|--------|-------|
| **Free (Basic)** | Limited access to profiles |
| **Pro Plan** | $29/month |
| **Enterprise** | Custom pricing |
| **API Access** | Requires paid plan for programmatic access |

**Data Available:** Company domain/website, funding data, employee count, social profiles.

**Verdict:** Useful for startup/tech companies (Crunchbase coverage is strong there). Poor coverage of SMBs and traditional businesses.

---

## 6. WHOIS Reverse Lookup

### How It Works
Search WHOIS registration records by company/organization name to find domains they registered.

### Key Providers

| Provider | Database Size | Pricing |
|----------|---------------|---------|
| **WhoisXML API** | Billions of records | Tiered pricing |
| **Whoxy** | Large | `api.whoxy.com/?key=xxx&reverse=whois&company=Acme+Corporation` |
| **WhoisFreaks** | Terabytes of WHOIS data | Tiered pricing |

### Limitations
- **WHOIS privacy:** Many domains use privacy protection, hiding the registrant company name
- **Registrant name mismatch:** Domains may be registered under a parent company, subsidiary, or holding entity
- **Historical data:** May return expired/transferred domains
- **Coverage gaps:** Newer TLDs and privacy-focused registrars provide minimal WHOIS data

**Verdict:** Useful as a supplementary signal but unreliable as a primary method. WHOIS privacy adoption has made this approach increasingly ineffective.

---

## 7. Free and Low-Cost Approaches

### 7.1 DNS-Based Domain Guessing (Free)

**Concept:** Generate candidate domains from the company name and check if they resolve.

```python
import dns.resolver

def guess_domain(company_name):
    """Try common domain patterns for a company name."""
    # Normalize: lowercase, remove common suffixes, strip spaces
    name = company_name.lower()
    for suffix in [' inc', ' llc', ' ltd', ' corp', ' corporation',
                   ' company', ' co', ' group', ' holdings']:
        name = name.replace(suffix, '')
    name = name.strip()

    # Generate candidates
    slug = name.replace(' ', '')
    slug_dash = name.replace(' ', '-')
    candidates = [
        f"{slug}.com",
        f"{slug}.io",
        f"{slug}.co",
        f"{slug}.net",
        f"{slug}.org",
        f"{slug}.ai",
        f"{slug_dash}.com",
        f"{slug_dash}.io",
    ]

    results = []
    for domain in candidates:
        try:
            dns.resolver.resolve(domain, 'A')
            results.append(domain)
        except:
            pass
    return results
```

**Pros:**
- Completely free — no API costs
- Fast DNS lookups (~50ms each)
- No rate limiting concerns

**Cons:**
- Low accuracy (~30-40% for common company names)
- Returns false positives (e.g., `apple.com` for a company named "Apple Orchards LLC")
- Cannot distinguish between parked domains and real company sites
- Fails for companies whose domain doesn't match their name

### 7.2 DNS MX Record Validation (Free)

After finding a candidate domain, verify it can receive email:

```python
import dns.resolver

def has_mx_records(domain):
    """Check if domain has MX records (can receive email)."""
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        return len(answers) > 0
    except:
        return False
```

**Python Libraries for Validation:**
- `email-validator` — syntax + DNS MX validation
- `py3-validate-email` — DNS MX + SMTP checking
- `dns-smtp-email-validator` — multi-level validation (format, domain, MX, SMTP)
- `dnspython` — low-level DNS queries (MX, A, AAAA records)

### 7.3 Google Search Scraping (Legally Gray)

**Legal Status:**
- hiQ Labs v. LinkedIn (2019, 2022): Court ruled scraping publicly available data doesn't violate CFAA
- However, scraping Google **violates Google's Terms of Service**
- Google hasn't aggressively pursued legal action but may serve CAPTCHAs, IP bans

**Rate Limiting:**
- Recommended: Max 1 request per 2-3 seconds
- Use rotating proxies and random delays
- Risk of IP bans and CAPTCHA walls

**Verdict:** Not recommended for production systems. Legal gray area, unreliable at scale, and maintenance burden is high. Use a proper SERP API instead ($0.001/query with Serper is negligible cost).

### 7.4 Open Datasets

- **Wikidata/Wikipedia:** Has website URLs for notable companies (API access free)
- **OpenCorporates:** Corporate registry data, sometimes includes websites
- **Common Crawl:** Free web crawl data — can be mined for company-domain associations
- **SEC EDGAR:** US public companies with website URLs in filings

### 7.5 The `duckduckgo-search` Python Package

```python
from duckduckgo_search import DDGS

def find_domain_ddg(company_name):
    """Use DuckDuckGo search to find company domain."""
    with DDGS() as ddgs:
        results = list(ddgs.text(f"{company_name} official website", max_results=5))
        # Filter and score results similar to Google approach
        return results
```

**Note:** This is an unofficial scraping library, not the official API. Subject to rate limiting and breakage.

---

## 8. Domain Validation

### 8.1 Multi-Step Validation Pipeline

After finding a candidate domain, validate it through multiple checks:

```
[Candidate Domain] --> [DNS Resolution] --> [MX Records] --> [Content Analysis] --> [Confirmed Domain]
```

### 8.2 Validation Steps

#### Step 1: DNS Resolution
```python
# Does the domain resolve to an IP address?
dns.resolver.resolve(domain, 'A')  # IPv4
dns.resolver.resolve(domain, 'AAAA')  # IPv6
```

#### Step 2: MX Record Check
```python
# Can the domain receive email? (Critical for email enrichment)
answers = dns.resolver.resolve(domain, 'MX')
# At least one valid MX record = domain can receive email
```

#### Step 3: HTTP Response Check
```python
# Does the domain serve a website?
response = requests.get(f"https://{domain}", timeout=10, allow_redirects=True)
# Check for 200 OK
# Track redirect chain (company.com might redirect to parent.com)
final_domain = urlparse(response.url).netloc
```

#### Step 4: Content Analysis (Optional, Higher Confidence)
```python
# Does the homepage mention the company name?
from bs4 import BeautifulSoup
soup = BeautifulSoup(response.text, 'html.parser')
title = soup.title.string if soup.title else ''
# Check if company name appears in title, meta description, or H1
```

### 8.3 Edge Cases to Handle

| Scenario | How to Handle |
|----------|---------------|
| **Domain redirects** | Follow redirects, use final domain. Log both. |
| **Parent vs subsidiary** | Check if redirect goes to parent domain. Flag for review. |
| **Multiple domains** | Company may have regional domains (co.uk, .de). Store primary + alternates. |
| **No website** | DNS resolves but no HTTP response. Domain may still receive email — check MX. |
| **Parked domain** | DNS resolves, HTTP works, but content is generic parking page. Detect and reject. |
| **Regional variations** | company.com vs company.co.uk — prefer .com unless country context says otherwise. |
| **Companies with no website** | Mark as "no domain found" rather than guessing. Better to skip than enrich wrong. |

### 8.4 Parked Domain Detection

Signs of a parked domain:
- Page contains "This domain is for sale"
- Hosted on GoDaddy, Sedo, Afternic parking pages
- Very short page content (<100 words)
- Contains only ads/affiliate links
- Title matches generic patterns ("Domain For Sale", "Coming Soon")

---

## 9. Domain Normalization

### 9.1 Normalization Rules

When processing domain inputs from any source, apply these transformations:

```python
from urllib.parse import urlparse
import tldextract

def normalize_domain(raw_input):
    """
    Normalize any URL or domain input to a clean root domain.

    Examples:
        "https://www.acme.com/about"  --> "acme.com"
        "HTTP://WWW.ACME.COM"         --> "acme.com"
        "www.acme.com"                --> "acme.com"
        "blog.acme.com"               --> "acme.com"
        "acme.com/"                   --> "acme.com"
        "acme.com"                    --> "acme.com"
    """
    raw = raw_input.strip().lower()

    # Add scheme if missing (needed for urlparse)
    if not raw.startswith(('http://', 'https://')):
        raw = 'https://' + raw

    # Parse URL
    parsed = urlparse(raw)
    hostname = parsed.netloc or parsed.path

    # Remove port
    hostname = hostname.split(':')[0]

    # Use tldextract for accurate domain extraction
    extracted = tldextract.extract(hostname)
    # Returns: ExtractResult(subdomain='www', domain='acme', suffix='com')

    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    return hostname
```

### 9.2 Why `tldextract` Over Simple String Operations

Naive approaches fail on multi-level TLDs:
- `forums.bbc.co.uk` — naive split gives `co.uk`, correct is `bbc.co.uk`
- `app.company.com.au` — naive split gives `com.au`, correct is `company.com.au`

`tldextract` uses the Public Suffix List (PSL) maintained by Mozilla to correctly handle all TLDs including:
- Country-code TLDs: `.co.uk`, `.com.au`, `.co.jp`
- New TLDs: `.company`, `.technology`, `.solutions`
- Special cases: `.github.io`, `.herokuapp.com`

### 9.3 Subdomain Handling

| Subdomain | Keep or Strip? | Reason |
|-----------|----------------|--------|
| `www.` | Strip | Standard alias, not meaningful |
| `blog.` | Strip | Subdomain of main domain |
| `app.` | Strip | Subdomain of main domain |
| `mail.` | Strip | Email subdomain |
| `shop.` | Strip — but note | E-commerce subdomain, main domain is the company |
| `*.github.io` | **Keep** | This IS the domain (no parent) |
| `*.herokuapp.com` | **Keep** | Platform-hosted, this IS the domain |
| `*.wordpress.com` | **Keep** | Platform-hosted site |

### 9.4 Common Input Variations

```python
# All of these should normalize to "acme.com":
inputs = [
    "acme.com",
    "www.acme.com",
    "https://acme.com",
    "http://www.acme.com",
    "https://www.acme.com/about-us",
    "ACME.COM",
    "acme.com/",
    "  acme.com  ",
]
```

---

## 10. Name-to-Domain Matching Challenges

### 10.1 Company Name Variations

| Variation Type | Examples | Handling Strategy |
|---------------|----------|-------------------|
| **Legal suffixes** | Inc, LLC, Ltd, Corp, GmbH, S.A. | Strip before matching |
| **Abbreviations** | IBM = International Business Machines | Maintain acronym lookup table |
| **"The" prefix** | The Boeing Company | Strip "The" |
| **Ampersand** | Johnson & Johnson | Try both `johnsonandjohnson` and `johnson-johnson` |
| **Punctuation** | AT&T, H&M, Yahoo! | Strip and try variations |
| **Numbers** | 3M, 7-Eleven | Keep numbers, try both spelled-out and digit forms |

### 10.2 Disambiguation Challenges

When a company name matches multiple organizations:
- "Mercury" — Mercury Financial? Mercury Insurance? Mercury Systems?
- "Atlas" — Atlas Copco? Atlas Air? Atlas Van Lines?
- "Apex" — hundreds of companies named Apex

**Mitigation Strategies:**
1. **Add context:** Include industry, location, or description in search query
2. **Multi-signal scoring:** Cross-reference company size, industry, location against returned results
3. **Human review flag:** When confidence is low, flag for manual review rather than guessing

### 10.3 Fuzzy Matching Techniques

**Standard Approaches:**
- **Levenshtein distance:** Edit distance between strings (good for typos)
- **Jaro-Winkler:** Emphasizes prefix similarity (good for company names)
- **Cosine similarity with TF-IDF:** Handles word reordering
- **Word embeddings:** Understands that "Corporation" and "Corp" are semantically similar

**Practical Pipeline:**
```
1. Exact match (preprocessed)     --> 100% confidence
2. Exact match (after suffix stripping) --> 95% confidence
3. Cosine similarity > 0.9        --> 85% confidence
4. Fuzzy match (Jaro-Winkler > 0.85) --> 70% confidence
5. No match                        --> Flag for review
```

### 10.4 Companies That Changed Names or Were Acquired

| Old Name | New Name | Domain Change |
|----------|----------|--------------|
| Facebook | Meta | facebook.com still works, meta.com is new |
| Google | Alphabet (parent) | google.com unchanged |
| Salesforce | Salesforce (acquired Slack) | slack.com still works |
| Twitter | X | twitter.com redirects to x.com |

**Strategy:** Maintain a mapping table of known acquisitions/renames. Check if domain redirects to a different domain and capture both.

---

## 11. Recommended Architecture

### 11.1 Multi-Source Domain Finding Waterfall

```
Input: Company Name (+ optional: industry, location, description)
│
├─ Step 1: Database Lookup (cached results)
│  └─ Check if we've already resolved this company name
│     Cost: $0 (local cache)
│
├─ Step 2: DNS Guessing (free)
│  └─ Try companyname.com, companyname.io, etc.
│  └─ Validate with MX record check
│     Cost: $0 (DNS queries are free)
│
├─ Step 3: FindCompanyDomain API
│  └─ Dedicated name-to-domain service
│     Cost: $0.003/lookup
│
├─ Step 4: Serper.dev Google Search
│  └─ Search "company name official website"
│  └─ Parse and score results, exclude social/directories
│     Cost: $0.001/search
│
├─ Step 5: Apollo Organization Search
│  └─ Search by company name, extract domain
│     Cost: 1 Apollo credit
│
├─ Step 6: Hunter.io Company Search
│  └─ Gets domain AND emails in one call
│     Cost: 1 Hunter credit
│
└─ Step 7: Flag for Manual Review
   └─ If no method found the domain with high confidence
      Cost: Human time
```

### 11.2 Confidence Scoring

Each source returns a domain with a confidence score:

| Source | Base Confidence | Boost Factors |
|--------|----------------|---------------|
| DNS guess + MX valid | 40% | +20% if company name is in the domain |
| FindCompanyDomain | 80% | API's own confidence score |
| Serper (Google #1 result) | 75% | +15% if domain contains company name |
| Apollo match | 85% | Apollo's matching quality |
| Hunter match | 80% | Hunter's matching quality |
| Multiple sources agree | 95%+ | Consensus = high confidence |

**Decision Rule:** Accept domain when confidence > 70%. If multiple sources return the same domain, confidence is automatically 95%+.

### 11.3 Caching Strategy

- Cache all resolved company-name-to-domain mappings
- Cache negative results too (prevent re-querying companies with no domain)
- TTL: 30-90 days (company domains rarely change)
- Key: Normalized company name (lowercase, suffix-stripped)

---

## 12. Cost Comparison Matrix

### Per-Lookup Costs (Domain Finding Only)

| Method | Cost per Lookup | Free Tier | Best For |
|--------|----------------|-----------|----------|
| DNS Guessing | $0.000 | Unlimited | First-pass filter |
| Serper.dev | $0.001 | 2,500 free | Bulk domain finding |
| FindCompanyDomain | $0.003 | 500 free | Dedicated domain resolution |
| Google Custom Search | $0.005 | 100/day | Legacy (sunsetting) |
| Brave Search | $0.005 | ~1,000/month | Secondary signal |
| EnrichmentAPI | $0.004 | 50 free | Domain + enrichment |
| Hunter.io | ~$0.05+ | 25/month | Domain + emails combo |
| Apollo | 1 credit | Limited | Already in stack |
| PeopleDataLabs | ~$0.10 | 100/month | Full company data |
| SerpAPI | $0.005-0.015 | 100/month | Multi-engine search |
| Clearbit | Subscription | None (sunsetted) | HubSpot customers only |

### Monthly Budget Scenarios

| Volume | Budget Approach | Estimated Monthly Cost |
|--------|----------------|----------------------|
| 100 companies | Free tiers only | $0 |
| 1,000 companies | DNS guess + Serper | ~$1 |
| 5,000 companies | DNS guess + FindCompanyDomain + Serper fallback | ~$20 |
| 10,000 companies | Full waterfall | ~$40-60 |
| 50,000 companies | Full waterfall + caching | ~$150-200 |

### Key Recommendations

1. **Always start with DNS guessing** — it's free and catches ~30-40% of cases
2. **Serper.dev is the best value** for search-based domain finding at $0.001/query
3. **FindCompanyDomain is the best dedicated API** at $0.003/lookup with 98% claimed accuracy
4. **Cache aggressively** — domain resolutions rarely change
5. **Use multiple sources** for high-confidence results — if 2+ sources agree, trust the domain
6. **Don't use Clearbit** for new integrations — it's locked behind HubSpot now
7. **Don't scrape Google directly** — SERP APIs are cheap enough to not justify the legal/technical risk
8. **Always validate with MX records** — a domain without MX records can't receive email

---

## Appendix: Key Technical References

### Python Libraries

| Library | Purpose | Install |
|---------|---------|---------|
| `tldextract` | Domain extraction from URLs | `pip install tldextract` |
| `dnspython` | DNS queries (MX, A records) | `pip install dnspython` |
| `email-validator` | Email + domain validation | `pip install email-validator` |
| `url-normalize` | URL normalization | `pip install url-normalize` |
| `fuzzywuzzy` | Fuzzy string matching | `pip install fuzzywuzzy` |
| `duckduckgo-search` | DuckDuckGo search (unofficial) | `pip install duckduckgo-search` |

### API Documentation Links

- [Google Custom Search API](https://developers.google.com/custom-search/v1/overview)
- [Serper.dev](https://serper.dev/)
- [Brave Search API](https://api-dashboard.search.brave.com/documentation/pricing)
- [Apollo Organization Search](https://docs.apollo.io/reference/organization-search)
- [Hunter.io Domain Search](https://hunter.io/api/domain-search)
- [PeopleDataLabs Company Search](https://docs.peopledatalabs.com/docs/company-search-api)
- [FindCompanyDomain](https://findcompanydomain.com/)
- [EnrichmentAPI.io](https://enrichmentapi.io/company-name-to-domain-api/)
- [Whoxy Reverse WHOIS](https://www.whoxy.com/reverse-whois/)
