# Settings Persistence Research

## Problem Statement

Clay-Dupe currently loads all configuration from `.env` at startup via `load_dotenv()` + `os.getenv()`. The `Settings` object is cached as a `@st.cache_resource` singleton. When users change settings in the UI (API keys, waterfall order, budgets, cache TTL), changes mutate the in-memory `Settings` object but are **lost on restart**. The UI even warns: *"Settings are stored in memory for this session."*

### Current Architecture

```
.env file --> load_dotenv() --> os.getenv() --> Settings (pydantic BaseModel)
                                                    |
                                          @st.cache_resource (singleton)
                                                    |
                                          UI mutates in-memory only
```

**Files involved:**
- `config/settings.py` — `Settings`, `ProviderConfig`, `ICPPreset`, `load_settings()`
- `ui/app.py` — `get_settings()` cached singleton
- `ui/pages/settings.py` — UI for changing settings (in-memory only)
- `cost/budget.py` — `BudgetManager` with in-memory `_daily_limits`, `_monthly_limits`

### Settings That Need Persistence

| Setting | Type | Sensitive? | Current Source | Change Frequency |
|---------|------|-----------|---------------|-----------------|
| API keys (5 providers) | string | YES | `.env` | Rare |
| Salesforce credentials | string | YES | `.env` | Rare |
| Anthropic API key | string | YES | `.env` | Rare |
| Waterfall order | list[str] | No | `.env` | Occasional |
| Daily budget per provider | int/None | No | Not persisted | Occasional |
| Monthly budget per provider | int/None | No | Not persisted | Occasional |
| Cache TTL days | int | No | `.env` | Rare |
| Max concurrent requests | int | No | Not persisted | Rare |
| ICP presets (custom) | dict | No | SQLite (already) | Occasional |
| UI preferences | various | No | Not persisted | Occasional |
| Export presets/column mappings | dict | No | Not persisted | Occasional |

---

## Approach 1: Database-Backed Settings (SQLite `app_settings` table)

### Schema Design

**Option A: Key-Value Store (Recommended)**

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,           -- JSON-encoded value
    value_type  TEXT NOT NULL DEFAULT 'string',  -- string, int, float, bool, json
    category    TEXT NOT NULL DEFAULT 'general', -- provider, waterfall, budget, ui, export
    is_secret   BOOLEAN DEFAULT 0,      -- flag for encrypted values
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by  TEXT                     -- future: user attribution
);
```

**Why key-value over structured columns:**
- New settings can be added without schema migrations
- No ALTER TABLE needed when we add export presets, UI preferences, etc.
- Categories allow grouping in the settings UI
- `value_type` enables proper deserialization

**Example rows:**
```
key                          | value                                    | value_type | category
waterfall_order              | ["apollo","icypeas","findymail","datagma"]| json       | waterfall
budget_daily_apollo          | 500                                      | int        | budget
budget_monthly_apollo        | 10000                                    | int        | budget
cache_ttl_days               | 30                                       | int        | general
max_concurrent_requests      | 5                                        | int        | general
ui_default_page              | results                                  | string     | ui
ui_table_page_size           | 50                                       | int        | ui
export_preset_outreach       | {"columns":["name","email",...],"format":"csv"} | json | export
```

**Option B: Structured Table (Not Recommended)**

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    id                      INTEGER PRIMARY KEY DEFAULT 1,  -- singleton row
    waterfall_order         TEXT,        -- JSON array
    cache_ttl_days          INTEGER,
    max_concurrent_requests INTEGER,
    -- ... one column per setting
);
```

This requires ALTER TABLE for every new setting. Rejected.

### Typed Value Handling

```python
import json
from typing import Any

def serialize_setting(value: Any, value_type: str) -> str:
    """Serialize a Python value to a string for DB storage."""
    if value_type == "json":
        return json.dumps(value)
    elif value_type == "bool":
        return "1" if value else "0"
    else:
        return str(value)

def deserialize_setting(raw: str, value_type: str) -> Any:
    """Deserialize a DB string back to the correct Python type."""
    if value_type == "string":
        return raw
    elif value_type == "int":
        return int(raw)
    elif value_type == "float":
        return float(raw)
    elif value_type == "bool":
        return raw in ("1", "true", "True")
    elif value_type == "json":
        return json.loads(raw)
    return raw
```

### Precedence Order (Layered Config)

```
Priority (highest to lowest):
1. Environment variables (os.environ) -- Docker/deployment overrides
2. .env file values -- developer/local defaults
3. Database settings -- user-configured via UI
4. Hardcoded defaults -- in Settings model
```

This means: if `WATERFALL_ORDER` is set in the environment or `.env`, it wins. If not, the DB value is used. If neither, the hardcoded default applies. This is the standard 12-factor approach and ensures Docker deployments can always override via `docker-compose.yml` env vars.

### Migration Strategy

When adding new settings:
1. Define the default in `Settings` model (hardcoded default)
2. No DB migration needed -- key-value store is schemaless for settings
3. On first read, if key doesn't exist in DB, return the hardcoded default
4. Only write to DB when user explicitly saves via UI

### Pros
- Changes survive restarts
- No file permission issues in Docker containers
- Already have SQLite infrastructure (async, WAL mode, migrations)
- Atomic updates (SQLite transactions)
- Audit trail possible (updated_at, updated_by)
- Works with existing `@st.cache_resource` pattern

### Cons
- API keys in SQLite are visible if someone gets the DB file
- Need encryption layer for secrets (adds complexity)
- Extra DB reads at startup (negligible -- single SELECT)
- Need to invalidate `@st.cache_resource` when settings change

### Implementation Complexity: **Low-Medium**

---

## Approach 2: File-Based Settings

### 2a: Write Changes Back to `.env`

```python
from dotenv import set_key

def save_setting_to_env(key: str, value: str):
    set_key(".env", key, value)
```

**Problems:**
- `.env` file might be read-only in Docker (mounted as volume or baked into image)
- `python-dotenv`'s `set_key()` rewrites the file -- can corrupt on crash
- No atomic writes (partial write = broken config)
- Concurrent access from multiple Streamlit workers is unsafe
- Mixing sensitive (API keys) and non-sensitive (waterfall order) in one file
- `.env` format only supports strings -- no native lists, dicts, bools
- Comments and formatting get lost on rewrite

**Verdict: Avoid.** Writing back to `.env` is fragile and fights against the 12-factor model where `.env` is an input, not a state store.

### 2b: Separate `settings.json` or `settings.yaml`

```python
import json
from pathlib import Path

SETTINGS_FILE = Path("data/settings.json")

def save_settings(settings_dict: dict):
    temp = SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(settings_dict, indent=2))
    temp.replace(SETTINGS_FILE)  # atomic on most OS

def load_settings_from_file() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {}
```

**Pros:**
- Simple to implement
- Human-readable/editable
- Atomic writes possible via temp file + rename
- Easy to backup/restore
- Docker: mount `data/` directory as volume

**Cons:**
- File locking needed for concurrent access (Streamlit reruns)
- No built-in schema validation
- Must handle file corruption (truncated writes)
- Separate from DB -- two persistence layers to manage
- API keys in plaintext JSON on disk

**File locking approach:**
```python
import fcntl  # Unix only -- not available on Windows natively

def save_with_lock(path, data):
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)
```

Note: `fcntl` is Unix-only. On Windows, use `msvcrt.locking()` or `portalocker` library. For a cross-platform app, this adds complexity.

### 2c: TOML Configuration File

```toml
# settings.toml
[general]
cache_ttl_days = 30
max_concurrent_requests = 5

[waterfall]
order = ["apollo", "icypeas", "findymail", "datagma"]

[budget.apollo]
daily = 500
monthly = 10000

[budget.findymail]
daily = 200
monthly = 5000
```

**Pros:**
- Clean, human-readable format
- Python 3.11+ has `tomllib` built-in (read-only)
- Good for structured config with sections

**Cons:**
- `tomllib` is read-only -- need `tomli-w` or `tomlkit` for writing
- Same file locking issues as JSON
- Same two-persistence-layer problem
- TOML spec is less flexible than JSON for arbitrary nested structures

### Implementation Complexity: **Low** (JSON), **Medium** (TOML with write support)

---

## Approach 3: Streamlit `secrets.toml`

Streamlit provides `.streamlit/secrets.toml` for managing sensitive configuration:

```toml
# .streamlit/secrets.toml
APOLLO_API_KEY = "key-here"
FINDYMAIL_API_KEY = "key-here"

[salesforce]
username = "user@example.com"
password = "secret"
security_token = "token"
```

Access via `st.secrets["APOLLO_API_KEY"]` or `st.secrets.salesforce.username`.

### Limitations

1. **Read-only at runtime** -- changes to `secrets.toml` require server restart
2. **No programmatic writes** -- `st.secrets` has no setter API
3. **File must exist before app starts** -- cannot create dynamically
4. **Global scope** -- no per-user settings
5. **Streamlit Cloud specific** -- on self-hosted, it's just a TOML file
6. **Restart required** -- if file is modified while app is running, changes are not picked up until restart

### Verdict

`secrets.toml` is designed for **deployment-time secrets**, not **runtime user configuration**. It's equivalent to `.env` but in TOML format. Not suitable for our use case of persisting UI-driven changes.

**Use case:** Could supplement `.env` for Streamlit Cloud deployments, but doesn't solve the persistence problem.

---

## Approach 4: Hybrid Approach (RECOMMENDED)

### Architecture

```
Layer 1 (Immutable Inputs):
    .env / Docker env vars / secrets.toml
    --> Sensitive values (API keys, SF credentials)
    --> Deployment-specific values (DB_PATH, ports)
    --> Read at startup, never written by app

Layer 2 (Persistent User Config):
    SQLite app_settings table
    --> Waterfall order, budgets, cache TTL
    --> UI preferences, export presets
    --> Read/written by app at runtime
    --> Survives restarts

Layer 3 (Ephemeral Session State):
    st.session_state
    --> Temporary UI state (expanded panels, form drafts)
    --> Lost on page refresh (by design)
    --> Never persisted
```

### Precedence Rules

```python
def get_setting(key: str) -> Any:
    # 1. Environment variable (highest priority -- deployment override)
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val

    # 2. .env file (loaded at startup)
    dotenv_val = os.getenv(key)  # already loaded by load_dotenv()
    if dotenv_val is not None:
        return dotenv_val

    # 3. Database setting (user-configured)
    db_val = db_settings_cache.get(key)
    if db_val is not None:
        return db_val

    # 4. Hardcoded default
    return DEFAULTS.get(key)
```

Note: In practice, steps 1 and 2 collapse because `load_dotenv()` populates `os.environ`. The key insight is that env vars always win over DB values.

### What Goes Where

| Setting | Layer | Rationale |
|---------|-------|-----------|
| API keys | .env only | Sensitive; should not be in DB without encryption |
| SF credentials | .env only | Sensitive |
| Waterfall order | DB (Layer 2) | User configures in UI, must persist |
| Daily/monthly budgets | DB (Layer 2) | User configures in UI, must persist |
| Cache TTL | DB (Layer 2) | User configures in UI |
| Max concurrent requests | DB (Layer 2) | Tuning parameter |
| ICP presets (custom) | DB (already done) | Already implemented in `icp_profiles` table |
| UI preferences | DB (Layer 2) | Table page size, default page, etc. |
| Export presets | DB (Layer 2) | Column mappings, format defaults |
| Form drafts, expanded panels | Session state (Layer 3) | Ephemeral by nature |

### Why NOT Store API Keys in the Database

1. **SQLite files are unencrypted** -- anyone with file access sees everything
2. **DB backups expose secrets** -- copying `clay_dupe.db` copies all keys
3. **No access control** -- SQLite has no user/role permissions
4. **Encryption adds complexity** -- need key management for the encryption key itself (chicken-and-egg: where do you store the encryption key?)
5. **`.env` is the standard** -- 12-factor apps expect secrets in env vars
6. **Docker best practice** -- secrets via `env_file`, Docker secrets, or vault

If we ever need API keys in the DB (e.g., multi-tenant), see the encryption section below.

---

## Security: Encrypting Sensitive Values

### When Encryption Is Needed

Only if we decide to store API keys in the database (e.g., for multi-user or if users insist on UI-only setup without `.env` access).

### Fernet Symmetric Encryption

```python
from cryptography.fernet import Fernet, MultiFernet
import os

# Encryption key stored in .env (or generated on first run)
# SETTINGS_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

def get_fernet() -> Fernet:
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY")
    if not key:
        # Generate on first run, save to .env
        key = Fernet.generate_key().decode()
        # Warn user to save this key
    return Fernet(key.encode() if isinstance(key, str) else key)

def encrypt_value(plaintext: str) -> str:
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()

def decrypt_value(ciphertext: str) -> str:
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
```

### Key Rotation with MultiFernet

```python
from cryptography.fernet import Fernet, MultiFernet

def rotate_encryption_key(old_key: str, new_key: str):
    """Re-encrypt all secrets with a new key."""
    old_f = Fernet(old_key.encode())
    new_f = Fernet(new_key.encode())
    multi = MultiFernet([new_f, old_f])  # new key first for encryption

    # Re-encrypt all secret settings
    for row in db.get_settings(is_secret=True):
        rotated = multi.rotate(row["value"].encode())
        db.update_setting(row["key"], rotated.decode())
```

### Security Considerations

- **Encryption key location**: Must be in `.env` or env var -- if it's in the DB alongside encrypted values, encryption is pointless
- **Key loss**: If encryption key is lost, all encrypted settings are unrecoverable -- document this clearly
- **Logging**: Never log decrypted values; mask API keys in all output (already done: `_mask_key()`)
- **Memory**: Decrypted values live in Python memory -- acceptable for our threat model (self-hosted, 3 users)
- **DB exports**: Encrypted values are safe to include in DB backups (as long as encryption key is separate)

### Recommendation for Our App

**Skip encryption for now.** Keep API keys in `.env` only. The 3-user, self-hosted deployment model means:
- Users have server access anyway (they edit `.env`)
- Encryption adds dependency (`cryptography` library) and complexity
- The encryption key would be in `.env` next to the API keys anyway
- If we add multi-tenant later, add encryption then

---

## Python Libraries Comparison

### pydantic-settings

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    apollo_api_key: str = ""
    waterfall_order: list[str] = ["apollo", "icypeas", "findymail", "datagma"]
    cache_ttl_days: int = 30

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):
        return (
            env_settings,        # 1. env vars (highest)
            dotenv_settings,     # 2. .env file
            SQLiteSettingsSource(settings_cls),  # 3. custom DB source
            init_settings,       # 4. defaults (lowest)
        )
```

**Pros:** Type-safe, validation built-in, custom sources via `settings_customise_sources`, already using pydantic
**Cons:** Requires refactoring `Settings` to extend `BaseSettings`, custom source needs implementation
**Verdict:** Good fit -- we already use pydantic. The custom SQLite source is ~50 lines.

### dynaconf

```python
from dynaconf import Dynaconf

settings = Dynaconf(
    settings_files=["settings.toml", ".env"],
    environments=True,
    env_prefix="CLAYDUPE",
)

# Access: settings.WATERFALL_ORDER, settings.CACHE_TTL_DAYS
```

**Pros:** Battle-tested, multiple file formats, environment layering, Flask/Django extensions
**Cons:** No native SQLite backend, adds a dependency, own DSL for settings files, no pydantic validation
**Verdict:** Overkill for our use case. We'd still need custom DB integration.

### python-decouple

```python
from decouple import config, Csv

WATERFALL_ORDER = config("WATERFALL_ORDER", default="apollo,icypeas", cast=Csv())
CACHE_TTL = config("CACHE_TTL_DAYS", default=30, cast=int)
```

**Pros:** Simple, lightweight, `.env` + `.ini` support
**Cons:** No DB backend, no pydantic integration, no type annotations, read-only
**Verdict:** Too simple. Doesn't solve the persistence problem.

### sqlconfig

```python
# pip install sqlconfig
# Stores config as SQLite database content with schema validation
```

**Pros:** Purpose-built for SQLite config storage
**Cons:** Very niche library (low adoption), limited features, no pydantic integration
**Verdict:** Not worth the dependency risk.

### Recommendation: **pydantic-settings with custom SQLite source**

We already use pydantic. Upgrading `Settings(BaseModel)` to `Settings(BaseSettings)` is minimal effort, and the custom source pattern is well-documented.

---

## Implementation Plan

### Phase 1: Database Layer (app_settings table)

**1. Add schema migration:**

```sql
-- In schema.sql
CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    value_type  TEXT NOT NULL DEFAULT 'string',
    category    TEXT NOT NULL DEFAULT 'general',
    is_secret   BOOLEAN DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by  TEXT
);
```

**2. Add DB methods to `Database` class:**

```python
async def get_all_settings(self) -> dict[str, Any]:
    """Load all app_settings as a typed dict."""
    async with self._connect() as conn:
        cursor = await conn.execute("SELECT key, value, value_type FROM app_settings")
        rows = await cursor.fetchall()
    return {
        row["key"]: deserialize_setting(row["value"], row["value_type"])
        for row in rows
    }

async def get_setting(self, key: str) -> Optional[Any]:
    """Load a single setting by key."""
    async with self._connect() as conn:
        cursor = await conn.execute(
            "SELECT value, value_type FROM app_settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return deserialize_setting(row["value"], row["value_type"])

async def save_setting(self, key: str, value: Any, value_type: str = "string",
                       category: str = "general"):
    """Upsert a single setting."""
    serialized = serialize_setting(value, value_type)
    async with self._connect() as conn:
        await conn.execute(
            """INSERT INTO app_settings (key, value, value_type, category, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   value_type = excluded.value_type,
                   updated_at = CURRENT_TIMESTAMP""",
            (key, serialized, value_type, category),
        )

async def delete_setting(self, key: str):
    """Remove a setting (revert to default)."""
    async with self._connect() as conn:
        await conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
```

### Phase 2: Settings Manager (Layered Config)

```python
# config/settings_manager.py

class SettingsManager:
    """Layered configuration: env vars > .env > DB > defaults."""

    # Registry of all known settings with defaults and types
    REGISTRY: dict[str, dict] = {
        "waterfall_order": {
            "default": ["apollo", "icypeas", "findymail", "datagma"],
            "value_type": "json",
            "category": "waterfall",
            "env_key": "WATERFALL_ORDER",  # maps to env var
            "env_parser": lambda s: [x.strip() for x in s.split(",")],
        },
        "cache_ttl_days": {
            "default": 30,
            "value_type": "int",
            "category": "general",
            "env_key": "CACHE_TTL_DAYS",
        },
        "max_concurrent_requests": {
            "default": 5,
            "value_type": "int",
            "category": "general",
        },
        "budget_daily_apollo": {
            "default": None,
            "value_type": "int",
            "category": "budget",
        },
        # ... etc
    }

    def __init__(self, db: Database):
        self._db = db
        self._cache: dict[str, Any] = {}
        self._loaded = False

    def load(self):
        """Load all DB settings into memory cache."""
        from data.sync import run_sync
        db_settings = run_sync(self._db.get_all_settings())
        self._cache = db_settings
        self._loaded = True

    def get(self, key: str) -> Any:
        """Get setting value with full precedence chain."""
        reg = self.REGISTRY.get(key, {})

        # 1. Environment variable
        env_key = reg.get("env_key")
        if env_key:
            env_val = os.environ.get(env_key)
            if env_val is not None:
                parser = reg.get("env_parser")
                return parser(env_val) if parser else env_val

        # 2. Database value
        if key in self._cache:
            return self._cache[key]

        # 3. Default
        return reg.get("default")

    def set(self, key: str, value: Any):
        """Save setting to DB and update cache."""
        from data.sync import run_sync
        reg = self.REGISTRY.get(key, {})
        value_type = reg.get("value_type", "string")
        category = reg.get("category", "general")
        run_sync(self._db.save_setting(key, value, value_type, category))
        self._cache[key] = value

    def reset(self, key: str):
        """Remove DB override, revert to default."""
        from data.sync import run_sync
        run_sync(self._db.delete_setting(key))
        self._cache.pop(key, None)

    def get_all_for_category(self, category: str) -> dict[str, Any]:
        """Get all settings for a category (for UI rendering)."""
        return {
            key: self.get(key)
            for key, reg in self.REGISTRY.items()
            if reg.get("category") == category
        }
```

### Phase 3: Integrate with Existing Code

**Modify `config/settings.py`:**

```python
def load_settings(db: Optional[Database] = None) -> Settings:
    """Load settings from env vars + DB overrides."""
    # API keys always from env (sensitive)
    providers = {}
    for pname in ProviderName:
        env_key = f"{pname.value.upper()}_API_KEY"
        api_key = os.getenv(env_key, "")
        providers[pname] = ProviderConfig(name=pname, api_key=api_key)

    # Non-sensitive settings: check DB first, then env, then defaults
    if db:
        mgr = SettingsManager(db)
        mgr.load()
        waterfall_order = mgr.get("waterfall_order")
        cache_ttl = mgr.get("cache_ttl_days")
        # Apply budget limits from DB
        for pname in ProviderName:
            daily = mgr.get(f"budget_daily_{pname.value}")
            monthly = mgr.get(f"budget_monthly_{pname.value}")
            if daily:
                providers[pname].daily_credit_limit = daily
            if monthly:
                providers[pname].monthly_credit_limit = monthly
    else:
        # Fallback: env-only (for tests, CLI)
        order_str = os.getenv("WATERFALL_ORDER", "apollo,icypeas,findymail,datagma")
        waterfall_order = [ProviderName(p.strip()) for p in order_str.split(",")]
        cache_ttl = int(os.getenv("CACHE_TTL_DAYS", "30"))

    return Settings(
        providers=providers,
        waterfall_order=[ProviderName(p) if isinstance(p, str) else p for p in waterfall_order],
        cache_ttl_days=cache_ttl,
        db_path=os.getenv("DB_PATH", "clay_dupe.db"),
        icp_presets=ICP_PRESETS,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    )
```

**Modify `ui/pages/settings.py` -- add Save button:**

```python
# After each settings section, add a save button
if st.button("Save Settings", type="primary", icon=":material/save:"):
    mgr = get_settings_manager()
    mgr.set("waterfall_order", [p.value for p in settings.waterfall_order])
    mgr.set("cache_ttl_days", settings.cache_ttl_days)
    mgr.set("max_concurrent_requests", settings.max_concurrent_requests)
    for pname in ProviderName:
        pcfg = settings.providers.get(pname)
        if pcfg:
            if pcfg.daily_credit_limit:
                mgr.set(f"budget_daily_{pname.value}", pcfg.daily_credit_limit)
            if pcfg.monthly_credit_limit:
                mgr.set(f"budget_monthly_{pname.value}", pcfg.monthly_credit_limit)
    st.success("Settings saved! Changes will persist across restarts.")
    st.cache_resource.clear()  # Force reload of settings singleton
    st.rerun()
```

### Phase 4: Cache Invalidation

When settings are saved via the UI, the `@st.cache_resource` singleton must be invalidated:

```python
# In ui/app.py
@st.cache_resource
def get_settings() -> Settings:
    db = get_database()
    return load_settings(db=db)

def invalidate_settings():
    """Clear cached settings to force reload from DB."""
    get_settings.clear()
```

The save button calls `invalidate_settings()` + `st.rerun()` to reload.

---

## Docker Compatibility

### Current Setup

```yaml
# docker-compose.yml
services:
  clay-dupe:
    build: .
    volumes:
      - ./data:/data       # SQLite DB persists here
    env_file:
      - .env               # API keys, sensitive config
```

### How This Works with DB Settings

- **DB settings persist** because SQLite file is on the mounted volume (`./data/`)
- **API keys stay in `.env`** -- mounted via `env_file` directive
- **No file permission issues** -- SQLite handles concurrent access
- **Container rebuild** doesn't lose settings (data volume survives)
- **Settings take effect immediately** -- no restart needed for DB-backed settings

### Override via Environment

Docker Compose env vars override everything:

```yaml
environment:
  - WATERFALL_ORDER=apollo,findymail  # overrides DB value
  - CACHE_TTL_DAYS=7                  # overrides DB value
```

This is correct behavior: deployment-level overrides should win.

---

## Settings Validation

### On Save

```python
def validate_waterfall_order(order: list[str]) -> list[str]:
    """Ensure waterfall order contains only valid provider names."""
    valid = {p.value for p in ProviderName}
    return [p for p in order if p in valid]

def validate_cache_ttl(days: int) -> int:
    """Clamp cache TTL to reasonable range."""
    return max(1, min(365, days))

def validate_budget(limit: Optional[int]) -> Optional[int]:
    """Ensure budget is positive or None."""
    if limit is not None and limit <= 0:
        return None
    return limit
```

### On Load (Defensive)

```python
def load_settings_safe(db: Database) -> Settings:
    """Load settings with fallback to defaults on corruption."""
    try:
        return load_settings(db=db)
    except Exception:
        # Log warning, return defaults
        return load_settings(db=None)  # env-only fallback
```

### Rolling Back Bad Settings

Since we're using a key-value store, rollback is simple:

```python
async def reset_setting(self, key: str):
    """Delete DB override, revert to env/default."""
    await self._db.delete_setting(key)

async def reset_all_settings(self):
    """Nuclear option: delete all DB settings."""
    async with self._db._connect() as conn:
        await conn.execute("DELETE FROM app_settings")
```

The UI should have a "Reset to Defaults" button per section and a global reset.

---

## Migration Path from Current `.env`-Only Approach

### Step 1: Add `app_settings` table to `schema.sql`
- No existing data to migrate -- table starts empty
- All settings fall through to env/defaults until user saves

### Step 2: Add `SettingsManager` class
- New file: `config/settings_manager.py`
- ~100 lines of code
- No changes to existing behavior until UI wires it up

### Step 3: Wire up Settings UI save
- Add "Save Settings" button to `ui/pages/settings.py`
- Replace footer caption with success message on save
- Add "Reset to Defaults" button

### Step 4: Modify `load_settings()` to accept DB
- Backward compatible: `db=None` falls back to env-only
- Tests continue to work without DB
- CLI continues to work without DB

### Step 5: Update `get_settings()` in `ui/app.py`
- Pass `db` to `load_settings(db=get_database())`
- Settings singleton now includes DB overrides

### Estimated LOC: ~200 new, ~50 modified

---

## Final Recommendation

**Use the Hybrid Approach (Approach 4) with these specifics:**

1. **API keys**: `.env` only. No DB storage. No encryption (for now).
2. **User preferences**: SQLite `app_settings` key-value table.
3. **Session state**: `st.session_state` for ephemeral UI state (unchanged).
4. **Library**: Stick with raw pydantic (no pydantic-settings upgrade needed). The `SettingsManager` class is simple enough that adding a dependency isn't justified.
5. **Precedence**: env vars > DB > hardcoded defaults.
6. **Validation**: Pydantic validators on `Settings` model + explicit validation on save.
7. **Docker**: Works naturally -- SQLite on mounted volume, env vars via `env_file`.
8. **Migration**: Zero-migration -- empty table, settings use defaults until user saves.

This approach is minimal, pragmatic, and fits our 3-user self-hosted model. It avoids over-engineering (no encryption, no pydantic-settings, no dynaconf) while solving the actual problem: user-configured settings that survive restarts.

---

## Sources

- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Dynaconf Documentation](https://www.dynaconf.com/)
- [Fernet Symmetric Encryption](https://cryptography.io/en/latest/fernet/)
- [Streamlit Secrets Management](https://docs.streamlit.io/develop/concepts/connections/secrets-management)
- [Streamlit config.toml](https://docs.streamlit.io/develop/api-reference/configuration/config.toml)
- [Docker Environment Variables Best Practices](https://docs.docker.com/compose/how-tos/environment-variables/best-practices/)
- [python-decouple](https://pypi.org/project/python-decouple/)
- [pydantic-settings PyPI](https://pypi.org/project/pydantic-settings/)
- [Encryption at Rest with SQLAlchemy (Fernet pattern)](https://blog.miguelgrinberg.com/post/encryption-at-rest-with-sqlalchemy)
- [sqlconfig PyPI](https://pypi.org/project/sqlconfig/)
- [FastAPI Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)
- [Twelve-Factor Python Applications Using Pydantic Settings](https://medium.com/datamindedbe/twelve-factor-python-applications-using-pydantic-settings-f74a69906f2f)
