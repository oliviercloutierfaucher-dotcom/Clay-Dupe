---
status: verifying
trigger: "docker-railway-deployment-broken"
created: 2026-03-14T00:00:00Z
updated: 2026-03-14T01:00:00Z
---

## Current Focus

hypothesis: All issues identified and fixed — Docker build should now produce a working container
test: Verify all fixes are correct and no remaining issues remain
expecting: Clean Docker build and all pages loading on Railway
next_action: Present verification checklist to user

## Symptoms

expected: App deploys and runs on Railway. All pages (dashboard, companies, search, results, enrich, emails, analytics, settings) load correctly.
actual: Streamlit sidebar loads with page names but every page shows "This app has encountered an error". The error was ModuleNotFoundError: No module named 'data'.
errors:
  1. ModuleNotFoundError: No module named 'data' — caused by .dockerignore excluding data/ directory
  2. /data is not writable — Railway volume mount permissions (fixed by running as root)
  3. .env file excluded by .dockerignore but needed for settings persistence
reproduction: Deploy to Railway, visit clay-dupe-production.up.railway.app
started: First deployment attempt. Never worked. Multiple fixes attempted.

## Eliminated

- hypothesis: PYTHONPATH not set
  evidence: Dockerfile sets ENV PYTHONPATH=/app correctly at runtime
  timestamp: 2026-03-14T01:00:00Z

- hypothesis: Missing __init__.py files
  evidence: All packages have __init__.py: cli, config, cost, data, enrichment, providers, quality, ui, ui/pages
  timestamp: 2026-03-14T01:00:00Z

- hypothesis: .dockerignore blocking code packages
  evidence: .dockerignore only blocks .git, .github, .planning, .claude, __pycache__, *.pyc, .env, .env.*, *.db, tests/, .pytest_cache, .mypy_cache, .ruff_cache, tasks/, CLAUDE.md, venv/, .venv/, exports/, *.egg-info/, dist/, build/, .vscode/, .idea/ — no code packages blocked
  timestamp: 2026-03-14T01:00:00Z

- hypothesis: Missing requirements
  evidence: requirements.txt has all necessary runtime packages including simple-salesforce
  timestamp: 2026-03-14T01:00:00Z

- hypothesis: Streamlit config.toml server settings wrong
  evidence: Settings are correct for headless server mode with proper port handling
  timestamp: 2026-03-14T01:00:00Z

- hypothesis: Missing schema.sql in Docker image
  evidence: data/schema.sql is not excluded and will be at /app/data/schema.sql in container
  timestamp: 2026-03-14T01:00:00Z

- hypothesis: PAGE references wrong
  evidence: st.Page("pages/dashboard.py") is correct — Streamlit resolves relative to script directory (ui/)
  timestamp: 2026-03-14T01:00:00Z

## Evidence

- timestamp: 2026-03-14T01:00:00Z
  checked: .dockerignore
  found: data/, config/, ui/, enrichment/, providers/, cost/, quality/, cli/ all NOT excluded — all code packages are included
  implication: The original data/ import error was from an old .dockerignore that has since been fixed

- timestamp: 2026-03-14T01:00:00Z
  checked: Dockerfile
  found: PYTHONPATH=/app set as runtime ENV, mkdir /data, DB_PATH=/data/clay_dupe.db, runs as root, EXPOSE 8501
  implication: Correct configuration for Railway volume mounts

- timestamp: 2026-03-14T01:00:00Z
  checked: entrypoint.sh
  found: mkdir -p /data, chmod 777 /data on permission failure, exec streamlit run ui/app.py --server.port="${PORT:-8501}"
  implication: Correct — handles Railway's port injection and volume permission issues

- timestamp: 2026-03-14T01:00:00Z
  checked: ui/pages/enrich.py (modified in git)
  found: BUG - SalesforceClient(sf_cfg) called with SalesforceConfig object instead of individual credentials
  implication: Would crash any enrichment run that has Salesforce configured

- timestamp: 2026-03-14T01:00:00Z
  checked: .streamlit/config.toml
  found: showErrorDetails = "none" hides ALL error details from Streamlit UI
  implication: Users only see "This app has encountered an error" with no actionable information — makes debugging impossible

- timestamp: 2026-03-14T01:00:00Z
  checked: requirements.txt
  found: pytest and pytest-asyncio included in production dependencies
  implication: Adds unnecessary packages to production Docker image (~15MB extra)

- timestamp: 2026-03-14T01:00:00Z
  checked: root directory
  found: Rogue file "=1.12.6" — output of bash misinterpreting "pip install simple-salesforce>=1.12.6" without quotes
  implication: Gets COPY'd into Docker image as artifact file

- timestamp: 2026-03-14T01:00:00Z
  checked: config/settings.py _ENV_PATH
  found: Path(__file__).parent.parent / ".env" resolves to /app/.env in Docker
  implication: Correct — settings can be persisted to /app/.env (created by Dockerfile RUN touch)

## Resolution

root_cause: Multiple issues compounding:
  1. FIXED PREVIOUSLY: .dockerignore was excluding data/ Python package (ModuleNotFoundError: No module named 'data')
  2. FIXED PREVIOUSLY: /data volume not writable — resolved by running as root
  3. BUG IN MODIFIED CODE: SalesforceClient instantiated with SalesforceConfig object instead of (username, password, security_token) — would crash enrichment when SF is configured
  4. ERROR MASKING: showErrorDetails = "none" hides all error details making debugging impossible
  5. ARTIFACT: Rogue "=1.12.6" file polluting Docker image
  6. UNNECESSARY: pytest/pytest-asyncio in production requirements

fix:
  1. Fixed ui/pages/enrich.py: SalesforceClient(sf_cfg) → SalesforceClient(sf_cfg.username, sf_cfg.password, sf_cfg.security_token)
  2. Fixed .streamlit/config.toml: showErrorDetails = "none" → "full"
  3. Fixed requirements.txt: removed pytest and pytest-asyncio
  4. Deleted rogue "=1.12.6" file from project root

verification: Awaiting human verification — redeploy to Railway and confirm all pages load
files_changed:
  - ui/pages/enrich.py (SalesforceClient instantiation fix)
  - .streamlit/config.toml (showErrorDetails: none → full)
  - requirements.txt (removed pytest/pytest-asyncio)
  - =1.12.6 (deleted)
