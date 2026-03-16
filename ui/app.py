"""Permanent Enrichment Tool -- Streamlit application entry point.

Configures page layout, initialises shared resources (database, settings),
and wires up the multi-page navigation using ``st.navigation()``.
"""
from __future__ import annotations

import base64
import hmac
import os
from pathlib import Path

import streamlit as st

from ui.styles import inject_permanent_theme

# ---------------------------------------------------------------------------
# Logo helper
# ---------------------------------------------------------------------------

_ASSETS_DIR = Path(__file__).parent / "assets"


def _logo_html(height: int = 40, centered: bool = False, variant: str = "default") -> str:
    """Return an <img> tag with the Permanent logo embedded as base64.

    Args:
        height: Logo height in pixels.
        centered: Center the logo horizontally.
        variant: 'default' (blue on light bg) or 'white' (white text for dark bg).
    """
    filename = "logo-white.svg" if variant == "white" else "logo.svg"
    svg_bytes = (_ASSETS_DIR / filename).read_bytes()
    b64 = base64.b64encode(svg_bytes).decode()
    style = f'height: {height}px;'
    if centered:
        return (
            f'<div style="text-align: center; margin: 48px 0 4px 0;">'
            f'<img src="data:image/svg+xml;base64,{b64}" style="{style}" />'
            f'</div>'
        )
    return (
        f'<div style="padding: 8px 0 4px 0;">'
        f'<img src="data:image/svg+xml;base64,{b64}" style="{style}" />'
        f'</div>'
    )


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

    # Login page with Permanent branding
    st.markdown(_logo_html(height=52, centered=True), unsafe_allow_html=True)
    st.markdown(
        '<p style="text-align: center; color: #64748b; font-size: 0.85rem; margin-bottom: 32px;">'
        'Enrichment Tool</p>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        entered = st.text_input("Password", type="password", key="login_password")
        if st.button("Log in", type="primary", use_container_width=True):
            if hmac.compare_digest(entered, password):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password")
    return False


# ---------------------------------------------------------------------------
# UI rendering -- entry point only (streamlit run ui/app.py)
# ---------------------------------------------------------------------------

# Page configuration
st.set_page_config(
    page_title="Permanent Enrichment Tool",
    page_icon=":material/corporate_fare:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_permanent_theme()

# Authentication gate -- blocks all pages until authenticated
if not check_password():
    st.stop()

# Navigation — flat list, no section groupings (matches Sourcing Dashboard)
pages = [
    st.Page("pages/dashboard.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("pages/companies.py", title="Companies", icon=":material/business:"),
    st.Page("pages/search.py", title="Find Leads", icon=":material/search:"),
    st.Page("pages/results.py", title="Data Table", icon=":material/table_chart:"),
    st.Page("pages/enrich.py", title="Enrich", icon=":material/bolt:"),
    st.Page("pages/emails.py", title="Emails", icon=":material/email:"),
    st.Page("pages/analytics.py", title="Analytics", icon=":material/bar_chart:"),
    st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
]

pg = st.navigation(pages)

# Sidebar branding
st.logo(
    str(_ASSETS_DIR / "logo.svg"),
    icon_image=str(_ASSETS_DIR / "logo-white.svg"),
    size="large",
)

# Run the selected page
pg.run()
