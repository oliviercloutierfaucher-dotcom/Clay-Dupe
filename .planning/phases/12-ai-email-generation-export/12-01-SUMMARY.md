---
phase: 12-ai-email-generation-export
plan: 01
subsystem: database, ai
tags: [anthropic, claude-haiku, email-generation, pydantic, sqlite, tenacity]

# Dependency graph
requires:
  - phase: 10-sourcing-infrastructure
    provides: "Person/Company models, Database class, campaign CRUD"
provides:
  - "EmailTemplate and GeneratedEmail Pydantic models"
  - "Database CRUD for email templates and generated emails"
  - "Email generation engine with Anthropic Claude Haiku 4.5"
  - "Variable substitution for template personalization"
  - "Batch generation function for background thread processing"
  - "3 starter templates (Consultative Intro, Case Study Follow-up, Breakup)"
affects: [12-02-ui-export]

# Tech tracking
tech-stack:
  added: ["anthropic>=0.40"]
  patterns: ["prompt caching via cache_control ephemeral", "tenacity retry on rate limit", "background thread batch generation"]

key-files:
  created:
    - "data/email_engine.py"
    - "tests/test_email_gen.py"
  modified:
    - "data/models.py"
    - "data/schema.sql"
    - "data/database.py"
    - "config/settings.py"
    - "requirements.txt"
    - "pyproject.toml"

key-decisions:
  - "Anthropic is NOT in ProviderName enum - separate ANTHROPIC_API_KEY in Settings"
  - "Sequential API calls with 1.2s delay chosen over Batch API for simplicity"
  - "Prompt caching on system prompt for 90% input cost reduction on batches"
  - "All 3 starter templates marked is_default=True for seed idempotency"

patterns-established:
  - "_call_anthropic uses tenacity retry on RateLimitError and APIConnectionError"
  - "run_batch_generation creates new Database instance for thread safety"
  - "_parse_subject_body with Subject: prefix fallback to first-line-as-subject"

requirements-completed: [EMAIL-01, EMAIL-02, EMAIL-03]

# Metrics
duration: 8min
completed: 2026-03-08
---

# Phase 12 Plan 01: Email Generation Backend Summary

**Claude Haiku 4.5 email generation engine with variable substitution, 3 starter templates, and batch processing via background threads**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-08T12:07:04Z
- **Completed:** 2026-03-08T12:15:31Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- EmailTemplate and GeneratedEmail models with full CRUD operations in SQLite
- Complete email generation engine with prompt caching and tenacity retry
- Variable substitution handles all Person/Company fields with None fallbacks
- 3 starter templates seeded idempotently (Consultative Intro, Case Study Follow-up, Breakup)
- 38 unit tests passing with mocked Anthropic client

## Task Commits

Each task was committed atomically:

1. **Task 1: Data layer - models, schema, database CRUD, and dependency setup** - `a338e1a` (feat)
2. **Task 2: Email generation engine - variable substitution, single/batch generation, cost tracking** - `c0f0687` (feat)

## Files Created/Modified
- `data/email_engine.py` - Email generation engine with variable substitution, single/batch generation, cost tracking, 3 starter templates
- `data/models.py` - Added EmailTemplate and GeneratedEmail Pydantic models
- `data/schema.sql` - Added email_templates and generated_emails tables with indexes
- `data/database.py` - Added CRUD methods for templates and generated emails, seed_default_templates, get_person_with_company
- `config/settings.py` - Added anthropic_api_key to Settings model and load_settings
- `requirements.txt` - Added anthropic>=0.40
- `pyproject.toml` - Added anthropic>=0.40 to dependencies
- `tests/test_email_gen.py` - 38 unit tests covering data layer and engine

## Decisions Made
- Anthropic API key stored as standalone Settings attribute, not in ProviderName enum (Anthropic is AI, not enrichment provider)
- Sequential API calls with 1.2s delay instead of Batch API (marginal cost savings not worth complexity at $2-4 per 3K emails)
- Prompt caching via cache_control ephemeral on system prompt for batch cost reduction
- All 3 starter templates flagged is_default=True for seed idempotency check

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FK constraint failures in generated email tests**
- **Found during:** Task 1 (data layer tests)
- **Issue:** Test generated_emails rows referenced non-existent campaign_id/person_id, violating FK constraints
- **Fix:** Added _make_campaign and _make_person helper functions to create prerequisite records
- **Files modified:** tests/test_email_gen.py
- **Verification:** All 18 Task 1 tests pass
- **Committed in:** a338e1a (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** FK constraint fix necessary for test correctness. No scope creep.

## Issues Encountered
None beyond the FK constraint fix documented above.

## User Setup Required
None - ANTHROPIC_API_KEY is loaded from .env when present, but all functionality works without it (tests use mocked client).

## Next Phase Readiness
- Email generation backend complete, ready for Plan 02 (UI page + export)
- All CRUD methods ready for Streamlit consumption
- Batch generation function ready for threading.Thread target
- STARTER_TEMPLATES available for seed_default_templates

---
*Phase: 12-ai-email-generation-export*
*Completed: 2026-03-08*
