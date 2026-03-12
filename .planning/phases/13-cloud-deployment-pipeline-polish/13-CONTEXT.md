# Phase 13: Cloud Deployment + Pipeline Polish - Context

**Gathered:** 2026-03-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Deploy the application to the cloud via Docker so it's accessible via URL, and verify the full source-to-export pipeline works end-to-end. No new features, no architecture changes — purely operational deployment and integration validation.

</domain>

<decisions>
## Implementation Decisions

### Deployment Platform
- **Railway** as primary target — simplest path for Streamlit + SQLite
- Use existing Dockerfile (already has non-root user, health check support)
- Railway persistent volume mounted at `/data` for SQLite DB
- Dynamic `$PORT` via `--server.port=${PORT:-8501}` in CMD
- Secrets via Railway dashboard environment variables (not .env file in image)
- Railway provides `*.up.railway.app` subdomain with automatic TLS
- Estimated cost: ~$5-7/month on Hobby plan

### Docker Production Config
- Add `.streamlit/config.toml` with production settings (headless=true, fileWatcher=none, CORS/XSRF enabled)
- Add HEALTHCHECK directive using `/_stcore/health` endpoint
- Add `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` env vars
- Entrypoint script pattern: run any startup checks, then exec streamlit
- Do NOT bake .env or secrets into the image

### CI/CD Pipeline
- **GitHub Actions push-to-deploy** — extend existing ci.yml
- On push to `main`: run tests, if green, deploy to Railway via `railway up` or GitHub integration
- Railway GitHub integration auto-deploys on push (preferred over CLI deploy)
- Keep it simple: test -> deploy, no staging environment for a 3-person team
- Add Docker build step to CI to catch build failures before deploy

### E2E Pipeline Validation
- **Automated integration test** (`tests/test_e2e_pipeline.py`) that exercises the full flow programmatically:
  1. Create a campaign with test companies (mock data, no real API calls)
  2. Run enrichment waterfall (mocked providers returning realistic data)
  3. Check Salesforce dedup gate (mocked SF client)
  4. Generate emails (mocked Anthropic client)
  5. Export CSV and verify column format matches Outreach.io spec
- **Manual smoke test checklist** in a SMOKE_TEST.md for post-deploy verification:
  - App loads at Railway URL
  - Auth gate blocks without password
  - Can navigate all pages (Companies, Enrich, Emails, Analytics, Settings)
  - Settings page shows API key validation status
  - Can import a CSV of companies
- Both automated and manual — automated catches regressions, manual catches UI/deploy issues

### Claude's Discretion
- Exact Railway configuration (railway.toml vs dashboard settings)
- Whether to add Fly.io as documented alternative
- .streamlit/config.toml exact settings beyond the specified ones
- Entrypoint script structure
- Smoke test checklist completeness

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Dockerfile` — already has non-root user (appuser), gcc build dep, pip install, /data directory
- `docker-compose.yml` — has .env volume mount, data volume, port mapping
- `.github/workflows/ci.yml` — existing CI with Python 3.11, pytest
- `.env.example` — complete with all 13 environment variables (Phase 12.1)
- `ui/app.py` — auth gate already in place (Phase 12.1)

### Established Patterns
- Settings loaded via `load_dotenv()` + `os.getenv()` — cloud-friendly (env vars work natively)
- `DB_PATH` env var already used for SQLite location (`/data/clay_dupe.db`)
- Schema migrations run on `_init_db()` with ALTER TABLE safety — handles fresh vs existing DB

### Integration Points
- `requirements.txt` — all dependencies listed, no private packages
- `pyproject.toml` — package installable via `pip install -e .`
- All providers use `os.getenv()` for API keys — Railway env vars map directly
- `_stcore/health` endpoint available natively from Streamlit

</code_context>

<deferred>
## Deferred Ideas

- **Fly.io as alternative** — document but don't implement (Railway is sufficient)
- **Database backup automation** — Litestream or cron sidecar for production backup
- **Custom domain** — user can add via Railway dashboard, no code changes needed
- **Monitoring/alerting** — Railway provides basic metrics, advanced monitoring is v3.0
- **Multi-environment (staging/prod)** — overkill for 3-person team, revisit at scale

</deferred>

---

*Phase: 13-cloud-deployment-pipeline-polish*
*Context gathered: 2026-03-08*
