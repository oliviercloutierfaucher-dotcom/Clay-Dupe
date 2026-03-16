# Docker + Streamlit Deployment Research

> Deep research conducted 2026-03-08
> Targeting: Railway, Fly.io, with SQLite persistence, secrets management, production hardening

---

## Table of Contents

1. [Streamlit Docker Fundamentals](#1-streamlit-docker-fundamentals)
2. [SQLite in Docker](#2-sqlite-in-docker)
3. [Secrets Management](#3-secrets-management)
4. [Railway Deployment](#4-railway-deployment)
5. [Fly.io Deployment](#5-flyio-deployment)
6. [Production Streamlit Configuration](#6-production-streamlit-configuration)
7. [Docker Compose: Dev vs Production](#7-docker-compose-dev-vs-production)
8. [Reverse Proxy Configuration](#8-reverse-proxy-configuration)
9. [CI/CD Pipelines](#9-cicd-pipelines)
10. [Alternative: DigitalOcean App Platform](#10-alternative-digitalocean-app-platform)
11. [Platform Comparison Matrix](#11-platform-comparison-matrix)
12. [Recommended Architecture](#12-recommended-architecture)

---

## 1. Streamlit Docker Fundamentals

### 1.1 Best Base Image

**Recommendation: `python:3.11-slim` (Debian bookworm-slim)**

| Image | Size | Pros | Cons |
|-------|------|------|------|
| `python:3.11-slim` | ~150MB | Small, has apt-get, good compatibility | Need to install build deps manually |
| `python:3.11-bookworm` | ~900MB | Everything pre-installed | Bloated for production |
| `python:3.11-alpine` | ~50MB | Tiny | musl libc issues, slow pip installs, compilation problems |

**Verdict**: `python:3.11-slim` is the sweet spot. Alpine causes too many issues with Python packages that need C compilation. The bookworm full image is unnecessarily large.

### 1.2 Optimal Dockerfile Structure

**Single-stage build** is sufficient for most Streamlit apps. Multi-stage adds complexity without major benefit since Streamlit apps don't have a "build artifact" stage.

```dockerfile
# === Production Dockerfile for Streamlit ===
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (curl needed for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Streamlit config
COPY .streamlit/ .streamlit/

# Copy application code
COPY . .

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

# Create data directory for SQLite
VOLUME ["/app/data"]

EXPOSE 8501

# Health check using Streamlit's built-in endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
```

**Critical note**: For Streamlit >= 1.10.0, `WORKDIR` MUST NOT be the root directory (`/`). Use `/app`.

### 1.3 Handling .streamlit/config.toml in Docker

Two approaches:

**Option A: Bake into image (recommended for production)**
```dockerfile
COPY .streamlit/config.toml .streamlit/config.toml
```

**Option B: Mount at runtime (good for flexibility)**
```bash
docker run -v ./config.toml:/app/.streamlit/config.toml streamlit-app
```

**Option C: Use CLI flags (overrides config.toml)**
```dockerfile
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
```

CLI flags take precedence over config.toml, which takes precedence over environment variables.

### 1.4 Server Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| `server.address` | `0.0.0.0` | Listen on all interfaces (required in Docker) |
| `server.port` | `8501` (or `$PORT`) | Default Streamlit port |
| `server.headless` | `true` | Prevents "open browser" prompt |
| `server.enableCORS` | `true` (default) | Keep enabled for security |
| `server.enableXsrfProtection` | `true` (default) | Keep enabled for CSRF defense |

For cloud platforms that assign dynamic ports (Railway, Fly.io), use:
```dockerfile
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
```

### 1.5 Health Check Endpoint

Streamlit exposes a built-in health endpoint:

```
GET http://localhost:8501/_stcore/health
```

Returns `"ok"` with HTTP 200 when the app is running.

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1
```

**Known issue**: In some cloud environments, WebSocket connections can interfere with health check parsing. If you encounter this, use a simple TCP check instead:
```dockerfile
HEALTHCHECK CMD curl -s http://localhost:8501/_stcore/health > /dev/null || exit 1
```

### 1.6 CORS and CSP Headers

Streamlit's built-in CORS/XSRF settings in `config.toml`:

```toml
[server]
enableCORS = true          # Cross-Origin Resource Sharing protection
enableXsrfProtection = true  # Cross-Site Request Forgery protection
```

**Important**: If XSRF protection is enabled and CORS is disabled, Streamlit will force-enable both. They work as a pair.

For production behind a reverse proxy:
- Keep CORS enabled (Streamlit handles it)
- If your reverse proxy handles CORS, you may need to coordinate headers to avoid double-CORS issues
- SSL termination should happen at the reverse proxy, not Streamlit

Streamlit does NOT support custom CSP headers natively. Use a reverse proxy (Nginx/Caddy) to add CSP headers.

### 1.7 Hiding UI Elements (Footer, Hamburger Menu)

No native config option exists. Use CSS injection:

```python
import streamlit as st

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDeployButton {display: none;}
    </style>
""", unsafe_allow_html=True)
```

**Alternative**: Append `?embed=true` to the URL to remove the hamburger menu (useful for iframe embedding).

### 1.8 File Upload Temp Directory

Streamlit uses Python's `tempfile` module by default. In Docker, configure with:

```dockerfile
ENV TMPDIR=/app/tmp
RUN mkdir -p /app/tmp && chown appuser:appuser /app/tmp
```

Or set `server.maxUploadSize` in config.toml (default: 200MB):
```toml
[server]
maxUploadSize = 50  # MB
```

### 1.9 File Watcher in Docker

**Disable for production** to save resources:

```toml
[server]
fileWatcherType = "none"    # Options: "auto", "watchdog", "poll", "none"
runOnSave = false
```

In development, use `"poll"` for Docker volumes (inotify doesn't work across volume boundaries):
```toml
[server]
fileWatcherType = "poll"
runOnSave = true
```

---

## 2. SQLite in Docker

### 2.1 Volume Mounting for Persistence

**Named volumes** are the recommended approach:

```bash
# Create named volume
docker volume create streamlit-data

# Run with volume
docker run -v streamlit-data:/app/data streamlit-app
```

**Convention**: Mount at `/app/data/` and store your SQLite database there.

```python
# In your application code
import os
DB_PATH = os.environ.get("DATABASE_PATH", "/app/data/app.db")
```

### 2.2 SQLite + Docker Gotchas

| Issue | Detail | Solution |
|-------|--------|----------|
| WAL mode on network FS | WAL mode can corrupt DB on NFS/CIFS | Use named volumes (host filesystem) |
| File locking | Unreliable across networked volumes | Single container only |
| Multi-container | SQLite = one writer at a time | Never share SQLite across containers |
| Permission errors | Non-root user can't write | Set proper ownership or use `RAILWAY_RUN_UID=0` |
| WAL/SHM files | Auxiliary files created alongside DB | Mount the directory, not the file |
| tmpfs | Data lost on restart | Never use tmpfs for SQLite |

**Critical**: Always mount the DIRECTORY containing the SQLite file, never mount the file itself. SQLite creates `-wal` and `-shm` companion files that must be in the same directory.

### 2.3 Optimal PRAGMA Settings for Docker

```python
import sqlite3

def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")           # Write-Ahead Logging
    conn.execute("PRAGMA synchronous=NORMAL")          # Balanced safety/speed
    conn.execute("PRAGMA cache_size=-64000")            # 64MB cache
    conn.execute("PRAGMA mmap_size=268435456")          # 256MB memory-mapped I/O
    conn.execute("PRAGMA busy_timeout=5000")            # Wait 5s on locks
    conn.execute("PRAGMA foreign_keys=ON")              # Enforce FK constraints
    return conn
```

### 2.4 Backup Strategies

**NEVER use `cp` to back up an active SQLite database.** It is not transactionally safe.

**Safe backup methods:**

```bash
# Method 1: SQLite .backup command (recommended)
sqlite3 /app/data/app.db ".backup /app/data/backups/app_$(date +%Y%m%d_%H%M%S).db"

# Method 2: VACUUM INTO (better under heavy writes, creates snapshot)
sqlite3 /app/data/app.db "VACUUM INTO '/app/data/backups/app_$(date +%Y%m%d_%H%M%S).db'"

# Method 3: SQL dump (portable, human-readable)
sqlite3 /app/data/app.db ".dump" > /app/data/backups/dump_$(date +%Y%m%d_%H%M%S).sql
```

**Docker cron backup sidecar:**

```dockerfile
# backup/Dockerfile
FROM alpine:3.19
RUN apk add --no-cache sqlite
COPY backup.sh /backup.sh
RUN chmod +x /backup.sh
CMD ["crond", "-f", "-d", "8"]
```

```bash
# backup.sh
#!/bin/sh
# Run daily at 2 AM
echo "0 2 * * * /usr/bin/sqlite3 /data/app.db '.backup /backups/app_\$(date +\%Y\%m\%d).db'" | crontab -
```

**Recommended backup tiers:**
- **Minimum**: Daily local backups, 30-day retention
- **Recommended**: Daily local + weekly cloud (S3/B2), 90-day retention
- **Production**: Hourly local + daily cloud to 2 providers, 1-year retention

**Litestream** is an excellent option for continuous SQLite replication to S3/B2/Azure.

### 2.5 Database Migrations in Docker

Run migrations on container startup via an entrypoint script:

```bash
#!/bin/bash
# entrypoint.sh

# Run database migrations
python migrate.py

# Start Streamlit
exec streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
```

```dockerfile
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
```

### 2.6 Performance: Docker vs Bare Metal

SQLite performance in Docker with named volumes is essentially identical to bare metal. The volume driver uses the host filesystem directly -- there is no virtualization overhead for storage I/O. The only measurable difference is in tmpfs (memory-only, no persistence) which is faster but loses data on restart.

### 2.7 Multi-Container Scaling Limitation

**SQLite cannot scale horizontally.** If you need multiple container replicas:
- Use PostgreSQL or MySQL instead
- Or use a read-replica pattern (Litestream + read-only SQLite copies)
- Or accept single-container deployment (fine for most internal tools)

For a Streamlit internal tool, single-container SQLite is perfectly acceptable.

---

## 3. Secrets Management

### 3.1 Passing API Keys to Docker

**Method 1: Environment variables (simplest)**
```bash
docker run -e API_KEY=xxx -e DB_PASSWORD=yyy streamlit-app
```

**Method 2: .env file**
```bash
docker run --env-file .env streamlit-app
```

**Method 3: Docker Secrets (Swarm mode only)**
```bash
echo "my-secret-value" | docker secret create api_key -
# Access in container at /run/secrets/api_key
```

**Method 4: File mount**
```bash
docker run -v ./secrets:/run/secrets:ro streamlit-app
```

### 3.2 Railway Secrets Management

Railway manages environment variables through:
- **Dashboard**: Settings > Variables for each service
- **CLI**: `railway variables set KEY=VALUE`
- **Shared variables**: Variables shared across services in a project
- **Reference variables**: `${{service.VARIABLE}}` syntax for cross-service references

Variables are injected as environment variables at runtime. They are NOT baked into the image.

### 3.3 Fly.io Secrets Management

```bash
# Set secrets (encrypted at rest)
fly secrets set API_KEY=xxx DB_PASSWORD=yyy

# List secrets (values hidden)
fly secrets list

# Remove a secret
fly secrets unset API_KEY
```

Secrets are injected as environment variables. Setting/unsetting triggers a redeployment automatically.

### 3.4 Avoiding Secrets in Docker Images

**NEVER do this:**
```dockerfile
# BAD - secrets baked into image layer
ENV API_KEY=my-secret-key
COPY .env /app/.env
```

**Instead:**
- Pass at runtime via `-e` or `--env-file`
- Use build secrets for build-time-only needs:
  ```dockerfile
  RUN --mount=type=secret,id=pip_token \
      pip install -r requirements.txt --extra-index-url https://$(cat /run/secrets/pip_token)@pypi.example.com/simple
  ```

### 3.5 Streamlit secrets.toml vs Environment Variables

| Aspect | secrets.toml | Environment Variables |
|--------|-------------|----------------------|
| Access | `st.secrets["key"]` | `os.environ["KEY"]` |
| Format | TOML (nested, typed) | Flat strings |
| Docker friendly | Needs file mount | Native support |
| Cloud platform support | Must mount file | Built-in on Railway/Fly.io |
| **Recommendation** | Development only | **Production** |

**Verdict**: Use environment variables in production Docker deployments. All cloud platforms (Railway, Fly.io, DO) inject env vars natively. Use `os.environ.get("KEY")` in your code.

If you must use `secrets.toml`, generate it at container startup:

```bash
# entrypoint.sh
cat > /app/.streamlit/secrets.toml << EOF
[api]
key = "${API_KEY}"
[database]
password = "${DB_PASSWORD}"
EOF
exec streamlit run app.py ...
```

### 3.6 Secret Rotation Without Rebuilding

- **Railway**: Update variable in dashboard/CLI -> automatic redeploy
- **Fly.io**: `fly secrets set KEY=new-value` -> automatic redeploy
- **Docker Compose**: Update `.env` file -> `docker compose up -d` (recreates container)
- **Docker Swarm**: `docker secret` rotation with versioned secret names

---

## 4. Railway Deployment

### 4.1 Step-by-Step Deployment

1. **Create Railway account** at [railway.com](https://railway.com)
2. **Install CLI**: `npm install -g @railway/cli` or `brew install railway`
3. **Login**: `railway login`
4. **Create project**: `railway init`
5. **Link GitHub repo** or use `railway up` for direct deployment
6. **Configure environment variables** in Railway dashboard
7. **Add volume** for SQLite persistence (if needed)
8. **Deploy**: Push to GitHub (auto-deploys) or `railway up`

### 4.2 Build Process

Railway detects your project type automatically:
- **With Dockerfile**: Uses your Dockerfile directly
- **Without Dockerfile**: Uses Railpack (successor to Nixpacks) for auto-detection
- Configure via `railway.toml` or dashboard

For Streamlit, Railway needs to know the start command:
```toml
# railway.toml (if not using Dockerfile)
[build]
builder = "nixpacks"

[deploy]
startCommand = "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true"
```

**Note**: Railway assigns a dynamic `$PORT` -- your app MUST listen on it.

### 4.3 Persistent Storage (Volumes)

Railway supports persistent volumes:

1. Go to Service > Settings > Volumes
2. Add volume with mount path (e.g., `/app/data`)
3. Volume persists across deployments

**Limitations:**
- Max 1 volume per service
- Cannot use replicas with volumes
- Redeployments cause brief downtime (even with health checks)
- Size limits: Free 0.5GB, Hobby 5GB, Pro 50GB (expandable to 250GB)
- Pricing: $0.15/GB/month

**SQLite on Railway IS possible** with volumes. The volume persists across deploys.

**Permission gotcha**: Non-root Docker images need `RAILWAY_RUN_UID=0` environment variable, or adjust your Dockerfile to use root for volume access.

### 4.4 Pricing

| Plan | Monthly Fee | Included Usage | Volume Storage |
|------|-------------|---------------|----------------|
| Trial | $0 | $5 one-time credit | 0.5 GB |
| Free | $0 | $1/month credit | 0.5 GB |
| Hobby | $5/mo | $5 resource usage | Up to 5 GB |
| Pro | $20/mo | $20 resource usage | Up to 50 GB |

**Resource rates:**
- RAM: $10/GB/month
- CPU: $20/vCPU/month
- Volume: $0.15/GB/month
- Egress: $0.05/GB

**Estimated cost for small Streamlit app**: ~$5-7/month on Hobby plan (256MB RAM, shared CPU, 1GB volume).

### 4.5 Custom Domains

- Railway provides `*.up.railway.app` subdomain automatically
- Custom domains: Add in Settings > Networking > Custom Domain
- SSL/TLS handled automatically by Railway
- CNAME your domain to the Railway-provided target

### 4.6 Health Checks

Configure in service settings:
- **Path**: `/_stcore/health`
- **Protocol**: HTTP
- **Timeout**: 10s
- **Interval**: 30s

Railway uses health checks for zero-downtime deploys (when not using volumes).

### 4.7 Nixpacks vs Dockerfile

| Aspect | Nixpacks/Railpack | Dockerfile |
|--------|-------------------|------------|
| Image size | 800MB-1.3GB | 76-200MB (optimized) |
| Build speed | Slower | Faster with layer caching |
| Control | Limited | Full control |
| Complexity | Zero config | Must write Dockerfile |
| **Recommendation** | Quick prototypes | **Production** |

**Important**: Nixpacks is deprecated. Railway now defaults to **Railpack** for new services. For production, use a custom Dockerfile for smaller images and more control.

### 4.8 Alternatives if Railway Doesn't Suit

If volume limitations are a concern:
- Fly.io (more mature volume support)
- DigitalOcean App Platform + managed DB
- Self-hosted on a VPS (full control)
- Use PostgreSQL addon instead of SQLite

---

## 5. Fly.io Deployment

### 5.1 Step-by-Step Deployment

1. **Install flyctl**: `curl -L https://fly.io/install.sh | sh`
2. **Sign up/Login**: `fly auth signup` or `fly auth login`
3. **Create app directory** with your Streamlit app, requirements.txt, Dockerfile
4. **Create `.streamlit/config.toml`**:
   ```toml
   [server]
   headless = true
   ```
5. **Launch**: `fly launch` (auto-detects Dockerfile, generates fly.toml)
6. **Create volume**: `fly volumes create app_data --region iad --size 1`
7. **Configure fly.toml** with volume mount
8. **Set secrets**: `fly secrets set API_KEY=xxx`
9. **Deploy**: `fly deploy`

### 5.2 fly.toml Configuration

```toml
app = "my-streamlit-app"
primary_region = "iad"    # US East (Ashburn, VA)

[build]
  dockerfile = "Dockerfile"

[env]
  PORT = "8501"
  DATABASE_PATH = "/data/app.db"

[mounts]
  source = "app_data"
  destination = "/data"

[http_service]
  internal_port = 8501
  force_https = true
  auto_stop_machines = "stop"       # Stop when idle (saves money)
  auto_start_machines = true        # Start on request
  min_machines_running = 0          # Allow scaling to zero
  processes = ["app"]

  [http_service.concurrency]
    type = "connections"
    hard_limit = 25
    soft_limit = 20

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  path = "/_stcore/health"
  timeout = "5s"

[processes]
  app = "streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true"
```

### 5.3 Volumes for SQLite Persistence

```bash
# Create a volume (1GB, in US East)
fly volumes create app_data --region iad --size 1

# List volumes
fly volumes list

# Extend volume size
fly volumes extend vol_xxxx --size 5
```

**Key facts about Fly.io volumes:**
- Volumes are bound to a specific region and host
- Snapshots taken daily, kept for 5 days
- Snapshot pricing: $0.08/GB/month (first 10GB free)
- Volume pricing: $0.15/GB/month
- Only ONE machine can mount a volume at a time
- Volumes survive deployments and machine restarts

### 5.4 Pricing

| Resource | Cost |
|----------|------|
| Shared CPU-1x, 256MB | ~$2.02/month |
| Shared CPU-1x, 512MB | ~$4.04/month |
| Volume storage | $0.15/GB/month |
| Volume snapshots | $0.08/GB/month (10GB free) |
| Dedicated IPv4 | $2/month |
| Shared IPv4 | Free (1 per app) |
| Egress (NA/EU) | $0.02/GB |
| SSL cert (first 10) | Free |

**Estimated cost for small Streamlit app**: ~$3-5/month (shared-cpu-1x 256MB + 1GB volume).

**No free tier for new customers** (since 2024). Free trial: 2 VM hours or 7 days.

### 5.5 Custom Domains

```bash
fly certs create myapp.example.com
```
- Add a CNAME record pointing to your app's `.fly.dev` hostname
- SSL/TLS provisioned automatically via Let's Encrypt
- Both `*.fly.dev` subdomain and custom domains supported

### 5.6 Health Checks

Configured in `fly.toml` (see section 5.2 above). Fly.io supports:
- HTTP health checks (recommended for Streamlit)
- TCP health checks
- Script-based health checks

### 5.7 Handling Container Restarts with SQLite

Fly.io may restart your machine for:
- Deployments
- Host maintenance
- Auto-stop/start (if configured)
- Crashes

**SQLite handles this well** because:
- WAL mode ensures crash recovery
- Volume data persists across restarts
- `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` provides good durability

**Add to entrypoint**: Run `PRAGMA integrity_check` on startup in development to verify DB health.

### 5.8 Regions and Latency

Choose the region closest to your users:
- `iad` - Ashburn, VA (US East)
- `ord` - Chicago (US Central)
- `sjc` - San Jose (US West)
- `lhr` - London
- `ams` - Amsterdam
- `nrt` - Tokyo

**For SQLite**: You can only run in ONE region (single volume limitation). Choose wisely.

---

## 6. Production Streamlit Configuration

### 6.1 Complete Production config.toml

```toml
[server]
headless = true
port = 8501
address = "0.0.0.0"
enableCORS = true
enableXsrfProtection = true
maxUploadSize = 50              # MB - adjust as needed
maxMessageSize = 200            # MB
fileWatcherType = "none"        # Disable file watching in production
runOnSave = false
enableWebsocketCompression = true
baseUrlPath = ""                # Set if behind reverse proxy at subpath

[browser]
gatherUsageStats = false        # Disable telemetry
serverAddress = "0.0.0.0"

[logger]
level = "info"                  # "error", "warning", "info", "debug"
messageFormat = "%(asctime)s %(levelname)s %(name)s: %(message)s"

[client]
showErrorDetails = "none"       # Hide error details from users in production
toolbarMode = "minimal"         # "auto", "developer", "viewer", "minimal"

[runner]
fastReruns = true
magicEnabled = false            # Disable magic for explicit code

[theme]
base = "light"                  # or "dark"
# primaryColor = "#FF4B4B"
# backgroundColor = "#FFFFFF"
# secondaryBackgroundColor = "#F0F2F6"
# textColor = "#262730"
# font = "sans serif"
```

### 6.2 Authentication Options

#### Option A: Streamlit Native Auth (st.login) -- Since v1.42.0

```python
import streamlit as st

# Requires secrets.toml or env vars for OIDC config
st.login()  # Redirects to OIDC provider (Google, Microsoft, etc.)

if st.session_state.get("authenticated"):
    st.write(f"Welcome, {st.experimental_user.email}")
    # Your app code here
else:
    st.stop()
```

Requires in `.streamlit/secrets.toml`:
```toml
[auth]
redirect_uri = "https://myapp.example.com/oauth2callback"
cookie_secret = "random-32-char-string"

[auth.google]
client_id = "xxx.apps.googleusercontent.com"
client_secret = "xxx"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

#### Option B: streamlit-authenticator Library

```python
import streamlit_authenticator as stauth

authenticator = stauth.Authenticate(
    credentials,       # dict or YAML with usernames/hashed passwords
    "cookie_name",
    "cookie_key",
    cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login("Login", "main")

if authentication_status:
    authenticator.logout("Logout", "sidebar")
    st.write(f"Welcome *{name}*")
    # App code here
elif authentication_status is False:
    st.error("Username/password is incorrect")
elif authentication_status is None:
    st.warning("Please enter your credentials")
```

#### Option C: Reverse Proxy Basic Auth

```nginx
# Nginx basic auth in front of Streamlit
location / {
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://streamlit:8501;
    # ... WebSocket headers ...
}
```

**Recommendation**: For internal tools, `streamlit-authenticator` is simplest. For enterprise/SSO, use `st.login()` with OIDC.

### 6.3 HTTPS

**Railway and Fly.io handle TLS automatically.** No configuration needed.

For self-hosted:

**Caddy (simplest -- auto-HTTPS)**:
```
myapp.example.com {
    reverse_proxy streamlit:8501
}
```

**Nginx + Let's Encrypt (via Certbot)**:
```nginx
server {
    listen 443 ssl;
    server_name myapp.example.com;
    ssl_certificate /etc/letsencrypt/live/myapp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.example.com/privkey.pem;

    location / {
        proxy_pass http://streamlit:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.4 Rate Limiting

Streamlit has no built-in rate limiting. Implement via:

**Nginx**:
```nginx
limit_req_zone $binary_remote_addr zone=streamlit:10m rate=10r/s;

location / {
    limit_req zone=streamlit burst=20 nodelay;
    proxy_pass http://streamlit:8501;
}
```

**Application-level** (Python):
```python
import time
from collections import defaultdict

rate_limiter = defaultdict(list)

def check_rate_limit(user_id, max_requests=60, window=60):
    now = time.time()
    rate_limiter[user_id] = [t for t in rate_limiter[user_id] if now - t < window]
    if len(rate_limiter[user_id]) >= max_requests:
        return False
    rate_limiter[user_id].append(now)
    return True
```

### 6.5 Logging and Monitoring

**Structured logging setup:**

```python
import logging
import streamlit as st
from pythonjsonlogger import jsonlogger

@st.cache_resource
def get_logger():
    logger = logging.getLogger("streamlit_app")
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = get_logger()
logger.info("App started", extra={"user": "anonymous", "page": "home"})
```

**Key**: Use `@st.cache_resource` to prevent duplicate loggers (Streamlit re-executes the entire script on each interaction).

**Monitoring options:**
- Docker health checks (built-in)
- Prometheus + Grafana (for metrics)
- Loki (for log aggregation)
- OpenTelemetry (traces, metrics, logs)
- Platform-native: Railway/Fly.io both provide log viewing in their dashboards

---

## 7. Docker Compose: Dev vs Production

### 7.1 Development docker-compose.yml

```yaml
# docker-compose.dev.yml
version: "3.9"

services:
  streamlit:
    build:
      context: .
      dockerfile: Dockerfile.dev
    ports:
      - "8501:8501"
    volumes:
      - .:/app                          # Hot reload - mount source code
      - ./data:/app/data                # SQLite persistence
      - ./.streamlit:/app/.streamlit    # Config overrides
    env_file:
      - .env                            # Local secrets
    environment:
      - STREAMLIT_SERVER_FILE_WATCHER_TYPE=poll
      - STREAMLIT_SERVER_RUN_ON_SAVE=true
    restart: unless-stopped
```

```dockerfile
# Dockerfile.dev
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Don't COPY source -- it's mounted as a volume
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

### 7.2 Production docker-compose.yml

```yaml
# docker-compose.prod.yml
version: "3.9"

services:
  streamlit:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8501:8501"
    volumes:
      - streamlit-data:/app/data       # Named volume for SQLite
    environment:
      - DATABASE_PATH=/app/data/app.db
      - STREAMLIT_SERVER_FILE_WATCHER_TYPE=none
      # Secrets injected via env vars (not .env file in production)
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
        reservations:
          memory: 256M
          cpus: "0.25"
    restart: always
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      start_period: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  streamlit-data:
    driver: local
```

### 7.3 SQLite File Handling

```python
import os
import sqlite3

# Works in both dev and prod
DB_PATH = os.environ.get("DATABASE_PATH", "./data/app.db")

# Ensure directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

---

## 8. Reverse Proxy Configuration

### 8.1 Why Use a Reverse Proxy?

- **WebSocket support**: Streamlit requires WebSocket; proxy must handle upgrade headers
- **HTTPS/TLS termination**: Offload SSL from Streamlit
- **Caching**: Static assets, compression
- **Rate limiting**: Protect from abuse
- **Custom headers**: CSP, HSTS, etc.
- **Multiple apps**: Route to different Streamlit apps by path

**Note**: Railway and Fly.io handle all of this automatically. A reverse proxy is only needed for self-hosted deployments.

### 8.2 Nginx Configuration (Complete)

```nginx
upstream streamlit {
    server streamlit:8501;
}

map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name myapp.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name myapp.example.com;

    ssl_certificate /etc/letsencrypt/live/myapp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.example.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:;";

    # Streamlit proxy
    location / {
        proxy_pass http://streamlit;
        proxy_http_version 1.1;

        # WebSocket support (CRITICAL for Streamlit)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts (important for long-running Streamlit operations)
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;

        # Buffering
        proxy_buffering off;
    }

    # Health check endpoint (for monitoring tools)
    location /_stcore/health {
        proxy_pass http://streamlit/_stcore/health;
    }
}
```

### 8.3 Caddy Configuration (Simpler)

```
# Caddyfile
myapp.example.com {
    reverse_proxy streamlit:8501

    # Security headers
    header {
        X-Frame-Options DENY
        X-Content-Type-Options nosniff
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
}
```

**Caddy advantages over Nginx for Streamlit:**
- WebSocket support works automatically (no `map` directive needed)
- Auto-HTTPS with Let's Encrypt (zero configuration)
- Simpler config syntax
- Automatic HTTP -> HTTPS redirect
- Automatic certificate renewal

**Recommendation**: Use Caddy for self-hosted Streamlit. It is dramatically simpler.

### 8.4 WebSocket Considerations

Streamlit uses WebSocket for its `/_stcore/stream` endpoint. Without proper WebSocket handling:
- The app will load but show "Please wait..." forever
- Widgets won't respond
- The connection status indicator will show "Connecting..."

**Critical headers** (Nginx):
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

**Critical timeouts**: Set `proxy_read_timeout` and `proxy_send_timeout` to high values (86400 = 24 hours) to prevent WebSocket disconnections during long idle periods.

---

## 9. CI/CD Pipelines

### 9.1 GitHub Actions: Build and Deploy

#### Deploy to Fly.io

```yaml
# .github/workflows/deploy-fly.yml
name: Deploy to Fly.io

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    concurrency: deploy-group
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

**Setup**: Create deploy token with `fly tokens create deploy -x 999999h` and add as GitHub secret `FLY_API_TOKEN`.

#### Deploy to Railway

```yaml
# .github/workflows/deploy-railway.yml
name: Deploy to Railway

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: bervProject/railway-deploy@main
        with:
          railway_token: ${{ secrets.RAILWAY_TOKEN }}
          service: ${{ secrets.RAILWAY_SERVICE_ID }}
```

**Alternative Railway deploy** (using CLI directly):
```yaml
  deploy:
    needs: test
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/railwayapp/cli:latest
    steps:
      - uses: actions/checkout@v4
      - run: railway up --service ${{ secrets.RAILWAY_SERVICE_ID }}
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

### 9.2 Testing Before Deployment

```yaml
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - run: pip install -r requirements.txt
      - run: pip install pytest ruff
      - name: Lint
        run: ruff check .
      - name: Type check (optional)
        run: |
          pip install mypy
          mypy app.py --ignore-missing-imports
      - name: Unit tests
        run: python -m pytest tests/ -v --tb=short
      - name: Smoke test (verify Streamlit imports)
        run: python -c "import streamlit; print(f'Streamlit {streamlit.__version__} OK')"
```

### 9.3 Zero-Downtime Deploys

- **Railway**: Supports zero-downtime deploys with health checks, BUT NOT when using volumes (volume services experience brief downtime during redeploy)
- **Fly.io**: Uses rolling deployments by default. New machine starts, health check passes, old machine stops. With volumes, only one machine can mount at a time, so there's brief downtime during switchover.

**Mitigation**: Set generous health check `start_period` / `grace_period` to allow the new container time to initialize.

### 9.4 Container Registry Options

| Registry | Free Tier | Notes |
|----------|-----------|-------|
| GitHub Container Registry (ghcr.io) | Unlimited public, 500MB private | Best for GitHub-hosted projects |
| Docker Hub | 1 private repo, unlimited public | Most widely known |
| Railway | Built-in (no registry needed) | Builds from source |
| Fly.io | Built-in (no registry needed) | Builds from Dockerfile |

**Note**: Railway and Fly.io build from your source code/Dockerfile directly -- no container registry needed unless you want pre-built images.

---

## 10. Alternative: DigitalOcean App Platform

### 10.1 Comparison to Railway/Fly.io

| Feature | DigitalOcean App Platform | Railway | Fly.io |
|---------|--------------------------|---------|--------|
| Ease of deploy | Easy (GitHub integration) | Easiest | Moderate (CLI-focused) |
| Pricing model | Fixed tier | Usage-based | Usage-based |
| Persistent storage | Volumes (separate product) | Built-in volumes | Built-in volumes |
| Multi-region | No | No | Yes (edge network) |
| Custom domains | Yes (auto-SSL) | Yes (auto-SSL) | Yes (auto-SSL) |
| Scale to zero | No | Yes (Pro plan) | Yes |
| Free tier | Static sites only | $1/month credit | No (trial only) |
| Maturity | Mature | Newer | Mature |

### 10.2 Pricing

| Component | Cost |
|-----------|------|
| Basic (1 vCPU, 512MB) | $5/month |
| Basic (1 vCPU, 1GB) | $10/month |
| Professional (1 vCPU, 1GB) | $12/month |
| Volume storage | $0.10/GiB/month |
| Bandwidth | Included (varies by tier) |

### 10.3 Persistent Storage

**App Platform does NOT natively support persistent volumes.** For SQLite persistence, you would need to:
1. Use a DigitalOcean Droplet instead (VPS with full control)
2. Use DigitalOcean Managed Database (PostgreSQL) instead of SQLite
3. Use Spaces (S3-compatible object storage) for file-based backups

**Verdict**: DigitalOcean App Platform is NOT ideal for SQLite-based apps. Use a Droplet or switch to PostgreSQL.

### 10.4 Ease of Deployment

1. Connect GitHub repo
2. Select "Python" or "Dockerfile" as build type
3. Configure start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
4. Set environment variables
5. Deploy

Auto-deploys on push to main branch. Simple but less flexible than Railway/Fly.io.

---

## 11. Platform Comparison Matrix

| Criteria | Railway | Fly.io | DigitalOcean App |
|----------|---------|--------|-----------------|
| **SQLite + Volume** | Yes (volumes) | Yes (volumes) | No (use Droplet) |
| **Volume pricing** | $0.15/GB/mo | $0.15/GB/mo | $0.10/GB/mo (Droplet) |
| **Min monthly cost** | ~$5 (Hobby) | ~$3 (shared) | ~$5 (Basic) |
| **Auto-SSL** | Yes | Yes | Yes |
| **Scale to zero** | Yes | Yes | No |
| **Custom domains** | Yes | Yes | Yes |
| **GitHub CI/CD** | Built-in + Actions | Actions | Built-in |
| **CLI** | Good | Excellent | Basic |
| **Dashboard** | Excellent | Good | Good |
| **Volume downtime** | Yes (redeploy) | Brief | N/A |
| **Multi-region** | No | Yes | No |
| **Best for** | Quick deploy, MVP | Performance, global | Stability, enterprise |

---

## 12. Recommended Architecture

### For Internal Tool / MVP (Our Use Case)

```
                    +------------------+
                    |   Railway.com    |
                    |   (or Fly.io)    |
                    +------------------+
                           |
                    +------+------+
                    |  Container  |
                    |  Streamlit  |
                    |  Port 8501  |
                    +------+------+
                           |
                    +------+------+
                    |   Volume    |
                    |  /app/data  |
                    |  SQLite DB  |
                    +-------------+
```

**Recommended stack:**
- **Platform**: Railway (simplest) or Fly.io (cheapest, more control)
- **Base image**: `python:3.11-slim`
- **Database**: SQLite with WAL mode on persistent volume at `/app/data`
- **Secrets**: Platform environment variables (Railway dashboard / `fly secrets set`)
- **Auth**: `streamlit-authenticator` for simple password auth, or `st.login()` for SSO
- **CI/CD**: GitHub Actions with automatic deploy on push to main
- **Backups**: Daily SQLite `.backup` command via entrypoint cron or Litestream
- **Monitoring**: Platform dashboard logs + structured JSON logging
- **HTTPS**: Handled automatically by platform

### Production Dockerfile (Final)

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Streamlit config
RUN mkdir -p /app/.streamlit
COPY .streamlit/config.toml /app/.streamlit/config.toml

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Use PORT env var for cloud platforms, default 8501
CMD streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true
```

### Production config.toml (Final)

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

[logger]
level = "info"

[client]
showErrorDetails = "none"
toolbarMode = "minimal"

[runner]
fastReruns = true
magicEnabled = false
```

---

## Sources

### Official Documentation
- [Streamlit Docker Deployment Guide](https://docs.streamlit.io/deploy/tutorials/docker)
- [Streamlit config.toml Reference](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
- [Railway Volumes Documentation](https://docs.railway.com/reference/volumes)
- [Railway Pricing Plans](https://docs.railway.com/reference/pricing/plans)
- [Fly.io Streamlit Guide](https://fly.io/docs/python/frameworks/streamlit/)
- [Fly.io Pricing](https://fly.io/docs/about/pricing/)
- [Fly.io GitHub Actions Deployment](https://fly.io/docs/launch/continuous-deployment-with-github-actions/)
- [Docker Secrets Documentation](https://docs.docker.com/engine/swarm/secrets/)

### Community & Guides
- [How to Run SQLite in Docker (2026)](https://oneuptime.com/blog/post/2026-02-08-how-to-run-sqlite-in-docker-when-and-how/view)
- [Railway Persistent Volume Issues](https://station.railway.com/questions/persistent-volume-not-persisting-data-ac-fd543a6e)
- [Deploying Streamlit with Nginx Reverse Proxy](https://medium.com/@amancodes/deploying-streamlit-apps-with-nginx-reverse-proxy-on-custom-url-paths-2e0fdcaa2ac2)
- [Streamlit Health Check Issues](https://github.com/streamlit/streamlit/issues/7076)
- [Caddy Reverse Proxy for Streamlit](https://discuss.streamlit.io/t/streamlit-reverse-proxy-problem-caddy-webserver/47396)
- [Railway Nixpacks vs Dockerfile](https://blog.railway.com/p/comparing-deployment-methods-in-railway)
- [Railway Moving from Nix to Railpack](https://blog.railway.com/p/introducing-railpack)
- [Fly.io Deploying with SQLite Volumes](https://community.fly.io/t/deploying-machines-with-sqlite-db-on-a-volume/12774)
- [Docker Secrets Best Practices (GitGuardian)](https://blog.gitguardian.com/how-to-handle-secrets-in-docker/)
- [SQLite WAL Mode in Docker Forum](https://sqlite.org/forum/info/87824f1ed837cdbb)
- [Production Logging in Streamlit (2026)](https://medium.com/data-science-short-pieces/production-grade-logging-in-streamlit-b0ebefbfefac)
- [Streamlit Hiding Menu/Footer](https://discuss.streamlit.io/t/how-do-i-hide-remove-the-menu-in-production/362)
- [DigitalOcean App Platform Pricing](https://www.digitalocean.com/pricing/app-platform)
- [Platform Comparison Guide (Railway)](https://blog.railway.com/p/paas-comparison-guide)
- [Fly.io vs Railway Comparison](https://docs.railway.com/platform/compare-to-fly)
- [GitHub Actions with Railway](https://blog.railway.com/p/github-actions)
- [Automated SQLite Backups in Docker](https://tech.oeru.org/automatic-versioned-backups-sqlite-docker-compose-container)
- [Litestream Cron-Based Backup Alternative](https://litestream.io/alternatives/cron/)
