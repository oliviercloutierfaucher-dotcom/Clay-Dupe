# Clay-Dupe: Self-Hosted B2B Enrichment Platform

## What This Is

A self-hosted alternative to Clay for B2B data enrichment, focused on finding emails, domains, and LinkedIn URLs for niche businesses (A&D, medical device, niche industrial) with 1-15M EBITDA, 10-100 employees in US, UK, and Canada. Uses a waterfall pattern to cascade through multiple API providers (Apollo, Findymail, Icypeas, ContactOut) to maximize find rate while minimizing cost.

## Core Value

Reliably find verified contact emails for target companies by cascading through multiple providers in cost-optimized order, with full cost tracking and caching to prevent wasted credits.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Inferred from existing codebase. -->

- ✓ Waterfall enrichment engine cascading through 4 providers — existing
- ✓ Apollo.io provider integration (company search, people search, email enrichment) — existing
- ✓ Findymail provider integration (email finding + verification) — existing
- ✓ Icypeas provider integration (email discovery, bulk operations) — existing
- ✓ ContactOut provider integration (LinkedIn-based email extraction) — existing
- ✓ Smart row classification into 8 route categories — existing
- ✓ Configurable provider sequencing per route category — existing
- ✓ Email pattern discovery and learning system — existing
- ✓ SQLite persistence with WAL mode (companies, people, campaigns, results, cache) — existing
- ✓ CSV/Excel import with fuzzy column mapping — existing
- ✓ CSV/Excel export of enrichment results — existing
- ✓ Per-provider daily/monthly budget limits — existing
- ✓ Credit usage tracking and cost analysis — existing
- ✓ Circuit breakers per provider (CLOSED/OPEN/HALF_OPEN) — existing
- ✓ Rate limiting per provider (sliding window) — existing
- ✓ Multi-factor confidence scoring (0-100) — existing
- ✓ Email verification via DNS/SMTP checks — existing
- ✓ Catch-all domain and role-based email detection — existing
- ✓ CLI interface with enrich, search, verify, stats commands — existing
- ✓ Streamlit web UI with dashboard, search, enrich, results, analytics, settings pages — existing
- ✓ TTL-based result caching to prevent duplicate API calls — existing
- ✓ ICP filter presets (A&D, medical device, niche industrial) — existing
- ✓ Async/await throughout providers and waterfall — existing
- ✓ Pydantic v2 data models with field validation — existing

### Active

<!-- Current scope — all items shipped in Hardening & Scaling milestone. -->

- ✓ Fix bare exception handling across all providers (specific exception types) — Phase 2
- ✓ Eliminate SQL injection risks in database layer (parameterized queries) — Phase 3
- ✓ Add input validation/sanitization for provider method parameters — Phase 3
- ✓ Add `.get()` fallbacks for all JSON response parsing (prevent KeyError crashes) — Phase 2
- ✓ Implement async batch processing with chunking strategy for large CSVs (500+ rows) — Phase 5
- ✓ Share HTTP clients across provider instances (connection pooling) — Phase 5
- ✓ Add adaptive concurrency limits based on provider rate limits — Phase 5
- ✓ Add campaign pause/resume capability — Phase 7
- ✓ Implement cross-campaign contact deduplication — Phase 8
- ✓ Add audit trail for all enrichment operations — Phase 8
- ✓ Implement provider A/B testing (compare hit rates and accuracy) — Phase 8
- ✓ Add automatic cache eviction beyond TTL — Phase 6
- ✓ Index frequently queried cache columns — Phase 6
- ✓ Implement row processing chunking for batch operations — Phase 5
- ✓ Add API key rotation mechanism — Phase 4
- ✓ Add rate limiting on email verification attempts per domain — Phase 4

### Out of Scope

<!-- Explicit boundaries. -->

- PostgreSQL/MySQL migration — SQLite sufficient for team-size workloads after indexing improvements
- Real-time collaboration features — team shares via Streamlit on local network
- Mobile app — web UI accessed via browser is sufficient
- Additional provider integrations — 4 providers covers the market well
- OAuth/SSO authentication — internal team tool, API keys in .env sufficient

## Context

- **Existing codebase:** ~5,000+ lines of Python across enrichment engine, providers, data layer, CLI, and web UI
- **Codebase map:** Full architecture, stack, conventions, and concerns documentation exists in `.planning/codebase/`
- **Known tech debt:** Resolved — exception handling hardened, SQL injection eliminated, JSON parsing safe, HTTP clients shared
- **Known performance issues:** Resolved — chunked batches, adaptive concurrency, cache indexed + evicted, WAL checkpointed
- **Test coverage:** 236 passing tests across 13 test files — CLI integration, concurrent DB, waterfall edge cases, malformed responses all covered
- **Stack:** Python >= 3.11, Typer, Streamlit, Pydantic v2, httpx, aiosqlite, aiometer, tenacity, SQLite, pandas

## Constraints

- **Tech stack**: Python — entire codebase is Python, no reason to change
- **Database**: SQLite — team-size workload, self-hosted, no server dependency
- **Providers**: Apollo, Findymail, Icypeas, ContactOut — existing integrations, API contracts locked
- **Deployment**: Self-hosted on local network — Streamlit for web, Typer for CLI

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep SQLite, improve with indexes | Team-size workload doesn't justify PostgreSQL complexity | Done — composite indexes, WAL checkpoints, cache eviction |
| Fix security before adding features | SQL injection and bare exceptions are production risks | Done — Phases 2-4 shipped before capabilities |
| Equal priority across all 4 areas | Tackle in architectural dependency order | Done — 9 phases in dependency order |

---
*Last updated: 2026-03-04 after Hardening & Scaling milestone completion*
