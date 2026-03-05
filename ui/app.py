"""Clay-Dupe Enrichment Platform -- Streamlit application entry point.

Configures page layout, initialises shared resources (database, settings),
and wires up the multi-page navigation using ``st.navigation()``.
"""
from __future__ import annotations

import streamlit as st

from config.settings import load_settings, Settings, ProviderName
from data.database import Database


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

enrichment_pages = [
    st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    st.Page("pages/search.py", title="Search", icon=":material/search:"),
    st.Page("pages/enrich.py", title="Enrich", icon=":material/bolt:"),
    st.Page("pages/results.py", title="Results", icon=":material/table_chart:"),
]

analytics_config_pages = [
    st.Page("pages/analytics.py", title="Analytics", icon=":material/bar_chart:"),
    st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
]

pg = st.navigation(
    {
        "Enrichment": enrichment_pages,
        "Analytics & Config": analytics_config_pages,
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
# Run the selected page
# ---------------------------------------------------------------------------

pg.run()
