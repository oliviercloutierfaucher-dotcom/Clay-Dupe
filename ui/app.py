"""Clay-Dupe Enrichment Platform -- Streamlit application entry point.

Configures page layout, initialises shared resources (database, settings),
and wires up the multi-page navigation using ``st.navigation()``.
"""
from __future__ import annotations

import streamlit as st

from config.settings import load_settings, Settings, ProviderName
from data.database import Database
from ui.styles import inject_clay_theme


# ---------------------------------------------------------------------------
# Shared resource singletons
# ---------------------------------------------------------------------------

@st.cache_resource
def get_database() -> Database:
    """Return a singleton Database instance (WAL-mode, thread-safe reads)."""
    settings = get_settings()
    return Database(db_path=settings.db_path)


@st.cache_resource
def get_settings() -> Settings:
    """Return a singleton Settings instance loaded from environment."""
    return load_settings()


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Clay-Dupe",
    page_icon=":material/database:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_clay_theme()

# ---------------------------------------------------------------------------
# Startup provider validation
# ---------------------------------------------------------------------------

settings = get_settings()
enabled = settings.get_enabled_providers()
if not enabled:
    st.error(
        "**No API keys configured.** Go to Settings to add your API keys. "
        "Without at least one provider key, enrichment will not work."
    )
else:
    missing_key_providers = [
        pname.value for pname, pcfg in settings.providers.items()
        if pcfg.enabled and not pcfg.api_key
    ]
    if missing_key_providers:
        st.warning(
            f"**Some providers have no API key:** {', '.join(missing_key_providers)}. "
            "These providers will be skipped during enrichment."
        )

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

data_pages = [
    st.Page("pages/dashboard.py", title="Overview", icon=":material/dashboard:"),
    st.Page("pages/search.py", title="Find Leads", icon=":material/search:"),
    st.Page("pages/results.py", title="Data Table", icon=":material/table_chart:", default=True),
]

tools_pages = [
    st.Page("pages/enrich.py", title="Enrich", icon=":material/bolt:"),
    st.Page("pages/analytics.py", title="Analytics", icon=":material/bar_chart:"),
    st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
]

pg = st.navigation(
    {
        "Data": data_pages,
        "Tools": tools_pages,
    }
)

# ---------------------------------------------------------------------------
# Sidebar branding
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Clay-Dupe")
    st.caption("Open-source enrichment platform")
    st.divider()

# ---------------------------------------------------------------------------
# Persistent top toolbar
# ---------------------------------------------------------------------------

_toolbar_left, _toolbar_credits, _toolbar_action = st.columns([6, 2, 2])

with _toolbar_credits:
    st.caption("Credits remaining: --")

with _toolbar_action:
    if st.button("Enrich Data", type="primary", icon=":material/bolt:", use_container_width=True):
        st.switch_page("pages/enrich.py")

# ---------------------------------------------------------------------------
# Run the selected page
# ---------------------------------------------------------------------------

pg.run()
