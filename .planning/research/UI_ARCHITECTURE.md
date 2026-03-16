# UI Architecture Research — Streamlit for B2B Data Enrichment Tools

> Research date: 2026-03-08
> Focus: Production-quality Streamlit applications for CRM-like data enrichment interfaces

---

## Table of Contents

1. [Multi-Page App Architecture](#1-multi-page-app-architecture)
2. [Session State Management](#2-session-state-management)
3. [Background Tasks & Progress Tracking](#3-background-tasks--progress-tracking)
4. [Concurrent Users & Session Isolation](#4-concurrent-users--session-isolation)
5. [Caching Strategies](#5-caching-strategies)
6. [File Upload Handling](#6-file-upload-handling)
7. [Data Table UI Patterns](#7-data-table-ui-patterns)
8. [Clay's Table UI — What Makes It Effective](#8-clays-table-ui--what-makes-it-effective)
9. [Inline Editing](#9-inline-editing)
10. [Column Mapping UI](#10-column-mapping-ui)
11. [Enrichment Status & Real-Time Dashboard](#11-enrichment-status--real-time-dashboard)
12. [Custom Components & React Integration](#12-custom-components--react-integration)
13. [Styling & Responsive Layouts](#13-styling--responsive-layouts)
14. [Authentication](#14-authentication)
15. [Performance Optimization](#15-performance-optimization)
16. [Framework Comparison & Alternatives](#16-framework-comparison--alternatives)
17. [Production Deployment](#17-production-deployment)
18. [Recommended Architecture for Our Platform](#18-recommended-architecture-for-our-platform)
19. [Component Implementation Plans](#19-component-implementation-plans)

---

## 1. Multi-Page App Architecture

### Current Best Practice (2025-2026): `st.navigation()` + `st.Page()`

The modern approach uses programmatic page definition rather than the older `pages/` directory convention.

```python
# app.py — main entry point
import streamlit as st

# Define pages programmatically
pages = {
    "Data": [
        st.Page("pages/companies.py", title="Companies", icon="🏢"),
        st.Page("pages/contacts.py", title="Contacts", icon="👤"),
        st.Page("pages/imports.py", title="Import CSV", icon="📥"),
    ],
    "Enrichment": [
        st.Page("pages/enrichment.py", title="Enrichment Jobs", icon="⚡"),
        st.Page("pages/waterfall.py", title="Waterfall Config", icon="🔧"),
        st.Page("pages/costs.py", title="Cost Dashboard", icon="📊"),
    ],
    "Settings": [
        st.Page("pages/api_keys.py", title="API Keys", icon="🔑"),
        st.Page("pages/settings.py", title="Settings", icon="⚙️"),
    ],
}

pg = st.navigation(pages)

# Common setup code runs before every page
# — auth checks, page config, global styles
st.set_page_config(page_title="GPO Platform", layout="wide")
apply_custom_css()
check_authentication()

pg.run()
```

### Key Benefits

- **Dynamic pages**: Pages can change at runtime (e.g., hide admin pages for non-admin users)
- **Grouped navigation**: Pages organized into sections in the sidebar
- **Common code**: `app.py` runs before every page — ideal for auth, styles, shared state init
- **Clean URLs**: Each page gets its own URL path

### Project Structure

```
project/
├── app.py                    # Entry point with st.navigation
├── pages/
│   ├── companies.py          # Company table view
│   ├── contacts.py           # Contact table view
│   ├── imports.py            # CSV import + mapping
│   ├── enrichment.py         # Enrichment job management
│   ├── waterfall.py          # Waterfall configuration
│   ├── costs.py              # Cost dashboard
│   ├── api_keys.py           # API key management
│   └── settings.py           # General settings
├── components/               # Reusable UI components
│   ├── tables.py             # Table rendering helpers
│   ├── charts.py             # Chart components
│   ├── status_badges.py      # Status indicator components
│   └── filters.py            # Filter/search components
├── services/                 # Business logic (no Streamlit imports)
│   ├── enrichment.py
│   ├── waterfall.py
│   └── export.py
├── utils/
│   ├── state.py              # Session state helpers
│   ├── cache.py              # Caching utilities
│   └── styles.py             # CSS injection
└── .streamlit/
    ├── config.toml            # Streamlit configuration
    └── secrets.toml           # Local secrets (gitignored)
```

---

## 2. Session State Management

### Core Pattern: Centralized State Initialization

```python
# utils/state.py
import streamlit as st
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

@dataclass
class AppState:
    """Centralized state container — all session state in one place."""
    # Data
    companies_df: Optional[pd.DataFrame] = None
    contacts_df: Optional[pd.DataFrame] = None

    # Enrichment
    active_jobs: dict = field(default_factory=dict)
    enrichment_progress: dict = field(default_factory=dict)

    # UI state
    selected_company_ids: list = field(default_factory=list)
    current_filter: str = ""
    sort_column: str = "company_name"
    sort_ascending: bool = True

    # Settings
    waterfall_order: list = field(default_factory=list)
    budget_limit: float = 100.0

def init_state():
    """Initialize session state with defaults. Call in app.py."""
    if "app" not in st.session_state:
        st.session_state.app = AppState()

def get_state() -> AppState:
    """Type-safe state access."""
    return st.session_state.app
```

### Best Practices

1. **Use a dataclass or dict-of-dicts** — avoids scattered `st.session_state["random_key"]` everywhere
2. **Initialize once in `app.py`** — the main entry point runs before every page
3. **Use callbacks for widget state** — `on_change` / `on_click` parameters prevent timing issues
4. **Never store large DataFrames in state unnecessarily** — use caching instead
5. **Use `st.query_params`** for URL-shareable state (filters, selected company ID)

### Callback Pattern for Complex Interactions

```python
def on_company_selected():
    """Callback when company selection changes."""
    state = get_state()
    state.selected_company_ids = st.session_state["company_selector"]
    # Trigger dependent data loads
    state.contacts_df = load_contacts_for_companies(state.selected_company_ids)

st.multiselect(
    "Select companies",
    options=company_list,
    key="company_selector",
    on_change=on_company_selected
)
```

### Cross-Page State Sharing

Session state persists across pages automatically. Use the centralized `AppState` dataclass so any page can read/write shared data without key collisions.

---

## 3. Background Tasks & Progress Tracking

### The Core Problem

Streamlit reruns the entire script on every interaction. Long-running enrichment jobs (30 seconds to 10+ minutes) cannot block the main thread.

### Recommended Architecture: External Task Queue + Polling Fragment

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Streamlit   │────>│  Task Queue  │────>│   Worker     │
│  (Frontend)  │     │  (SQLite/    │     │  (Thread/    │
│              │<────│   Redis)     │<────│   Process)   │
│  Polls for   │     │              │     │  Runs        │
│  status      │     │  Stores      │     │  enrichment  │
└──────────────┘     │  progress    │     └──────────────┘
                     └──────────────┘
```

### Implementation Pattern

```python
import threading
import streamlit as st
from datetime import datetime

# Background worker (runs in a thread, NO Streamlit imports in worker logic)
def enrichment_worker(job_id: str, company_ids: list, progress_store: dict):
    """Runs enrichment in background thread. Updates progress_store dict."""
    total = len(company_ids)
    for i, cid in enumerate(company_ids):
        try:
            result = run_enrichment_for_company(cid)  # Your enrichment logic
            progress_store[job_id] = {
                "status": "running",
                "completed": i + 1,
                "total": total,
                "percent": (i + 1) / total,
                "current_company": cid,
                "last_update": datetime.now().isoformat(),
            }
        except Exception as e:
            progress_store[job_id]["errors"] = progress_store[job_id].get("errors", [])
            progress_store[job_id]["errors"].append({"company": cid, "error": str(e)})

    progress_store[job_id]["status"] = "complete"

# Start job from Streamlit
def start_enrichment_job(company_ids: list):
    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Use st.cache_resource to share progress across reruns
    progress_store = get_shared_progress_store()

    progress_store[job_id] = {"status": "starting", "completed": 0, "total": len(company_ids)}

    thread = threading.Thread(
        target=enrichment_worker,
        args=(job_id, company_ids, progress_store),
        daemon=True,
    )
    thread.start()

    st.session_state.current_job_id = job_id
    return job_id

@st.cache_resource
def get_shared_progress_store():
    """Shared dict accessible across reruns. Lives in server memory."""
    return {}
```

### Real-Time Progress Display with `st.fragment`

```python
@st.fragment(run_every=2)  # Auto-rerun every 2 seconds
def enrichment_progress_panel():
    """Fragment that polls for progress without rerunning the full page."""
    job_id = st.session_state.get("current_job_id")
    if not job_id:
        st.info("No active enrichment job.")
        return

    progress_store = get_shared_progress_store()
    job = progress_store.get(job_id, {})

    status = job.get("status", "unknown")
    completed = job.get("completed", 0)
    total = job.get("total", 1)
    percent = job.get("percent", 0)

    if status == "running":
        st.progress(percent, text=f"Enriching: {completed}/{total} companies")
        col1, col2, col3 = st.columns(3)
        col1.metric("Completed", completed)
        col2.metric("Remaining", total - completed)
        col3.metric("Status", "Running")
    elif status == "complete":
        st.success(f"Enrichment complete! {total} companies processed.")
        if st.button("Dismiss"):
            del st.session_state.current_job_id
            st.rerun()
    elif status == "starting":
        st.spinner("Starting enrichment job...")

    # Show errors if any
    errors = job.get("errors", [])
    if errors:
        with st.expander(f"Errors ({len(errors)})"):
            for err in errors:
                st.error(f"{err['company']}: {err['error']}")
```

### Key Considerations

- **Thread safety**: Use `threading.Lock()` if multiple workers update the same data
- **`st.cache_resource`** for the progress store — shared across all reruns (not copied)
- **`st.fragment(run_every=N)`** for polling — only reruns the fragment, not the full page
- **Daemon threads**: Set `daemon=True` so threads die when the Streamlit process stops
- **For production**: Consider using Celery + Redis or a simple SQLite-based task queue instead of in-memory dicts (survives server restarts)

---

## 4. Concurrent Users & Session Isolation

### How Streamlit Handles Sessions

- Each browser tab = one WebSocket connection = one session
- `st.session_state` is **per-session** (isolated by default)
- `st.cache_resource` is **shared across all sessions** (global server state)
- `st.cache_data` returns **copies** per session (safe from cross-contamination)

### Common Pitfalls

| Problem | Cause | Solution |
|---------|-------|----------|
| Users see each other's data | Using global variables or `st.cache_resource` for user data | Use `st.session_state` or `st.cache_data` for user-specific data |
| Session crosstalk | Mutating `st.cache_resource` return values | Use locks or make data immutable |
| Memory exhaustion | Each session loads full dataset | Use shared `st.cache_resource` for read-only reference data |

### Session-Safe Architecture

```python
# SHARED (read-only reference data) — use st.cache_resource
@st.cache_resource
def load_provider_configs():
    """Provider configs shared across all users."""
    return load_from_db()

# PER-USER (mutable user data) — use st.session_state
def get_user_companies():
    """User-specific company list."""
    if "companies" not in st.session_state:
        st.session_state.companies = fetch_companies_for_user(st.session_state.user_id)
    return st.session_state.companies

# CACHED BUT COPIED (expensive computation, safe per-user) — use st.cache_data
@st.cache_data(ttl=300)
def compute_icp_scores(company_ids: tuple):
    """Expensive computation cached but each session gets its own copy."""
    return calculate_scores(company_ids)
```

### Scaling for Multiple Users

- **Single instance**: Handles ~10-50 concurrent users depending on complexity
- **Horizontal scaling**: Run multiple Streamlit instances behind Nginx with session affinity (sticky sessions)
- **Resource sizing**: Each active session consumes memory for its state + any loaded DataFrames
- **WebSocket requirement**: Load balancers must support WebSocket passthrough

---

## 5. Caching Strategies

### Decision Matrix

| Use Case | Decorator | Why |
|----------|-----------|-----|
| Database queries returning DataFrames | `@st.cache_data(ttl=300)` | Returns copy per session; safe from mutation |
| Loading CSV/Excel files | `@st.cache_data` | Avoid re-parsing on every rerun |
| API responses (enrichment results) | `@st.cache_data(ttl=600)` | Cache with TTL to get fresh data periodically |
| Database connections | `@st.cache_resource` | Single connection shared across sessions |
| ML models / heavy objects | `@st.cache_resource` | Load once, share across sessions |
| Progress stores / shared state | `@st.cache_resource` | Must be shared, not copied |
| Provider client instances | `@st.cache_resource` | Reuse HTTP sessions/auth tokens |

### Key Differences

```python
# st.cache_data — COPIES the return value (serializes/deserializes)
# Safe: each caller gets independent copy
# Use for: DataFrames, dicts, lists, query results
@st.cache_data(ttl=300)
def get_companies():
    return pd.read_sql("SELECT * FROM companies", conn)

# st.cache_resource — SHARES the actual object (no copy)
# Dangerous: mutations affect all sessions
# Use for: connections, models, shared state
@st.cache_resource
def get_db_connection():
    return sqlite3.connect("enrichment.db", check_same_thread=False)
```

### Cache Invalidation

```python
# Clear specific cache
get_companies.clear()

# Clear all caches
st.cache_data.clear()
st.cache_resource.clear()

# TTL-based expiration
@st.cache_data(ttl=60)  # Expires after 60 seconds
def get_enrichment_status():
    return fetch_status_from_db()
```

---

## 6. File Upload Handling

### Efficient Large CSV Processing

```python
import streamlit as st
import pandas as pd

def handle_csv_upload():
    uploaded_file = st.file_uploader(
        "Upload company list",
        type=["csv", "xlsx"],
        help="Max 200MB. Supported: CSV, Excel"
    )

    if uploaded_file is not None:
        # Show file info
        file_size_mb = uploaded_file.size / (1024 * 1024)
        st.caption(f"File: {uploaded_file.name} ({file_size_mb:.1f} MB)")

        # Read with progress indication
        with st.spinner(f"Reading {uploaded_file.name}..."):
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

        # Store in session state
        st.session_state.uploaded_df = df
        st.session_state.upload_filename = uploaded_file.name

        # Preview
        st.write(f"**{len(df):,} rows** x **{len(df.columns)} columns**")
        st.dataframe(df.head(20), use_container_width=True)

        return df
    return None
```

### Performance Tips for Large Files

1. **Increase upload limit** in `.streamlit/config.toml`:
   ```toml
   [server]
   maxUploadSize = 200  # MB
   ```
2. **Use chunked reading** for very large files (100K+ rows):
   ```python
   chunks = pd.read_csv(file, chunksize=10000)
   df = pd.concat(chunks, ignore_index=True)
   ```
3. **Consider Polars** for 10x faster CSV parsing:
   ```python
   import polars as pl
   df = pl.read_csv(uploaded_file).to_pandas()  # Convert back if needed
   ```
4. **Downcast types** to reduce memory:
   ```python
   df = df.convert_dtypes()  # Use nullable pandas dtypes
   ```

---

## 7. Data Table UI Patterns

### Option A: Native `st.dataframe` (Simple, Good Enough for Many Cases)

```python
st.dataframe(
    df,
    use_container_width=True,
    height=600,
    column_config={
        "icp_score": st.column_config.ProgressColumn(
            "ICP Score", min_value=0, max_value=100, format="%d%%"
        ),
        "website": st.column_config.LinkColumn("Website"),
        "enrichment_status": st.column_config.SelectboxColumn(
            "Status",
            options=["pending", "enriching", "complete", "failed"],
        ),
        "last_enriched": st.column_config.DatetimeColumn(
            "Last Enriched", format="YYYY-MM-DD HH:mm"
        ),
    },
    column_order=["company_name", "website", "icp_score", "enrichment_status"],
    hide_index=True,
)
```

### Option B: Streamlit-AgGrid (Full-Featured, Excel-Like)

```python
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode

gb = GridOptionsBuilder.from_dataframe(df)

# Configure columns
gb.configure_default_column(
    resizable=True,
    filterable=True,
    sortable=True,
    editable=False,
)
gb.configure_column("company_name", headerName="Company", pinned="left", width=200)
gb.configure_column("icp_score", headerName="ICP Score", type=["numericColumn"])
gb.configure_column("enrichment_status", headerName="Status",
    cellStyle={"function": """
        params.value === 'complete' ? {'background-color': '#d4edda'} :
        params.value === 'failed' ? {'background-color': '#f8d7da'} :
        params.value === 'enriching' ? {'background-color': '#fff3cd'} :
        {'background-color': '#e2e3e5'}
    """})

# Enable features
gb.configure_selection("multiple", use_checkbox=True)
gb.configure_pagination(paginationAutoPageSize=True)
gb.configure_side_bar(filters_panel=True, columns_panel=True)

grid_options = gb.build()

grid_response = AgGrid(
    df,
    gridOptions=grid_options,
    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    update_mode="MODEL_CHANGED",
    fit_columns_on_grid_load=True,
    height=600,
    theme="streamlit",  # or "alpine", "balham", "material"
)

# Access selected rows
selected_rows = grid_response["selected_rows"]
```

### Comparison for Our Use Case

| Feature | st.dataframe | st.data_editor | AgGrid |
|---------|-------------|----------------|--------|
| Sorting | Built-in | Built-in | Built-in + multi-column |
| Filtering | Column search only | Column search only | Full filter panel |
| Inline editing | No | Yes | Yes (advanced) |
| Row selection | No | No | Checkbox / click |
| Pagination | Virtual scroll | Virtual scroll | Full pagination |
| Custom cell rendering | column_config | column_config | JS cell renderers |
| Bulk actions | No | No | Yes (with selection) |
| Performance (10K rows) | Good | Good | Excellent |
| Dependency | None | None | streamlit-aggrid |

**Recommendation**: Use **AgGrid** for the main company/contact tables (need selection, filtering, bulk actions). Use **st.dataframe** for read-only previews and simple displays.

---

## 8. Clay's Table UI — What Makes It Effective

### Key Design Principles from Clay

1. **Spreadsheet-First Mental Model**: Clay uses a grid/spreadsheet interface that sales teams are already familiar with. Columns represent data fields and enrichment actions.

2. **Enrichment as Columns**: Each enrichment source becomes a column. Adding an enrichment = adding a column that auto-populates. This is brilliant because:
   - Users see which provider found which data
   - Empty cells immediately show gaps
   - The workflow is visual and intuitive

3. **Waterfall Transparency**: Clay shows which provider in the waterfall found each data point, giving users confidence in data quality.

4. **Inline Status Per Row**: Each row shows its enrichment status (pending/enriching/complete/failed), making batch progress visible at a glance.

5. **Add Column = Add Enrichment**: The "Add Column" button on the rightmost column opens the enrichment panel, making it discoverable.

6. **Categorized Enrichment Panel**: Enrichments are grouped by category (contact info, company data, technographics, etc.) to help users find what they need.

### What We Should Replicate

- Grid-based layout with familiar spreadsheet interactions
- Status badges per row (color-coded)
- Column-level enrichment source attribution
- One-click bulk enrichment from row selection
- Real-time progress indicators embedded in the table

### What We Can Improve On

- Clay's table is a custom React app — we can approximate 80% of it with AgGrid
- We can add cost-per-row display (Clay hides credit costs in the flow)
- We can show waterfall path per cell (which providers were tried, which succeeded)

---

## 9. Inline Editing

### Using `st.data_editor`

```python
edited_df = st.data_editor(
    df,
    column_config={
        "company_name": st.column_config.TextColumn("Company", required=True),
        "industry": st.column_config.SelectboxColumn(
            "Industry",
            options=["SaaS", "Fintech", "Healthcare", "E-commerce", "Other"],
        ),
        "employee_count": st.column_config.NumberColumn(
            "Employees", min_value=1, max_value=1000000
        ),
        "icp_tier": st.column_config.SelectboxColumn(
            "ICP Tier", options=["Tier 1", "Tier 2", "Tier 3", "Not ICP"]
        ),
        # Read-only columns
        "enrichment_status": st.column_config.TextColumn("Status", disabled=True),
        "last_enriched": st.column_config.DatetimeColumn("Last Enriched", disabled=True),
    },
    num_rows="dynamic",  # Allow adding/deleting rows
    use_container_width=True,
    hide_index=True,
    key="company_editor",
)

# Detect changes
if not edited_df.equals(st.session_state.get("original_df")):
    st.warning("You have unsaved changes.")
    if st.button("Save Changes"):
        save_to_database(edited_df)
        st.session_state.original_df = edited_df.copy()
        st.success("Changes saved!")
```

### Limitations of st.data_editor

- Cannot style individual editable cells differently (open GitHub issue)
- No row-level validation (only column-level type constraints)
- No undo/redo support
- Limited event handling (no on_cell_change callback)

For more advanced inline editing needs, **AgGrid with editable columns** provides better control.

---

## 10. Column Mapping UI

### Building a CSV Column Mapper

This is critical for CSV imports — mapping uploaded columns to system fields.

```python
def column_mapping_ui(uploaded_columns: list, system_fields: dict):
    """
    UI for mapping CSV columns to system fields.

    system_fields: {"field_name": {"label": "...", "required": True/False, "type": "str"}}
    """
    st.subheader("Map Your Columns")
    st.caption("Match each system field to a column from your CSV file.")

    mapping = {}
    unmapped_required = []

    cols = st.columns([2, 1, 2])
    cols[0].markdown("**System Field**")
    cols[1].markdown("")
    cols[2].markdown("**Your CSV Column**")

    st.divider()

    for field_name, field_info in system_fields.items():
        col1, col2, col3 = st.columns([2, 1, 2])

        label = field_info["label"]
        required = field_info.get("required", False)
        display_label = f"{label} {'*' if required else ''}"

        col1.markdown(f"**{display_label}**")
        col2.markdown("→")

        # Auto-detect likely matches
        default_idx = 0
        options = ["— Skip —"] + uploaded_columns
        for i, ucol in enumerate(uploaded_columns):
            if ucol.lower().replace(" ", "_") == field_name.lower():
                default_idx = i + 1
                break

        selected = col3.selectbox(
            f"Map {label}",
            options=options,
            index=default_idx,
            key=f"map_{field_name}",
            label_visibility="collapsed",
        )

        if selected != "— Skip —":
            mapping[field_name] = selected
        elif required:
            unmapped_required.append(label)

    # Validation
    if unmapped_required:
        st.error(f"Required fields not mapped: {', '.join(unmapped_required)}")

    # Preview mapped data
    if mapping and st.checkbox("Preview mapped data"):
        preview_df = st.session_state.uploaded_df.rename(
            columns={v: k for k, v in mapping.items()}
        )[list(mapping.keys())]
        st.dataframe(preview_df.head(10), use_container_width=True)

    return mapping, len(unmapped_required) == 0
```

### System Fields Definition

```python
SYSTEM_FIELDS = {
    "company_name": {"label": "Company Name", "required": True, "type": "str"},
    "domain": {"label": "Website/Domain", "required": True, "type": "str"},
    "industry": {"label": "Industry", "required": False, "type": "str"},
    "employee_count": {"label": "Employee Count", "required": False, "type": "int"},
    "linkedin_url": {"label": "LinkedIn URL", "required": False, "type": "str"},
    "location": {"label": "Location", "required": False, "type": "str"},
    "revenue": {"label": "Revenue", "required": False, "type": "str"},
}
```

---

## 11. Enrichment Status & Real-Time Dashboard

### Per-Row Status Display

```python
def render_status_badge(status: str) -> str:
    """Return HTML badge for enrichment status."""
    colors = {
        "pending": ("#6c757d", "white"),    # Gray
        "queued": ("#0d6efd", "white"),     # Blue
        "enriching": ("#ffc107", "black"),  # Yellow
        "complete": ("#198754", "white"),   # Green
        "partial": ("#fd7e14", "white"),    # Orange
        "failed": ("#dc3545", "white"),     # Red
    }
    bg, fg = colors.get(status, ("#6c757d", "white"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:12px;font-size:0.8em">{status}</span>'
```

### Real-Time Dashboard with Fragments

```python
@st.fragment(run_every=3)
def enrichment_dashboard():
    """Auto-refreshing dashboard showing enrichment metrics."""
    stats = get_enrichment_stats()  # Query from DB/cache

    # Top-level KPIs
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Companies", f"{stats['total']:,}")
    col2.metric("Enriched", f"{stats['enriched']:,}",
                delta=f"+{stats['enriched_today']}")
    col3.metric("Success Rate", f"{stats['success_rate']:.1f}%")
    col4.metric("Credits Used", f"${stats['credits_cost']:.2f}")

    # Progress bar for active job
    if stats.get("active_job"):
        job = stats["active_job"]
        st.progress(
            job["percent"],
            text=f"Enriching batch: {job['completed']}/{job['total']}"
        )

    # Status breakdown chart
    import plotly.express as px
    status_df = pd.DataFrame(stats["status_breakdown"])
    fig = px.pie(status_df, values="count", names="status",
                 color="status",
                 color_discrete_map={
                     "complete": "#198754",
                     "pending": "#6c757d",
                     "failed": "#dc3545",
                     "enriching": "#ffc107",
                 })
    fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)
```

### Cost Dashboard

```python
def cost_dashboard():
    """Provider cost tracking and analysis."""
    st.subheader("Cost Analysis")

    costs = get_cost_data()  # From DB

    # Cost metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Spent", f"${costs['total']:.2f}")
    col2.metric("Cost Per Contact", f"${costs['per_contact']:.4f}")
    col3.metric("Budget Remaining", f"${costs['budget_remaining']:.2f}")

    # Cost by provider
    fig = px.bar(
        costs["by_provider"],
        x="provider",
        y="cost",
        color="provider",
        title="Cost by Provider",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Cost over time
    fig2 = px.line(
        costs["over_time"],
        x="date",
        y="cumulative_cost",
        title="Cumulative Cost Over Time",
    )
    st.plotly_chart(fig2, use_container_width=True)

    # Provider performance table
    st.subheader("Provider Performance")
    st.dataframe(
        costs["provider_performance"],
        column_config={
            "provider": "Provider",
            "requests": st.column_config.NumberColumn("Requests"),
            "hits": st.column_config.NumberColumn("Hits"),
            "hit_rate": st.column_config.ProgressColumn(
                "Hit Rate", min_value=0, max_value=100, format="%.1f%%"
            ),
            "avg_cost": st.column_config.NumberColumn("Avg Cost", format="$%.4f"),
        },
        use_container_width=True,
        hide_index=True,
    )
```

---

## 12. Custom Components & React Integration

### When to Build Custom Components

Build a custom component when:
- No existing Streamlit widget or community component does what you need
- You need complex client-side interactivity (drag-and-drop, canvas drawing)
- You need to embed a specific JavaScript library
- Performance requires client-side rendering

**For our use case**: We likely do NOT need custom components. AgGrid + native Streamlit + Plotly cover 95% of our needs. Only consider custom components for:
- Drag-and-drop waterfall ordering (could also use numbered selectboxes)
- Advanced cell renderers (AgGrid's JS cell renderers may suffice)

### Architecture (If Needed)

```
Custom Component Architecture:
┌─────────────────────────────────────┐
│  Python (Streamlit)                 │
│  - st.components.v1.declare_component│
│  - Sends data to frontend via args  │
│  - Receives data via Streamlit.setComponentValue │
└──────────────┬──────────────────────┘
               │ iframe
┌──────────────▼──────────────────────┐
│  React/JS Frontend                  │
│  - Renders in iframe                │
│  - Uses streamlit-component-lib     │
│  - Calls Streamlit.setComponentValue│
│    to send data back to Python      │
└─────────────────────────────────────┘
```

### Simpler Alternative: `st.components.v1.html()`

For one-off custom rendering without building a full component:

```python
import streamlit.components.v1 as components

def waterfall_visualization(waterfall_data):
    """Render waterfall chart using custom HTML/JS."""
    html = f"""
    <div id="waterfall" style="font-family: sans-serif;">
        {"".join(f'''
        <div style="display:flex;align-items:center;margin:4px 0;">
            <div style="width:120px;font-size:14px;">{step['provider']}</div>
            <div style="flex:1;height:24px;background:#e0e0e0;border-radius:4px;overflow:hidden;">
                <div style="width:{step['hit_rate']}%;height:100%;
                     background:{'#198754' if step['found'] else '#dc3545'};
                     border-radius:4px;display:flex;align-items:center;
                     padding-left:8px;color:white;font-size:12px;">
                    {'Found' if step['found'] else 'Miss'}
                </div>
            </div>
            <div style="width:80px;text-align:right;font-size:12px;color:#666;">
                ${step['cost']:.4f}
            </div>
        </div>
        ''' for step in waterfall_data)}
    </div>
    """
    components.html(html, height=len(waterfall_data) * 32 + 20)
```

---

## 13. Styling & Responsive Layouts

### Custom CSS Injection

```python
# utils/styles.py
import streamlit as st

def apply_custom_css():
    st.markdown("""
    <style>
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Custom metrics styling */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
    }

    /* Status badge styling */
    .status-complete { background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 12px; }
    .status-failed { background: #f8d7da; color: #721c24; padding: 2px 8px; border-radius: 12px; }
    .status-pending { background: #e2e3e5; color: #383d41; padding: 2px 8px; border-radius: 12px; }

    /* Tighter padding for data-heavy layouts */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 0rem;
    }

    /* Responsive columns */
    @media (max-width: 768px) {
        [data-testid="column"] {
            width: 100% !important;
            flex: 100% !important;
        }
    }

    /* Custom sidebar width */
    [data-testid="stSidebar"] {
        min-width: 280px;
        max-width: 280px;
    }
    </style>
    """, unsafe_allow_html=True)
```

### Theme Configuration

```toml
# .streamlit/config.toml
[theme]
primaryColor = "#4A90D9"       # Blue — buttons, links, active elements
backgroundColor = "#FFFFFF"     # White background
secondaryBackgroundColor = "#F0F2F6"  # Light gray — sidebar, cards
textColor = "#262730"           # Dark text
font = "sans serif"

[server]
maxUploadSize = 200
enableCORS = false
enableXsrfProtection = true
```

### Layout Patterns for Data Tools

```python
# Wide layout with sidebar filters
st.set_page_config(layout="wide")

# Sidebar for filters
with st.sidebar:
    st.header("Filters")
    status_filter = st.multiselect("Status", ["complete", "pending", "failed"])
    icp_filter = st.slider("Min ICP Score", 0, 100, 0)

# Main content area
col_main, col_detail = st.columns([3, 1])

with col_main:
    st.header("Companies")
    # Main data table here

with col_detail:
    st.header("Details")
    # Selected company details here

# Tabs for related data
tab1, tab2, tab3 = st.tabs(["Contacts", "Enrichment History", "Notes"])
with tab1:
    # Contacts table
    pass
```

---

## 14. Authentication

### Option 1: Native OIDC (Recommended for Production)

Streamlit >= 1.32 supports OIDC natively.

```toml
# .streamlit/secrets.toml
[auth]
redirect_uri = "https://your-app.com/oauth2/callback"
cookie_secret = "random-secret-string"

[auth.microsoft]
client_id = "your-client-id"
client_secret = "your-client-secret"
server_metadata_url = "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"

[auth.google]
client_id = "your-client-id"
client_secret = "your-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

```python
# In app.py
if not st.experimental_user.is_logged_in:
    st.login("microsoft")  # or "google"
    st.stop()

# User info available after login
user_email = st.experimental_user.email
```

### Option 2: streamlit-authenticator (Simpler, Self-Contained)

```python
import streamlit_authenticator as stauth

authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_name="gpo_auth",
    cookie_key="random_key",
    cookie_expiry_days=30,
)

name, authentication_status, username = authenticator.login()

if authentication_status:
    st.session_state.user = username
    authenticator.logout("Logout", "sidebar")
    # App content here
elif authentication_status is False:
    st.error("Username/password is incorrect")
elif authentication_status is None:
    st.warning("Please enter credentials")
```

### Recommendation for Our Platform

- **Internal team tool (< 10 users)**: streamlit-authenticator with hardcoded credentials
- **Company-wide deployment**: Native OIDC with Microsoft Entra / Google Workspace
- **SaaS product**: Custom auth with JWT tokens + database-backed users

---

## 15. Performance Optimization

### Fragment-Based Optimization (Most Important)

```python
# BAD: Entire page reruns when filter changes
status = st.selectbox("Filter by status", options)
chart = expensive_chart(filtered_data)  # Reruns every time

# GOOD: Only the filtered table reruns, chart stays
@st.fragment
def filterable_table():
    status = st.selectbox("Filter by status", options)
    filtered = df[df["status"] == status] if status else df
    st.dataframe(filtered)

# Chart runs once, doesn't rerun on filter change
chart = expensive_chart(all_data)
filterable_table()  # Fragment — isolated reruns
```

### Performance Checklist

| Technique | Impact | Effort |
|-----------|--------|--------|
| `@st.cache_data` for DB queries | High | Low |
| `@st.fragment` for interactive sections | High | Low |
| `@st.cache_resource` for connections | Medium | Low |
| Pagination (not loading all rows at once) | High | Medium |
| Lazy loading (load data on demand) | High | Medium |
| Polars instead of Pandas for large data | Medium | Medium |
| Reduce widget count per page | Medium | Low |
| Use `st.empty()` containers for dynamic content | Low | Low |
| Minimize session state size | Medium | Low |

### Specific Optimizations for Our App

1. **Company table**: Use AgGrid with server-side pagination — never load 10K+ rows into browser
2. **Enrichment results**: Cache with TTL — don't re-query on every rerun
3. **Charts**: Wrap in fragments so they don't rerun when table filters change
4. **Dashboard metrics**: Use `@st.fragment(run_every=5)` for auto-refresh without full page reload
5. **File uploads**: Process once, cache the parsed DataFrame

---

## 16. Framework Comparison & Alternatives

### Head-to-Head Comparison

| Criterion | Streamlit | Reflex | NiceGUI | Dash | Gradio | Panel |
|-----------|-----------|--------|---------|------|--------|-------|
| **Learning curve** | Very easy | Moderate | Easy | Moderate | Easy | Moderate |
| **Data tables** | Good (AgGrid) | React tables | AG Grid | Dash DataTable | Basic | Tabulator |
| **Real-time updates** | Fragments | WebSocket native | WebSocket native | Callbacks | Limited | Param watching |
| **State management** | session_state | Built-in reactive | Pythonic | Callbacks | Limited | Param-based |
| **Custom styling** | CSS injection | Full CSS/Tailwind | Full CSS | Full CSS | Limited | Full CSS |
| **Auth** | OIDC / library | Custom | Custom | Custom | Basic | Custom |
| **Deployment** | Docker/Cloud | Docker | Docker | Docker/Dash Enterprise | HF Spaces | Docker |
| **Concurrency** | Limited | Good | Good | Good | Limited | Good |
| **Full-stack capability** | No | Yes (Next.js) | Moderate | No | No | No |
| **Community/ecosystem** | Largest | Growing | Small | Large | Large (ML) | Medium |
| **Production maturity** | Medium | Low-Medium | Low | High | Medium | Medium |

### Detailed Framework Assessment

#### Streamlit — RECOMMENDED (with caveats)
**Pros**: Fastest to build, largest ecosystem, great for data apps, excellent DataFrame support, built-in charting, active development by Snowflake.
**Cons**: Full-script rerun model (mitigated by fragments), scaling limits (~50 concurrent users per instance), limited custom styling, no built-in RBAC.
**Verdict**: Best choice for our MVP and initial deployment. Can handle 5-20 internal users easily. Switch only if we outgrow it.

#### Reflex — WATCH
**Pros**: Full-stack Python, compiles to React/Next.js, proper state management, better for complex multi-page apps.
**Cons**: Younger ecosystem, fewer data-specific components, steeper learning curve, may be overkill for a data tool.
**Verdict**: Consider if we need a full web app (customer-facing SaaS) rather than an internal tool.

#### Dash (Plotly) — STRONG ALTERNATIVE
**Pros**: Callback model (no full reruns), production-grade, Dash Enterprise for teams, best charting (Plotly), DataTable component.
**Cons**: More verbose code, steeper learning curve, callbacks can get complex.
**Verdict**: Best alternative if Streamlit's rerun model becomes a bottleneck. More boilerplate but more control.

#### NiceGUI — NICHE
**Pros**: FastAPI backend, desktop-like UI, good for admin panels and forms.
**Cons**: Small community, fewer data-specific components.
**Verdict**: Not ideal for data-heavy tables and enrichment workflows.

#### Gradio — NOT SUITABLE
**Pros**: Great for ML demos, easy API creation.
**Cons**: Not designed for data management tools, limited table support, no complex state management.
**Verdict**: Wrong tool for CRM/data enrichment.

#### Panel — VIABLE
**Pros**: Flexible, works in Jupyter, good for dashboards.
**Cons**: Less intuitive API, smaller community, harder to build complex UIs.
**Verdict**: Could work but Streamlit or Dash are better choices.

### Migration Path

If we outgrow Streamlit:
1. **Phase 1 (now)**: Build with Streamlit — fastest MVP
2. **Phase 2 (if needed)**: Migrate to Dash or Reflex if:
   - We need > 50 concurrent users
   - Full-script reruns become a UX problem
   - We need customer-facing SaaS features (RBAC, multi-tenant)
3. **Phase 3 (if SaaS)**: Consider React + FastAPI if going fully custom

### Decision: Stay with Streamlit

For our GPO platform (internal B2B tool, < 20 users, data-centric), Streamlit is the right choice because:
- Fastest development speed
- Best DataFrame and table ecosystem
- Fragments solve the rerun problem for our use cases
- Background tasks work via threading + shared state
- AgGrid covers our advanced table needs
- We can always migrate later — the business logic layer should be framework-agnostic

---

## 17. Production Deployment

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Streamlit config
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py"]
```

### Docker Compose with Nginx

```yaml
# docker-compose.yml
version: "3.8"

services:
  streamlit:
    build: .
    restart: always
    volumes:
      - ./data:/app/data
      - ./.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro
    environment:
      - STREAMLIT_SERVER_PORT=8501
    networks:
      - app-network

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - streamlit
    networks:
      - app-network

networks:
  app-network:
```

### Nginx Configuration (with WebSocket support)

```nginx
# nginx.conf
upstream streamlit {
    server streamlit:8501;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;

    # WebSocket support (CRITICAL for Streamlit)
    location / {
        proxy_pass http://streamlit;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;  # 24 hours for long connections
        proxy_send_timeout 86400;
    }

    # Health check endpoint
    location /_stcore/health {
        proxy_pass http://streamlit;
    }
}
```

### Secrets Management

| Environment | Method | Details |
|-------------|--------|---------|
| Local dev | `.streamlit/secrets.toml` | Gitignored, per-developer |
| Docker | Environment variables or mounted secrets file | `docker-compose.yml` env section or volume mount |
| Cloud (AWS/GCP) | Secrets Manager + env vars | Inject at container startup |
| Streamlit Cloud | Built-in secrets UI | Web console, encrypted at rest |

```python
# Accessing secrets in code
import streamlit as st

# From secrets.toml or environment
APOLLO_API_KEY = st.secrets.get("APOLLO_API_KEY", "")
HUNTER_API_KEY = st.secrets.get("HUNTER_API_KEY", "")

# With fallback to environment variables
import os
DB_URL = st.secrets.get("DB_URL", os.environ.get("DB_URL", "sqlite:///data/enrichment.db"))
```

### Monitoring

- **Health check**: `GET /_stcore/health` returns 200 when app is running
- **Logging**: Streamlit logs to stdout — capture with Docker logging driver
- **Error tracking**: Use `try/except` with Sentry or custom error handlers
- **Metrics**: Track enrichment jobs, API calls, costs in the database — display in the dashboard

---

## 18. Recommended Architecture for Our Platform

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                    │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │Companies │ │Contacts  │ │Enrichment│ │  Cost     │ │
│  │Table     │ │Table     │ │Dashboard │ │  Dashboard│ │
│  │(AgGrid)  │ │(AgGrid)  │ │(Plotly)  │ │  (Plotly) │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬──────┘ │
│       │             │            │             │        │
│  ┌────▼─────────────▼────────────▼─────────────▼──────┐ │
│  │              Session State Manager                  │ │
│  └────────────────────┬───────────────────────────────┘ │
└───────────────────────┼─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  Service Layer (Python)                   │
│  (No Streamlit imports — pure business logic)            │
│                                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ Enrichment   │ │ Waterfall    │ │ Export/Import    │ │
│  │ Service      │ │ Engine       │ │ Service          │ │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────────┘ │
│         │                │                │              │
│  ┌──────▼────────────────▼────────────────▼───────────┐ │
│  │              Database Layer (SQLite/PostgreSQL)      │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Provider Clients                        │ │
│  │  Apollo | Hunter | Clearbit | ZoomInfo | ...         │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **Separation of concerns**: Service layer has ZERO Streamlit imports — can be tested independently and migrated to any framework
2. **AgGrid for main tables**: Company and Contact tables use streamlit-aggrid for sorting, filtering, selection, and bulk actions
3. **Plotly for charts**: Cost dashboard, enrichment stats, waterfall visualization
4. **Fragments for real-time**: Enrichment progress and dashboard metrics use `@st.fragment(run_every=N)`
5. **Threading for background tasks**: Enrichment jobs run in daemon threads with progress stored in `@st.cache_resource` dict
6. **SQLite for MVP**: Simple, no external dependencies. Migrate to PostgreSQL when scaling
7. **Docker + Nginx for deployment**: HTTPS termination, WebSocket support, health checks

---

## 19. Component Implementation Plans

### Priority Order

| # | Component | Complexity | Streamlit Approach | Dependencies |
|---|-----------|-----------|-------------------|--------------|
| 1 | Company Table | Medium | AgGrid with filters, selection, status badges | streamlit-aggrid |
| 2 | CSV Import + Column Mapping | Medium | st.file_uploader + selectbox mapping grid | pandas |
| 3 | Enrichment Progress Panel | Medium | st.fragment(run_every=2) + st.progress | threading |
| 4 | Contact Table | Medium | AgGrid with email verification badges | streamlit-aggrid |
| 5 | Cost Dashboard | Medium | Plotly bar/line/pie charts + st.metric | plotly |
| 6 | Settings Panel | Low | st.text_input for API keys, st.number_input for budgets | streamlit-authenticator |
| 7 | Waterfall Visualization | Medium | Plotly horizontal bar or custom HTML | plotly |
| 8 | CSV Export Builder | Low | Field checkboxes + st.download_button | pandas |
| 9 | Campaign Progress | Medium | st.fragment + AgGrid with status column | streamlit-aggrid |

### Required Python Packages

```txt
# requirements.txt — UI layer
streamlit>=1.40.0
streamlit-aggrid>=1.0.0
streamlit-authenticator>=0.3.0
plotly>=5.20.0
pandas>=2.2.0
polars>=1.0.0          # For fast CSV processing
openpyxl>=3.1.0        # Excel file support
```

### Key Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AgGrid compatibility with latest Streamlit | Could break table UI | Pin versions, test before upgrading |
| Concurrent enrichment jobs cause memory issues | App crashes | Use SQLite for progress storage instead of in-memory dicts |
| Large CSV uploads (100K+ rows) slow down app | Poor UX | Use Polars, chunked processing, pagination |
| Full-page reruns on complex pages | Laggy UI | Use fragments aggressively, minimize widget count |
| Session state corruption with multiple tabs | Data loss | Use database as source of truth, not session state |

---

## Sources

### Official Documentation
- [Streamlit Multipage Apps](https://docs.streamlit.io/develop/concepts/multipage-apps)
- [st.Page and st.navigation](https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation)
- [Session State](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
- [Caching Overview](https://docs.streamlit.io/develop/concepts/architecture/caching)
- [st.cache_data](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data)
- [st.cache_resource](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource)
- [st.fragment](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
- [Working with Fragments](https://docs.streamlit.io/develop/concepts/architecture/fragments)
- [st.data_editor](https://docs.streamlit.io/develop/api-reference/data/st.data_editor)
- [Custom Components](https://docs.streamlit.io/develop/concepts/custom-components/intro)
- [Theming](https://docs.streamlit.io/develop/concepts/configuration/theming)
- [Authentication](https://docs.streamlit.io/develop/concepts/connections/authentication)
- [Secrets Management](https://docs.streamlit.io/develop/concepts/connections/secrets-management)
- [Display Progress and Status](https://docs.streamlit.io/develop/api-reference/status)
- [Client-Server Architecture](https://docs.streamlit.io/develop/concepts/architecture/architecture)
- [Dataframes](https://docs.streamlit.io/develop/concepts/design/dataframes)
- [2025 Release Notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2025)

### Community & Third-Party
- [Streamlit-AgGrid GitHub](https://github.com/PablocFonseca/streamlit-aggrid)
- [Streamlit-Authenticator GitHub](https://github.com/mkhorasani/Streamlit-Authenticator)
- [Streamlit Component Template](https://github.com/streamlit/component-template)
- [Streamlit Reverse Proxy Demo](https://github.com/shiftlabai/streamlit-reverse-proxy)
- [Microsoft Streamlit UI Template](https://github.com/microsoft/Streamlit_UI_Template)

### Framework Comparisons
- [Reflex vs Streamlit](https://reflex.dev/blog/2025-08-20-reflex-streamlit/)
- [Streamlit vs Dash 2026](https://docs.kanaries.net/topics/Streamlit/streamlit-vs-dash)
- [Best Streamlit Alternatives 2025](https://plotly.com/blog/best-streamlit-alternatives-production-data-apps/)
- [Streamlit vs Gradio 2025](https://www.squadbase.dev/en/blog/streamlit-vs-gradio-in-2025-a-framework-comparison-for-ai-apps)
- [Python Framework Survey](https://ploomber.io/blog/survey-python-frameworks/)
- [Streamlit vs NiceGUI](https://www.bitdoze.com/streamlit-vs-nicegui/)

### Production & Scaling
- [Scaling Streamlit with Task Queue](https://ploomber.io/blog/scaling-streamlit/)
- [Streamlit at Scale: Why My App Froze with 100 Users](https://medium.com/@hadiyolworld007/streamlit-at-scale-why-my-app-froze-with-100-users-666e736fcff0)
- [Concurrent Users Discussion](https://discuss.streamlit.io/t/maximum-number-of-concurrent-users-for-streamlit-app/22438)
- [Background Tasks in Streamlit](https://discuss.streamlit.io/t/how-to-run-a-background-task-in-streamlit-and-notify-the-ui-when-it-finishes/95033)
- [Deploy Streamlit with Nginx + Docker](https://discuss.streamlit.io/t/deploy-streamlit-with-nginx-docker/52907)
- [Deploying Secure Streamlit Apps (Docker + Nginx + HTTPS)](https://medium.com/@sstarr1879/deploying-secure-streamlit-apps-on-aws-ec2-with-docker-nginx-and-https-39bc941f8710)

### Clay UI & Data Enrichment
- [Clay Enrichment Search UI](https://www.clay.com/changelog/find-more-data-with-clays-new-enrichment-search-ui)
- [How to Use Clay Data Enrichment 2026](https://coldiq.com/blog/clay-data-enrichment)
- [What Is Clay](https://pipeline.zoominfo.com/sales/what-is-clay)
- [Clay Data Enrichment via Zapier](https://zapier.com/blog/clay-data-enrichment/)
