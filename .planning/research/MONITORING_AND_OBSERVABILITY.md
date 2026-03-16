# Monitoring, Logging & Observability — Deep Research

**Date**: 2026-03-08
**Scope**: Production monitoring for Clay-Dupe (Python 3.11 + Streamlit + SQLite + Docker)
**Trigger**: Production readiness audit flagged: no logging config, no health checks, no alerting

---

## Table of Contents

1. [Structured Logging](#1-structured-logging)
2. [Health Checks](#2-health-checks)
3. [Metrics & Dashboards](#3-metrics--dashboards)
4. [Alerting](#4-alerting)
5. [Error Tracking](#5-error-tracking)
6. [Audit Trail](#6-audit-trail)
7. [Recommendations for Clay-Dupe](#7-recommendations-for-clay-dupe)

---

## 1. Structured Logging

### 1.1 Library Choice: structlog

**Recommendation: structlog** over loguru or stdlib logging.

| Criteria | stdlib `logging` | `loguru` | `structlog` |
|---|---|---|---|
| Structured JSON output | Manual formatters | Plugin | Native |
| Context binding (correlation IDs) | No | No | Yes — core feature |
| asyncio / contextvars | Manual | Manual | Native (`structlog.contextvars`) |
| Backwards-compatible with stdlib | N/A | Separate | Yes — wraps stdlib |
| Production vs dev output | Manual | Automatic | Built-in (`ConsoleRenderer` vs `JSONRenderer`) |
| Performance (async) | Baseline | ~1.5x | ~2.6x throughput via contextvars |

**Why structlog wins for us:**
- We already use `import logging` in 15+ modules — structlog wraps stdlib, so migration is incremental (not a rewrite)
- Context binding is essential for enrichment: attach `campaign_id`, `contact_id`, `provider` to every log line automatically
- JSON output in Docker, pretty output in dev — one config switch
- Async-native via `contextvars` — critical for our waterfall pipeline

### 1.2 Setup Configuration

```python
# core/logging.py — centralized logging configuration
import logging
import sys
import structlog

def configure_logging(log_level: str = "INFO", json_output: bool = None):
    """Configure structured logging for the application.

    Args:
        log_level: DEBUG, INFO, WARNING, ERROR
        json_output: Force JSON output. If None, auto-detect (JSON in Docker, pretty in terminal).
    """
    if json_output is None:
        json_output = not sys.stderr.isatty()  # Docker = no TTY = JSON

    # Shared processors for both structlog and stdlib
    shared_processors = [
        structlog.contextvars.merge_contextvars,     # Pull in bound context
        structlog.processors.add_log_level,           # Add "level" field
        structlog.processors.TimeStamper(fmt="iso"),  # ISO 8601 timestamps
        structlog.processors.StackInfoRenderer(),     # Stack traces
        structlog.processors.format_exc_info,         # Exception formatting
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[*shared_processors, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("streamlit").setLevel(logging.WARNING)
```

### 1.3 Context Binding (Correlation IDs)

The key structlog feature: bind context once, it appears in every subsequent log line.

```python
import structlog

# At enrichment start — bind campaign context
structlog.contextvars.bind_contextvars(
    campaign_id=campaign.id,
    campaign_name=campaign.name,
    user="admin",
    operation="enrichment",
)

# In waterfall.py — add per-contact context
log = structlog.get_logger()
log = log.bind(contact_id=contact.id, email=contact.email_masked)

log.info("starting_enrichment", provider_count=len(providers))
# Output: {"timestamp": "2026-03-08T14:30:00Z", "level": "info", "event": "starting_enrichment",
#          "campaign_id": 42, "campaign_name": "Q1 Outreach", "contact_id": 123,
#          "provider_count": 4}

# At enrichment end — clear context
structlog.contextvars.unbind_contextvars("campaign_id", "campaign_name")
```

### 1.4 Log Level Guidelines for Clay-Dupe

| Level | When to Use | Examples in Our Codebase |
|---|---|---|
| **DEBUG** | Detailed diagnostic info, only for troubleshooting | Pattern engine template matching details, cache key generation, provider request/response bodies (redacted) |
| **INFO** | Normal operational events, confirmations | "Enrichment started", "Provider returned email", "Campaign completed", "Pattern learned", "Cache hit" |
| **WARNING** | Unexpected but recoverable situations | Provider timeout (will retry), rate limit hit, pattern confidence below threshold, disk space < 20% |
| **ERROR** | Failures that affect functionality | Provider returned error, DB write failed, all providers exhausted for contact, circuit breaker tripped |
| **CRITICAL** | System cannot continue | Database corruption, no providers configured, out of disk space, startup failure |

**Rule of thumb for production**: Run at INFO level. One INFO line per enrichment step (not per contact). DEBUG only when investigating issues.

### 1.5 Logging API Calls to Providers

Every provider call should log a structured record with:

```python
# In providers/base.py — wrap around actual API call
log = structlog.get_logger()

async def _call_with_logging(self, method: str, url: str, **kwargs):
    start = time.monotonic()
    try:
        response = await self.client.request(method, url, **kwargs)
        elapsed_ms = (time.monotonic() - start) * 1000

        log.info(
            "provider_api_call",
            provider=self.name.value,
            method=method,
            endpoint=url,                    # URL without query params
            status_code=response.status_code,
            latency_ms=round(elapsed_ms, 1),
            credits_used=self._extract_credits(response),
            cache_hit=False,
        )
        return response

    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        log.error(
            "provider_api_error",
            provider=self.name.value,
            method=method,
            endpoint=url,
            error_type=type(exc).__name__,
            error_msg=str(exc),
            latency_ms=round(elapsed_ms, 1),
        )
        raise
```

**Fields to capture per API call:**
- `provider` — which provider (apollo, icypeas, findymail, etc.)
- `endpoint` — the API endpoint called (not full URL with params)
- `status_code` — HTTP response code
- `latency_ms` — round-trip time
- `credits_used` — if the provider reports credit consumption
- `cache_hit` — whether result came from pattern cache
- `error_type` / `error_msg` — on failure

### 1.6 Sensitive Data Protection

**Problem**: API keys, email addresses, and PII can leak into logs.

**Solution**: Custom structlog processor that masks sensitive fields before rendering.

```python
import re

# Patterns to detect and mask
SENSITIVE_PATTERNS = {
    "api_key": re.compile(r"[a-zA-Z0-9_-]{20,}"),  # Long alphanumeric strings
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
}

# Keys whose values should always be masked
SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "api_id", "token", "secret", "password",
    "authorization", "x-api-key", "cookie",
})

def mask_sensitive_data(_, __, event_dict):
    """Structlog processor: mask PII and secrets before logging."""
    for key, value in list(event_dict.items()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
        elif isinstance(value, str) and key not in ("event", "level", "timestamp"):
            # Mask emails in free-text fields
            event_dict[key] = SENSITIVE_PATTERNS["email"].sub("[EMAIL]", value)
    return event_dict

# Add to processor chain (BEFORE the renderer):
# shared_processors = [
#     ...
#     mask_sensitive_data,        # <-- mask before output
#     structlog.processors.JSONRenderer(),
# ]
```

**Additional practices:**
- Never log full API responses (may contain PII from provider data)
- Log contact IDs, not contact emails/names
- Use `email_masked` helper: `"j***@example.com"` for debugging
- Never log HTTP headers (contain API keys)
- Sentry: configure `before_send` to strip PII

### 1.7 Log Rotation and Retention

**For Docker deployment (our case): No rotation needed.**

- Log to stdout/stderr (structlog default)
- Docker handles rotation via `--log-opt max-size=50m --log-opt max-file=3`
- Or configure in `docker-compose.yml`:

```yaml
services:
  clay-dupe:
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
```

**If we ever need file logging** (non-Docker):
- Use `logging.handlers.RotatingFileHandler` (stdlib, battle-tested)
- Config: `maxBytes=50MB`, `backupCount=5` = ~250MB max
- loguru's rotation is nicer API but adds a dependency for one feature
- structlog's `WriteLoggerFactory` can write to files but doesn't rotate — use stdlib handler

**Retention policy:**
- Application logs: 30 days (sufficient for debugging)
- Audit logs (in SQLite): 365 days (compliance)
- Error events (Sentry): 90 days (free tier default)

### 1.8 Streamlit + asyncio Logging

**Challenge**: Streamlit runs Tornado's event loop. Our enrichment runs asyncio tasks. Both need unified logging.

**Solution**:

```python
# In ui/app.py — initialize logging once at startup
from core.logging import configure_logging

# Must be called before any logger.getLogger() in imported modules
configure_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    json_output=os.environ.get("LOG_FORMAT") == "json",
)

# For async enrichment tasks, use structlog.contextvars
# contextvars automatically propagate across asyncio tasks
async def enrich_campaign(campaign_id: int):
    structlog.contextvars.bind_contextvars(campaign_id=campaign_id)
    try:
        # All log lines from here and child coroutines include campaign_id
        await waterfall.process(...)
    finally:
        structlog.contextvars.clear_contextvars()
```

**Key points:**
- structlog.contextvars uses Python's `contextvars` module, which properly isolates context per asyncio task
- No thread-safety issues — each task gets its own context copy
- Streamlit's re-run model means logging init should be in a `@st.cache_resource` or at module level
- Suppress Streamlit's own verbose logging: `logging.getLogger("streamlit").setLevel(logging.WARNING)`

---

## 2. Health Checks

### 2.1 Streamlit's Built-in Health Endpoint

Streamlit exposes `/_stcore/health` which returns `"ok"` with HTTP 200 when the server is running.

**Limitations:**
- Only checks if the Streamlit server process is alive
- Does NOT check application health (DB connectivity, providers, etc.)
- Returns "ok" even if the app has errors
- Previously was `/_stcore/health`, older versions used `/healthz`

### 2.2 Custom Health Check Implementation

```python
# core/health.py
import time
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional
import aiosqlite
import httpx

@dataclass
class HealthStatus:
    healthy: bool
    checks: dict[str, dict] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self):
        return {
            "healthy": self.healthy,
            "checks": self.checks,
            "timestamp": self.timestamp,
        }

async def check_health() -> HealthStatus:
    """Run all health checks and return aggregate status."""
    checks = {}
    all_healthy = True

    # 1. Database connectivity
    try:
        start = time.monotonic()
        async with aiosqlite.connect(os.environ.get("DB_PATH", "clay_dupe.db")) as db:
            await db.execute("SELECT 1")
        latency = round((time.monotonic() - start) * 1000, 1)
        checks["database"] = {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # 2. Disk space
    try:
        usage = shutil.disk_usage("/data" if os.path.exists("/data") else ".")
        free_pct = round(usage.free / usage.total * 100, 1)
        checks["disk"] = {
            "status": "healthy" if free_pct > 10 else "warning" if free_pct > 5 else "unhealthy",
            "free_percent": free_pct,
            "free_gb": round(usage.free / (1024**3), 2),
        }
        if free_pct <= 5:
            all_healthy = False
    except Exception as e:
        checks["disk"] = {"status": "unknown", "error": str(e)}

    # 3. Provider API status (lightweight — just check auth, not full enrichment)
    # Only check providers that have API keys configured
    provider_checks = {}
    # Example: Apollo health check
    apollo_key = os.environ.get("APOLLO_API_KEY")
    if apollo_key:
        try:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.apollo.io/api/v1/auth/health",
                    headers={"x-api-key": apollo_key},
                )
            latency = round((time.monotonic() - start) * 1000, 1)
            provider_checks["apollo"] = {
                "status": "healthy" if resp.status_code == 200 else "degraded",
                "latency_ms": latency,
            }
        except Exception:
            provider_checks["apollo"] = {"status": "unreachable"}

    checks["providers"] = provider_checks

    # 4. SQLite database size
    db_path = os.environ.get("DB_PATH", "clay_dupe.db")
    if os.path.exists(db_path):
        db_size_mb = round(os.path.getsize(db_path) / (1024**2), 2)
        checks["database_size_mb"] = db_size_mb

    from datetime import datetime, timezone
    return HealthStatus(
        healthy=all_healthy,
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
```

### 2.3 Exposing Health Status in the UI

```python
# In the Streamlit analytics/dashboard page
import asyncio
from core.health import check_health

def render_health_widget():
    """Sidebar health status widget."""
    status = asyncio.run(check_health())

    if status.healthy:
        st.sidebar.success("System Healthy")
    else:
        st.sidebar.error("System Issues Detected")

    with st.sidebar.expander("Health Details"):
        for check_name, check_data in status.checks.items():
            if isinstance(check_data, dict):
                icon = "✓" if check_data.get("status") == "healthy" else "!"
                st.text(f"{icon} {check_name}: {check_data.get('status', 'unknown')}")
```

### 2.4 Docker HEALTHCHECK

Add to our Dockerfile:

```dockerfile
# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Health check: verify Streamlit is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1
```

**Parameters explained:**
- `--interval=30s` — check every 30 seconds (not too frequent for small app)
- `--timeout=10s` — fail if no response in 10s
- `--start-period=15s` — give Streamlit time to start before first check
- `--retries=3` — mark unhealthy after 3 consecutive failures

**For docker-compose:**
```yaml
services:
  clay-dupe:
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3
```

### 2.5 Railway / Fly.io Health Checks

**Railway:**
- Uses TCP health checks by default (port open = healthy)
- Custom HTTP health checks: set `RAILWAY_HEALTHCHECK_URL=/_stcore/health`
- Timeout: default 300s for initial deploy, then 5s per check
- Failed health checks trigger automatic restart

**Fly.io:**
- Configured in `fly.toml`:
```toml
[[services.http_checks]]
  interval = 30000       # 30s
  grace_period = "15s"
  method = "GET"
  path = "/_stcore/health"
  timeout = 5000         # 5s
```
- Failed checks remove instance from load balancer, then restart

**For our Docker deployment (self-hosted):**
- Docker's built-in HEALTHCHECK is sufficient
- If using docker-compose with `restart: unless-stopped`, Docker automatically restarts unhealthy containers
- No need for external orchestration for a 3-person team

---

## 3. Metrics & Dashboards

### 3.1 Key Metrics for an Enrichment Platform

#### Enrichment Metrics (most important)
| Metric | Type | Description |
|---|---|---|
| `enrichment.total` | Counter | Total enrichment attempts |
| `enrichment.success` | Counter | Successful enrichments (email found) |
| `enrichment.success_rate` | Gauge | Success rate (success / total), per provider and overall |
| `enrichment.by_provider` | Counter | Enrichments per provider (shows waterfall fallthrough) |
| `enrichment.pattern_hits` | Counter | Emails found via pattern engine (zero cost) |
| `enrichment.cache_hits` | Counter | Results served from cache |
| `enrichment.duration_seconds` | Histogram | Time per enrichment (P50, P95, P99) |

#### Provider Metrics
| Metric | Type | Description |
|---|---|---|
| `provider.api_calls` | Counter | API calls per provider |
| `provider.api_errors` | Counter | Failed API calls per provider |
| `provider.latency_ms` | Histogram | Response time per provider |
| `provider.circuit_breaker_state` | Gauge | 0=closed, 1=half-open, 2=open |
| `provider.rate_limit_hits` | Counter | Rate limit responses (429s) |

#### Cost Metrics
| Metric | Type | Description |
|---|---|---|
| `cost.total_usd` | Counter | Total spend across all providers |
| `cost.per_provider_usd` | Counter | Spend per provider |
| `cost.per_enrichment_usd` | Gauge | Average cost per successful enrichment |
| `cost.daily_budget_remaining` | Gauge | Remaining daily budget |
| `cost.pattern_savings_usd` | Counter | Money saved by pattern engine |

#### System Metrics
| Metric | Type | Description |
|---|---|---|
| `queue.active_enrichments` | Gauge | Currently processing contacts |
| `queue.pending` | Gauge | Contacts waiting to be processed |
| `db.size_bytes` | Gauge | SQLite database file size |
| `db.query_latency_ms` | Histogram | Database query times |

### 3.2 Collecting Metrics in Python

**Option A: prometheus_client (if you want Prometheus/Grafana later)**

```python
from prometheus_client import Counter, Histogram, Gauge

enrichment_total = Counter(
    "enrichment_total", "Total enrichment attempts",
    ["provider", "campaign_id"]
)
enrichment_success = Counter(
    "enrichment_success", "Successful enrichments",
    ["provider", "campaign_id"]
)
api_latency = Histogram(
    "provider_api_latency_seconds", "Provider API latency",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
```

**Option B: Simple in-app metrics (recommended for us)**

For a 3-person team with SQLite, we don't need Prometheus. We already have the data:

```python
# core/metrics.py — lightweight metrics from existing data
from data.database import Database

class MetricsCollector:
    """Compute metrics from existing database tables. No new infrastructure."""

    def __init__(self, db: Database):
        self.db = db

    async def get_enrichment_metrics(self, campaign_id: int = None) -> dict:
        """Compute enrichment metrics from the contacts table."""
        where = f"WHERE campaign_id = {campaign_id}" if campaign_id else ""

        rows = await self.db.fetch_all(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) as found,
                SUM(CASE WHEN email_source = 'pattern' THEN 1 ELSE 0 END) as pattern_hits,
                SUM(CASE WHEN email_source = 'cache' THEN 1 ELSE 0 END) as cache_hits
            FROM contacts {where}
        """)

        total = rows[0]["total"] or 0
        found = rows[0]["found"] or 0
        return {
            "total": total,
            "found": found,
            "success_rate": round(found / total * 100, 1) if total > 0 else 0,
            "pattern_hits": rows[0]["pattern_hits"] or 0,
            "cache_hits": rows[0]["cache_hits"] or 0,
        }

    async def get_provider_metrics(self) -> list[dict]:
        """Per-provider success rates and latency from api_call_log."""
        return await self.db.fetch_all("""
            SELECT
                provider,
                COUNT(*) as total_calls,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes,
                ROUND(AVG(latency_ms), 1) as avg_latency_ms,
                ROUND(SUM(cost_usd), 4) as total_cost_usd
            FROM api_call_log
            GROUP BY provider
            ORDER BY total_calls DESC
        """)

    async def get_cost_summary(self) -> dict:
        """Cost metrics from the cost tracking table."""
        return await self.db.fetch_one("""
            SELECT
                ROUND(SUM(cost_usd), 4) as total_spend,
                ROUND(SUM(CASE WHEN date(timestamp) = date('now') THEN cost_usd ELSE 0 END), 4) as today_spend,
                COUNT(DISTINCT provider) as active_providers
            FROM api_call_log
        """)
```

### 3.3 Displaying Metrics in Streamlit

We already have an analytics page. Enhance it with real-time metrics:

```python
# ui/pages/analytics.py — metrics dashboard
import streamlit as st
from core.metrics import MetricsCollector

def render_metrics_dashboard(db):
    metrics = MetricsCollector(db)

    # Top-level KPIs
    col1, col2, col3, col4 = st.columns(4)
    enrichment = asyncio.run(metrics.get_enrichment_metrics())
    cost = asyncio.run(metrics.get_cost_summary())

    col1.metric("Success Rate", f"{enrichment['success_rate']}%")
    col2.metric("Contacts Found", enrichment["found"])
    col3.metric("Pattern Saves", enrichment["pattern_hits"])
    col4.metric("Total Spend", f"${cost['total_spend']:.2f}")

    # Provider breakdown
    st.subheader("Provider Performance")
    providers = asyncio.run(metrics.get_provider_metrics())
    st.dataframe(providers)

    # Cost trend chart (from existing data)
    st.subheader("Daily Spend")
    daily_cost = asyncio.run(db.fetch_all("""
        SELECT date(timestamp) as day,
               ROUND(SUM(cost_usd), 4) as spend
        FROM api_call_log
        GROUP BY date(timestamp)
        ORDER BY day DESC
        LIMIT 30
    """))
    st.line_chart(daily_cost, x="day", y="spend")
```

### 3.4 Simple Monitoring Philosophy

**What we DON'T need:**
- Prometheus server (overkill for 3-person team)
- Grafana dashboards (Streamlit IS our dashboard)
- ELK stack (Docker JSON logs + grep is fine)
- Datadog / New Relic (expensive, unnecessary at our scale)

**What we DO need:**
- Structured JSON logs to stdout (structlog)
- Health check endpoint (Docker HEALTHCHECK)
- Metrics computed from existing database tables (no new infra)
- Sentry for error tracking (free tier, 5K events/month)
- Simple alerting via webhooks (Slack/Discord/email)

---

## 4. Alerting

### 4.1 Alert Categories and Thresholds

#### Budget Alerts
| Condition | Severity | Threshold |
|---|---|---|
| Daily spend > 80% of daily budget | Warning | Configurable, e.g., $8 of $10 |
| Daily spend > 95% of daily budget | Critical | Auto-pause enrichment |
| Monthly spend > 80% of monthly budget | Warning | Email notification |
| Provider cost spike (>3x normal daily) | Warning | Anomaly detection |

#### Provider Failure Alerts
| Condition | Severity | Threshold |
|---|---|---|
| Provider error rate > 20% in 5 minutes | Warning | May be transient |
| Provider error rate > 50% in 5 minutes | Critical | Circuit breaker should trip |
| Circuit breaker opened | Critical | Provider is offline |
| All providers down | Critical | Enrichment halted |
| Provider latency > 10s (P95) | Warning | Degraded performance |

#### System Alerts
| Condition | Severity | Threshold |
|---|---|---|
| Disk space < 20% | Warning | Proactive |
| Disk space < 5% | Critical | Imminent failure |
| Database size > 1GB | Warning | May need cleanup |
| Health check failing | Critical | Service degraded |
| Enrichment queue stalled (no progress in 5 min) | Warning | Possible hang |

### 4.2 Sending Alerts

#### Slack Webhook (Recommended)

```python
# core/alerting.py
import httpx
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class Alert:
    title: str
    message: str
    severity: AlertSeverity
    source: str  # e.g., "budget", "provider", "system"

SEVERITY_EMOJI = {
    AlertSeverity.INFO: "ℹ️",
    AlertSeverity.WARNING: "⚠️",
    AlertSeverity.CRITICAL: "🚨",
}

async def send_slack_alert(alert: Alert, webhook_url: str):
    """Send alert to Slack via incoming webhook."""
    payload = {
        "text": f"{SEVERITY_EMOJI[alert.severity]} *{alert.title}*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{SEVERITY_EMOJI[alert.severity]} *{alert.title}*\n"
                        f"{alert.message}\n"
                        f"_Source: {alert.source} | Severity: {alert.severity.value}_"
                    ),
                },
            }
        ],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload, timeout=10.0)
        resp.raise_for_status()

async def send_discord_alert(alert: Alert, webhook_url: str):
    """Send alert to Discord via webhook."""
    color_map = {
        AlertSeverity.INFO: 3447003,      # Blue
        AlertSeverity.WARNING: 16776960,   # Yellow
        AlertSeverity.CRITICAL: 15158332,  # Red
    }
    payload = {
        "embeds": [{
            "title": f"{SEVERITY_EMOJI[alert.severity]} {alert.title}",
            "description": alert.message,
            "color": color_map[alert.severity],
            "footer": {"text": f"Source: {alert.source}"},
        }]
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload, timeout=10.0)
        resp.raise_for_status()

async def send_email_alert(alert: Alert, smtp_config: dict):
    """Send alert via SMTP email."""
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(f"{alert.title}\n\n{alert.message}\n\nSource: {alert.source}")
    msg["Subject"] = f"[Clay-Dupe {alert.severity.value.upper()}] {alert.title}"
    msg["From"] = smtp_config["from"]
    msg["To"] = smtp_config["to"]

    with smtplib.SMTP(smtp_config["host"], smtp_config.get("port", 587)) as server:
        server.starttls()
        server.login(smtp_config["user"], smtp_config["password"])
        server.send_message(msg)
```

#### Alert Manager (Coordinates All Channels)

```python
# core/alerting.py (continued)
import time
from collections import defaultdict

class AlertManager:
    """Manages alert routing, deduplication, and cooldowns."""

    def __init__(self, config: dict):
        self.config = config  # slack_url, discord_url, smtp_config, etc.
        self._last_sent: dict[str, float] = defaultdict(float)
        self._cooldown_seconds = 300  # 5 minute cooldown per alert type

    async def send(self, alert: Alert):
        """Send alert to configured channels with dedup."""
        # Deduplication: don't spam the same alert
        alert_key = f"{alert.source}:{alert.title}"
        now = time.time()
        if now - self._last_sent[alert_key] < self._cooldown_seconds:
            return  # Still in cooldown
        self._last_sent[alert_key] = now

        # Route to configured channels
        if self.config.get("slack_webhook_url"):
            await send_slack_alert(alert, self.config["slack_webhook_url"])
        if self.config.get("discord_webhook_url"):
            await send_discord_alert(alert, self.config["discord_webhook_url"])
        if self.config.get("smtp"):
            await send_email_alert(alert, self.config["smtp"])
```

### 4.3 Avoiding Alert Fatigue

1. **Cooldown periods**: Same alert type suppressed for 5 minutes (configurable)
2. **Severity routing**: INFO alerts to log only, WARNING to Slack, CRITICAL to Slack + email
3. **Aggregation**: "Provider X failed 47 times in 5 minutes" instead of 47 individual alerts
4. **Business hours**: Optional — suppress non-CRITICAL alerts outside 8am-6pm
5. **Auto-resolve**: Send "resolved" message when condition clears
6. **Thresholds, not individual errors**: Alert on *rates* (20% error rate), not individual failures

---

## 5. Error Tracking

### 5.1 Sentry Setup

**Why Sentry:**
- Free tier: 5,000 events/month, 1 team member (sufficient for us)
- Automatic exception grouping, stack traces, breadcrumbs
- Python SDK with asyncio integration
- No infrastructure to maintain

**Installation:**
```bash
pip install sentry-sdk
```

**Initialization:**

```python
# core/sentry.py
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration

def init_sentry(dsn: str = None, environment: str = "production"):
    """Initialize Sentry error tracking.

    Call this early in the application startup, ideally inside an async context
    for proper asyncio integration.
    """
    dsn = dsn or os.environ.get("SENTRY_DSN")
    if not dsn:
        return  # Sentry is optional — no DSN = no tracking

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=0.1,  # 10% of transactions for performance monitoring

        integrations=[
            AsyncioIntegration(),
        ],

        # Strip PII before sending to Sentry
        before_send=_scrub_sensitive_data,

        # Don't send expected errors
        ignore_errors=[
            KeyboardInterrupt,
        ],

        # Release tracking
        release=os.environ.get("APP_VERSION", "dev"),
    )

def _scrub_sensitive_data(event, hint):
    """Remove PII and secrets from Sentry events."""
    # Scrub request headers (may contain API keys)
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        for key in list(headers.keys()):
            if key.lower() in ("authorization", "x-api-key", "cookie"):
                headers[key] = "[REDACTED]"

    # Scrub email addresses from exception messages
    if "exception" in event:
        for exc in event["exception"].get("values", []):
            if exc.get("value"):
                import re
                exc["value"] = re.sub(
                    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                    "[EMAIL]",
                    exc["value"],
                )

    return event
```

### 5.2 Integrating with Streamlit

Streamlit catches exceptions and displays them in the UI, which means Sentry won't see them unless we explicitly capture:

```python
# In Streamlit pages — wrap enrichment calls
import sentry_sdk

try:
    result = await run_enrichment(campaign)
except Exception as e:
    sentry_sdk.capture_exception(e)
    st.error(f"Enrichment failed: {e}")
```

**Better approach — global error handler:**

```python
# core/error_handler.py
import sentry_sdk
import structlog

log = structlog.get_logger()

def handle_error(error: Exception, context: dict = None):
    """Centralized error handler: log + Sentry + optional alert."""
    log.error(
        "unhandled_error",
        error_type=type(error).__name__,
        error_msg=str(error),
        **(context or {}),
    )
    sentry_sdk.capture_exception(error)

    # For critical errors, also alert
    if isinstance(error, (DatabaseError, SystemError)):
        asyncio.create_task(alert_manager.send(Alert(
            title=f"Critical Error: {type(error).__name__}",
            message=str(error),
            severity=AlertSeverity.CRITICAL,
            source="system",
        )))
```

### 5.3 Sentry + asyncio

Critical note from Sentry docs: **The SDK needs the event loop to be running when instrumenting asyncio.**

```python
# Two initialization approaches:

# Approach 1: Init inside first async function (preferred)
async def main():
    init_sentry()  # Event loop is running here
    await run_app()

# Approach 2: Deferred integration (when you don't control the event loop)
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration

sentry_sdk.init(dsn="...", integrations=[])  # Init without asyncio
# Later, when event loop is running:
AsyncioIntegration.setup_once()  # Or use enable_asyncio_integration()
```

For Streamlit (which manages its own event loop), Approach 1 inside a cached startup function works best:

```python
@st.cache_resource
def _init_monitoring():
    configure_logging()
    init_sentry()
```

### 5.4 Alternatives to Sentry

| Tool | Free Tier | Self-Hosted | Python SDK | Notes |
|---|---|---|---|---|
| **Sentry** | 5K events/mo | Yes (complex) | Excellent | Best overall for our needs |
| **GlitchTip** | Open source | Yes (simple) | Uses Sentry SDK | Sentry-compatible, lighter weight |
| **BugSnag** | 7.5K events/mo | No | Good | More expensive paid tiers |
| **Rollbar** | 5K events/mo | No | Good | Good grouping, less async support |
| **Highlight.io** | 500 sessions/mo | Yes | Good | Full observability, heavier |

**Recommendation**: Sentry SaaS (free tier) for now. If we need self-hosted later, GlitchTip is a drop-in replacement using the same SDK.

### 5.5 Tracking Unhandled Exceptions

With Sentry + structlog, unhandled exceptions are captured at multiple levels:

1. **Sentry SDK**: Automatically captures unhandled exceptions in asyncio tasks (via `AsyncioIntegration`)
2. **structlog**: `logger.exception()` in except blocks logs full stack trace
3. **Streamlit**: Shows exception in UI (user-visible)
4. **sys.excepthook**: Last resort for truly unhandled exceptions

```python
# Ensure nothing escapes uncaught
import sys

_original_excepthook = sys.excepthook

def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """Last-resort handler for truly unhandled exceptions."""
    if exc_type is not KeyboardInterrupt:
        log.critical(
            "unhandled_exception",
            error_type=exc_type.__name__,
            error_msg=str(exc_value),
        )
        sentry_sdk.capture_exception(exc_value)
    _original_excepthook(exc_type, exc_value, exc_traceback)

sys.excepthook = _global_exception_handler
```

---

## 6. Audit Trail

### 6.1 What Actions to Log

We already have an `audit_log` table. Here's what should go in it:

#### Must-Log (Security & Compliance)
| Action | Entity Type | Details |
|---|---|---|
| `campaign.create` | campaign | name, settings |
| `campaign.delete` | campaign | name, contact count at deletion |
| `enrichment.start` | campaign | contact count, provider config |
| `enrichment.complete` | campaign | duration, success rate, cost |
| `settings.update` | settings | which setting changed, old/new value |
| `api_key.add` | provider | provider name (NOT the key itself) |
| `api_key.remove` | provider | provider name |
| `export.csv` | campaign | row count, columns exported |
| `export.salesforce` | campaign | row count, SF object type |
| `contacts.import` | campaign | source (CSV/SF), row count |
| `contacts.delete` | campaign | count deleted |

#### Nice-to-Have (Operational Visibility)
| Action | Entity Type | Details |
|---|---|---|
| `budget.threshold` | system | budget %, amount |
| `circuit_breaker.trip` | provider | provider name, error count |
| `circuit_breaker.reset` | provider | provider name |
| `pattern.learned` | pattern | domain, pattern template, confidence |

### 6.2 Implementation

```python
# data/audit.py
import json
from datetime import datetime, timezone
from data.database import Database

class AuditLogger:
    """Write audit events to the audit_log table."""

    def __init__(self, db: Database):
        self.db = db

    async def log(
        self,
        action: str,
        entity_type: str = None,
        entity_id: str = None,
        user_id: str = "system",
        details: dict = None,
    ):
        """Record an audit event.

        Args:
            action: Dot-notation action, e.g., "campaign.create"
            entity_type: Type of entity affected, e.g., "campaign"
            entity_id: ID of the entity, e.g., "42"
            user_id: Who performed the action (default "system" for automated)
            details: Additional context as a dict (stored as JSON)
        """
        await self.db.execute(
            """INSERT INTO audit_log (timestamp, user_id, action, entity_type, entity_id, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                user_id,
                action,
                entity_type,
                entity_id,
                json.dumps(details or {}),
            ),
        )

    async def query(
        self,
        action: str = None,
        entity_type: str = None,
        since: str = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query audit log with filters."""
        conditions = []
        params = []

        if action:
            conditions.append("action LIKE ?")
            params.append(f"{action}%")
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        return await self.db.fetch_all(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        )
```

### 6.3 Fields in the Audit Log

Our existing schema is close but could use enhancements:

```sql
-- Current schema (already in schema.sql)
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id         TEXT,
    action          TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    details         TEXT DEFAULT '{}'
);

-- Recommended additions for v2.0:
-- 1. Add hash chain for tamper resistance
-- 2. Add IP address for compliance
ALTER TABLE audit_log ADD COLUMN ip_address TEXT;
ALTER TABLE audit_log ADD COLUMN prev_hash TEXT;  -- SHA-256 of previous row
ALTER TABLE audit_log ADD COLUMN row_hash TEXT;    -- SHA-256 of this row
```

### 6.4 Tamper Resistance

For a small self-hosted app, full blockchain-style immutability is overkill. Pragmatic approaches:

**Level 1 — Hash Chain (recommended for us):**

```python
import hashlib
import json

async def log_with_hash(self, action: str, **kwargs):
    """Append audit entry with hash chain for tamper detection."""
    # Get hash of previous entry
    prev = await self.db.fetch_one(
        "SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1"
    )
    prev_hash = prev["row_hash"] if prev else "GENESIS"

    # Compute hash of this entry
    entry_data = json.dumps({
        "action": action,
        "prev_hash": prev_hash,
        **kwargs,
    }, sort_keys=True)
    row_hash = hashlib.sha256(entry_data.encode()).hexdigest()

    await self.db.execute(
        """INSERT INTO audit_log (timestamp, user_id, action, entity_type,
           entity_id, details, prev_hash, row_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (..., prev_hash, row_hash),
    )
```

**Level 2 — SQLite Triggers (prevent updates/deletes):**

```sql
-- Prevent any modification of audit records
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
    BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'Audit log records are immutable');
    END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'Audit log records cannot be deleted');
    END;
```

**Level 3 — External backup** (for true compliance): Periodically export audit log to an append-only external store (S3 with Object Lock, or a separate read-only database copy).

### 6.5 Compliance Requirements

| Framework | Retention | Key Requirements |
|---|---|---|
| **GDPR** | Varies (30-365 days typical) | Right to erasure (but audit logs are exempt if needed for security), minimize PII in logs, document legal basis |
| **SOC 2** | 365 days minimum | Who did what, when. Tamper-evident. Regular review. Alert on unauthorized access |
| **For our scale** | 365 days | We're a small internal tool. Focus on: who changed settings, who ran enrichments, what was exported |

**GDPR-specific for audit logs:**
- Audit logs are generally exempt from "right to erasure" if they serve a legitimate security interest
- But minimize PII: log user IDs, not names/emails
- Don't log the actual enriched data (emails found) in audit trail — just the counts
- Document that audit log retention is 365 days in a privacy notice

---

## 7. Recommendations for Clay-Dupe

### 7.1 Minimum Viable Monitoring Setup

**Implement for v2.0 (estimated 2-3 days):**

| Component | Tool | Effort | Impact |
|---|---|---|---|
| Structured logging | structlog wrapping stdlib | 4-6 hours | High — replaces ad-hoc logging across 15+ modules |
| PII masking | Custom structlog processor | 1-2 hours | High — security requirement |
| Docker HEALTHCHECK | curl to `/_stcore/health` | 15 minutes | Medium — auto-restart on crash |
| Sentry error tracking | sentry-sdk (free tier) | 1-2 hours | High — catch errors before users report them |
| Budget alerts | Slack/Discord webhook | 2-3 hours | High — prevent overspending |
| Audit log usage | Wire up existing table | 2-3 hours | Medium — operational visibility |
| Metrics dashboard | Streamlit page (from existing DB) | 2-3 hours | Medium — visible success rates and costs |

**Total: ~15-20 hours of work for massive production readiness improvement.**

### 7.2 Defer to Later

| Component | Why Defer |
|---|---|
| Prometheus/Grafana | Overkill for 3-person team. Streamlit dashboards suffice. |
| ELK/Loki log aggregation | Docker JSON logs + `docker logs --since` is fine at our scale |
| OpenTelemetry distributed tracing | Single service, not distributed. structlog context is enough. |
| PagerDuty/OpsGenie | Slack webhooks are sufficient |
| Tamper-resistant hash chain | Nice-to-have, not blocking production use |
| Self-hosted Sentry/GlitchTip | SaaS free tier is fine for now |

### 7.3 Recommended Library Stack

```
# Add to requirements.txt
structlog>=24.1.0         # Structured logging
sentry-sdk>=2.0.0         # Error tracking (with asyncio integration)
# That's it. No prometheus, no grafana, no ELK.
```

### 7.4 Implementation Order

1. **structlog setup** (`core/logging.py`) — foundation for everything else
2. **PII masking processor** — before any logs go to production
3. **Docker HEALTHCHECK** — 15 minute win
4. **Sentry init** (`core/sentry.py`) — catches errors immediately
5. **Alert manager** (`core/alerting.py`) — budget and provider alerts
6. **Wire up audit logger** — use existing table, add calls at key points
7. **Metrics dashboard** — enhance existing analytics page

### 7.5 Environment Variables

```bash
# Logging
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json             # json or pretty (auto-detected in Docker)

# Sentry
SENTRY_DSN=                 # Optional — no DSN = Sentry disabled

# Alerting
SLACK_WEBHOOK_URL=          # Optional — Slack incoming webhook
DISCORD_WEBHOOK_URL=        # Optional — Discord webhook
ALERT_EMAIL_TO=             # Optional — alert recipient email
SMTP_HOST=                  # Required if using email alerts
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
```

### 7.6 Migration Path from Current Logging

The codebase currently uses `logging.getLogger(__name__)` in 15+ modules. Migration to structlog is **non-breaking**:

1. Add `structlog` to requirements
2. Create `core/logging.py` with `configure_logging()`
3. Call `configure_logging()` once at app startup (in `ui/app.py`)
4. **Existing `logger.info()`, `logger.error()` calls continue to work** — structlog wraps stdlib
5. Gradually migrate modules to `structlog.get_logger()` for context binding
6. Add `.bind(provider=self.name)` in provider base class for automatic context

No big-bang rewrite needed.

---

## Sources

- [structlog Documentation — Logging Best Practices](https://www.structlog.org/en/stable/logging-best-practices.html)
- [Better Stack — Comprehensive Guide to Python Logging with Structlog](https://betterstack.com/community/guides/logging/structlog/)
- [Dash0 — Leveling Up Python Logs with Structlog](https://www.dash0.com/guides/python-logging-with-structlog)
- [structlog ContextVars: Python Async Logging 2026](https://johal.in/structlog-contextvars-python-async-logging-2026/)
- [Better Stack — Top Python Logging Libraries Comparison](https://betterstack.com/community/guides/logging/best-python-logging-libraries/)
- [Sentry asyncio Integration Docs](https://docs.sentry.io/platforms/python/integrations/asyncio/)
- [Sentry Python Platform Docs](https://docs.sentry.io/platforms/python/)
- [Sentry — Scrubbing Sensitive Data](https://docs.sentry.io/platforms/python/guides/logging/data-management/sensitive-data/)
- [Streamlit — Creating a Health Check Endpoint](https://discuss.streamlit.io/t/creating-a-health-check-endpoint-in-streamlit/3920)
- [Streamlit — Docker Deployment Docs](https://docs.streamlit.io/deploy/tutorials/docker)
- [Streamlit — HEALTHCHECK in Docker Compose](https://discuss.streamlit.io/t/streamlit-healthcheck-in-docker-compose/29450)
- [GitHub — Streamlit Health Check Endpoint Issue #7076](https://github.com/streamlit/streamlit/issues/7076)
- [prometheus_client Python — GitHub](https://github.com/prometheus/client_python)
- [Better Stack — Monitoring Python with Prometheus](https://betterstack.com/community/guides/monitoring/prometheus-python-metrics/)
- [DEV Community — Mask Sensitive Data Using Python Logging](https://dev.to/camillehe1992/mask-sensitive-data-using-python-built-in-logging-module-45fa)
- [Better Stack — Safeguarding Sensitive Data in Logs](https://betterstack.com/community/guides/logging/sensitive-data/)
- [Slack Developer Docs — Webhook Client](https://slack.dev/python-slack-sdk/webhook/index.html)
- [Discord Webhooks Complete Guide 2025](https://inventivehq.com/blog/discord-webhooks-guide)
- [DEV Community — Slack Notifications with Python](https://dev.to/jajera/how-to-send-notifications-to-slack-using-python-57ch)
- [Python Logging HOWTO — Official Docs](https://docs.python.org/3/howto/logging.html)
- [Dash0 — Python Log Levels Explained](https://www.dash0.com/faq/python-log-levels-explained)
- [SigNoz — Python Logging Best Practices](https://signoz.io/guides/python-logging-best-practices/)
- [Streamlit — Threading and Multithreading Docs](https://docs.streamlit.io/develop/concepts/design/multithreading)
- [SQLite Forum — Blockchain and Immutable Records](https://www.sqliteforum.com/p/sqlite-and-blockchain-storing-immutable)
- [CloudEagle — SOC 2 Audit Complete Guide 2025](https://www.cloudeagle.ai/blogs/soc-2-audit)
- [HubiFi — Immutable Audit Log Guide](https://www.hubifi.com/blog/immutable-audit-log-guide)
