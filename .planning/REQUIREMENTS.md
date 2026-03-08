# Requirements: Clay-Dupe

**Defined:** 2026-03-07
**Core Value:** Source, enrich, and qualify target companies with maximum accuracy in a single platform — preventing duplicate outreach to Salesforce contacts and generating personalized emails ready for Outreach.io sequences.

## v2.0 Requirements

Requirements for v2.0 Full Prospecting Platform. Each maps to roadmap phases.

### Salesforce

- [ ] **SF-01**: User can configure Salesforce connection credentials in settings page
- [ ] **SF-02**: User can test Salesforce connection and see success/failure status
- [ ] **SF-03**: System checks if company domain exists as Account in Salesforce before enrichment
- [ ] **SF-04**: System flags rows that match existing Salesforce accounts in the enrichment UI

### Company Sourcing

- [x] **SRC-01**: User can search for companies via Apollo with ICP filters (employee count, location, industry)
- [x] **SRC-02**: User can import company lists from CSV/Excel files
- [x] **SRC-03**: User can manually add individual companies (name, domain, industry)
- [x] **SRC-04**: User can discover contacts at sourced companies via Apollo people search
- [x] **SRC-05**: System tracks the source of each company (apollo_search, csv_import, manual)
- [x] **SRC-06**: System auto-scores companies against ICP criteria (employee count, revenue, industry match)

### AI Email Generation

- [ ] **EMAIL-01**: User can generate personalized cold emails from enriched contact/company data
- [ ] **EMAIL-02**: User can create and edit email prompt templates with variable substitution
- [ ] **EMAIL-03**: User can batch-generate emails for an entire campaign
- [ ] **EMAIL-04**: User can preview and edit generated emails before export
- [ ] **EMAIL-05**: User can export emails as Outreach.io-ready CSV (email, name, subject, body)

### Infrastructure

- [x] **INFRA-01**: System validates real API keys on startup and reports status
- [ ] **INFRA-02**: Application deploys to cloud via Docker (Railway/Fly.io)
- [x] **INFRA-03**: SQLite write queue prevents concurrent write contention

## Future Requirements

Deferred to v2.x or v3.0. Tracked but not in current roadmap.

### Salesforce (v2.x)

- **SF-05**: System performs fuzzy matching on company name + domain for dedup
- **SF-06**: System caches SF dedup results for 24h to avoid repeated queries
- **SF-07**: User can configure skip/flag/disabled dedup mode per campaign

### AI Email (v2.x)

- **EMAIL-06**: System adjusts email specificity based on enrichment confidence score
- **EMAIL-07**: User can save and load multiple prompt templates
- **EMAIL-08**: System tracks cost-per-lead across sourcing + enrichment + email generation

### Company Sourcing (v3.0)

- **SRC-07**: User can auto-segment companies into micro-campaigns by industry/size
- **SRC-08**: Additional sourcing providers (Grata, Inven, Ocean.io)

### Salesforce (v3.0)

- **SF-08**: System pushes enriched contacts back to Salesforce as Leads
- **SF-09**: User can map enrichment fields to Salesforce Lead/Contact fields

### Outreach (v3.0)

- **OUT-01**: System pushes generated emails directly to Outreach.io sequences via API

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| PostgreSQL migration | SQLite sufficient for team-size workloads |
| Mobile app | Web UI via browser sufficient |
| Email sending from platform | Stay focused on generation; Outreach handles deliverability |
| React/Next.js frontend rewrite | Streamlit sufficient for v2.0, revisit in v3.0 |
| Bidirectional Salesforce sync | Read-only check for v2.0; write-back is dangerous scope increase |
| Multi-LLM provider support | Abstract interface but ship with one provider (Claude) |
| Real-time Salesforce webhooks | Batch check before enrichment is sufficient for prospecting cadence |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 10 | Complete |
| INFRA-03 | Phase 10 | Complete |
| SRC-01 | Phase 10 | Complete |
| SRC-02 | Phase 10 | Complete |
| SRC-03 | Phase 10 | Complete |
| SRC-04 | Phase 10 | Complete |
| SRC-05 | Phase 10 | Complete |
| SRC-06 | Phase 10 | Complete |
| SF-01 | Phase 11 | Pending |
| SF-02 | Phase 11 | Pending |
| SF-03 | Phase 11 | Pending |
| SF-04 | Phase 11 | Pending |
| EMAIL-01 | Phase 12 | Pending |
| EMAIL-02 | Phase 12 | Pending |
| EMAIL-03 | Phase 12 | Pending |
| EMAIL-04 | Phase 12 | Pending |
| EMAIL-05 | Phase 12 | Pending |
| INFRA-02 | Phase 13 | Pending |

**Coverage:**
- v2.0 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-07*
*Last updated: 2026-03-07 after roadmap creation*
