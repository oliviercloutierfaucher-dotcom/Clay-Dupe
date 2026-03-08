---
phase: 11-salesforce-integration
plan: 01
subsystem: integration
tags: [salesforce, simple-salesforce, soql, domain-matching, dedup-gate]

# Dependency graph
requires:
  - phase: 10-infra-sourcing
    provides: Company model, database layer, config/settings pattern
provides:
  - SalesforceClient with health_check() and check_domains_batch()
  - SalesforceConfig model and load_salesforce_config()
  - Company model sf_account_id, sf_status, sf_instance_url fields
  - Database update_company_sf_status() and get_companies_by_sf_status()
affects: [11-02-sf-settings-ui, 12-email-generation, companies-page]

# Tech tracking
tech-stack:
  added: [simple-salesforce]
  patterns: [schema-migration-section, alter-table-duplicate-safety]

key-files:
  created:
    - providers/salesforce.py
  modified:
    - config/settings.py
    - data/models.py
    - data/database.py
    - data/schema.sql
    - requirements.txt
    - tests/test_salesforce.py

key-decisions:
  - "SF is a dedup gate, NOT in ProviderName enum -- per research anti-pattern"
  - "Schema migrations use ALTER TABLE with duplicate-column safety in _init_db"
  - "health_check() creates fresh SF connection (not cached) for reliable credential testing"

patterns-established:
  - "Schema migrations section: ALTER TABLE statements after '-- Schema migrations' marker, executed individually with error tolerance"
  - "SF domain matching: Unique_Domain__c exact match first, Website LIKE fallback second"

requirements-completed: [SF-01, SF-02, SF-03]

# Metrics
duration: 5min
completed: 2026-03-08
---

# Phase 11 Plan 01: SF Foundation Summary

**SalesforceClient with health_check and batch domain matching via simple-salesforce, plus Company model SF status extensions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-08T05:34:51Z
- **Completed:** 2026-03-08T05:39:46Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- SalesforceClient with health_check() and check_domains_batch() fully implemented
- Two-phase domain matching: Unique_Domain__c exact match with Website LIKE fallback
- Company model extended with sf_account_id, sf_status, sf_instance_url
- Database schema migration pattern established for ALTER TABLE safety
- 18 unit tests covering config, client, model, and database operations

## Task Commits

Each task was committed atomically:

1. **Task 1: SalesforceClient module, config model, and tests**
   - `2de024c` (test: failing tests for SF client and config)
   - `26c519e` (feat: implement SalesforceClient and SalesforceConfig)
2. **Task 2: Database schema and model extensions for SF status**
   - `d8d8759` (test: failing tests for Company SF fields and DB methods)
   - `32783b5` (feat: extend Company model and DB with SF status fields)

_TDD tasks had separate RED/GREEN commits_

## Files Created/Modified
- `providers/salesforce.py` - SalesforceClient with health_check and check_domains_batch
- `config/settings.py` - SalesforceConfig model and load_salesforce_config helper
- `data/models.py` - Company model with sf_account_id, sf_status, sf_instance_url
- `data/database.py` - update_company_sf_status, get_companies_by_sf_status, migration-safe _init_db
- `data/schema.sql` - ALTER TABLE migrations for SF columns and index
- `requirements.txt` - Added simple-salesforce>=1.12.6
- `tests/test_salesforce.py` - 18 tests for config, client, model, and DB

## Decisions Made
- SF is a dedup gate, NOT in ProviderName enum (per research anti-pattern)
- Schema migrations use ALTER TABLE with duplicate-column safety in _init_db
- health_check() creates fresh SF connection (not cached) for reliable credential testing
- Session expiry handled with automatic reconnect retry

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Schema migration _init_db refactor for ALTER TABLE safety**
- **Found during:** Task 2 (database schema extensions)
- **Issue:** executescript() fails on ALTER TABLE if columns already exist; naive split-by-semicolon broke TRIGGER bodies
- **Fix:** Split schema into main DDL (executescript) + migration section (individual execute with duplicate-column error tolerance)
- **Files modified:** data/database.py
- **Verification:** All 18 tests pass, full suite 362 tests pass
- **Committed in:** 32783b5 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix necessary for correct schema migration handling. No scope creep.

## Issues Encountered
None beyond the schema migration approach documented above.

## User Setup Required
None - no external service configuration required. SF credentials are loaded from .env when configured.

## Next Phase Readiness
- SF client foundation complete, ready for settings UI (11-02)
- SalesforceConfig.is_configured() enables conditional UI rendering
- check_domains_batch() ready for pre-enrichment gate integration

---
*Phase: 11-salesforce-integration*
*Completed: 2026-03-08*
