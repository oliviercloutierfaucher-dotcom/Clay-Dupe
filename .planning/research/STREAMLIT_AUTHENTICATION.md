# Streamlit Authentication — Deep Research

> Research date: 2026-03-08
> Status: Complete
> Priority: #1 critical blocker from production readiness audit

---

## Table of Contents

1. [Streamlit Native Authentication (st.login)](#1-streamlit-native-authentication)
2. [streamlit-authenticator Library](#2-streamlit-authenticator-library)
3. [Simple Password Gate (st.secrets)](#3-simple-password-gate)
4. [OAuth/OIDC Integration](#4-oauthoidc-integration)
5. [Reverse Proxy Authentication](#5-reverse-proxy-authentication)
6. [Zero-Trust Network Access](#6-zero-trust-network-access)
7. [Comparison Matrix](#7-comparison-matrix)
8. [Recommendation for Clay-Dupe v2.0](#8-recommendation)
9. [Implementation Plan](#9-implementation-plan)

---

## 1. Streamlit Native Authentication

### Overview

Streamlit 1.42.0 (February 2025) introduced built-in authentication via OpenID Connect (OIDC). This was one of the most requested features in Streamlit's history.

### Key APIs

| API | Purpose | Added |
|-----|---------|-------|
| `st.login()` | Redirect user to OIDC provider | v1.42.0 |
| `st.logout()` | Remove identity cookie, start new session | v1.42.0 |
| `st.user` | Dict-like object with user info | v1.42.0 (GA) |
| `st.user.is_logged_in` | Check login status | v1.42.0 |

### How It Works

1. User visits app -> `st.user.is_logged_in` is `False`
2. User clicks login button -> `st.login()` redirects to OIDC provider
3. User authenticates with provider (Google, Microsoft, etc.)
4. Provider redirects back to app at `/oauth2callback`
5. Streamlit stores an identity cookie (30-day expiry, non-configurable)
6. `st.user` now contains user info (name, email, etc.)

### Configuration (secrets.toml)

**Single provider:**

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "a-strong-random-secret-string"
client_id = "your-client-id-from-provider"
client_secret = "your-client-secret-from-provider"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

**Multiple providers:**

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "a-strong-random-secret-string"

[auth.google]
client_id = "xxx"
client_secret = "xxx"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[auth.microsoft]
client_id = "xxx"
client_secret = "xxx"
server_metadata_url = "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
```

### Code Example

```python
import streamlit as st

def login_screen():
    st.header("This app is private.")
    st.subheader("Please log in.")
    st.button("Log in with Google", on_click=st.login)

if not st.user.is_logged_in:
    login_screen()
    st.stop()

st.button("Log out", on_click=st.logout)
st.markdown(f"Welcome! {st.user.name}")
```

### Cookie & Session Behavior

- Identity cookie expires after **30 days** (not configurable)
- Opening new tab in same browser auto-authenticates (same cookie)
- `st.logout()` removes cookie from current session only; other active sessions remain
- Streamlit does NOT modify cookies set by the identity provider itself
- Streamlit automatically enables CORS and XSRF protection when auth is configured

### Limitations

- **OIDC only** — no username/password login, no local user database
- **No role-based access** — just authenticated vs. not; no admin/user distinction
- **No user management** — can't add/remove users from within Streamlit
- **No authorization** — only authentication (who are you), not authorization (what can you do)
- **30-day cookie** — not configurable
- **Requires external OIDC provider** — Google, Microsoft, Okta, Auth0 etc.
- **Requires Authlib>=1.3.2** — additional dependency
- **No email allow-list** — anyone with a valid Google/Microsoft account can log in (you control this at the provider level, e.g., Google test users, Azure AD tenant restrictions)

### Verdict for Clay-Dupe

**Not ideal as sole solution.** Requires setting up an external OIDC provider (Google Cloud Console, Azure AD, etc.) which is overkill for a 3-person internal tool. No role-based access. However, it's excellent if the team already has Google Workspace or Microsoft 365.

---

## 2. streamlit-authenticator Library

### Overview

The most popular third-party authentication library for Streamlit. Provides username/password login with bcrypt hashing, cookie-based sessions, role support, and user management widgets.

- **Package:** `streamlit-authenticator`
- **Latest version:** 0.4.2 (March 2025)
- **License:** MIT
- **PyPI:** https://pypi.org/project/streamlit-authenticator/

### Installation

```bash
pip install streamlit-authenticator
```

Dependencies: `bcrypt`, `PyYAML`, `streamlit`

### YAML Configuration File (config.yaml)

```yaml
cookie:
  expiry_days: 30
  key: "a-random-signature-key"    # Signs the cookie — keep secret
  name: "clay_dupe_auth"           # Cookie name in browser

credentials:
  usernames:
    odelaneau:
      email: olivier@company.com
      first_name: Olivier
      last_name: Faucher
      password: "$2b$12$..."       # bcrypt hash (auto-hashed if plain text)
      roles:
        - admin
    sales_user1:
      email: user1@company.com
      first_name: Sales
      last_name: User
      password: "$2b$12$..."
      roles:
        - user
    sales_user2:
      email: user2@company.com
      first_name: Sales
      last_name: User2
      password: "$2b$12$..."
      roles:
        - user

preauthorized:
  emails: []                       # Emails allowed to self-register (optional)
```

### Password Hashing

**Automatic hashing (default):** Plain-text passwords in YAML are automatically hashed on first login when `auto_hash=True` (default). The YAML file is updated in-place.

**Pre-hashing passwords (recommended for production):**

```python
import streamlit_authenticator as stauth

# Hash a single password
hashed = stauth.Hasher.hash("my_secure_password")
print(hashed)  # $2b$12$...

# Hash all passwords in a credentials dict
import yaml
with open('config.yaml') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

stauth.Hasher.hash_passwords(config['credentials'])

with open('config.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False)
```

### Complete Application Code

```python
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# Load config
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Create authenticator
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Render login widget
try:
    authenticator.login()
except Exception as e:
    st.error(e)

# Check authentication status
if st.session_state.get('authentication_status'):
    # AUTHENTICATED — show app content
    authenticator.logout()
    st.write(f'Welcome *{st.session_state.get("name")}*')
    st.write(f'Roles: {st.session_state.get("roles")}')

    # Role-based access
    if 'admin' in st.session_state.get('roles', []):
        st.write("Admin panel here...")

    # ... rest of your app ...

elif st.session_state.get('authentication_status') is False:
    st.error('Username/password is incorrect')

elif st.session_state.get('authentication_status') is None:
    st.warning('Please enter your username and password')
```

### Session State Keys

After login, these keys are available in `st.session_state`:

| Key | Value |
|-----|-------|
| `authentication_status` | `True`, `False`, or `None` |
| `name` | User's full name |
| `username` | Login username |
| `roles` | List of roles (e.g., `['admin']`) |

### Cookie Behavior

- Cookie name and key are set in YAML config
- `expiry_days` controls how long the cookie persists (default: 30)
- Set `expiry_days: 0` to disable cookie-based re-authentication (session only)
- Cookie is encrypted/signed with the `key` value
- Re-authentication happens automatically if a valid cookie exists

### Additional Widgets

**Reset Password (for logged-in users):**

```python
if st.session_state.get('authentication_status'):
    try:
        if authenticator.reset_password(st.session_state.get('username')):
            st.success('Password modified successfully')
    except Exception as e:
        st.error(e)
```

**Register User:**

```python
try:
    email, username, name = authenticator.register_user()
    if email:
        st.success('User registered successfully')
except Exception as e:
    st.error(e)
```

**Forgot Password:**

```python
try:
    username, email, new_password = authenticator.forgot_password()
    if username:
        st.success(f'New password sent to {email}')
except Exception as e:
    st.error(e)
```

### Protecting Individual Pages (Multi-Page App)

For Streamlit's `st.navigation()` multi-page apps, add the auth check to the main `app.py` before rendering any page:

```python
# In app.py (entry point)
authenticator.login()

if not st.session_state.get('authentication_status'):
    st.stop()  # Block all pages until authenticated

# Only reached if authenticated
page = st.navigation([...])
page.run()
```

For page-level role checks:

```python
# In a specific page file
import streamlit as st

if 'admin' not in st.session_state.get('roles', []):
    st.error("You don't have access to this page")
    st.stop()

# Admin-only content below
```

### Known Issues & Limitations

1. **Compatibility issues with Streamlit >= 1.37** — multipage routing can conflict
2. **Login sometimes requires two clicks** — known issue #184
3. **YAML file must be writable** — auto-hash and register-user update the file on disk
4. **No built-in email sending** — forgot_password returns the new password, you must email it yourself (or use their API key for email-based features)
5. **Cookie key must be kept secret** — if leaked, sessions can be forged
6. **v0.4.2 API key requirement** — optional API key for email-based features (password reset, 2FA) via streamlitauthenticator.com
7. **No CSRF protection** — relies on Streamlit's own XSRF token

### Verdict for Clay-Dupe

**Best fit for our use case.** Simple username/password, role-based access (admin vs user), no external provider needed, works in Docker, YAML-based user management is perfect for 3 users. Cookie persistence means users stay logged in.

---

## 3. Simple Password Gate (st.secrets)

### Overview

The simplest possible authentication: a single shared password stored in `secrets.toml`. No user management, no roles, just "do you know the password?"

### Implementation

**.streamlit/secrets.toml:**

```toml
[auth]
password = "your-secure-password-here"
```

**app.py:**

```python
import streamlit as st

def check_password():
    """Returns True if the user has entered the correct password."""
    if st.session_state.get("authenticated"):
        return True

    password = st.text_input("Password", type="password")
    if st.button("Log in"):
        if password == st.secrets["auth"]["password"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False

if not check_password():
    st.stop()

# App content below
st.title("Welcome to Clay-Dupe")
```

### Per-User Passwords Variant

**.streamlit/secrets.toml:**

```toml
[passwords]
olivier = "hashed_password_1"
user1 = "hashed_password_2"
user2 = "hashed_password_3"
```

### Pros

- Dead simple — ~15 lines of code
- No dependencies
- No external config files
- Works everywhere

### Cons

- **No session persistence** — refreshing the page logs you out (session state is lost)
- **No cookie support** — must re-enter password every session
- **No role-based access** — everyone gets the same access
- **Password in plain text** in secrets.toml (or you must hash manually)
- **Shared password** — can't distinguish users
- **No audit trail** — no way to know who did what
- **Not production-grade** — no brute-force protection, no lockout

### Verdict for Clay-Dupe

**Too basic for production.** Might work for a quick prototype, but the lack of session persistence and user differentiation makes it unsuitable for a production tool.

---

## 4. OAuth/OIDC Integration

### 4a. Streamlit Native OIDC (st.login)

See [Section 1](#1-streamlit-native-authentication) above.

### 4b. Google OAuth Setup (with st.login)

**Prerequisites:**
- Google Cloud account
- Streamlit >= 1.42.0
- Authlib >= 1.3.2

**Steps:**
1. Create project in Google Cloud Console
2. Go to Google Auth Platform > Branding (fill in app info)
3. Go to Audience > add test user emails
4. Go to Clients > Create Client (Web application)
5. Add authorized redirect URI: `http://localhost:8501/oauth2callback`
6. Copy Client ID and Client Secret

**secrets.toml:**
```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "$(python -c 'import secrets; print(secrets.token_hex(32))')"
client_id = "your-google-client-id.apps.googleusercontent.com"
client_secret = "your-google-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

**Limitation:** In Testing mode, only emails you manually add as test users can log in. In Published mode, anyone with a Google account can log in — you'd need to add email-based filtering in your app code.

### 4c. Microsoft Entra ID (Azure AD)

**secrets.toml:**
```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "xxx"
client_id = "xxx"
client_secret = "xxx"
server_metadata_url = "https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration"
```

Replace `{tenant-id}` with your Azure AD tenant ID. Using your organization's tenant restricts login to company accounts only.

### 4d. Third-Party OAuth Libraries

- **streamlit-oauth** — community library for OAuth2 flows outside OIDC
- **streamlit-authenticator experimental_guest_login()** — OAuth2 via Google/Microsoft built into the authenticator library

### Verdict for Clay-Dupe

**Viable if using Google Workspace or Microsoft 365.** The native `st.login()` is clean and simple, but requires setting up OAuth credentials with a cloud provider. For a 3-person team, this is more setup than needed unless you want SSO convenience.

---

## 5. Reverse Proxy Authentication

### 5a. Nginx Basic Auth (Simplest)

Place nginx in front of Streamlit with HTTP Basic Authentication.

**docker-compose.yml:**
```yaml
services:
  streamlit:
    build: .
    command: ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
    # No ports exposed — only nginx is public

  nginx:
    image: nginx:alpine
    ports:
      - "8080:8080"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
      - ./nginx/.htpasswd:/etc/nginx/.htpasswd
    depends_on:
      - streamlit
```

**nginx/nginx.conf:**
```nginx
upstream streamlit {
    server streamlit:8501;
}

server {
    listen 8080;

    auth_basic "Clay-Dupe Login";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://streamlit;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support (required for Streamlit)
    location /_stcore/stream {
        proxy_pass http://streamlit/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

**Generate .htpasswd:**
```bash
# Using htpasswd (from apache2-utils)
htpasswd -c nginx/.htpasswd olivier
# Enter password when prompted

# Add more users
htpasswd nginx/.htpasswd user1
htpasswd nginx/.htpasswd user2

# Or using Docker (no local install needed)
docker run --rm httpd:alpine htpasswd -nb olivier mypassword >> nginx/.htpasswd
```

**Pros:** Simple, battle-tested, no app changes needed, browser remembers credentials.
**Cons:** Ugly browser popup (not a form), no roles, no session management, can't customize UI.

### 5b. OAuth2 Proxy

Full OAuth2 authentication at the proxy level — zero changes to the Streamlit app.

**docker-compose.yml:**
```yaml
services:
  streamlit:
    build: .
    command: ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

  nginx:
    image: nginx:alpine
    ports:
      - "8000:8000"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - streamlit
      - oauth2-proxy

  oauth2-proxy:
    image: quay.io/oauth2-proxy/oauth2-proxy:v7.8.1
    env_file:
      - .env
```

**nginx.conf for oauth2-proxy:**
```nginx
upstream app {
    server streamlit:8501;
}

upstream oauth2 {
    server oauth2-proxy:4180;
}

server {
    listen 8000;

    location / {
        auth_request /oauth2/auth;
        error_page 401 = @error401;
        try_files $uri @proxy_to_app;
    }

    location /_stcore/stream {
        auth_request /oauth2/auth;
        error_page 401 = @error401;
        proxy_pass http://app/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    location @error401 {
        return 302 /oauth2/sign_in;
    }

    location /oauth2/ {
        try_files $uri @proxy_to_oauth2;
    }

    location @proxy_to_oauth2 {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://oauth2;
    }

    location @proxy_to_app {
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_pass http://app;
    }
}
```

**Passing user identity to Streamlit:**
```nginx
# In the proxy_to_app location, add:
proxy_set_header X-Forwarded-User $upstream_http_x_auth_request_user;
proxy_set_header X-Forwarded-Email $upstream_http_x_auth_request_email;
```

Then in Streamlit:
```python
import streamlit as st
user_email = st.context.headers.get("X-Forwarded-Email", "unknown")
```

### 5c. Caddy with Basic Auth

Caddy is simpler than nginx for basic setups.

**Caddyfile:**
```
:8080 {
    basicauth {
        olivier $2a$14$...  # bcrypt hash
        user1   $2a$14$...
    }
    reverse_proxy streamlit:8501
}
```

Generate hash: `caddy hash-password --plaintext "mypassword"`

### Verdict for Clay-Dupe

**Nginx basic auth is the fastest path to "secure enough."** It requires zero app changes, works perfectly in Docker, and the browser-native auth popup, while ugly, is functional. OAuth2 Proxy is more polished but requires an external OAuth provider.

---

## 6. Zero-Trust Network Access

### 6a. Tailscale

- Mesh VPN using WireGuard — devices connect directly peer-to-peer
- Install Tailscale on the server and on each team member's device
- Streamlit is only accessible to devices on the Tailscale network
- No port forwarding, no firewall rules needed
- Free for up to 3 users (personal plan) or 100 users on business plan
- Authentication delegated to identity provider (Google, Microsoft, GitHub, etc.)

**Docker setup:**
```yaml
services:
  streamlit:
    build: .
    network_mode: "service:tailscale"

  tailscale:
    image: tailscale/tailscale
    environment:
      - TS_AUTHKEY=tskey-auth-xxx
      - TS_HOSTNAME=clay-dupe
    volumes:
      - tailscale-data:/var/lib/tailscale
    cap_add:
      - NET_ADMIN

volumes:
  tailscale-data:
```

Access at: `http://clay-dupe:8501` (only from Tailscale network)

### 6b. Cloudflare Access / Cloudflare Tunnel

- Create outbound-only tunnel from server to Cloudflare
- No open ports, no firewall changes
- Cloudflare Access policies control who can reach the app
- Supports email-based one-time pins, Google/Microsoft SSO, IP ranges
- Free tier available for up to 50 users

### Verdict for Clay-Dupe

**Tailscale is the most secure option for our use case.** If the tool is only used by 3 people in the office/remotely, Tailscale makes Streamlit invisible to the internet entirely. Combined with app-level auth (streamlit-authenticator), this is defense in depth.

---

## 7. Comparison Matrix

| Approach | Setup Effort | User Management | Roles | Session Persist | Docker Support | Security Level | Best For |
|----------|-------------|----------------|-------|-----------------|---------------|----------------|----------|
| **st.login (native OIDC)** | Medium | Via provider | No | 30-day cookie | Yes | High | Teams with Google/MS 365 |
| **streamlit-authenticator** | Low | YAML file | Yes | Configurable cookie | Yes | Medium-High | Small teams, self-hosted |
| **st.secrets password** | Very Low | None | No | No (session only) | Yes | Low | Quick prototypes |
| **Nginx basic auth** | Low | .htpasswd file | No | Browser-managed | Yes | Medium | Quick production lock |
| **OAuth2 Proxy** | High | Via provider | Via provider | Cookie-based | Yes | High | Enterprise setups |
| **Tailscale** | Low | Tailscale admin | Via ACLs | Always on (VPN) | Yes | Very High | Self-hosted internal tools |
| **Cloudflare Access** | Medium | CF dashboard | Via policies | Cookie-based | Yes | Very High | Internet-facing apps |

---

## 8. Recommendation for Clay-Dupe v2.0

### Context
- 3-person internal sales team
- Self-hosted in Docker
- Need: simple login, no self-registration needed
- Nice-to-have: admin vs user roles
- Must work behind reverse proxy and in Docker

### Recommended Approach: Layered Defense

**Layer 1 (Network): Tailscale or Nginx basic auth**
- If the tool should NEVER be on the public internet: use Tailscale (VPN)
- If it needs to be on a company network without VPN: use nginx as reverse proxy (even without auth, it hides Streamlit's default port)

**Layer 2 (Application): streamlit-authenticator**
- Username/password login with bcrypt hashing
- Admin vs user roles in YAML config
- Cookie-based session persistence (configurable expiry)
- No external provider dependencies
- 3 users = just edit a YAML file, no database needed

### Why NOT the Alternatives

| Approach | Why Not |
|----------|---------|
| st.login (OIDC) | Requires external OAuth provider setup; overkill for 3 internal users; no role support |
| st.secrets password gate | No session persistence; no roles; no user differentiation |
| OAuth2 Proxy | Too complex for 3 users; requires external OAuth provider |
| Cloudflare Access | Requires Cloudflare account and DNS routing; overkill |

### Implementation Priority

1. **Phase 1 (Must-have):** streamlit-authenticator in app.py — blocks ALL pages behind login
2. **Phase 2 (Should-have):** Role-based page visibility (admin sees settings/config, user sees enrich/export)
3. **Phase 3 (Nice-to-have):** Tailscale for network-level isolation
4. **Phase 4 (Future):** Audit logging of who ran which enrichment

---

## 9. Implementation Plan

### File Changes Required

**New files:**
- `config/auth.yaml` — user credentials and cookie config
- `scripts/hash_password.py` — CLI helper to hash passwords

**Modified files:**
- `ui/app.py` — add authentication gate before `st.navigation()`
- `requirements.txt` — add `streamlit-authenticator>=0.4.2`
- `Dockerfile` — ensure config/auth.yaml is included
- `docker-compose.yml` — mount auth.yaml as volume (for easy user changes)

### config/auth.yaml

```yaml
cookie:
  expiry_days: 7          # Re-authenticate weekly
  key: "CHANGE_ME_TO_RANDOM_STRING"
  name: "clay_dupe_auth"

credentials:
  usernames:
    admin:
      email: admin@company.com
      first_name: Admin
      last_name: User
      password: "$2b$12$..."   # pre-hashed with bcrypt
      roles:
        - admin
    sales1:
      email: sales1@company.com
      first_name: Sales
      last_name: User1
      password: "$2b$12$..."
      roles:
        - user
    sales2:
      email: sales2@company.com
      first_name: Sales
      last_name: User2
      password: "$2b$12$..."
      roles:
        - user
```

### scripts/hash_password.py

```python
"""CLI tool to hash passwords for auth.yaml."""
import sys
import streamlit_authenticator as stauth

if len(sys.argv) < 2:
    print("Usage: python scripts/hash_password.py <password>")
    sys.exit(1)

password = sys.argv[1]
hashed = stauth.Hasher.hash(password)
print(f"Hashed password: {hashed}")
print("Copy this into config/auth.yaml under the user's password field.")
```

### ui/app.py Changes (Conceptual)

```python
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from pathlib import Path

# --- Authentication ---
AUTH_CONFIG_PATH = Path(__file__).parent.parent / "config" / "auth.yaml"

@st.cache_resource
def load_auth_config():
    with open(AUTH_CONFIG_PATH) as f:
        return yaml.load(f, Loader=SafeLoader)

auth_config = load_auth_config()

authenticator = stauth.Authenticate(
    auth_config['credentials'],
    auth_config['cookie']['name'],
    auth_config['cookie']['key'],
    auth_config['cookie']['expiry_days'],
    auto_hash=False,  # We pre-hash passwords
)

try:
    authenticator.login()
except Exception as e:
    st.error(e)

if not st.session_state.get('authentication_status'):
    if st.session_state.get('authentication_status') is False:
        st.error('Username/password is incorrect')
    st.stop()

# --- Authenticated content below ---
authenticator.logout(location='sidebar')
st.sidebar.write(f"Logged in as: **{st.session_state.get('name')}**")

# Role-based page filtering
user_roles = st.session_state.get('roles', [])
is_admin = 'admin' in user_roles

pages = [
    st.Page("pages/enrich.py", title="Enrich"),
    st.Page("pages/results.py", title="Results"),
]

if is_admin:
    pages.append(st.Page("pages/settings.py", title="Settings"))

page = st.navigation(pages)
page.run()
```

### Docker Volume Mount

```yaml
# docker-compose.yml
services:
  app:
    build: .
    volumes:
      - ./config/auth.yaml:/app/config/auth.yaml
    ports:
      - "8501:8501"
```

This allows editing users without rebuilding the Docker image.

### Security Checklist

- [ ] Generate strong random `cookie.key` (min 32 chars)
- [ ] Pre-hash all passwords with bcrypt before deployment
- [ ] Add `config/auth.yaml` to `.gitignore` (contains hashed passwords + cookie key)
- [ ] Ship a `config/auth.yaml.example` with placeholder values
- [ ] Set `expiry_days` to 7 (not 30) for tighter session control
- [ ] Ensure Streamlit's XSRF protection is enabled (default)
- [ ] Do NOT expose port 8501 directly — use nginx reverse proxy
- [ ] Consider Tailscale for network isolation

---

## Sources

- [Streamlit Authentication Docs](https://docs.streamlit.io/develop/concepts/connections/authentication)
- [st.login API Reference](https://docs.streamlit.io/develop/api-reference/user/st.login)
- [Streamlit Google OAuth Tutorial](https://docs.streamlit.io/develop/tutorials/authentication/google)
- [Streamlit Microsoft Entra Tutorial](https://docs.streamlit.io/develop/tutorials/authentication/microsoft)
- [Streamlit 2025 Release Notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2025)
- [streamlit-authenticator GitHub](https://github.com/mkhorasani/Streamlit-Authenticator)
- [streamlit-authenticator PyPI](https://pypi.org/project/streamlit-authenticator/)
- [streamlit-authenticator ReadTheDocs](https://streamlit-authenticator.readthedocs.io/en/latest/)
- [OAuth2-Proxy + Nginx + Streamlit](https://github.com/gonzalo123/streamlit_oauth2)
- [Nginx Basic Auth Docs](https://docs.nginx.com/nginx/admin-guide/security-controls/configuring-http-basic-authentication/)
- [Tailscale vs Cloudflare Access](https://tailscale.com/compare/cloudflare-access)
- [Streamlit Auth Components](https://streamlit.io/components?category=authentication)
