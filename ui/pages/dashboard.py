"""Dashboard page -- key metrics, credit balances, and recent campaigns."""
from __future__ import annotations

import streamlit as st

from config.settings import ProviderName
from cost.budget import BudgetManager
from data.models import CampaignStatus
from data.sync import run_sync


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

st.header("Dashboard")

# Retrieve singletons from app.py cache
from ui.app import get_database, get_settings  # noqa: E402

db = get_database()
settings = get_settings()

# ---- Top-level metric cards ------------------------------------------------

stats = run_sync(db.get_dashboard_stats())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Enriched", f"{stats['total_enriched']:,}")
col2.metric("Email Find Rate", f"{stats['email_find_rate']}%")
col3.metric("Active Campaigns", stats["total_campaigns"])
col4.metric("Spent (30 d)", f"{stats['cost_30d']:,.1f} credits")

st.divider()

# ---- Credit remaining bars per provider ------------------------------------

st.subheader("Credit Balances")

budget_mgr = BudgetManager(db)

# Apply configured limits from settings
for pname, pcfg in settings.providers.items():
    if pcfg.daily_credit_limit:
        budget_mgr.set_daily_limit(pname, pcfg.daily_credit_limit)
    if pcfg.monthly_credit_limit:
        budget_mgr.set_monthly_limit(pname, pcfg.monthly_credit_limit)

provider_cols = st.columns(len(ProviderName))
for idx, pname in enumerate(ProviderName):
    with provider_cols[idx]:
        balance = run_sync(budget_mgr.get_balance(pname))
        st.markdown(f"**{pname.value.title()}**")

        # Daily usage bar
        daily_limit = balance["daily_limit"]
        daily_used = balance["daily_used"]
        if daily_limit and daily_limit > 0:
            daily_pct = min(daily_used / daily_limit, 1.0)
            st.progress(daily_pct, text=f"Daily: {daily_used:,.0f} / {daily_limit:,.0f}")
        else:
            st.caption(f"Daily: {daily_used:,.0f} (no limit)")

        # Monthly usage bar
        monthly_limit = balance["monthly_limit"]
        monthly_used = balance["monthly_used"]
        if monthly_limit and monthly_limit > 0:
            monthly_pct = min(monthly_used / monthly_limit, 1.0)
            st.progress(monthly_pct, text=f"Monthly: {monthly_used:,.0f} / {monthly_limit:,.0f}")
        else:
            st.caption(f"Monthly: {monthly_used:,.0f} (no limit)")

        if balance.get("at_daily_cap") or balance.get("at_monthly_cap"):
            st.warning("Near budget cap", icon=":material/warning:")

st.divider()

# ---- Recent campaigns table ------------------------------------------------

st.subheader("Recent Campaigns")

campaigns = run_sync(db.get_recent_campaigns(limit=10))

if not campaigns:
    st.info("No campaigns yet. Head to the **Enrich** page to create one.")
else:
    for c in campaigns:
        status_label = c.status.value
        color = _status_color(status_label)
        progress_pct = (
            c.enriched_rows / c.total_rows * 100 if c.total_rows > 0 else 0
        )

        with st.expander(
            f":{color}[{status_label.upper()}] **{c.name}**  --  "
            f"{c.enriched_rows}/{c.total_rows} rows  ({progress_pct:.0f}%)",
            expanded=False,
        ):
            meta_cols = st.columns(4)
            meta_cols[0].metric("Found", c.found_rows)
            meta_cols[1].metric("Failed", c.failed_rows)
            meta_cols[2].metric("Skipped", c.skipped_rows)
            meta_cols[3].metric("Credits", f"{c.total_credits_used:,.1f}")

            if c.description:
                st.caption(c.description)

            st.caption(f"Created: {c.created_at:%Y-%m-%d %H:%M}")

            if c.status == CampaignStatus.RUNNING:
                st.progress(
                    min(progress_pct / 100.0, 1.0),
                    text=f"Processing row {c.last_processed_row} of {c.total_rows}",
                )

st.divider()

# ---- Quick action buttons ---------------------------------------------------

st.subheader("Quick Actions")

action_cols = st.columns(4)

with action_cols[0]:
    if st.button("New Enrichment", icon=":material/bolt:", use_container_width=True):
        st.switch_page("pages/enrich.py")

with action_cols[1]:
    if st.button("Search Companies", icon=":material/search:", use_container_width=True):
        st.switch_page("pages/search.py")

with action_cols[2]:
    if st.button("View Results", icon=":material/table_chart:", use_container_width=True):
        st.switch_page("pages/results.py")

with action_cols[3]:
    if st.button("Analytics", icon=":material/bar_chart:", use_container_width=True):
        st.switch_page("pages/analytics.py")
