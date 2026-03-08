"""Clay-Dupe Enrichment Platform -- Streamlit application entry point.

Configures page layout, initialises shared resources (database, settings),
and wires up the multi-page navigation using ``st.navigation()``.
"""
from __future__ import annotations

import streamlit as st

from config.settings import load_settings, Settings, ProviderName
from data.database import Database
from ui.styles import inject_clay_theme
from ui.validation import validate_api_keys, get_validated_providers


# ---------------------------------------------------------------------------
# Shared resource singletons (safe to call from sub-pages via import)
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


@st.cache_data(ttl=300)
def _cached_validate_api_keys() -> dict[str, bool]:
    """Run API key validation with 5-minute cache."""
    return validate_api_keys(get_settings())


def get_key_validation_status() -> dict[str, bool]:
    """Get current API key validation status (cached)."""
    return _cached_validate_api_keys()


# ---------------------------------------------------------------------------
# UI rendering -- only when run as entry point (streamlit run ui/app.py)
# Guard prevents duplicate element IDs when sub-pages import this module.
# ---------------------------------------------------------------------------

def _is_entry_point() -> bool:
    """Check if this module is being run as the Streamlit entry point."""
    import __main__
    import os
    main_file = getattr(__main__, "__file__", "") or ""
    return os.path.basename(main_file) == "app.py"


if _is_entry_point():
    # Page configuration
    st.set_page_config(
        page_title="Clay-Dupe",
        page_icon=":material/database:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_clay_theme()

    # Startup provider validation
    settings = get_settings()

    key_status = get_key_validation_status()
    valid_providers = [k for k, v in key_status.items() if v]
    invalid_providers = [k for k, v in key_status.items() if not v]

    if not valid_providers:
        st.error(
            "**No valid API keys detected.** Go to Settings to add your API keys. "
            "Without at least one valid provider key, enrichment will not work."
        )
    elif invalid_providers:
        configured_invalid = [
            name for name in invalid_providers
            if settings.providers.get(ProviderName(name), None) is not None
            and settings.providers[ProviderName(name)].enabled
            and settings.providers[ProviderName(name)].api_key
        ]
        if configured_invalid:
            st.warning(
                f"**Invalid API keys detected:** {', '.join(configured_invalid)}. "
                "These providers will be skipped during enrichment."
            )

    # Navigation
    data_pages = [
        st.Page("pages/dashboard.py", title="Overview", icon=":material/dashboard:"),
        st.Page("pages/companies.py", title="Companies", icon=":material/business:"),
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

    # Sidebar branding
    with st.sidebar:
        st.markdown("### Clay-Dupe")
        st.caption("Open-source enrichment platform")
        st.divider()

    # Persistent top toolbar
    _toolbar_left, _toolbar_credits, _toolbar_action = st.columns([6, 2, 2])

    with _toolbar_credits:
        st.caption("Credits remaining: --")

    with _toolbar_action:
        if st.button("Enrich Data", type="primary", icon=":material/bolt:", use_container_width=True, key="toolbar_enrich"):
            st.switch_page("pages/enrich.py")

    # Run the selected page
    pg.run()
