# Phase 13: Cloud Deployment + Pipeline Polish - Research

**Researched:** 2026-03-08
**Domain:** Docker deployment (Railway), CI/CD (GitHub Actions), E2E integration testing
**Confidence:** HIGH

## Summary

Phase 13 is an operational phase with no new features -- it deploys the existing application to Railway via Docker and validates the full pipeline end-to-end. The existing codebase is well-prepared: Dockerfile already has non-root user, gcc deps, pip install, and /data directory. The `DB_PATH` env var is already used for SQLite location. All provider configs use `os.getenv()`, making Railway env var injection seamless.

The primary work is: (1) update Dockerfile for Railway compatibility (dynamic PORT, HEALTHCHECK, entrypoint script, Python env vars), (2) create `.streamlit/config.toml` with production settings, (3) write an E2E integration test exercising the full pipeline with mocked providers, (4) extend CI to build Docker image and optionally deploy via Railway GitHub integration, (5) create a manual smoke test checklist.

**Primary recommendation:** Use Railway's native GitHub integration for auto-deploy (simplest path), add a Docker build step to CI to catch build failures early, and write `tests/test_e2e_pipeline.py` that exercises create-campaign -> enrich -> SF-check -> email-gen -> CSV-export with all external services mocked.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Railway** as primary deployment target (not Fly.io)
- Use existing Dockerfile (already has non-root user, health check support)
- Railway persistent volume at `/data` for SQLite DB
- Dynamic `$PORT` via `--server.port=${PORT:-8501}` in CMD
- Secrets via Railway dashboard environment variables (not .env file in image)
- `.streamlit/config.toml` with production settings (headless=true, fileWatcher=none, CORS/XSRF enabled)
- HEALTHCHECK directive using `/_stcore/health` endpoint
- `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` env vars
- Entrypoint script pattern: run startup checks, then exec streamlit
- Do NOT bake .env or secrets into the image
- GitHub Actions push-to-deploy extending existing ci.yml
- Railway GitHub integration auto-deploys on push (preferred over CLI deploy)
- Simple pipeline: test -> deploy, no staging environment
- Docker build step in CI to catch build failures
- Automated E2E test (`tests/test_e2e_pipeline.py`) with mocked providers
- Manual smoke test checklist in SMOKE_TEST.md

### Claude's Discretion
- Exact Railway configuration (railway.toml vs dashboard settings)
- Whether to add Fly.io as documented alternative
- `.streamlit/config.toml` exact settings beyond the specified ones
- Entrypoint script structure
- Smoke test checklist completeness

### Deferred Ideas (OUT OF SCOPE)
- Fly.io as alternative (document but don't implement)
- Database backup automation (Litestream or cron sidecar)
- Custom domain (user can add via Railway dashboard)
- Monitoring/alerting (Railway provides basic metrics, advanced is v3.0)
- Multi-environment staging/prod (overkill for 3-person team)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-02 | Application deploys to cloud via Docker (Railway/Fly.io) | Dockerfile updates (PORT, HEALTHCHECK, entrypoint), Railway volume for SQLite, .streamlit/config.toml production settings, CI/CD pipeline, E2E validation |
</phase_requirements>

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|-------------|---------|---------|--------------|
| Docker | Latest | Container runtime | Already in use, Dockerfile exists |
| Railway | N/A (PaaS) | Cloud deployment platform | User decision; simplest for Streamlit + SQLite |
| GitHub Actions | v4 | CI/CD pipeline | Already in use for pytest |
| pytest | >=8.0 | E2E integration tests | Already in requirements.txt |

### Supporting
| Library/Tool | Version | Purpose | When to Use |
|-------------|---------|---------|-------------|
| curl | System | Docker HEALTHCHECK command | Required inside container for health endpoint |
| pytest-asyncio | >=0.23 | Async test support | Already in requirements.txt; needed for E2E test with async waterfall |

### No New Dependencies

This phase introduces zero new Python dependencies. All work is configuration and test code using existing libraries.

## Architecture Patterns

### Recommended Changes to Existing Files

```
(modified)  Dockerfile          # Add HEALTHCHECK, dynamic PORT, entrypoint, env vars, curl
(modified)  docker-compose.yml  # Update for production parity (optional)
(new)       .streamlit/config.toml    # Production Streamlit settings
(new)       entrypoint.sh             # Startup script: checks + exec streamlit
(new)       .dockerignore             # Exclude .git, __pycache__, .env, tests, .planning
(modified)  .github/workflows/ci.yml  # Add Docker build step
(new)       tests/test_e2e_pipeline.py  # Full pipeline integration test
(new)       SMOKE_TEST.md             # Manual post-deploy verification checklist
```

### Pattern 1: Entrypoint Script with Exec

**What:** Shell script that runs startup checks then hands off to streamlit via `exec`
**When to use:** Production Docker deployments that need pre-flight checks
**Example:**
```bash
#!/bin/bash
set -e

# Ensure data directory exists and is writable
mkdir -p /data
if [ ! -w /data ]; then
    echo "ERROR: /data is not writable" >&2
    exit 1
fi

# Start Streamlit (exec replaces the shell process for proper signal handling)
exec streamlit run ui/app.py \
    --server.port="${PORT:-8501}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
```
Source: Existing research at .planning/research/DOCKER_STREAMLIT_DEPLOYMENT.md

### Pattern 2: Dynamic PORT for Railway

**What:** Railway assigns a random `$PORT` environment variable. The app MUST listen on it.
**When to use:** Any Railway deployment
**Key detail:** The CMD/entrypoint must use `${PORT:-8501}` to support both Railway (dynamic) and local (8501 default).
**HEALTHCHECK caveat:** The HEALTHCHECK in Dockerfile always uses localhost:8501 (or a fixed port). On Railway, the health check is configured via the dashboard, not the Dockerfile HEALTHCHECK directive. The Dockerfile HEALTHCHECK is for local Docker and docker-compose usage.

Source: [Railway Docs - Dockerfiles](https://docs.railway.com/builds/dockerfiles)

### Pattern 3: Railway Volume Permissions for Non-Root User

**What:** Railway mounts volumes as root. Non-root Docker users get permission denied.
**Solution:** Set `RAILWAY_RUN_UID=0` in Railway environment variables, OR use the entrypoint script to create/chown the data directory before dropping to appuser.
**Recommendation:** Use `RAILWAY_RUN_UID=0` as documented by Railway. This is the official solution.
**Caveat:** `RAILWAY_RUN_UID` is available on Pro plan and above. For Hobby plan, the entrypoint approach (run initial setup as root, then switch) may be needed. However, existing Dockerfile already creates /data and chowns it to appuser BEFORE the volume mount, so the volume mount at runtime will overlay this.
**Simplest fix:** In the entrypoint, ensure /data exists and is writable. If permissions fail, log a clear error.

Source: [Railway Docs - Volumes](https://docs.railway.com/reference/volumes), [Railway Help - Permission denied](https://station.railway.com/questions/permission-denied-when-accessing-volume-bdf6b993)

### Pattern 4: E2E Pipeline Test with Mocked Externals

**What:** A single test that exercises the full programmatic flow: create campaign -> add companies -> enrich (mocked) -> SF check (mocked) -> generate emails (mocked) -> export CSV
**When to use:** Regression prevention before each deploy
**Key design decisions:**
- Use a temporary SQLite database (pytest `tmp_path` fixture)
- Mock all HTTP calls (providers, Salesforce, Anthropic) at the `httpx` / client level
- Verify CSV output contains expected Outreach.io columns
- Test should run in < 30 seconds
- No Streamlit UI interaction -- test the programmatic layer only

```python
# Conceptual structure for tests/test_e2e_pipeline.py
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from data.database import Database
from data.models import Company, Person, CampaignStatus
from enrichment.waterfall import WaterfallEnricher
from data.email_engine import generate_single_email

@pytest.fixture
async def db(tmp_path):
    """Fresh database for each test."""
    db = Database(db_path=str(tmp_path / "test.db"))
    # _init_db runs on first connection
    return db

class TestE2EPipeline:
    """Full pipeline: source -> enrich -> SF check -> email -> export."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, db, tmp_path):
        # 1. Create campaign + add companies
        # 2. Enrich with mocked providers
        # 3. Verify SF dedup gate was called
        # 4. Generate email with mocked Anthropic
        # 5. Export CSV and verify columns
        pass
```

### Anti-Patterns to Avoid
- **Baking .env into Docker image:** Secrets leak in image layers. Use runtime env vars only.
- **Hardcoding port 8501:** Railway assigns dynamic PORT. Always use `${PORT:-8501}`.
- **COPY .env in Dockerfile:** Even if .dockerignore catches it, never have a COPY .env line.
- **Testing against real APIs in CI:** All external calls must be mocked in E2E test.
- **Using `pip install -e .` in production:** Editable installs create overhead. Use `pip install .` instead (non-editable).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Health monitoring | Custom health endpoint | Streamlit's `/_stcore/health` | Built-in, well-tested, Railway/Docker both support it |
| SSL/TLS | Manual cert management | Railway's automatic TLS | Railway provisions and renews certs automatically |
| Secret injection | Custom secret loading | Railway dashboard env vars | Direct `os.getenv()` already used throughout codebase |
| Docker image building | Multi-stage complex builds | Single-stage python:3.11-slim | App has no build artifacts; multi-stage adds complexity without benefit |

## Common Pitfalls

### Pitfall 1: Railway Volume Permissions
**What goes wrong:** Non-root user in Docker gets "permission denied" writing to Railway volume
**Why it happens:** Railway mounts volumes as root; the Docker USER directive creates a non-root user
**How to avoid:** Set `RAILWAY_RUN_UID=0` in Railway env vars (Pro+), or ensure entrypoint handles permissions
**Warning signs:** App starts but SQLite creation fails silently; health check passes but app errors on first write

### Pitfall 2: PORT Mismatch
**What goes wrong:** App starts on 8501 but Railway routes traffic to a different PORT
**Why it happens:** Railway sets `$PORT` environment variable; if app ignores it, traffic never reaches the app
**How to avoid:** Use `${PORT:-8501}` in entrypoint; never hardcode port in config.toml (use CLI flags instead)
**Warning signs:** Health check timeouts; app shows "running" in Railway logs but URL returns 502

### Pitfall 3: HEALTHCHECK Port Discrepancy
**What goes wrong:** Dockerfile HEALTHCHECK checks port 8501, but Railway runs on dynamic PORT
**Why it happens:** HEALTHCHECK in Dockerfile is static; Railway PORT is dynamic
**How to avoid:** The Dockerfile HEALTHCHECK is for local Docker/compose. Railway configures its own health check via dashboard (path: `/_stcore/health`). The Dockerfile HEALTHCHECK should use 8501 (local default). Railway ignores it and uses its own.
**Warning signs:** None locally; Railway health check must be configured separately in dashboard

### Pitfall 4: SQLite WAL Files Not in Volume
**What goes wrong:** Database works initially but loses data or corrupts on redeploy
**Why it happens:** SQLite creates `-wal` and `-shm` companion files. If DB_PATH points to a file outside the volume mount, these files are ephemeral.
**How to avoid:** `DB_PATH=/data/clay_dupe.db` (already set correctly in existing Dockerfile)
**Warning signs:** Data loss after redeployment; "database is locked" errors

### Pitfall 5: .env File Mounted in docker-compose Leaking to Image
**What goes wrong:** Existing docker-compose.yml mounts `.env` file. If someone builds production image from compose, .env ends up in a layer.
**Why it happens:** docker-compose is for local dev; Railway uses Dockerfile only
**How to avoid:** Add `.env` to `.dockerignore`; don't use docker-compose for Railway deployment
**Warning signs:** `docker history` shows .env in image layers

### Pitfall 6: Editable Install in Production
**What goes wrong:** `pip install -e .` creates symlinks instead of copying files, adds overhead
**Why it happens:** Dev convenience carried into production
**How to avoid:** Use `pip install .` (non-editable) in production Dockerfile. Keep `-e` only for local dev.
**Warning signs:** Slightly larger image, minor startup overhead

## Code Examples

### Updated Dockerfile (Production)
```dockerfile
FROM python:3.11-slim

# Prevent .pyc files and enable unbuffered output for logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (curl needed for HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package (non-editable for production)
RUN pip install --no-cache-dir .

# Create data directory for SQLite persistence
RUN mkdir -p /data

# Default DB path inside the persistent volume
ENV DB_PATH=/data/clay_dupe.db

# Run as non-root user for container security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
RUN chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8501

# Health check using Streamlit's built-in endpoint (for local Docker/compose)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:${PORT:-8501}/_stcore/health || exit 1

# Entrypoint handles startup checks + dynamic PORT
COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
```

Note: The COPY entrypoint.sh should come before the USER directive change, and the file should be chmod +x. Adjust ordering in actual implementation.

### Production .streamlit/config.toml
```toml
[server]
headless = true
enableCORS = true
enableXsrfProtection = true
maxUploadSize = 50
fileWatcherType = "none"
runOnSave = false
enableWebsocketCompression = true

[browser]
gatherUsageStats = false

[client]
showErrorDetails = "none"
toolbarMode = "minimal"

[runner]
fastReruns = true
magicEnabled = false

[logger]
level = "info"
```

Do NOT set `server.port` or `server.address` in config.toml -- these MUST come from CLI flags to support dynamic PORT.

### .dockerignore
```
.git
.github
.planning
__pycache__
*.pyc
.env
.env.*
*.db
*.db-wal
*.db-shm
data/
tests/
.pytest_cache
.mypy_cache
.ruff_cache
tasks/
CLAUDE.md
```

### CI Extension (Docker Build Step)
```yaml
# Add to existing .github/workflows/ci.yml
  docker-build:
    runs-on: ubuntu-latest
    needs: test  # Only build if tests pass
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t clay-dupe:${{ github.sha }} .

      - name: Verify health check
        run: |
          docker run -d --name test-container -p 8501:8501 \
            -e APP_PASSWORD=test123 \
            clay-dupe:${{ github.sha }}
          sleep 15
          curl --fail http://localhost:8501/_stcore/health || exit 1
          docker stop test-container
```

Railway's native GitHub integration handles deployment automatically when push to main succeeds. No `railway up` CLI step needed in CI.

### Railway Configuration

**Recommendation:** Use dashboard settings, not railway.toml. Railway.toml is optional and dashboard is simpler for a single-service app.

**Dashboard settings to configure:**
1. **Service > Settings > Build:** Dockerfile (auto-detected)
2. **Service > Settings > Networking:** Generate domain (`*.up.railway.app`)
3. **Service > Settings > Health Check:** Path = `/_stcore/health`, Timeout = 10s
4. **Service > Settings > Volumes:** Mount path = `/data`
5. **Service > Variables:** All 13 env vars from .env.example

**Environment variables to set in Railway:**
```
APOLLO_API_KEY=<value>
FINDYMAIL_API_KEY=<value>
ICYPEAS_API_KEY=<value>
CONTACTOUT_API_KEY=<value>
DATAGMA_API_KEY=<value>
ANTHROPIC_API_KEY=<value>
WATERFALL_ORDER=apollo,icypeas,findymail,contactout
CACHE_TTL_DAYS=30
DB_PATH=/data/clay_dupe.db
SALESFORCE_USERNAME=<value>
SALESFORCE_PASSWORD=<value>
SALESFORCE_SECURITY_TOKEN=<value>
APP_PASSWORD=<strong-password>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Nixpacks (Railway) | Railpack (Railway) | 2025 | Auto-detection builder replaced; custom Dockerfile recommended for production |
| Railway free tier generous | Railway free tier limited ($1/mo credit) | 2024 | Hobby plan ($5/mo) is minimum viable for persistent apps |
| `pip install -e .` everywhere | `pip install .` for production | Best practice | Non-editable installs are smaller and faster in containers |

## Open Questions

1. **Railway Hobby plan volume permissions**
   - What we know: `RAILWAY_RUN_UID=0` solves permission issues but docs say "Pro and above"
   - What's unclear: Whether Hobby plan actually blocks this env var, or just doesn't document it
   - Recommendation: Test with Hobby plan first; if permissions fail, adjust entrypoint to handle it (mkdir -p + chown before USER switch)

2. **Railway health check vs Dockerfile HEALTHCHECK interaction**
   - What we know: Railway configures its own health check via dashboard; Dockerfile HEALTHCHECK is for local Docker
   - What's unclear: Whether Railway uses Dockerfile HEALTHCHECK if no dashboard config is set
   - Recommendation: Configure both -- Dockerfile HEALTHCHECK for local dev, Railway dashboard for production

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 + pytest-asyncio >= 0.23 |
| Config file | None (uses defaults, pyproject.toml may have pytest section) |
| Quick run command | `pytest tests/test_e2e_pipeline.py -x -v` |
| Full suite command | `pytest -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-02a | Docker image builds successfully | integration | `docker build -t clay-dupe:test .` | N/A (CI step) |
| INFRA-02b | App starts and health check passes in container | integration | `docker run + curl /_stcore/health` | N/A (CI step) |
| INFRA-02c | Full pipeline: source -> enrich -> SF -> email -> export | integration | `pytest tests/test_e2e_pipeline.py -x` | Wave 0 |
| INFRA-02d | App accessible via Railway URL | manual | See SMOKE_TEST.md | N/A |
| INFRA-02e | Auth gate works on Railway | manual | See SMOKE_TEST.md | N/A |

### Sampling Rate
- **Per task commit:** `pytest tests/test_e2e_pipeline.py -x -v`
- **Per wave merge:** `pytest -v` (full suite, 277+ tests)
- **Phase gate:** Full suite green + Docker build succeeds + Railway deployment accessible

### Wave 0 Gaps
- [ ] `tests/test_e2e_pipeline.py` -- full pipeline integration test (source -> enrich -> SF -> email -> export)
- [ ] `.streamlit/config.toml` -- production Streamlit config
- [ ] `entrypoint.sh` -- Docker entrypoint script
- [ ] `.dockerignore` -- exclude dev/planning files from image
- [ ] `SMOKE_TEST.md` -- manual post-deploy verification checklist

## Sources

### Primary (HIGH confidence)
- [Railway Docs - Dockerfiles](https://docs.railway.com/builds/dockerfiles) - Build process, Dockerfile detection, build-time variables
- [Railway Docs - Volumes](https://docs.railway.com/reference/volumes) - Volume limits, permissions, non-root user caveats, pricing
- [Railway Docs - GitHub Autodeploys](https://docs.railway.com/guides/github-autodeploys) - Auto-deploy on push, waiting for CI
- [Railway Blog - GitHub Actions](https://blog.railway.com/p/github-actions) - Using GitHub Actions with Railway, RAILWAY_TOKEN setup
- `.planning/research/DOCKER_STREAMLIT_DEPLOYMENT.md` - Comprehensive existing research on Docker + Streamlit + Railway
- `.planning/research/SELF_HOSTED_ARCHITECTURE.md` - Architecture patterns for self-hosted deployment
- Existing codebase: Dockerfile, docker-compose.yml, .github/workflows/ci.yml, .env.example

### Secondary (MEDIUM confidence)
- [Railway Help - SQLite permissions](https://station.railway.com/questions/sqlite-readonly-attempt-to-write-a-read-2e6e370a) - Real-world SQLite + volume permission issues
- [Railway Help - Volume persistence](https://station.railway.com/questions/persistent-volume-not-persisting-data-ac-fd543a6e) - Volume persistence across deployments

### Tertiary (LOW confidence)
- Railway Hobby plan `RAILWAY_RUN_UID` availability (docs say Pro+, community reports mixed)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; all tools already in use or well-documented
- Architecture: HIGH - Existing research covers Docker+Streamlit+Railway thoroughly; codebase already cloud-ready
- Pitfalls: HIGH - Railway volume permissions and PORT issues are well-documented in official docs and community
- E2E test design: MEDIUM - Test structure is straightforward but exact mock points depend on implementation details

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (Railway platform is stable; Docker patterns are mature)
