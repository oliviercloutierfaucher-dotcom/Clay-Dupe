---
phase: 13
slug: cloud-deployment-pipeline-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio 0.23+ |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `pytest tests/test_e2e_pipeline.py -x -v` |
| **Full suite command** | `pytest tests/ -x --timeout=60` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_e2e_pipeline.py -x -v`
- **After every plan wave:** Run `pytest tests/ -x --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green + Docker build succeeds
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | INFRA-02 | integration | `docker build -t clay-dupe:test .` | N/A (CI) | pending |
| 13-01-02 | 01 | 1 | INFRA-02 | integration | `pytest tests/test_e2e_pipeline.py -x` | No - Wave 0 | pending |
| 13-02-01 | 02 | 2 | INFRA-02 | manual | See SMOKE_TEST.md | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_e2e_pipeline.py` — E2E integration test (source -> enrich -> SF -> email -> export) with all external services mocked
- [ ] Fixtures: mock providers, mock Salesforce client, mock Anthropic client, ephemeral SQLite via tmp_path

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| App accessible via Railway URL | INFRA-02 | External deployment | Navigate to Railway URL, verify app loads |
| Auth gate works on Railway | INFRA-02 | Cloud environment | Verify password prompt appears before content |
| All pages navigable | INFRA-02 | UI rendering in cloud | Navigate Companies, Enrich, Emails, Analytics, Settings |
| Docker build succeeds | INFRA-02 | Build environment | `docker build -t clay-dupe:test .` completes without error |
| Health check passes in container | INFRA-02 | Container runtime | `curl http://localhost:8501/_stcore/health` returns "ok" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
