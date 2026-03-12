---
phase: 12
slug: ai-email-generation-export
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.23+ |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `pytest tests/test_email_gen.py -x` |
| **Full suite command** | `pytest tests/ -x --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_email_gen.py -x`
- **After every plan wave:** Run `pytest tests/ -x --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | EMAIL-01 | unit | `pytest tests/test_email_gen.py::test_generate_single -x` | No - Wave 0 | pending |
| 12-01-02 | 01 | 1 | EMAIL-02 | unit | `pytest tests/test_email_gen.py::test_template_crud -x` | No - Wave 0 | pending |
| 12-01-03 | 01 | 1 | EMAIL-02 | unit | `pytest tests/test_email_gen.py::test_variable_substitution -x` | No - Wave 0 | pending |
| 12-02-01 | 02 | 2 | EMAIL-03 | unit | `pytest tests/test_email_gen.py::test_batch_generate -x` | No - Wave 0 | pending |
| 12-02-02 | 02 | 2 | EMAIL-04 | unit | `pytest tests/test_email_gen.py::test_email_status_workflow -x` | No - Wave 0 | pending |
| 12-02-03 | 02 | 2 | EMAIL-05 | unit | `pytest tests/test_email_gen.py::test_export_outreach_csv -x` | No - Wave 0 | pending |
| 12-02-04 | 02 | 2 | EMAIL-05 | unit | `pytest tests/test_email_gen.py::test_export_sf_csv -x` | No - Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_email_gen.py` — stubs for EMAIL-01 through EMAIL-05 (all mocked, no real API calls)
- [ ] `pip install anthropic` — new dependency
- [ ] Fixtures: mock `Anthropic` client, mock message responses with subject/body parsing

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Email generation UI page renders | EMAIL-01 | UI rendering | Navigate to Emails page, verify campaign selector + generate button |
| Template editor with variable preview | EMAIL-02 | UI interaction | Create template, verify {variable} highlighting and preview |
| Batch progress bar updates | EMAIL-03 | UI rendering + polling | Start batch generation, verify progress bar and live count |
| Inline edit + approve/reject | EMAIL-04 | UI interaction | Click email row, edit subject/body, click approve/reject |
| CSV download produces valid file | EMAIL-05 | File output | Export Outreach CSV, open in Excel, verify columns |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
