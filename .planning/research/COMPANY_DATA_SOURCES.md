# Private Company Data Sources — Comprehensive Research Report

**Target Profile:** Niche industrial, manufacturing, A&D, and medical device companies with 1-15M EBITDA and 10-100 employees in US, UK, Canada.

**Date:** 2026-03-08

---

## Table of Contents

1. [Company Discovery Sources](#1-company-discovery-sources)
2. [EBITDA Estimation for Private Companies](#2-ebitda-estimation-for-private-companies)
3. [Industry Classification (SIC/NAICS)](#3-industry-classification-sicnaics)
4. [Free/Cheap Company Data APIs](#4-freecheap-company-data-apis)
5. [Recommended Architecture for GPO Platform](#5-recommended-architecture-for-gpo-platform)

---

## 1. Company Discovery Sources

### 1.1 Apollo.io

**Coverage:** 210M+ contacts, 35M+ companies globally.

**Relevant Filters:**
- **Industry:** Extensive industry list + SIC/NAICS code filtering (can combine multiple codes)
- **Company type:** Public vs. Private filter
- **Employee count:** Range filter (e.g., 10-100)
- **Revenue:** Revenue range filter (estimated)
- **Geography:** Country, state, city filtering
- **Technologies:** Tech stack detection (65+ data attributes total)
- **Keywords:** Keyword search on company descriptions

**API:** Full REST API available. Organization Search endpoint for company discovery. Free tier available (limited credits).

**Coverage Gaps & Accuracy:**
- Claims 91% data accuracy, but independent reviews suggest **65-70% real-world accuracy**
- **Weak on small/niche companies** — data quality drops significantly for companies under 50 employees in niche industries
- **Revenue estimates for private companies are modeled, not verified** — accuracy for small private manufacturers is likely 40-60%
- **Strong US coverage, weak internationally** — accuracy drops to ~60% outside US
- **Phone numbers expensive (8 credits) and often inaccurate**

**Pricing:** Free tier available. Paid plans from $49/user/month (Basic) to $119/user/month (Organization).

**Verdict for GPO:** Good starting point for US-based industrial companies. Use as one source in a waterfall, not as sole source. Employee count data is more reliable than revenue data for small privates.

**Sources:**
- [Apollo Industry Filter Options](https://knowledge.apollo.io/hc/en-us/articles/4409230850189-Industry-Filter-Options)
- [Apollo Organization Search API](https://docs.apollo.io/reference/organization-search)
- [Apollo SIC Code Search](https://knowledge.apollo.io/hc/en-us/articles/4413193954189-Use-Apollo-Supported-SIC-Codes-in-a-Search)
- [Apollo.io Review - Revenue Reveal](https://revenuereveal.co/apollo-io-review/)

---

### 1.2 ZoomInfo

**Coverage:** 100M+ business profiles, including private companies.

**Data Available for Private Companies:**
- Company name, address, phone, website
- Employee count (modeled for privates)
- Revenue estimates (modeled — ML-based predictions)
- Industry classification (SIC/NAICS)
- Technographics (tech stack)
- Org charts and contacts
- Intent data and buying signals

**Revenue Estimate Accuracy:**
- **~50% accuracy for lower middle-market companies** (per Searchfunder community)
- Uses ML models trained on public company data extrapolated to privates
- 300+ human researchers supplement algorithmic data
- First-party data (from companies' own sites) reaches ~95% accuracy, but third-party estimates much lower

**Coverage Gaps:**
- Strongest at mid-enterprise and larger companies
- **Small private manufacturers (10-100 employees) are poorly covered** — these companies don't self-report
- Better for tech/SaaS companies than traditional manufacturing/industrial
- International coverage weaker than US

**Pricing:** Enterprise pricing only, typically $15,000-$40,000+/year. No free tier. No self-serve API.

**Verdict for GPO:** Best-in-class for contact enrichment, but expensive and revenue estimates for small private manufacturers are unreliable. Worth using for enrichment after initial discovery, not as primary discovery tool for this segment.

**Sources:**
- [ZoomInfo Data](https://www.zoominfo.com/data)
- [ZoomInfo Revenue Accuracy - Searchfunder](https://searchfunder.com/post/accuracy-of-zoominfos-revenue-data-for-deal-sourcing)
- [ZoomInfo Data Methodology](https://pipeline.zoominfo.com/sales/data-demystified-algorithms)

---

### 1.3 Crunchbase

**Coverage:** Primarily VC/PE-backed and tech companies. Weaker for bootstrapped industrial/manufacturing.

**Data Available:**
- Company profiles, founding date, location
- Funding rounds and investors
- Revenue estimates (for larger companies)
- Employee count
- Industry categories
- Acquisitions and IPO data

**API Access:**
- **Pro Plan:** $49/month — basic company data, limited searches
- **Business Plan:** $199/month — more data, exports
- **API Plan:** Custom pricing (contact sales) — full API with firmographics and advanced financials
- No meaningful free API tier for production use

**Coverage Gaps:**
- **Heavily biased toward VC-backed and tech companies**
- Small bootstrapped manufacturers rarely appear in Crunchbase
- Revenue estimates only available for larger companies
- Limited coverage of traditional industrial sectors

**Verdict for GPO:** Poor fit for niche industrial/manufacturing companies. Most target companies (bootstrapped, 10-100 employees, manufacturing) won't be in Crunchbase. Skip for primary discovery; may be useful to cross-reference PE-backed targets.

**Sources:**
- [Crunchbase Pricing](https://www.g2.com/products/crunchbase/pricing)
- [Crunchbase API](https://about.crunchbase.com/products/crunchbase-api/)
- [Crunchbase Free vs Paid](https://support.crunchbase.com/hc/en-us/articles/360062989313)

---

### 1.4 PitchBook

**Coverage:** Strongest for VC/PE deal data. 3.6M+ companies, focused on capital markets.

**Data Available:**
- Company profiles, financials, valuations
- Deal history (M&A, PE, VC transactions)
- Fund data and investor profiles
- Board members and executives
- Comparable company analysis

**API Access:**
- **Available** but enterprise-priced
- Custom quotes based on data scope and API call volume
- Typical pricing: $20,000/year (single user) to $60,000+/year (multi-user)
- No free tier or self-serve option

**Coverage Gaps:**
- Excellent for PE-backed companies
- **Weak for companies never touched by institutional capital** — most niche manufacturers
- Coverage skews toward larger deals (>$25M enterprise value)
- Limited data on companies below $5M revenue that haven't raised capital

**Verdict for GPO:** Useful for identifying companies already PE-backed or recently transacted, but most GPO targets (bootstrapped manufacturers) won't be covered. Too expensive for the coverage gap. Consider for enrichment of known targets only.

**Sources:**
- [PitchBook Data](https://pitchbook.com/data)
- [PitchBook Pricing](https://pitchbook.com/pricing)
- [PitchBook API](https://pitchbook.com/products/direct-access-data/api)

---

### 1.5 LinkedIn Sales Navigator

**Coverage:** 900M+ member profiles, 65M+ company pages. Best for people-level data.

**Company Search Capabilities:**
- Industry filter (manufacturing, aerospace, medical devices, etc.)
- Company headcount filter (1-10, 11-50, 51-200, etc.)
- Geography filter (country, state, city)
- Technologies used
- Department headcount growth
- Keyword search in company descriptions
- Recent activities and job postings

**Export Options:**
- Direct CSV export of lead/account lists
- CRM sync (Salesforce, HubSpot, Dynamics) — requires Advanced Plus plan
- **No public API** — LinkedIn paused new SNAP partner applications indefinitely
- Third-party scraping tools exist (Evaboot, PhantomBuster) but violate ToS

**Coverage Gaps:**
- Company-level data is thin (no revenue, no financials)
- Employee count is self-reported and often outdated
- Industry classifications are broad and self-selected by company admins
- Many small manufacturers have minimal LinkedIn presence
- **Cannot export at scale without violating ToS**

**Pricing:** ~$100-$180/month/seat (Sales Navigator Advanced).

**Verdict for GPO:** Good for validating company existence and finding contacts once companies are identified. Not useful for primary discovery of small manufacturers — many won't have robust LinkedIn pages. Use for enrichment, not discovery.

**Sources:**
- [LinkedIn Sales Navigator Industries](https://evaboot.com/blog/linkedin-sales-navigator-industries-list)
- [LinkedIn Sales Navigator API](https://evaboot.com/blog/linkedin-sales-navigator-api)
- [LinkedIn Sales API](https://developer.linkedin.com/product-catalog/sales)

---

### 1.6 D&B (Dun & Bradstreet) / D&B Hoovers

**Coverage:** 170M+ company records worldwide. **Best coverage of small private companies** due to DUNS number system.

**Data Available:**
- DUNS number (universal business identifier)
- SIC/NAICS codes (D&B assigns these)
- Revenue estimates (modeled for privates)
- Employee count
- Company hierarchy (parent/subsidiary)
- Financial stress scores
- Trade credit data
- Years in business
- Business type (manufacturer, distributor, etc.)

**API Access:**
- D&B Direct API — enterprise pricing, custom quotes
- **Essentials:** $49/month, 150 credits — basic company lookups
- **Enterprise:** $25,000+/year — full API access, advanced analytics
- D&B Direct 2.0 REST API for industry code lookups and company searches

**Strengths for GPO Use Case:**
- **Best SIC/NAICS classification** — D&B actually assigns these codes based on investigation
- **DUNS system covers small manufacturers** that other databases miss
- Revenue estimates exist even for very small companies
- Trade credit data can proxy financial health
- Company hierarchy helps identify subsidiaries

**Coverage Gaps:**
- Revenue estimates still modeled (not verified) for privates
- Data freshness varies — some records years out of date
- Expensive at scale for API access
- UI/UX of D&B Hoovers is dated

**Verdict for GPO:** **Top-tier source for small manufacturer discovery.** DUNS coverage is unmatched for the 10-100 employee segment. SIC/NAICS codes are the most reliable across any source. Revenue estimates are directional, not precise. Consider as primary discovery source despite cost.

**Sources:**
- [D&B SIC/NAICS Codes](https://www.dnb.com/en-us/resources/sales/sic-naics-industry-codes.html)
- [D&B Direct API](https://docs.dnb.com/direct/2.0/en-US/entitylist/latest/findindustry/rest-API)
- [D&B Hoovers Pricing](https://www.bookyourdata.com/blog/db-hoovers-pricing)

---

### 1.7 Owler

**Coverage:** 15-20M company profiles globally.

**Data Available:**
- Company name, address, website
- Revenue estimates (crowdsourced + ML)
- Employee count
- Competitors
- News and funding data
- Social media links

**API Access:**
- **Basic API (free):** Company name, address, phone, website URL
- **Premium API (paid):** Revenue, employees, competitors, industry data
- Pricing not publicly disclosed

**Data Quality:**
- Crowdsourced from 5M+ business professionals
- Enhanced with AI/ML and human verification
- Revenue estimates based on public filings, funding rounds, and community input
- **Accuracy for small private companies is questionable** — crowdsourcing doesn't work well for niche manufacturers that few people interact with

**Verdict for GPO:** Free basic API is useful for validation. Premium API could supplement other sources. Not reliable as primary discovery for niche manufacturers.

**Sources:**
- [Owler About](https://corp.owler.com/about)
- [Owler API on Databar](https://databar.ai/explore/owler-api/owler-company-data-premium-api)
- [Owler Pricing](https://www.uplead.com/owler-pricing/)

---

### 1.8 Glassdoor / Indeed — Employee Count Estimation

**Methodology:** Use job posting volume and review count as proxy signals for company size and growth.

**Signals Available:**
- Number of active job postings (hiring velocity)
- Total reviews (proxy for employee count over time)
- Rating trends (company health indicator)
- Salary data (helps estimate total compensation costs)
- Department-level hiring (signals growth areas)

**Data Access:**
- No public API for job posting data
- Third-party scraping tools exist (Bright Data offers Glassdoor datasets at ~$250/100K records)
- Indeed job postings can be accessed via Indeed Publisher API (limited)

**Practical Application:**
- A company with 5+ active job postings and 50+ Glassdoor reviews likely has 50+ employees
- High hiring velocity in manufacturing roles suggests growth/capacity expansion
- Multiple engineering/R&D postings signal product development investment

**Verdict for GPO:** Useful as supplementary signal for sizing companies and detecting growth, but not for primary discovery. Difficult to access at scale.

---

### 1.9 SEC EDGAR

**What's Available for Private Companies:** Almost nothing directly. However:

**Indirect Discovery Methods:**
- **Supplier/customer mentions in public company 10-K filings** — public companies must disclose material suppliers/customers
- **Full-text search API** — search all filings since 2001 for company names
- **Example:** Search "custom machining" or "precision manufacturing" in 10-K filings to find suppliers mentioned by public A&D primes (Lockheed, Raytheon, Boeing)

**API Access:**
- **Free REST API** — no authentication required
- data.sec.gov provides JSON-formatted XBRL data
- EDGAR Full-Text Search for searching all filing content
- Third-party APIs (sec-api.io) provide enhanced search with 18M+ filings

**Practical Application for GPO:**
1. Search 10-K filings of major A&D primes for supplier mentions
2. Cross-reference mentioned suppliers against company databases
3. Suppliers to public companies are often strong acquisition targets (proven revenue, sticky relationships)

**Verdict for GPO:** **Highly underrated discovery method for A&D subcontractors.** Free, unique data that competitors aren't using. Build a pipeline that scrapes public filings for supplier mentions to discover hidden targets.

**Sources:**
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [EDGAR Full-Text Search](https://www.sec.gov/edgar/search/)
- [SEC Filing Full-Text Search API](https://sec-api.io/docs/full-text-search-api/)

---

### 1.10 State Business Registrations (Secretary of State)

**Data Available:**
- Company name, formation date, status (active/inactive)
- Registered agent and address
- Officers/directors (varies by state)
- Business type (LLC, Corp, etc.)
- SIC/NAICS codes (some states)
- Annual report filings

**Access Methods:**
- **Individual state websites** — free but manual
- **Bulk downloads** — available in some states:
  - California: RESTful API + "Master Unload" CSV files
  - Minnesota: Weekly CSV download ($30/week)
  - Kentucky: Monthly bulk data subscription
  - North Carolina: Data subscription contracts
  - South Dakota: Free database downloads
- **Third-party aggregators:**
  - Cobalt Intelligence API — all 50 states, 20+ attributes
  - Middesk — business verification across all states
  - iDenfy — Secretary of State API for all 50 states

**Coverage Gaps:**
- No revenue or financial data
- Employee count not available
- Industry classification inconsistent across states
- Data freshness varies widely
- No indication of company size or EBITDA

**Verdict for GPO:** Useful for **validation** (confirming a company exists and is active) and **officer data**. Not useful for discovery or sizing. Best used as an enrichment layer after initial discovery.

**Sources:**
- [Secretary of State API - Middesk](https://www.middesk.com/blog/secretary-of-state-api)
- [Cobalt Intelligence SoS API](https://cobaltintelligence.com/blog/post/top-secretary-of-state-api-solutions-for-verifying-businesses)

---

### 1.11 Industry Associations & Trade Directories

**Key Associations by Sector:**

**Aerospace & Defense:**
- Aerospace Industries Association (AIA) — premier US A&D trade association
- Aviation Distributors and Manufacturers Association (ADMA)
- Aerospace Components Manufacturers (ACM)
- General Aviation Manufacturers Association (GAMA)
- National Defense Industrial Association (NDIA)
- Precision Machined Products Association (PMPA)

**Medical Devices:**
- Advanced Medical Technology Association (AdvaMed)
- Medical Device Manufacturers Association (MDMA)
- MEMA (Motor & Equipment Manufacturers Association)

**Manufacturing (General):**
- National Association of Manufacturers (NAM)
- Association for Manufacturing Technology (AMT)
- Fabricators & Manufacturers Association (FMA)
- IQS Directory — comprehensive industrial association directory

**Data Access:**
- Most associations publish **member directories** (often free or with membership)
- Directories typically include company name, contact info, capabilities, and employee size range
- **No APIs** — manual scraping or data purchases required
- Member lists can be cross-referenced with other data sources for enrichment

**Verdict for GPO:** **Excellent discovery source for niche manufacturers.** Association members are self-selected as active in the industry. Combine member directories with D&B/Apollo enrichment for a powerful pipeline. Manual effort required.

---

### 1.12 Import/Export Records (Customs Data)

**Key Platforms:**

**ImportGenius:**
- US customs import/export records at bill-of-lading level
- 25+ countries covered
- Data from 2006 to present
- Can identify manufacturers by their shipping/receiving patterns
- **API available** (Enterprise tier)
- Pricing: Self-serve plans available; Enterprise by quote

**Panjiva (S&P Global):**
- 2B+ import/export transaction records
- 22 customs authorities, 190+ countries
- 9M+ companies, 13M+ trade relationships
- Search by HS/HTS code, product name, DUNS number
- **API available** (Enterprise)
- Pricing: Enterprise only (typically $10,000+/year)

**Practical Application for GPO:**
1. Search for US importers of aerospace components, medical device parts, or industrial raw materials
2. Identify manufacturers by their import patterns (companies importing raw materials and exporting finished goods)
3. Cross-reference with NAICS codes to confirm manufacturing activity
4. Shipping volume can proxy for revenue estimation

**Verdict for GPO:** **Unique and underutilized source for finding manufacturers.** Import patterns definitively identify companies that make physical products. Expensive but provides data unavailable elsewhere.

**Sources:**
- [ImportGenius Pricing](https://www.importgenius.com/pricing)
- [Panjiva](https://panjiva.com/)

---

### 1.13 Government Contracting (SAM.gov / USAspending)

**SAM.gov:**
- Registration database for government contractors
- All companies doing business with the US government must register
- Includes: company name, DUNS, NAICS codes, size standards, address, capabilities
- **Free API** — SAM.gov Contract Awards API (JSON format, no auth required for public data)
- Can filter by NAICS code, state, size standard (small business thresholds)

**USAspending.gov:**
- Federal spending data from FY2008 to present
- Contract awards, grants, loans
- Searchable by contractor name, NAICS, agency
- **Free API and bulk downloads**
- Includes subcontract data through FSRS

**Practical Application for GPO:**
1. Search SAM.gov for registered contractors in A&D NAICS codes (3364xx)
2. Filter by small business size standard to find companies in target range
3. Cross-reference contract award amounts with revenue estimates
4. Use USAspending to see actual contract values (proxy for revenue)
5. Subcontract data reveals smaller A&D companies in the supply chain

**Verdict for GPO:** **Essential source for A&D subcontractors.** Free, comprehensive, and provides actual contract dollar values (not estimates). Any company doing defense work must be registered. This is the single best source for A&D company discovery.

**Sources:**
- [SAM.gov Contract Awards API](https://open.gsa.gov/api/contract-awards/)
- [USAspending.gov](https://www.usaspending.gov/)
- [SAM.gov Contract Data](https://sam.gov/contract-data)

---

### 1.14 Google Maps / Places API

**Coverage:** 200M+ places globally, including businesses.

**Data Available:**
- Business name, address, phone, website
- Business category/type
- Operating hours
- User ratings and reviews
- Photos
- Place ID (unique identifier)

**API Pricing:**
- $200/month free credit
- Text Search: $32 per 1,000 requests (basic)
- Place Details: $17 per 1,000 requests (basic)
- Nearby Search available for geographic discovery

**Limitations for Manufacturing Discovery:**
- Category granularity is limited — "manufacturing" is broad
- Many manufacturers don't have Google Business profiles
- No revenue, employee count, or financial data
- No industry classification beyond basic categories
- Better for retail/service businesses than B2B manufacturers

**Verdict for GPO:** Useful for validating addresses and finding local businesses, but poor for systematic manufacturing company discovery. Most B2B manufacturers don't optimize their Google Business profiles.

**Sources:**
- [Places API Pricing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing)

---

### 1.15 ThomasNet

**Coverage:** 500,000+ North American suppliers (manufacturers, distributors, service companies).

**Data Available:**
- Company name, address, phone, website
- Product/service categories (detailed industrial taxonomy)
- Capabilities (certifications, processes, materials)
- CAD drawings and catalogs
- Annual revenue range (self-reported)
- Employee count range (self-reported)
- Year established
- Certifications (ISO, AS9100, ITAR, etc.)

**API Access:**
- **No official public API**
- Third-party scrapers exist (Apify Thomasnet Scraper)
- Data is structured and scrapable but requires custom tooling

**Strengths for GPO:**
- **Purpose-built for industrial/manufacturing discovery**
- Detailed capability data (processes, materials, certifications)
- Companies self-list, so they're actively marketing manufacturing services
- Certification data (AS9100, ITAR) directly identifies A&D subcontractors
- Revenue/employee ranges provide sizing signals

**Verdict for GPO:** **Best discovery source for manufacturing companies specifically.** The data is exactly what we need — manufacturers self-listing with capabilities, certifications, and sizing data. No API means custom scraping required, but the data quality for this use case is unmatched.

**Sources:**
- [ThomasNet Supplier Search](https://www.thomasnet.com/suppliers)
- [ThomasNet Browse Companies](https://www.thomasnet.com/browsecompanies.html)

---

### 1.16 Kompass

**Coverage:** 57-60M+ companies in 70+ countries. **Strongest in industrial/manufacturing profiles.**

**Data Available:**
- Company name, address, contacts
- Executive contacts and job titles
- Industry classifications (67 sectors, 3,000+ industries, 55,000+ products/services)
- Employee count
- Revenue figures
- Import/export activities
- Product and service details

**API Access:**
- Custom API solutions available
- EasyBusiness online B2B database for self-service
- Bespoke Data List service
- CRM integration options

**Strengths for GPO:**
- **Largest database of industrial-profile companies**
- Detailed product/service taxonomy (55,000 categories)
- Strong international coverage (UK, Canada well covered)
- Manufacturing and industrial focus aligns perfectly with GPO target

**Coverage Gaps:**
- Data accuracy varies; contact info can be outdated
- Less comprehensive for newer/smaller businesses
- Pricing not transparent

**Verdict for GPO:** **Strong source for international (UK/Canada) industrial companies.** Complements ThomasNet (which is North America focused) with broader global coverage. Worth evaluating for UK targets especially.

**Sources:**
- [Kompass Directory](https://us.kompass.com/businessplace/)
- [Kompass Solutions](https://www.solutions.kompass.com/)

---

### 1.17 Bonus: Deal-Sourcing Platforms (Grata, SourceScrub, PrivCo)

**Grata:**
- **19M+ private middle-market companies** with investment-grade data
- 3M+ financials, 800K+ deals
- AI-powered search using company descriptions (not just SIC/NAICS)
- Machine learning industry classification (superior to standard codes)
- **Purpose-built for PE/M&A deal sourcing** — exactly our use case
- Integrates with Salesforce, HubSpot, DealCloud
- Pricing: Enterprise (contact sales)

**SourceScrub (now Datasite):**
- 16M deeply profiled companies, 220,000 sources
- Revenue estimates for hard-to-find private companies
- API for workflow integration
- Strong for lower middle-market discovery
- Acquired by Datasite (Aug 2025)

**PrivCo:**
- US private company financial data
- Revenue, EBITDA, employee counts, valuations, growth signals
- 401(k) plan data (unique proxy for company size/health)
- Pricing: Enterprise

**Verdict for GPO:** **Grata is the closest off-the-shelf solution to what we're building.** Understanding Grata's approach validates our strategy but also shows the competitive landscape. Consider whether building custom or licensing from these platforms is more cost-effective.

**Sources:**
- [Grata Platform](https://grata.com/)
- [SourceScrub Data](https://www.sourcescrub.com/product/data)
- [Grata Industry Classifications](https://grata.com/resources/industry-classifications)

---

## 2. EBITDA Estimation for Private Companies

### 2.1 Revenue Estimation Methodologies

#### Method 1: Employee Count (Most Reliable for Manufacturing)

| Industry | Revenue per Employee | Source |
|----------|---------------------|--------|
| General Manufacturing | $200,000 - $400,000 | Industry benchmarks |
| Aerospace & Defense | $250,000 - $500,000 | CSIMarket Q3 2025 |
| Medical Devices | $200,000 - $350,000 | CSIMarket Q2 2025 |
| Precision Manufacturing | $250,000 - $450,000 | FOCUS Bankers 2025 |
| SaaS/Software (comparison) | $150,000 - $300,000 | Industry benchmarks |

**Formula:** `Estimated Revenue = Employee Count x Revenue-per-Employee Ratio`

**Example:** A precision machining company with 45 employees:
- Low estimate: 45 x $250,000 = $11.25M
- Mid estimate: 45 x $350,000 = $15.75M
- High estimate: 45 x $450,000 = $20.25M

#### Method 2: Salary-Based Floor Estimate

Use BLS average wages by industry, multiply by employee count to get minimum labor cost, then apply industry-typical labor-cost-to-revenue ratios (typically 25-40% for manufacturing).

**Formula:** `Minimum Revenue = (Avg Salary x Employees) / Labor Cost Ratio`

**Example:** 45 employees, $65K avg salary, 30% labor ratio:
- (45 x $65,000) / 0.30 = $9.75M minimum revenue

#### Method 3: Government Contract Data (A&D specific)

For A&D subcontractors registered in SAM.gov:
- Sum recent contract awards from USAspending
- Government contracts typically represent 50-90% of revenue for A&D subcontractors
- **Formula:** `Estimated Revenue = Total Contract Awards / Government Revenue Percentage`

#### Method 4: Import Volume (Manufacturing specific)

- Customs import data reveals raw material purchases
- Typical raw material cost is 30-50% of revenue for manufacturers
- **Formula:** `Estimated Revenue = Import Value / Raw Material Cost Ratio`

#### Method 5: Web Traffic & Digital Signals

- SimilarWeb/Semrush traffic data
- LinkedIn company followers
- Job posting volume and types
- These are weak proxies for manufacturing (many manufacturers have minimal web presence)

### 2.2 EBITDA Estimation from Revenue

#### EBITDA Margins by Industry

| Industry | Typical EBITDA Margin | Notes |
|----------|----------------------|-------|
| General Manufacturing | 8-12% | Capital-intensive, lower margins |
| Precision Manufacturing | 12-18% | Higher value-add, better margins |
| Aerospace Components | 12-20% | Certification moats drive margins |
| Defense Subcontractors | 10-15% | Cost-plus contracts compress margins |
| Medical Device Manufacturing | 15-25% | Regulatory barriers support pricing |
| Custom/Job Shop Manufacturing | 10-15% | Depends on specialization |
| Industrial Equipment | 10-15% | Aftermarket/service lifts margins |

**Formula:** `Estimated EBITDA = Estimated Revenue x Industry EBITDA Margin`

**Example:** Precision machining company, 45 employees:
- Revenue estimate: $15.75M (mid)
- EBITDA margin: 15% (precision manufacturing)
- **Estimated EBITDA: $2.36M**

### 2.3 Target Company Sizing

For our target range of **1-15M EBITDA** and **10-100 employees:**

| Employees | Est. Revenue (Manufacturing) | Est. EBITDA (12-18% margin) |
|-----------|-----------------------------|-----------------------------|
| 10 | $2M - $4M | $240K - $720K |
| 25 | $5M - $10M | $600K - $1.8M |
| 50 | $10M - $20M | $1.2M - $3.6M |
| 75 | $15M - $30M | $1.8M - $5.4M |
| 100 | $20M - $40M | $2.4M - $7.2M |

**Key Insight:** To consistently hit 1-15M EBITDA in manufacturing, we're primarily looking at companies with **25-100+ employees** and **$8M-$100M revenue.** The 10-25 employee range will mostly fall below 1M EBITDA unless margins are exceptional.

### 2.4 Accuracy of Data Provider Revenue Estimates

| Provider | Claimed Accuracy | Real-World Accuracy (Small Privates) | Notes |
|----------|-----------------|-------------------------------------|-------|
| Apollo.io | 91% | 40-60% for revenue | Better for contact data than financials |
| ZoomInfo | "High" | ~50% for lower middle-market | Better for larger companies |
| D&B | Not disclosed | 50-65% (directional) | Best coverage of small companies |
| Owler | Not disclosed | 30-50% | Crowdsourced; weak for niche |
| Grata | Not disclosed | 60-70% (estimated) | Purpose-built for this segment |
| PrivCo | Not disclosed | 55-70% | Uses 401K data as unique signal |

**Bottom Line:** No single source provides accurate EBITDA data for private companies. The best approach is:
1. Use employee count as primary sizing signal (most verifiable)
2. Apply industry revenue-per-employee ratios
3. Apply industry EBITDA margins
4. Cross-reference with government contract data (for A&D)
5. Validate with import/export volumes (for manufacturers)

### 2.5 Valuation Multiples (for context)

| Sector | EV/EBITDA Multiple (2025) | Notes |
|--------|--------------------------|-------|
| General Manufacturing | 6-8x | Commodity, lower growth |
| Precision Manufacturing | 10-12x | Technology-driven premium |
| Aerospace Components | 11-14x | Avg 13.4x for A&D sector |
| Defense Subcontractors | 10-12x | Government contract stability |
| Medical Devices | 12-18x | Regulatory moats, recurring revenue |

**Sources:**
- [CSIMarket A&D Revenue per Employee](https://csimarket.com/Industry/industry_Efficiency.php?ind=201)
- [Damodaran Margins Data](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/margin.html)
- [Precision Machining Valuations - FOCUS Bankers](https://focusbankers.com/why-precision-machining-shops-are-seeing-premium-valuations-right-now/)
- [EBITDA Multiples by Industry](https://firstpagesage.com/seo-blog/ebitda-multiples-by-industry/)
- [Aerospace EBITDA Multiples](https://firstpagesage.com/business/aerospace-ebitda-valuation-multiples/)

---

## 3. Industry Classification (SIC/NAICS)

### 3.1 SIC vs NAICS — Which to Use?

| Aspect | SIC Codes | NAICS Codes |
|--------|-----------|-------------|
| Introduced | 1937 | 1997 (replaced SIC) |
| Structure | 4-digit | 6-digit (more granular) |
| Maintained by | OSHA (no longer updated) | US Census Bureau |
| Coverage | ~1,000 industries | ~1,000+ industries |
| Manufacturing detail | Good | Better (more granular) |
| Government use | Legacy systems | Current standard |
| Apollo.io support | Yes | Yes |
| D&B support | Yes (primary + secondary) | Yes |
| SAM.gov | Both | Primary |

**Recommendation:** Use **NAICS as primary** (more granular, actively maintained) with **SIC as fallback** (some older databases still use SIC). Build mapping tables between them.

### 3.2 Key NAICS Codes for GPO Targets

#### Aerospace & Defense Manufacturing
```
3364   - Aerospace Product and Parts Manufacturing
33641  - Aircraft Manufacturing
336411 - Aircraft Manufacturing
336412 - Aircraft Engine and Engine Parts Manufacturing
336413 - Other Aircraft Parts and Auxiliary Equipment Manufacturing
336414 - Guided Missile and Space Vehicle Manufacturing
336415 - Guided Missile and Space Vehicle Propulsion Unit Manufacturing
336419 - Other Guided Missile and Space Vehicle Parts Manufacturing
```

#### Defense Electronics & Systems
```
334511 - Search, Detection, Navigation, Guidance, Aeronautical Systems
334290 - Other Communications Equipment Manufacturing
334419 - Other Electronic Component Manufacturing
334513 - Instruments for Measuring/Testing Electricity
```

#### Medical Device Manufacturing
```
3391   - Medical Equipment and Supplies Manufacturing
339112 - Surgical and Medical Instrument Manufacturing
339113 - Surgical Appliance and Supplies Manufacturing
339114 - Dental Equipment and Supplies Manufacturing
339115 - Ophthalmic Goods Manufacturing
339116 - Dental Laboratories
```

#### Custom / Precision Manufacturing
```
332710 - Machine Shops
332721 - Precision Turned Product Manufacturing
332722 - Bolt, Nut, Screw, Rivet Manufacturing
332811 - Metal Heat Treating
332812 - Metal Coating and Nonprecious Engraving
332813 - Electroplating, Anodizing, Coloring
332999 - All Other Miscellaneous Fabricated Metal Product Manufacturing
333249 - Other Industrial Machinery Manufacturing
333514 - Special Die and Tool, Die Set, Jig Manufacturing
333515 - Cutting Tool and Machine Tool Accessory Manufacturing
333517 - Machine Tool Manufacturing
```

#### Niche Industrial Manufacturing
```
333911 - Pump and Pumping Equipment Manufacturing
333912 - Air and Gas Compressor Manufacturing
333913 - Measuring and Dispensing Pump Manufacturing
333921 - Elevator and Moving Stairway Manufacturing
333922 - Conveyor and Conveying Equipment Manufacturing
333923 - Overhead Traveling Crane Manufacturing
333924 - Industrial Truck, Tractor, and Stacker Manufacturing
333991 - Power-Driven Handtool Manufacturing
333992 - Welding and Soldering Equipment Manufacturing
333993 - Packaging Machinery Manufacturing
333994 - Industrial Process Furnace and Oven Manufacturing
333995 - Fluid Power Cylinder and Actuator Manufacturing
333996 - Fluid Power Pump and Motor Manufacturing
```

### 3.3 Key SIC Codes (Legacy/Fallback)

```
3721 - Aircraft
3724 - Aircraft Engines and Engine Parts
3728 - Aircraft Parts and Auxiliary Equipment, NEC
3761 - Guided Missiles and Space Vehicles
3769 - Guided Missiles/Space Vehicle Parts, NEC
3812 - Defense Electronics and Communications Equipment
3841 - Surgical and Medical Instruments
3842 - Orthopedic, Prosthetic, and Surgical Appliances
3843 - Dental Equipment and Supplies
3599 - Industrial Machinery, NEC
3462 - Iron and Steel Forgings
3544 - Special Dies, Tools, Jigs, and Fixtures
3599 - Industrial and Commercial Machinery, NEC
```

### 3.4 Programmatic Industry Classification

**Approach 1: BEACON (US Census Bureau)**
- Open-source ML tool for NAICS classification
- Input: business description text
- Output: ranked list of 6-digit NAICS codes
- GitHub: [uscensusbureau/BEACON](https://github.com/uscensusbureau/BEACON)

**Approach 2: Zero-Shot Classification with LLMs**
- Use GPT-4/Claude to classify companies from website text
- No training data needed
- Prompt: "Given this company description, assign the most appropriate NAICS codes"
- Accuracy: ~85-90% for clear cases, ~70% for ambiguous

**Approach 3: TF-IDF + Classifier**
- Scrape company websites
- Extract text features via TF-IDF
- Train Naive Bayes/SVM on labeled examples
- Requires labeled training set

**Approach 4: Grata's Approach**
- ML-derived industry classifications trained on millions of companies
- Proprietary taxonomy designed for deal sourcing
- More nuanced than NAICS (e.g., "custom precision machining for aerospace" vs generic "machine shops")

**Detecting "Custom Manufacturing" Companies:**
Key signals from company descriptions/websites:
- Terms: "custom," "precision," "job shop," "contract manufacturing," "OEM," "made to order," "engineered to spec"
- Certifications: AS9100 (aerospace), ISO 13485 (medical), ITAR (defense), NADCAP
- Customer types: mentions of Boeing, Lockheed, Raytheon, major OEMs
- Process descriptions: CNC machining, EDM, 5-axis, turning, milling, grinding

**Sources:**
- [BEACON GitHub](https://github.com/uscensusbureau/BEACON)
- [Grata Industry Classifications](https://grata.com/resources/industry-classifications)
- [NLP Company Classification Paper](https://www.mdpi.com/2078-2489/15/2/77)

---

## 4. Free/Cheap Company Data APIs

### 4.1 Completely Free APIs

| API | Data | Rate Limits | Coverage |
|-----|------|-------------|----------|
| **SEC EDGAR** | Public filings, XBRL data | No auth, fair use | US public companies + supplier mentions |
| **SAM.gov** | Government contractor registrations | Free, API key required | All US gov contractors |
| **USAspending.gov** | Federal spending/contracts | Free, bulk downloads | FY2008-present |
| **Companies House (UK)** | UK company registrations, filings, financials | 600 req/5 min, free API key | 4M+ UK companies |
| **OpenCorporates** | Company registrations | Limited free tier | 200M+ companies, 140+ jurisdictions |
| **NAICS API** | NAICS code lookups | Free | All NAICS codes |
| **Google Places** | Business info, categories | $200/month free credit | 200M+ places |

### 4.2 Low-Cost APIs (Under $5,000/year)

| API | Data | Pricing | Best For |
|-----|------|---------|----------|
| **Apollo.io** | Companies, contacts, emails | Free-$119/user/month | US company discovery, contact enrichment |
| **Owler (Basic)** | Company name, address, website | Free | Basic company validation |
| **Crunchbase Pro** | Company profiles, funding | $49/month | VC-backed company research |
| **OpenCorporates** | Company registrations | From L2,250/year (~$2,800) | Multi-jurisdiction validation |

### 4.3 Mid-Range APIs ($5,000-$25,000/year)

| API | Data | Pricing | Best For |
|-----|------|---------|----------|
| **D&B Essentials** | Company profiles, DUNS | $5,388/year | Small manufacturer discovery |
| **ImportGenius** | Customs/trade data | Enterprise pricing | Identifying manufacturers |
| **ZoomInfo** | Company + contact data | $15,000+/year | Contact enrichment at scale |

### 4.4 Enterprise APIs ($25,000+/year)

| API | Data | Pricing | Best For |
|-----|------|---------|----------|
| **D&B Enterprise** | Full API, analytics | $25,000+/year | Comprehensive company data |
| **PitchBook** | Deal data, financials | $20,000-$60,000/year | PE-backed company research |
| **Panjiva** | Global trade intelligence | $10,000+/year | Import/export intelligence |
| **Grata** | Private company search | Enterprise | Deal sourcing (direct competitor) |
| **SourceScrub** | Private company profiles | Enterprise | Deal sourcing |

### 4.5 Companies House UK — Detailed Free API

The best free data source for UK company intelligence:

- **100% free**, government-provided
- Real-time data on 4M+ registered companies
- Financial statements (accounts filed at Companies House)
- Officer/director information
- Filing history
- Company status (active, dissolved, etc.)
- SIC codes
- Registered address

**Key Insight for UK Targets:** UK companies (even private ones) must file annual accounts at Companies House. Small companies file abbreviated accounts, but these still include balance sheet data. Medium companies include P&L. This means **actual financial data** is available for UK private companies — far more than US equivalents.

**Sources:**
- [Companies House API](https://developer.company-information.service.gov.uk/)
- [Companies House Free Data](https://download.companieshouse.gov.uk/en_output.html)

---

## 5. Recommended Architecture for GPO Platform

### 5.1 Tiered Data Strategy

```
TIER 1 — Primary Discovery (Find companies)
├── ThomasNet scraping       → Manufacturing companies (US/Canada)
├── Kompass                   → Manufacturing companies (UK, international)
├── SAM.gov API               → A&D government contractors (US)
├── Apollo.io API             → Broad company search with SIC/NAICS filters
├── Companies House API       → UK company discovery with financials
└── Industry association dirs → Niche manufacturer member lists

TIER 2 — Enrichment (Size and qualify)
├── D&B / DUNS lookup         → Revenue estimates, employee count, SIC/NAICS
├── Apollo.io enrichment      → Contact data, tech stack
├── LinkedIn (manual/tools)   → Employee count validation, key contacts
├── Glassdoor/Indeed          → Job posting signals, employee count proxy
├── Owler API                 → Revenue estimates, competitors
└── Companies House (UK)      → Actual financial statements

TIER 3 — Deep Intelligence (Validate targets)
├── SEC EDGAR full-text       → Supplier mentions in public company filings
├── USAspending.gov           → Government contract award values
├── Import/export records     → Manufacturing volume, raw material sourcing
├── State SoS databases       → Corporate status, officers, formation date
└── Website scraping + LLM    → Capabilities, certifications, customer base

TIER 4 — EBITDA Estimation Model
├── Employee count (most reliable input)
├── Industry revenue-per-employee ratio
├── Industry EBITDA margin
├── Government contract values (A&D)
├── Import volumes (manufacturing)
├── UK Companies House financials (UK targets)
└── Cross-validation across multiple sources
```

### 5.2 Cost Estimate (Annual)

| Component | Cost | Priority |
|-----------|------|----------|
| Free APIs (SEC, SAM, Companies House, NAICS) | $0 | Must-have |
| Apollo.io (Professional) | ~$1,200/year | Must-have |
| Google Places API | ~$200-500/year | Nice-to-have |
| ThomasNet scraping (custom) | Dev time only | Must-have |
| D&B Essentials | ~$5,400/year | Should-have |
| OpenCorporates | ~$2,800/year | Nice-to-have |
| ImportGenius | ~$3,000-10,000/year | Nice-to-have |
| **Total (core stack)** | **~$7,000-10,000/year** | |
| **Total (full stack)** | **~$12,000-20,000/year** | |

### 5.3 Data Pipeline Architecture

```
[Discovery Sources] → [Deduplication] → [Enrichment Waterfall] → [EBITDA Model] → [Scoring] → [CRM]

Step 1: Ingest from multiple discovery sources
Step 2: Deduplicate using company name + address + domain matching
Step 3: Enrich via waterfall (try D&B → Apollo → Owler → web scraping)
Step 4: Classify industry via NAICS + LLM analysis of website
Step 5: Estimate revenue from employee count + industry ratios
Step 6: Estimate EBITDA from revenue + industry margins
Step 7: Score companies on fit (EBITDA range, industry, geography, certifications)
Step 8: Push qualified leads to CRM/outreach pipeline
```

### 5.4 Key Insight: Clay.com as Orchestration Layer

Clay.com already provides waterfall enrichment across 100+ data providers in a spreadsheet-like interface. Rather than building custom integrations for each data source, consider:

1. **Use Clay as the enrichment orchestration layer** — it already connects Apollo, ZoomInfo, LinkedIn, and many others
2. **Build custom discovery pipelines** for sources Clay doesn't cover (ThomasNet, SAM.gov, industry associations)
3. **Feed discovered companies into Clay** for automated enrichment waterfall
4. **Use Clay's API** to integrate with your CRM/scoring system

This approach reduces custom integration work while maintaining access to the broadest data coverage.

**Sources:**
- [Clay Data Enrichment](https://www.clay.com/blog/data-waterfalls)
- [Clay FAQ](https://www.clay.com/faq)

---

## Appendix: Source Summary Table

| Source | Discovery | Enrichment | Financials | Cost | GPO Relevance |
|--------|-----------|------------|------------|------|---------------|
| Apollo.io | Good | Strong | Weak | Low | HIGH |
| ZoomInfo | Fair | Strong | Weak | High | MEDIUM |
| Crunchbase | Poor | Fair | Weak | Medium | LOW |
| PitchBook | Poor | Fair | Good | High | LOW |
| LinkedIn Sales Nav | Fair | Good | None | Medium | MEDIUM |
| D&B / Hoovers | Strong | Strong | Fair | High | HIGH |
| Owler | Fair | Fair | Weak | Low | MEDIUM |
| Glassdoor/Indeed | Poor | Fair | None | Low | LOW |
| SEC EDGAR | Fair* | Good* | None | Free | HIGH (A&D) |
| State SoS | Poor | Fair | None | Low | LOW |
| Industry Assocs | Strong | Poor | None | Low | HIGH |
| Import/Export | Good | Good | Fair | High | MEDIUM |
| SAM.gov | Strong* | Good | Good* | Free | HIGH (A&D) |
| Google Places | Fair | Poor | None | Low | LOW |
| ThomasNet | Strong | Good | Fair | Free** | HIGH |
| Kompass | Strong | Good | Fair | Medium | HIGH (UK) |
| Grata | Strong | Strong | Good | High | COMPETITOR |
| SourceScrub | Strong | Strong | Fair | High | COMPETITOR |
| Companies House | Good* | Good | Strong* | Free | HIGH (UK) |

*For specific segments (A&D, UK respectively)
**Scraping required

---

*Report compiled 2026-03-08. Data and pricing subject to change.*
