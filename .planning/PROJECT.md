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

<!-- Current scope. Building toward these across hardening, performance, capabilities, and scaling. -->

- [ ] Fix bare exception handling across all providers (specific exception types)
- [ ] Eliminate SQL injection risks in database layer (parameterized queries)
- [ ] Add input validation/sanitization for provider method parameters
- [ ] Add `.get()` fallbacks for all JSON response parsing (prevent KeyError crashes)
- [ ] Implement async batch processing with chunking strategy for large CSVs (500+ rows)
- [ ] Share HTTP clients across provider instances (connection pooling)
- [ ] Add adaptive concurrency limits based on provider rate limits
- [ ] Add campaign pause/resume capability
- [ ] Implement cross-campaign contact deduplication
- [ ] Add audit trail for all enrichment operations
- [ ] Implement provider A/B testing (compare hit rates and accuracy)
- [ ] Add automatic cache eviction beyond TTL
- [ ] Index frequently queried cache columns
- [ ] Implement row processing chunking for batch operations
- [ ] Add API key rotation mechanism
- [ ] Add rate limiting on email verification attempts per domain

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
- **Known tech debt:** Bare exception handling in providers, SQL injection risk in database.py, JSON response fragility, unshared HTTP clients
- **Known performance issues:** Sequential batch processing, fixed concurrency limits, unbounded cache growth, unindexed cache queries
- **Test coverage:** 1,357 lines across 8 test files — gaps in CLI integration, UI pages, concurrent DB access, waterfall edge cases
- **Stack:** Python 3.x, Typer, Streamlit, Pydantic v2, httpx, SQLite, pandas

## Constraints

- **Tech stack**: Python — entire codebase is Python, no reason to change
- **Database**: SQLite — team-size workload, self-hosted, no server dependency
- **Providers**: Apollo, Findymail, Icypeas, ContactOut — existing integrations, API contracts locked
- **Deployment**: Self-hosted on local network — Streamlit for web, Typer for CLI

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep SQLite, improve with indexes | Team-size workload doesn't justify PostgreSQL complexity | — Pending |
| Fix security before adding features | SQL injection and bare exceptions are production risks | — Pending |
| Equal priority across all 4 areas | Tackle in architectural dependency order | — Pending |

---
*Last updated: 2026-03-04 after initialization*
