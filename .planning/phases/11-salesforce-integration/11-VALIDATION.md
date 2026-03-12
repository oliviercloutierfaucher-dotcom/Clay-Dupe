---
phase: 11
slug: salesforce-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.23+ |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `pytest tests/test_salesforce.py -x` |
| **Full suite command** | `pytest tests/ -x --timeout=60` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_salesforce.py -x`
- **After every plan wave:** Run `pytest tests/ -x --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | SF-01 | unit | `pytest tests/test_salesforce.py::test_sf_config -x` | No - Wave 0 | pending |
| 11-01-02 | 01 | 1 | SF-02 | unit | `pytest tests/test_salesforce.py::test_sf_health_check -x` | No - Wave 0 | pending |
| 11-01-03 | 01 | 1 | SF-03 | unit | `pytest tests/test_salesforce.py::test_domain_batch_check -x` | No - Wave 0 | pending |
| 11-02-01 | 02 | 2 | SF-03 | unit | `pytest tests/test_salesforce.py::test_pre_enrichment_gate -x` | No - Wave 0 | pending |
| 11-02-02 | 02 | 2 | SF-04 | unit | `pytest tests/test_salesforce.py::test_company_sf_fields -x` | No - Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_salesforce.py` — stubs for SF-01, SF-02, SF-03, SF-04 (all mocked, no real SF calls)
- [ ] `pip install simple-salesforce` — new dependency
- [ ] Fixtures: mock `Salesforce` class, mock SOQL responses

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SF credentials UI in settings page | SF-01 | UI rendering | Navigate to settings, verify SF card with 3 input fields |
| Test Connection shows success/failure | SF-02 | UI interaction | Enter valid/invalid SF creds, click Test Connection |
| Companies table shows SF Status column | SF-04 | UI rendering | View companies page, verify "In SF" badge + clickable link |
| SF Status filter works | SF-04 | UI interaction | Filter companies by In SF / Not in SF |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
