---
phase: 10
slug: infrastructure-company-sourcing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-07
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0 + pytest-asyncio >=0.23 |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `pytest tests/ -x --timeout=30` |
| **Full suite command** | `pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x --timeout=30`
- **After every plan wave:** Run `pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | INFRA-03 | unit | `pytest tests/test_concurrent_db.py -x` | Yes (extend) | pending |
| 10-01-02 | 01 | 1 | INFRA-01 | unit | `pytest tests/test_key_validation.py -x` | No - Wave 0 | pending |
| 10-02-01 | 02 | 1 | SRC-01 | unit | `pytest tests/test_company_sourcing.py::test_apollo_search -x` | No - Wave 0 | pending |
| 10-02-02 | 02 | 1 | SRC-02 | unit | `pytest tests/test_company_sourcing.py::test_csv_import -x` | No - Wave 0 | pending |
| 10-02-03 | 02 | 1 | SRC-03 | unit | `pytest tests/test_company_sourcing.py::test_manual_add -x` | No - Wave 0 | pending |
| 10-02-04 | 02 | 1 | SRC-05 | unit | `pytest tests/test_company_sourcing.py::test_source_tracking -x` | No - Wave 0 | pending |
| 10-03-01 | 03 | 2 | SRC-04 | unit | `pytest tests/test_contact_discovery.py -x` | No - Wave 0 | pending |
| 10-03-02 | 03 | 2 | SRC-06 | unit | `pytest tests/test_icp_scoring.py -x` | No - Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_key_validation.py` — stubs for INFRA-01
- [ ] `tests/test_company_sourcing.py` — stubs for SRC-01, SRC-02, SRC-03, SRC-05
- [ ] `tests/test_contact_discovery.py` — stubs for SRC-04
- [ ] `tests/test_icp_scoring.py` — stubs for SRC-06
- [ ] Extend `tests/test_concurrent_db.py` — add write lock verification for INFRA-03

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboard shows API key status on startup | INFRA-01 | UI rendering | Launch app, check sidebar/dashboard for provider status indicators |
| Company list page renders with filters | SRC-01 | UI rendering | Navigate to companies page, verify table, filters, sorting |
| CSV upload UI works end-to-end | SRC-02 | File upload UX | Upload a test CSV, verify mapped columns, check DB |
| Manual add form creates company | SRC-03 | Form submission UX | Fill form, submit, verify in company list |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
