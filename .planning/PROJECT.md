# Clay-Dupe: Self-Hosted B2B Enrichment Platform

## What This Is

A self-hosted alternative to Clay for B2B data enrichment. Uses a waterfall pattern to cascade through 5 API providers (Apollo, Icypeas, Findymail, Datagma, ContactOut) in cost-optimized order to find verified emails, phone numbers, and company data for niche businesses (A&D, medical device, niche industrial) with 1-15M EBITDA, 10-100 employees.

## Core Value

Reliably find verified contact emails for target companies by cascading through multiple providers in cost-optimized order, with full cost tracking and caching to prevent wasted credits.

## Requirements

### Validated

- ✓ Waterfall enrichment engine cascading through 5 providers — v1.0
- ✓ Apollo, Findymail, Icypeas, ContactOut, Datagma provider integrations — v1.0
- ✓ Smart row classification into 8 route categories — v1.0
- ✓ Email pattern discovery and learning system — v1.0
- ✓ SQLite persistence with WAL mode — v1.0
- ✓ CSV/Excel import with fuzzy column mapping + export — v1.0
- ✓ Per-provider daily/monthly budget limits with in-memory caching — v1.0
- ✓ Circuit breakers and rate limiting per provider — v1.0
- ✓ Multi-factor confidence scoring (0-100) — v1.0
- ✓ Email verification via DNS/SMTP checks — v1.0
- ✓ CLI interface (enrich, search, verify, stats) — v1.0
- ✓ Streamlit web UI with Clay-inspired design — v1.0
- ✓ TTL-based result caching with automatic eviction — v1.0
- ✓ Typed exception handling across all providers — v1.0
- ✓ Parameterized SQL queries (no injection surface) — v1.0
- ✓ Input validation before all provider API calls — v1.0
- ✓ Async batch processing with chunking + shared HTTP pool — v1.0
- ✓ Campaign pause/resume with per-row checkpoints — v1.0
- ✓ Cross-campaign contact deduplication — v1.0
- ✓ Provider A/B testing framework — v1.0
- ✓ Audit trail for all enrichment operations — v1.0
- ✓ 277 tests: retry, CLI, waterfall edge cases, malformed responses, concurrent DB — v1.0

### Active

- [ ] Wire up real API keys and test with live data
- [ ] Cloud deployment (Vercel, Railway, or VPS)
- [ ] Provider cost comparison reports over time
- [ ] Scheduled/recurring campaign runs

### Out of Scope

- PostgreSQL migration — SQLite sufficient for team-size workloads
- OAuth/SSO — internal team tool, API keys in .env sufficient
- Mobile app — web UI via browser sufficient
- AI-generated email personalization — out of scope for enrichment tool

## Context

- **Shipped v1.0** on 2026-03-07 with 14,586 LOC Python, 64 files, 277 tests
- **Stack:** Python >= 3.11, Typer, Streamlit, Pydantic v2, httpx, aiosqlite, aiometer, tenacity, SQLite, pandas
- **Providers:** Apollo ($0.01/cr), Icypeas ($0.009/cr), Findymail ($0.02/cr), Datagma ($0.005/cr), ContactOut ($0.05/cr, optional)
- **Default waterfall:** Apollo → Icypeas → Findymail → Datagma
- **Estimated cost:** ~$466/mo for 10K contacts at 92-95% email find rate

## Constraints

- **Tech stack**: Python — entire codebase is Python
- **Database**: SQLite — team-size workload, self-hosted
- **Providers**: Apollo, Icypeas, Findymail, Datagma (primary), ContactOut (optional)
- **Deployment**: Self-hosted — Streamlit for web, Typer for CLI

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep SQLite, improve with indexes | Team-size workload doesn't justify PostgreSQL | ✓ Good — composite indexes, WAL checkpoints, cache eviction |
| Fix security before adding features | SQL injection and bare exceptions are production risks | ✓ Good — Phases 2-4 shipped before capabilities |
| Cost-effective waterfall: Apollo→Icypeas→Findymail→Datagma | Lowest $/found email at 92-95% find rate | ✓ Good — $466/mo for 10K contacts |
| Add Datagma, keep ContactOut optional | Datagma cheapest for phones ($0.042/mobile), ContactOut capped at 2K/mo | ✓ Good — no capability loss |
| Clay-inspired UI redesign | Professional data-centric UX with inline filters, 2-column layout | ✓ Good — matches user expectations |

---
*Last updated: 2026-03-07 after v1.0 milestone*
