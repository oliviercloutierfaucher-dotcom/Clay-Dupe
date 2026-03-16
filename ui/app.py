"""Clay-Dupe Enrichment Platform -- Streamlit application entry point.

Configures page layout, initialises shared resources (database, settings),
and wires up the multi-page navigation using ``st.navigation()``.
"""
from __future__ import annotations

import hmac
import os

import streamlit as st

from config.settings import ProviderName
from ui.shared import get_settings, get_key_validation_status
from ui.styles import inject_clay_theme
from ui.validation import validate_salesforce


# ---------------------------------------------------------------------------
# Authentication gate
# ---------------------------------------------------------------------------


def _get_app_password() -> str:
    """Get app password from secrets.toml or environment variable."""
    try:
        return st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        return os.getenv("APP_PASSWORD", "")


def check_password() -> bool:
    """Show login form and return True if authenticated.

    Fallback chain: st.secrets -> APP_PASSWORD env var -> warn and allow.
    Uses hmac.compare_digest for timing-safe comparison.
    """
    if st.session_state.get("authenticated"):
        return True

    password = _get_app_password()
    if not password:
        st.warning(
            "No APP_PASSWORD configured. "
            "Set it in .streamlit/secrets.toml or as environment variable."
        )
        return True

    st.markdown("### Clay-Dupe Login")
    entered = st.text_input("Password", type="password", key="login_password")
    if st.button("Log in", type="primary"):
        if hmac.compare_digest(entered, password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False


# ---------------------------------------------------------------------------
# UI rendering -- entry point only (streamlit run ui/app.py)
# No pages import this module, so no guard needed.
# ---------------------------------------------------------------------------

# Page configuration
st.set_page_config(
    page_title="Clay-Dupe",
    page_icon=":material/database:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_clay_theme()

# Authentication gate -- blocks all pages until authenticated
if not check_password():
    st.stop()

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

# Salesforce connection status
sf_status = validate_salesforce()
if sf_status.get("configured") and not sf_status.get("connected"):
    st.warning(
        "**Salesforce connection failed.** SF dedup will be skipped during enrichment. "
        "Check your credentials in Settings."
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
    st.Page("pages/emails.py", title="Emails", icon=":material/email:"),
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
