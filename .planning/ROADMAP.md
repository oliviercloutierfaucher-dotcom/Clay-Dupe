# Roadmap: Clay-Dupe

## Milestones

- ✅ **v1.0 Hardening & Scaling** - Phases 1-9 (shipped 2026-03-07)
- 🚧 **v2.0 Full Prospecting Platform** - Phases 10-13 (in progress)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (10.1, 10.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

<details>
<summary>v1.0 Hardening & Scaling (Phases 1-9) - SHIPPED 2026-03-07</summary>

9 phases, 28 plans completed. See .planning/MILESTONES.md for details.

</details>

### v2.0 Full Prospecting Platform

**Milestone Goal:** Transform from enrichment-only tool into end-to-end prospecting platform with company sourcing, Salesforce dedup, AI outreach, and cloud deployment.

- [x] **Phase 10: Infrastructure + Company Sourcing** - SQLite write queue, API key validation, and full company sourcing pipeline (Apollo search, CSV import, manual add, contact discovery, ICP scoring) (completed 2026-03-08)
- [ ] **Phase 11: Salesforce Integration** - Connection management, batch account dedup, and duplicate flagging in enrichment UI
- [ ] **Phase 12: AI Email Generation + Export** - Claude-powered personalized emails with templates, batch generation, preview/edit, and Outreach.io CSV export
- [ ] **Phase 13: Cloud Deployment + Pipeline Polish** - Docker-based cloud deployment and end-to-end pipeline integration testing

## Phase Details

### Phase 10: Infrastructure + Company Sourcing
**Goal**: Users can source companies from multiple channels and the platform handles concurrent writes safely with validated API keys
**Depends on**: v1.0 complete (Phase 9)
**Requirements**: INFRA-01, INFRA-03, SRC-01, SRC-02, SRC-03, SRC-04, SRC-05, SRC-06
**Success Criteria** (what must be TRUE):
  1. User sees API key validation status for all configured providers on startup (pass/fail per key)
  2. User can search Apollo for companies using ICP filters (employee count, location, industry) and see results in UI
  3. User can import a CSV of companies and manually add individual companies, with source tracked per record
  4. User can discover contacts at any sourced company via Apollo people search
  5. System auto-scores each sourced company against ICP criteria and displays the score
**Plans**: 4 plans

Plans:
- [ ] 10-01-PLAN.md -- Infrastructure hardening: write lock, API key validation, schema/model updates
- [ ] 10-02-PLAN.md -- Core engines: ICP scoring and contact discovery modules
- [ ] 10-03-PLAN.md -- Company sourcing: Apollo save, CSV import, manual add, company list page
- [ ] 10-04-PLAN.md -- Integration: ICP scoring UI, contact discovery UI, pipeline wiring

### Phase 11: Salesforce Integration
**Goal**: Users can check enrichment targets against Salesforce to prevent duplicate outreach and save enrichment credits
**Depends on**: Phase 10
**Requirements**: SF-01, SF-02, SF-03, SF-04
**Success Criteria** (what must be TRUE):
  1. User can enter Salesforce credentials in the settings page and save them
  2. User can test the Salesforce connection and see a clear success or failure message
  3. System checks company domains against Salesforce Accounts before enrichment and skips matches
  4. Rows matching existing Salesforce accounts are visually flagged in the enrichment UI
**Plans**: 2 plans

Plans:
- [ ] 11-01-PLAN.md -- SF client module, config model, database schema extensions, and unit tests
- [ ] 11-02-PLAN.md -- Settings UI card, pre-enrichment dedup gate, companies page SF status display

### Phase 12: AI Email Generation + Export
**Goal**: Users can generate personalized cold emails from enriched data and export them ready for Outreach.io sequences
**Depends on**: Phase 11
**Requirements**: EMAIL-01, EMAIL-02, EMAIL-03, EMAIL-04, EMAIL-05
**Success Criteria** (what must be TRUE):
  1. User can generate a personalized cold email for any enriched contact using company and contact data
  2. User can create and edit email prompt templates with variable placeholders (company name, contact name, industry, etc.)
  3. User can batch-generate emails for an entire campaign and see progress
  4. User can preview each generated email, edit it inline, and approve or reject before export
  5. User can export approved emails as a CSV with columns matching Outreach.io import format (email, name, subject, body)
**Plans**: TBD

Plans:
- [ ] 12-01: TBD
- [ ] 12-02: TBD
- [ ] 12-03: TBD

### Phase 13: Cloud Deployment + Pipeline Polish
**Goal**: Application runs in the cloud via Docker and the full source-to-export pipeline works end-to-end
**Depends on**: Phase 12
**Requirements**: INFRA-02
**Success Criteria** (what must be TRUE):
  1. Application builds and runs in a Docker container with all dependencies
  2. Application deploys to a cloud provider (Railway or Fly.io) and is accessible via URL
  3. Full pipeline works end-to-end: source companies, check Salesforce, enrich contacts, generate emails, export CSV
**Plans**: TBD

Plans:
- [ ] 13-01: TBD
- [ ] 13-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 10 -> 10.x -> 11 -> 11.x -> 12 -> 12.x -> 13

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 10. Infrastructure + Company Sourcing | 4/4 | Complete    | 2026-03-08 | - |
| 11. Salesforce Integration | v2.0 | 0/2 | Not started | - |
| 12. AI Email Generation + Export | v2.0 | 0/? | Not started | - |
| 13. Cloud Deployment + Pipeline Polish | v2.0 | 0/? | Not started | - |
