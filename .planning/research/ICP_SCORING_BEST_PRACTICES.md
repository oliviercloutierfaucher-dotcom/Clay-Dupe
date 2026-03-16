# ICP Scoring & Lead Qualification: Deep Research Report

> Research Date: 2026-03-08
> Focus: B2B ICP scoring methodologies, platform comparisons, and application to niche industrial/manufacturing targets

---

## Table of Contents

1. [How Top Platforms Score Prospects](#1-how-top-platforms-score-prospects)
2. [ICP Scoring Dimensions](#2-icp-scoring-dimensions)
3. [Scoring Methodology](#3-scoring-methodology)
4. [EBITDA Estimation for Private Companies](#4-ebitda-estimation-for-private-companies)
5. [Identifying Niche Manufacturing Companies Programmatically](#5-identifying-niche-manufacturing-companies-programmatically)
6. [Quality Tier Design (Gold/Silver/Bronze)](#6-quality-tier-design-goldsilverbronze)
7. [Recommended Scoring Model for Our ICP](#7-recommended-scoring-model-for-our-icp)

---

## 1. How Top Platforms Score Prospects

### 1.1 Clay

**Approach:** Formula-based scoring with AI enrichment and 100+ data providers.

**How it works:**
- Users define scoring criteria based on their ICP characteristics
- Conditional logic formulas assign points per attribute (e.g., employee count > 300 = 5 pts, > 150 = 3 pts, > 50 = 2 pts)
- Multi-condition scoring with AND logic (`&&`) for compound criteria
- Scores sum across dimensions, scaled to 0-100
- AI agent "Claygent" can research any company attribute and feed it into scoring

**Scoring formula pattern:**
```
score = firmographics(40%) + tech_fit(25%) + title_seniority(20%) + signals(15%)
```

**Key differentiator:** Clay is a scoring *workbench* — it does not prescribe a model. Users build custom scoring using enrichment data from 150+ providers (Owler, Google Jobs, web scrapers, etc.) and combine them with formulas. Scores auto-update CRMs.

**Strengths for our use case:** Maximum flexibility. Can build custom EBITDA estimation formulas, scrape websites for manufacturing keywords, and combine multiple enrichment sources.

**Sources:**
- [Clay Account Scoring](https://www.clay.com/account-scoring)
- [Lead Scoring in Clay](https://www.clay.com/blog/lead-scoring-in-clay)
- [Clay University: Find Your ICP with AI](https://www.clay.com/university/lesson/find-your-icp-with-ai)

---

### 1.2 Apollo.io

**Approach:** Dual scoring — manual rules + AI-generated models.

**How it works:**
- **Manual scoring:** Users define criteria, weightings, and variables. Scores 0-100.
- **AI scoring:** Analyzes CRM deal history (won/lost accounts) to auto-generate predictive models. Requires sufficient succeeded and failed accounts for training.
- Combines firmographic, demographic, behavioral, and product/marketing data.
- Scores filter directly in search — reps see scored prospects in real-time.
- Full transparency into why each lead received its score.

**AI model requirements:** Needs accounts in a "succeeded" stage and accounts in a "not succeeded" stage (or in-progress >30 days) to train the model. Accuracy improves over time as more deals close.

**Key differentiator:** The AI model learns from YOUR historical conversion patterns, not generic benchmarks. Also operates against a 210M+ contact database.

**Sources:**
- [Apollo Scores Overview](https://knowledge.apollo.io/hc/en-us/articles/4988048582285-Scores-Overview)
- [Apollo Lead Scoring Product](https://www.apollo.io/product/scores)
- [AI Lead Scoring Guide](https://www.apollo.io/magazine/identify-your-perfect-leads-with-ai-powered-lead-scoring)

---

### 1.3 ZoomInfo

**Approach:** AI-driven ICP generation + Copilot account prioritization.

**How it works:**
- **Automated ICP generation:** Upload CRM export of won/lost deals. ZoomInfo's algorithms identify which company attributes correlate with wins.
- **Copilot AI prioritization:** Creates customized high-priority account lists per seller, combining firmographic, technographic, and intent signals.
- **Fit-based scoring:** Evaluates whether the account matches the ICP.
- **Engagement-based scoring:** Evaluates whether the account is actively engaging.

**Best-in-class model (per ZoomInfo):** Uses two dimensions:
| | High Fit | Low Fit |
|---|---|---|
| **High Engagement** | Sales-ready | Marketing nurture |
| **Low Engagement** | SDR outreach | Deprioritize |

**Key differentiator:** The "auto ICP" feature — feed it your deals and it tells you what your ICP actually is (vs. what you think it is).

**Sources:**
- [ZoomInfo ICP Guide](https://pipeline.zoominfo.com/marketing/ideal-customer-profile)
- [ZoomInfo Copilot Account Prioritization](https://pipeline.zoominfo.com/sales/zoominfo-copilot-account-prioritization)
- [Auto ICP Generation Play](https://pipeline.zoominfo.com/sales/auto-icp-generation)

---

### 1.4 Clearbit / Breeze Intelligence (HubSpot)

**Approach:** 2D scoring (Fit + Intent) with A/B/F letter-grade tiers.

**How it works:**
- **Fit score (letter grade A-D):** Based on firmographic data — B2B orientation, employee count, location, technology used.
- **Intent score (numeric 1-10):** Based on behavioral signals — website visits, content downloads, demo requests.
- Combined into pairs like "A2" (great fit, low intent) or "D10" (poor fit, high intent).
- Leads classified into three buckets:
  - **A Class:** Matches ICP with ideal questionnaire answers → AE handles
  - **B Class:** Matches ICP but suboptimal use case → AE handles
  - **F Class:** Everyone else → SDR vets before any outreach

**Critical principle from Clearbit:** "Make fit scores (not intent scores) the main gatekeeper for sales attention." High-fit/low-intent leads should still go to sales (reps can develop intent). Low-fit/high-intent leads should NOT distract sales.

**Scoring evolution (3 stages):**
1. **Basic:** Manual filtering only
2. **Medium:** Point-based A/B/F buckets using industry, business model, technology, revenue, employees, country, job title, leadership level
3. **Advanced:** Machine learning (MadKudu) + custom intent model using data warehouse (Segment → Redshift → dbt → Census)

**Sources:**
- [Clearbit Lead Scoring Basics](https://clearbit.com/resources/books/lead-qualification/lead-scoring-basics)
- [Clearbit Lead Scoring Examples](https://clearbit.com/resources/books/lead-qualification/lead-scoring-examples)
- [Clearbit Lead Scoring Stages](https://clearbit.com/resources/books/lead-qualification/lead-scoring-stages)

---

### 1.5 6sense

**Approach:** AI predictive buying stage model with intent + engagement scoring.

**How it works:**
- **Intent Score (0-100):** Measures account readiness to buy based on content consumption, research behavior, and engagement across first-party and third-party channels.
- **Engagement Score (0-100):** Tracks direct interactions with your brand.
- **Predictive Buying Stages** mapped from intent score:

| Stage | Intent Score | Action |
|---|---|---|
| Target | < 20 | Not in-market |
| Awareness | 20-49 | Top of funnel, early stage |
| Consideration | 50-69 | Above-average engagement history |
| Decision | 70-84 | Actively comparing options |
| Purchase | 85+ | Ready for immediate sales outreach |

- **6QA (6sense Qualified Account):** Accounts in Decision or Purchase stage = sales-ready.
- AI identifies accounts entering buying cycles up to 6 months before competitors.

**Signal sources:** Trillions of buyer signals from "Signalverse" — website visits, content downloads, ad interactions, CRM data, webinar attendance, email interactions, social media activity, keyword research, and third-party content consumption.

**Key differentiator:** Purely intent-driven. Does not require manual scoring rules — the AI predicts buying stage from observed signals.

**Sources:**
- [6sense Predictive Buying Stages](https://support.6sense.com/docs/predictive-buying-stages)
- [6sense Intent & Engagement Scores](https://6sense.com/blog/magic-numbers-breaking-down-6senses-intent-and-engagement-scores/)
- [6sense Predictive Analytics](https://6sense.com/platform/predictive-analytics/)

---

### 1.6 Demandbase

**Approach:** Unified scoring across three pillars — Fit + Intent + Engagement.

**How it works:**
- **Fit (ICP):** Firmographic (industry, size, revenue, geography) + technographic (tech stack)
- **Intent:** First-party (website visits, downloads) + third-party (publisher research, competitor searches)
- **Engagement:** Direct brand interactions from passive (email opens) to active (demo attendance, proposal requests)

**Scoring example with point values:**

| Signal | Points |
|---|---|
| Industry match | 20 |
| Company size >500 employees | 15 |
| Competitor research detected | 20 |
| Analyst site downloads | 10 |
| Pricing page visits | 30 |
| C-level case study downloads | 20 |

**Tier thresholds:**
- **Tier A (85+):** Immediate sales routing within 24 hours
- **Tier B (60-84):** ABM campaigns and nurture sequences
- **Tier C (<60):** Low-cost, broad marketing channels

**Intent detection specifics:**
- **Trending Intent:** Activity increased 2 standard deviations over last 7 days vs. last 8 weeks
- **Intent Surge:** Third-party signals from Bombora, G2, TrustRadius

**Model maintenance:** Quarterly validation minimum. Test win rates across tiers. High-growth teams refine continuously.

**Best practices:**
- Keep models simple: 3-5 attributes per pillar
- Weight intentionally — without it, junior email opens outrank executive demo requests
- Validate against closed-won pipeline data
- Healthy MQA conversion benchmark: 60-80%

**Sources:**
- [Demandbase Account Scoring Guide](https://www.demandbase.com/blog/account-scoring/)
- [Demandbase Intent Signals](https://www.demandbase.com/faq/intent-signals/)
- [Demandbase Qualification Scores](https://support.demandbase.com/hc/en-us/articles/360053937452-Understanding-Qualification-Scores)

---

## 2. ICP Scoring Dimensions

### 2.1 Company-Level Signals

| Signal | Data Sources | Scoring Relevance | Notes |
|---|---|---|---|
| **Revenue / EBITDA** | PrivCo, PitchBook, D&B, modeled estimates | Critical — primary size filter | Must estimate for private cos (see Section 4) |
| **Employee count** | LinkedIn, Apollo, ZoomInfo, Clay enrichment | High — proxy for revenue + company stage | Self-reported on LinkedIn; verify with multiple sources |
| **Industry / SIC / NAICS** | SEC filings, D&B, enrichment providers | Critical — determines ICP fit | 6-digit NAICS for specificity; multiple codes per company possible |
| **Year founded / age** | Crunchbase, D&B, state registrations | Medium — indicates stability | Older = more established but also more entrenched |
| **Geography** | Enrichment providers, website, registrations | High — regulatory and market relevance | Country + state + metro area |
| **Technology stack** | BuiltWith, Wappalyzer, HG Insights, Slintel | Medium-High — indicates sophistication | Best for SaaS targeting; less relevant for manufacturing |
| **Growth signals** | Job postings, funding, press releases | High — indicates buying capacity | Hiring = growth; layoffs = contraction |
| **Company type** | D&B, PitchBook, state filings | High — PE-backed vs family-owned matters | PE-backed = more acquisitive, faster decisions |
| **Website quality** | Web scraping, SEMrush, SimilarWeb | Low-Medium — vanity metric for manufacturing | Poor proxy for manufacturing quality |

### 2.2 Contact-Level Signals

| Signal | Data Sources | Scoring Relevance |
|---|---|---|
| **Job title / seniority** | LinkedIn, Apollo, ZoomInfo | Critical — determines decision authority |
| **Department / function** | LinkedIn, enrichment providers | High — operations vs. engineering vs. C-suite |
| **Time in role** | LinkedIn | Medium — new hires = change agents |
| **LinkedIn activity** | LinkedIn Sales Navigator | Low-Medium — many manufacturing execs are not active |
| **Decision-making authority** | Title inference, org chart analysis | Critical — owner/CEO/VP vs. manager |

### 2.3 Behavioral / Intent Signals

| Signal | Detection Method | Value |
|---|---|---|
| **Website visits** | First-party tracking, IP resolution | High if identified |
| **Content downloads** | Marketing automation | High |
| **Job postings** | Indeed, LinkedIn, Google Jobs | High — hiring for roles = buying signal |
| **Technology adoption/changes** | BuiltWith changes, G2 reviews | Medium |
| **Funding rounds** | Crunchbase, PitchBook | High — fresh capital = buying capacity |
| **M&A activity** | Press releases, SEC filings | High — integration = new tool purchases |
| **News mentions** | Google News API, media monitoring | Medium |
| **Regulatory changes** | Industry publications, government sites | High for A&D and medical device |

---

## 3. Scoring Methodology

### 3.1 Weighted Scoring vs. Machine Learning

| Approach | When to Use | Pros | Cons |
|---|---|---|---|
| **Manual weighted scoring** | Early stage, < 100 closed deals, clear ICP | Simple, transparent, fast to implement | Subjective weights, doesn't improve automatically |
| **Machine learning** | 200+ closed deals, rich CRM data | Data-driven, discovers hidden patterns, improves over time | Black box, needs training data, cold start problem |
| **Hybrid** | Most B2B companies | Best of both — manual rules as baseline, ML for refinement | More complex to maintain |

**Research finding (2025 Frontiers study):** Gradient Boosting Classifier achieved 98.39% accuracy in B2B lead scoring. Random Forest handles missing values effectively and works with diverse data types.

**Recommendation for our use case:** Start with manual weighted scoring (we likely have < 200 closed deals). Transition to ML once enough deal history exists. Use Random Forest if attempting ML — it handles missing data natively.

### 3.2 Weight Calibration

**Manual tuning approach:**
1. List all scoring criteria
2. Assign initial weights based on sales team intuition
3. Run the model against 50-100 known good/bad accounts
4. Compare model predictions vs. actual outcomes
5. Adjust weights where model disagrees with reality
6. Repeat quarterly

**Data-driven approach (when enough data exists):**
1. Export all won and lost deals from CRM
2. For each attribute, calculate correlation with win/loss
3. Attributes with strongest correlation get highest weights
4. Use logistic regression coefficients as initial weights
5. Validate with holdout set

### 3.3 Handling Missing Data

| Strategy | When to Use |
|---|---|
| **Don't penalize** | When data is commonly unavailable (e.g., EBITDA for private cos) |
| **Score as neutral** | Assign the median score for that attribute when data is missing |
| **Normalize against available data** | Calculate score only from attributes that have data, then scale |
| **Flag for manual review** | When the missing attribute is critical (e.g., employee count) |
| **Use proxy data** | Estimate from available data (e.g., revenue from employee count) |

**Best practice:** Never penalize a company for data you can't find. A company with 3 out of 5 attributes matching Gold criteria should score based on those 3, not be penalized for 2 unknowns. Normalize: `score = (points_earned / points_possible) * 100`.

### 3.4 Tiering Systems

| System | Pros | Cons |
|---|---|---|
| **Absolute tiers (Gold/Silver/Bronze)** | Clear, fixed criteria everyone understands | May need recalibration as market shifts |
| **Numeric scores (0-100)** | Granular, flexible | Hard for reps to interpret quickly |
| **Percentile ranks** | Auto-adjusts to data distribution | Relative — Gold account today may not be Gold tomorrow |
| **Letter + Number (A2, B7)** | Separates fit from intent clearly | More complex to implement |

**Recommendation:** Use absolute tiers (Gold/Silver/Bronze) with numeric scores underneath. Tiers give reps clear routing rules. Numeric scores break ties within tiers.

### 3.5 Score Recalculation Frequency

| Data Type | Recalculation Frequency |
|---|---|
| Firmographic (employee count, revenue) | Monthly — changes slowly |
| Technographic (tech stack) | Monthly |
| Intent signals (website visits, content) | Daily or real-time |
| Engagement (email opens, meetings) | Real-time |
| News/events (funding, M&A) | Daily |
| Full model revalidation | Quarterly |

---

## 4. EBITDA Estimation for Private Companies

### 4.1 The Problem

Our ICP targets companies with 1-15M EBITDA. Most are private and do not disclose financials. We need reliable estimation methods.

### 4.2 Data Sources for Private Company EBITDA

| Source | Coverage | Accuracy | Cost |
|---|---|---|---|
| **PrivCo** | 900K+ private companies | High for larger companies | Expensive ($10K+/yr) |
| **PitchBook** | PE-backed and VC-backed | High | Very expensive ($20K+/yr) |
| **D&B / Dun & Bradstreet** | Broad | Medium — modeled estimates | Moderate |
| **ZoomInfo** | Broad | Medium — modeled | Included in platform |
| **Apollo** | Broad | Low-Medium — ranges only | Included in platform |
| **Clay (multi-provider)** | Varies by provider | Best when waterfall across providers | Per-credit cost |
| **State/county filings** | Limited to certain states | Low | Free but manual |
| **Industry databases (IBISWorld)** | Industry-level, not company | Medium for benchmarking | Moderate |

### 4.3 Revenue-to-EBITDA Estimation Framework

When EBITDA is unavailable, estimate it from revenue using industry-specific margins:

**Step 1: Estimate revenue from employee count**

| Industry | Revenue per Employee (approximate) |
|---|---|
| Aerospace/Defense | $250K-400K |
| Medical Devices | $200K-350K |
| Industrial Machinery | $200K-350K |
| Custom Manufacturing | $150K-300K |
| Specialty Services | $150K-250K |
| Metal Fabrication | $150K-250K |

*Note: NYU Stern data shows Aerospace/Defense at ~$38K revenue/employee for large public companies, but this includes massive primes with huge workforces. For smaller niche manufacturers, revenue/employee is typically much higher.*

**Step 2: Apply EBITDA margin by industry**

| Industry | Typical EBITDA Margin | Source |
|---|---|---|
| Aerospace/Defense | 10-15% | NYU Stern (10.69% EBITDA/Sales) |
| Medical Devices | 15-25% (profitable ones) | Varies widely; early-stage often negative |
| Industrial Machinery | 12-20% | NYU Stern (19.62% for Machinery) |
| Custom Manufacturing | 8-15% | Industry benchmarks |
| Specialty Services | 15-25% | Higher margins for specialized knowledge |
| Metal Fabrication | 8-12% | Lower margins, capital intensive |

**Step 3: Calculate estimated EBITDA**

```
Estimated Revenue = Employee Count x Revenue per Employee (industry)
Estimated EBITDA = Estimated Revenue x EBITDA Margin (industry)
```

**Example:**
- Company: 50 employees, custom manufacturing
- Estimated Revenue: 50 x $200K = $10M
- Estimated EBITDA: $10M x 12% = $1.2M
- Result: Below our 1M EBITDA minimum but close — classify as Silver

**Step 4: Adjust with available signals**

Increase confidence if:
- Company has been operating 20+ years (stable margins)
- Company owns real estate (asset-backed)
- Company serves A&D or medical (higher margins)
- Company has PE backing (optimized margins)
- Company is hiring (growth = likely profitable)

Decrease confidence if:
- Company has recent layoffs
- Company is in commodity manufacturing (lower margins)
- Company is < 5 years old (unstable margins)

### 4.4 EBITDA Validation Checklist

When an estimated EBITDA looks promising, validate with:
1. Revenue estimates from multiple enrichment providers (Clay waterfall)
2. Employee count from LinkedIn vs. enrichment providers
3. Glassdoor salary data (can estimate labor costs)
4. Job posting volume (growth indicator)
5. Facility size from Google Maps / county records
6. Equipment/asset indicators from website
7. Customer lists or contracts mentioned on website
8. Industry awards or certifications (quality indicator)

---

## 5. Identifying Niche Manufacturing Companies Programmatically

### 5.1 NAICS/SIC Code Strategy

**Relevant NAICS codes for our ICP:**

| NAICS Code | Description | Relevance |
|---|---|---|
| 332710 | Machine Shops | High — custom machining |
| 332999 | All Other Miscellaneous Fabricated Metal Product Manufacturing | High |
| 332710-332999 | Fabricated Metal Product Manufacturing (332) | Broad manufacturing |
| 333249 | Other Industrial Machinery Manufacturing | High |
| 333514 | Special Die and Tool, Die Set, Jig, and Fixture Manufacturing | High — tooling |
| 333515 | Cutting Tool and Machine Tool Accessory Manufacturing | High |
| 334511 | Search, Detection, Navigation, Guidance, Aeronautical Systems | A&D |
| 334519 | Other Measuring and Controlling Device Manufacturing | Medical/Industrial |
| 336411 | Aircraft Manufacturing | A&D |
| 336412 | Aircraft Engine and Engine Parts Manufacturing | A&D |
| 336413 | Other Aircraft Parts and Auxiliary Equipment Manufacturing | A&D |
| 339112 | Surgical and Medical Instrument Manufacturing | Medical Device |
| 339113 | Surgical Appliance and Supplies Manufacturing | Medical Device |
| 339114 | Dental Equipment and Supplies Manufacturing | Medical Device |

**Strategy:** Use NAICS codes as initial filter, then refine with keyword analysis.

### 5.2 Keyword-Based Detection for "Niche" vs. "Generic" Industrial

**Website keyword signals for niche/custom manufacturing:**

| Signal Type | Keywords to Detect | Scoring Impact |
|---|---|---|
| **Custom work indicators** | "custom", "bespoke", "made-to-order", "engineered-to-order", "prototype", "low-volume", "high-mix" | Strong positive |
| **Specialty certifications** | "AS9100" (A&D), "ISO 13485" (medical), "ITAR", "NADCAP", "ISO 9001" | Strong positive |
| **Material specialization** | "titanium", "inconel", "exotic alloys", "composites", "ceramics" | Positive |
| **Process specialization** | "5-axis", "EDM", "laser cutting", "precision grinding", "CNC", "additive manufacturing" | Positive |
| **Customer types** | "OEM", "Tier 1 supplier", "defense contractor", "medical OEM" | Strong positive |
| **Commodity indicators** | "high-volume", "mass production", "standard parts", "catalog" | Negative — indicates generic |

**Implementation approach:**
1. Scrape company website using Clay/Claygent or Firecrawl
2. Extract text from About page, Capabilities page, and Services page
3. Run keyword matching against the lists above
4. Score based on keyword density and combination
5. Companies with 3+ niche indicators = likely custom manufacturer

### 5.3 Additional Programmatic Detection Methods

| Method | How It Works | Accuracy |
|---|---|---|
| **Certification database lookup** | Query AS9100, ISO 13485, NADCAP registrar databases | High — certifications don't lie |
| **Industry association membership** | Check NTMA, PMI, AMT, NDIA member directories | High |
| **Government contract databases** | SAM.gov, FPDS for defense contractors | High for A&D |
| **Patent filings** | USPTO search for company patents | Medium — indicates innovation |
| **Trade show exhibitor lists** | IMTS, AeroDef, MD&M exhibitor databases | High |
| **Google Maps category** | "Machine shop", "Metal fabrication", "Aerospace manufacturer" | Medium |

---

## 6. Quality Tier Design (Gold/Silver/Bronze)

### 6.1 How Other Tools Define Tiers

| Platform | Tiers | Routing Logic |
|---|---|---|
| Demandbase | Tier A (85+) / Tier B (60-84) / Tier C (<60) | A = immediate sales (24hr), B = ABM nurture, C = broad marketing |
| Clearbit | A / B / F | A = AE direct, B = AE with context, F = SDR vets first |
| 6sense | Target / Awareness / Consideration / Decision / Purchase | Decision + Purchase = 6QA = sales ready |
| Apollo | 0-100 numeric | Custom thresholds per team |
| LeanData | Strong / Moderate / Weak fit | Combined with intent stage |

### 6.2 Recommended Tier Design for Our ICP

**Should tiers be absolute or relative?**

Use **absolute tiers** with fixed criteria. Rationale:
- Our target market (niche industrial 1-15M EBITDA) is well-defined
- Relative tiers would shift as our database grows, creating inconsistency
- Absolute tiers are easier for reps to understand and trust
- Recalibrate thresholds quarterly, not the tier system itself

### 6.3 Proposed Gold/Silver/Bronze Criteria

#### Gold Tier (Score 80-100) — Immediate Outreach

Must meet ALL of:
- **EBITDA:** Estimated 3-15M (or revenue proxy suggesting this range)
- **Employees:** 25-100
- **Geography:** US, UK, or Canada
- **Industry:** Matches target NAICS codes (A&D, medical device, niche industrial)

Must meet 2+ of:
- Certifications detected (AS9100, ISO 13485, ITAR, NADCAP)
- Custom/specialty manufacturing keywords on website
- PE-backed or acquisition target indicators
- Company age > 10 years
- Active job postings (growth signal)
- Government contracts (SAM.gov presence)

#### Silver Tier (Score 50-79) — Qualified for Nurture + Research

Must meet ALL of:
- **EBITDA:** Estimated 1-3M OR 15-25M (close to range, either direction)
- **Employees:** 10-150
- **Geography:** US, UK, Canada, or other English-speaking
- **Industry:** Manufacturing or industrial (broader than Gold)

Must meet 1+ of:
- Some niche indicators on website
- Related industry (not exact but adjacent)
- Right size but unclear EBITDA
- Right EBITDA but slightly outside other criteria

#### Bronze Tier (Score 20-49) — Low Priority / Future Pipeline

Meets SOME criteria but not enough for Silver:
- Right geography but wrong size
- Right industry but too small/large
- Generic manufacturing (not niche/custom)
- Data quality too low to classify higher
- Right size but wrong geography

#### Disqualified (Score < 20) — Exclude

- Outside all target geographies
- Clearly wrong industry (retail, SaaS, etc.)
- < 5 employees or > 500 employees
- Known non-target (competitor, vendor, etc.)

### 6.4 Scoring Weights for Our ICP

| Dimension | Weight | Rationale |
|---|---|---|
| **EBITDA / Revenue fit** | 30% | Primary qualification criteria — are they the right size? |
| **Employee count fit** | 15% | Secondary size indicator, validates EBITDA estimate |
| **Industry match** | 25% | Must be in target industries |
| **Geography match** | 10% | Binary — US/UK/Canada or not |
| **Niche/Custom indicators** | 15% | Differentiates custom manufacturers from commodity |
| **Growth/Intent signals** | 5% | Nice-to-have, not a must-have for our model |

**Total: 100%**

### 6.5 Detailed Point Allocation

#### EBITDA / Revenue Fit (30 points max)

| Estimated EBITDA | Points |
|---|---|
| $3M - $15M | 30 |
| $1M - $3M | 20 |
| $15M - $25M | 15 |
| $500K - $1M | 10 |
| $25M - $50M | 5 |
| Outside range | 0 |

#### Employee Count (15 points max)

| Employees | Points |
|---|---|
| 25-100 | 15 |
| 10-25 | 10 |
| 100-150 | 10 |
| 150-250 | 5 |
| < 10 or > 250 | 0 |

#### Industry Match (25 points max)

| Industry | Points |
|---|---|
| Exact NAICS match (A&D, medical device, specialty industrial) | 25 |
| Adjacent industrial (general machining, fabrication) | 15 |
| Broad manufacturing | 10 |
| Services related to target industries | 5 |
| Non-manufacturing | 0 |

#### Geography (10 points max)

| Geography | Points |
|---|---|
| US (target states: TX, CA, OH, MI, CT, PA, FL) | 10 |
| US (other states) | 8 |
| Canada or UK | 8 |
| Other English-speaking | 3 |
| Other | 0 |

#### Niche/Custom Indicators (15 points max)

| Indicator | Points (additive, cap at 15) |
|---|---|
| AS9100, ISO 13485, ITAR, or NADCAP certified | 5 |
| "Custom", "bespoke", "engineered-to-order" on website | 4 |
| Specialty materials/processes mentioned | 3 |
| Government contractor (SAM.gov) | 3 |
| Industry association member | 2 |
| Trade show exhibitor | 2 |

#### Growth/Intent Signals (5 points max)

| Signal | Points (additive, cap at 5) |
|---|---|
| Active job postings (3+ open roles) | 2 |
| Recent funding or PE investment | 2 |
| Recent acquisition or M&A news | 2 |
| Website visits to our content | 1 |
| Hiring for roles that indicate need | 1 |

### 6.6 Score-to-Tier Mapping

| Score | Tier | Action |
|---|---|---|
| 80-100 | Gold | Immediate personalized outreach. Assign to AE. |
| 50-79 | Silver | Enrich further. Add to nurture sequence. SDR validates. |
| 20-49 | Bronze | Low-priority pool. Automated nurture only. |
| 0-19 | Disqualified | Exclude from outreach. |

---

## 7. Recommended Scoring Model for Our ICP

### 7.1 Implementation Phases

**Phase 1: Manual Weighted Scoring (Now)**
- Implement the scoring model above in Clay
- Use conditional formulas for each dimension
- Enrich with employee count (LinkedIn/Apollo), industry (NAICS), geography
- Estimate EBITDA from employee count x industry revenue/employee x EBITDA margin
- Scrape websites for niche manufacturing keywords
- Score, tier, and route

**Phase 2: Validated Scoring (After 50+ deals)**
- Compare tier distribution vs. actual win rates
- Adjust weights based on which attributes correlate with wins
- Add data sources that proved most predictive
- Drop attributes that didn't differentiate

**Phase 3: ML-Assisted Scoring (After 200+ deals)**
- Train model on CRM deal history
- Use Random Forest (handles missing data well)
- Keep manual scoring as baseline — ML augments
- A/B test ML scores vs. manual scores

### 7.2 Data Enrichment Waterfall for Our ICP

For each company, enrich in this order:

1. **Employee count:** LinkedIn → Apollo → ZoomInfo → Clay providers
2. **Industry/NAICS:** D&B → Apollo → website scraping
3. **Revenue estimate:** ZoomInfo → Apollo → D&B → employee-based estimate
4. **EBITDA estimate:** PrivCo (if available) → Revenue x industry margin
5. **Geography:** Enrichment providers → website → state filings
6. **Website content:** Claygent scrape → keyword extraction
7. **Certifications:** Claygent scrape → certification databases
8. **Growth signals:** Google Jobs → LinkedIn hiring → Crunchbase

### 7.3 Key Implementation Decisions

| Decision | Recommendation | Rationale |
|---|---|---|
| Scoring tool | Clay | Maximum flexibility for custom scoring formulas |
| Score range | 0-100 | Industry standard, maps cleanly to tiers |
| Tier system | Absolute (Gold/Silver/Bronze) | Fixed criteria, clear for reps |
| Missing data handling | Score on available data, normalize | Never penalize for unavailable data |
| EBITDA source | Multi-provider waterfall + estimation | No single source is reliable for private cos |
| Recalculation frequency | Weekly for enrichment, quarterly for model | Balance freshness vs. compute cost |
| Fit vs. Intent weighting | 95% fit / 5% intent | Our market has low digital intent signals; fit is king |

### 7.4 Why Intent Signals Are Less Important for Our ICP

Unlike SaaS or technology buyers who leave heavy digital footprints (searching for solutions, reading G2 reviews, visiting pricing pages), niche manufacturers:
- Rarely research solutions online before buying
- Make decisions through relationships and referrals
- Do not attend webinars or download whitepapers
- May not have sophisticated digital presence
- Buying decisions are made by owner/CEO, not a "buying committee"

**Therefore:** Weight fit (firmographic + industry + niche signals) at 95% and intent at 5%. This is the opposite of what 6sense or Demandbase recommend for tech companies, but it matches our market reality.

---

## Summary: Platform Comparison Matrix

| Feature | Clay | Apollo | ZoomInfo | Clearbit | 6sense | Demandbase |
|---|---|---|---|---|---|---|
| **Custom scoring** | Formulas | Rules + AI | AI-generated | Point-based | AI-only | Rules + AI |
| **EBITDA data** | Via providers | Ranges | Modeled | Limited | No | No |
| **Manufacturing coverage** | Good (via providers) | Good | Good | Limited | Limited | Limited |
| **Niche detection** | Best (web scraping + AI) | Basic | Basic | Basic | No | No |
| **Missing data handling** | Manual (formula) | Neutral scoring | Auto-adjusted | Manual | AI handles | Manual |
| **Best for our ICP** | Yes — most flexible | Good secondary | Good data source | Less relevant | Not ideal | Not ideal |
| **Price point** | Moderate | Moderate | Expensive | HubSpot bundle | Expensive | Expensive |

**Winner for our use case: Clay** — the only platform flexible enough to build custom EBITDA estimation formulas, scrape websites for manufacturing keywords, and combine multiple enrichment sources into a custom scoring model for niche industrial companies.

---

*Research compiled from analysis of platform documentation, industry publications, and academic studies (Frontiers in AI, 2025). All scoring recommendations are starting points — calibrate against actual deal outcomes quarterly.*
