---
phase: 10-infrastructure-company-sourcing
plan: 03
subsystem: ui, data
tags: [streamlit, csv-import, column-mapper, company-sourcing, apollo, domain-normalization]

# Dependency graph
requires:
  - phase: 10-01
    provides: "Company model with source_type/icp_score/status, upsert_company, search_companies"
provides:
  - Three company sourcing channels: Apollo search save, CSV import, manual add
  - ColumnMapper with company-specific aliases (revenue, ebitda, founded_year, etc.)
  - map_to_companies() function for CSV-to-Company mapping with domain dedup
  - Sortable company table with bulk status update
  - Source type tracking per company record
affects: [10-04, 11-infrastructure-salesforce]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "map_to_companies() converts mapped DataFrame to Company objects with domain dedup"
    - "ColumnMapper auto-detects company-specific columns (revenue, ebitda, founded_year)"
    - "CSV import uses ColumnMapper + map_to_companies pipeline with progress bar"

key-files:
  created:
    - tests/test_company_sourcing.py
  modified:
    - data/io.py
    - ui/pages/search.py
    - ui/pages/companies.py

key-decisions:
  - "Separated website_url from company_domain in ColumnMapper to avoid ambiguity (domain used for dedup, website for display)"
  - "map_to_companies deduplicates by normalized domain, first occurrence wins with COALESCE merge for non-None fields"
  - "Company table upgraded from markdown table to st.dataframe for sortability and multi-row selection"

patterns-established:
  - "CSV import pipeline: read_input_file -> ColumnMapper -> map_to_companies -> upsert_company"
  - "Source type tracking: csv_import, apollo_search, manual set on Company creation"

requirements-completed: [SRC-01, SRC-02, SRC-03, SRC-05]

# Metrics
duration: 8min
completed: 2026-03-08
---

# Phase 10 Plan 03: Company Sourcing Channels Summary

**Three-channel company sourcing (Apollo save, CSV import with ColumnMapper auto-detection, manual add) with sortable dataframe table and bulk status management**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-08T01:36:58Z
- **Completed:** 2026-03-08T01:44:33Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- ColumnMapper extended with 7 company-specific field groups (revenue, ebitda, founded_year, website_url, description, employee_count aliases, linkedin aliases)
- map_to_companies() function converts CSV data to Company objects with source_type tracking and domain-based deduplication
- Search page gains "Save Selected to Database" button for Apollo company results with source_type="apollo_search"
- Companies page upgraded: sortable st.dataframe, name/domain search, ColumnMapper-based CSV import with progress bar, bulk status update

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for company sourcing** - `47bc074` (test)
2. **Task 1 GREEN: Column mapper + map_to_companies + search save** - `010bac6` (feat)
3. **Task 2: Companies page with CSV import, sortable table, bulk status** - `f112a6a` (feat)

_Note: TDD task -- tests written first (RED), then implementation (GREEN)._

## Files Created/Modified
- `tests/test_company_sourcing.py` - 19 tests: ColumnMapper company fields, CSV mapping, source tracking, domain dedup
- `data/io.py` - Added revenue_usd, ebitda_usd, founded_year, website_url, description aliases; map_to_companies() function
- `ui/pages/search.py` - Added "Save Selected to Database" button with source_type="apollo_search"
- `ui/pages/companies.py` - Upgraded CSV import to ColumnMapper, replaced markdown table with sortable st.dataframe, added bulk status update and name/domain search

## Decisions Made
- Separated website_url from company_domain in ColumnMapper to avoid ambiguity -- domain is used for dedup, website for display
- map_to_companies deduplicates by normalized domain with first-occurrence-wins and COALESCE merge for non-None fields
- Company table upgraded from markdown table to st.dataframe for sortability and multi-row selection

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three sourcing channels operational: Apollo search save, CSV import, manual add
- Source type tracked per company record for downstream filtering
- Company table provides sortable view with bulk status management
- ColumnMapper pipeline ready for any CSV format from Grata/Inven/Ocean.io lists

## Self-Check: PASSED

- All 4 files verified present on disk
- Commit 47bc074 (Task 1 RED) verified in git log
- Commit 010bac6 (Task 1 GREEN) verified in git log
- Commit f112a6a (Task 2) verified in git log
- 40 tests passing (19 company sourcing + 21 existing io tests)

---
*Phase: 10-infrastructure-company-sourcing*
*Completed: 2026-03-08*
