"""Dashboard page -- key metrics, credit balances, and recent campaigns."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import ProviderName
from cost.budget import BudgetManager
from data.models import CampaignStatus
from data.sync import run_sync
from ui.styles import section_header


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_color(status: str) -> str:
    """Map campaign status to a colour label for st.markdown badges."""
    mapping = {
        "running": "blue",
        "completed": "green",
        "failed": "red",
        "paused": "orange",
        "cancelled": "gray",
        "created": "violet",
        "queued": "violet",
        "mapping": "violet",
    }
    return mapping.get(status, "gray")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Overview")

# Retrieve singletons
from ui.shared import get_database, get_settings, get_key_validation_status  # noqa: E402

db = get_database()
settings = get_settings()

# ---- API Key Status -------------------------------------------------------

key_status = get_key_validation_status()

section_header("Provider Status", "blue")
with st.container(border=True):
    any_invalid = False
    status_cols = st.columns(len(key_status) if key_status else 1)
    for idx, (provider_name, is_valid) in enumerate(key_status.items()):
        with status_cols[idx]:
            if is_valid:
                st.markdown(f":green[**{provider_name.title()}**] :white_check_mark:")
            else:
                st.markdown(f":red[**{provider_name.title()}**] :x:")
                any_invalid = True
    if any_invalid:
        invalid_names = [k for k, v in key_status.items() if not v]
        st.warning(
            f"Enrichment may be limited -- invalid API keys detected: "
            f"{', '.join(invalid_names)}"
        )

# ---- Top-level metric cards ------------------------------------------------

section_header("Key Metrics", "teal")

stats = run_sync(db.get_dashboard_stats())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Enriched", f"{stats['total_enriched']:,}")
col2.metric("Email Find Rate", f"{stats['email_find_rate']}%")
col3.metric("Active Campaigns", stats["total_campaigns"])
col4.metric("Spent (30 d)", f"{stats['cost_30d']:,.1f} credits")

# ---- Compact credit usage --------------------------------------------------

section_header("Credit Usage", "orange")

budget_mgr = BudgetManager(db)

# Apply configured limits from settings
for pname, pcfg in settings.providers.items():
    if pcfg.daily_credit_limit:
        budget_mgr.set_daily_limit(pname, pcfg.daily_credit_limit)
    if pcfg.monthly_credit_limit:
        budget_mgr.set_monthly_limit(pname, pcfg.monthly_credit_limit)

with st.container(border=True):
    for pname in ProviderName:
        balance = run_sync(budget_mgr.get_balance(pname))
        daily_limit = balance["daily_limit"]
        daily_used = balance["daily_used"]

        cols = st.columns([2, 5, 3])
        with cols[0]:
            st.caption(pname.value.title())
        with cols[1]:
            if daily_limit and daily_limit > 0:
                daily_pct = min(daily_used / daily_limit, 1.0)
                st.progress(daily_pct)
            else:
                st.progress(0.0)
        with cols[2]:
            if daily_limit and daily_limit > 0:
                st.caption(f"{daily_used:,.0f} / {daily_limit:,.0f}")
            else:
                st.caption(f"{daily_used:,.0f} (no limit)")

# ---- Recent campaigns table ------------------------------------------------

section_header("Recent Campaigns", "navy")

campaigns = run_sync(db.get_recent_campaigns(limit=10))

if not campaigns:
    st.info("No campaigns yet. Head to the **Enrich** page to create one.")
else:
    campaign_rows = []
    for c in campaigns:
        campaign_rows.append({
            "Status": c.status.value.title(),
            "Campaign": c.name,
            "Progress": f"{c.enriched_rows}/{c.total_rows}",
            "Found": c.found_rows,
            "Failed": c.failed_rows,
            "Credits": f"{c.total_credits_used:,.1f}",
            "Created": c.created_at.strftime("%Y-%m-%d"),
        })
    st.dataframe(
        pd.DataFrame(campaign_rows),
        use_container_width=True,
        hide_index=True,
        height=300,
    )
