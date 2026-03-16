# Research Summary — 13 Deep Research Reports

**Date:** 2026-03-08
**Location:** `.planning/research/` (all files)
**Purpose:** Inform v2.0 roadmap restructuring around "vertical weapon" strategy

---

## Strategic Direction

Clay-Dupe is pivoting from enrichment-only to a **vertical weapon**: Source → Enrich → Dedup SF → AI Emails → Export CSV for Salesforce. No built-in email sending — just CSV export in SF-ready format.

---

## Key Findings by Topic

### 1. Competitive Landscape (`COMPETITIVE_LANDSCAPE.md`)
- 20 tools analyzed. Clay dominates at $100M ARR / $3.1B valuation
- Clay's weakness: complexity, 10x API markup, no outreach, fragile CRM integrations
- Our edge: BYOK (bring your own keys), pay-only-on-success, self-hosted, transparent pricing
- No open-source enrichment orchestrator exists — we're the only one

### 2. Free API Providers (`FREE_API_PROVIDERS.md`)
- **Apollo: 10,000 email credits/month free** — clear winner
- PeopleDataLabs: 100/month free, richest data fields (100+ per record)
- Prospeo: 75/month free, supports LinkedIn URL
- Hunter.io: 25 searches + 50 verifications/month free
- Combined free capacity: ~10,250 enrichments/month at zero cost

### 3. Salesforce CSV Export (`SALESFORCE_CSV_EXPORT.md`)
- User's target fields: Company Name, Website, Quality (Gold/Silver/Bronze), Year Established, Employees, Description, First/Last Name, Title, Email, Portfolio, Vertical, Account Owner, Lead Owner, City, Province, Country
- Province/Country MUST be separate columns for SF import
- Owner fields need SF User IDs (not names) or mapping
- Quality = custom field `Quality__c` with Gold/Silver/Bronze picklist (NOT SF default Rating Hot/Warm/Cold)
- Report includes CSV header presets for SF Lead, SF Account+Contact, HubSpot, Outreach.io

### 4. LinkedIn Enrichment (`LINKEDIN_ENRICHMENT.md`)
- LinkedIn's own API is useless for enrichment
- Legal safe path: use provider APIs, not scraping
- LinkedIn waterfall: Apollo (60-70%) → ContactOut (+10-15%) → Prospeo (+5-10%) → Hunter (+3-5%) = 80-90% hit rate
- All major providers except Icypeas accept LinkedIn URL as input
- Sales Navigator has no native CSV export — users need Evaboot/PhantomBuster

### 5. Waterfall Optimization (`WATERFALL_OPTIMIZATION.md`)
- **3-5 providers is the sweet spot** — beyond 7 is diminishing returns
- Hunter.io underperforms (28% find rate despite brand recognition)
- Current waterfall order is near-optimal: Apollo → Icypeas → Findymail
- Pattern engine can reduce API calls by 60-80% (we're at 40-50%)
- Catch-all domains are 15-28% of B2B — need dedicated strategy
- Target cost: $0.06-0.10 per verified email

### 6. AI Email Personalization (`AI_EMAIL_PERSONALIZATION.md`)
- AI-personalized emails: 18% reply rate vs 5% generic (3.6x improvement)
- Claude Haiku at $0.53/1K emails with batch+cache — generation cost is negligible
- **Data quality matters more than AI model quality**
- Optimal email: 120 words, 70% of responses from emails 2-4 in sequence
- Gmail Gemini AI now does semantic spam filtering — need hybrid approach (AI + spintax)
- Full prompt template system and production architecture included

### 7. ICP Scoring (`ICP_SCORING_BEST_PRACTICES.md`)
- EBITDA estimation: `Employee Count × Revenue/Employee × EBITDA Margin`
  - A&D: $250-400K/employee, 10-15% margin
  - Custom Mfg: $150-300K/employee, 8-15% margin
- 15+ NAICS codes mapped for target industries
- Niche detection via certifications: AS9100, ISO 13485, ITAR, NADCAP
- Gold/Silver/Bronze tiers: EBITDA 30%, Industry 25%, Employee 15%, Niche 15%, Geo 10%, Intent 5%
- **Intent signals only matter ~5% for niche manufacturers** — they buy through relationships

### 8. Email Verification (`EMAIL_VERIFICATION_DEEP_DIVE.md`)
- Free local checks (syntax + DNS + MX) eliminate 20-30% of bad emails before API calls
- Catch-all domains: 15-60% of B2B — Findymail's catch-all resolution adds 23% more valid emails
- Self-hosted SMTP verification is risky (IP blacklisting) — use API services
- Target bounce rate: <2% for cold B2B email
- 7-layer verification pipeline: syntax → DNS → MX → disposable → role-based → SMTP → catch-all scoring
- Free verification APIs: ZeroBounce (100/month), Emailable (250/month)

### 9. Company Data Sources (`COMPANY_DATA_SOURCES.md`)
- **SAM.gov (FREE API)** — every A&D government subcontractor must register. Contract values, NAICS codes
- **ThomasNet (FREE)** — 500K+ industrial suppliers with certifications
- **Companies House UK (FREE API)** — UK private companies file actual financials
- **SEC EDGAR (FREE)** — 10-K supplier mentions reveal hidden A&D subcontractors
- Employee count is the most reliable proxy for private company sizing
- Grata ($19M+ raised) validates our approach commercially

### 10. Self-Hosted Architecture (`SELF_HOSTED_ARCHITECTURE.md`)
- SQLite is correct — switch to Postgres only at >10 concurrent writers or >10GB
- Single Python process handles ~100-200 concurrent enrichments (provider rate limits are the bottleneck)
- Provider plugin via `__init_subclass__` for zero-config registration
- TTL: 30 days company, 7-14 days contacts, 90 days patterns
- Field-level AES-256-GCM encryption recommended for PII
- No open-source tool does full waterfall — we fill a genuine gap

### 11. Compliance & Regulations (`COMPLIANCE_AND_REGULATIONS.md`)
- **US (CAN-SPAM)**: Opt-out law, least strict. Need physical address + unsubscribe
- **Canada (CASL)**: **World's strictest** — opt-in required. Cold B2B only via "conspicuous publication". $10M CAD penalties
- **UK (PECR)**: Corporate emails OK, named individuals need legitimate interest
- **Germany**: Effectively prohibits unsolicited B2B email without express consent
- Implementation specs included for suppression lists, consent tracking, jurisdiction rules

### 12. UI Architecture (`UI_ARCHITECTURE.md`)
- Stay with Streamlit (sufficient for <20 internal users)
- AgGrid for main tables (sorting, filtering, bulk selection)
- `@st.fragment` solves rerun problem for real-time progress
- Threading + `cache_resource` for background enrichment jobs
- Service layer with zero Streamlit imports enables future migration
- Plotly for dashboards

### 13. Domain Finding (`DOMAIN_FINDING.md`)
- DNS guessing is free, catches 30-40% (try companyname.com with MX validation)
- Serper.dev: best Google Search proxy ($0.001/query, 2,500 free)
- Clearbit Name-to-Domain is dead (sunsetted April 2025)
- Google Custom Search API shutting down January 2027
- 10K companies/month domain finding costs ~$40-60 total with caching

---

## Proposed v2.0 Roadmap (Under Discussion)

| Phase | What | Status |
|-------|------|--------|
| 11 | Salesforce Integration (read-only dedup) | Planned, ready to execute |
| 12 | New Providers (free-tier focus: Hunter, PeopleDataLabs, Prospeo) | Proposed |
| 13 | LinkedIn Workflow (URL → enriched contacts) | Proposed |
| 14 | Salesforce CSV Export (user's exact format) | Proposed |
| 15 | AI Email Generation (Claude-powered personalization) | Proposed |
| 16 | Cloud Deployment + Polish | Proposed |

**User decisions locked:**
- No built-in email sending — CSV export to Salesforce only
- More providers with free APIs preferred
- LinkedIn workflow: yes
- Intent signals: later
- More runway to build
- Quality field = Gold/Silver/Bronze (custom SF field, not standard Rating)
