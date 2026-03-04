"""Enrich page -- multi-step wizard for CSV/Excel enrichment campaigns.

Steps:
    1. Upload file (CSV / Excel)
    2. Preview first 20 rows
    3. Column mapping with auto-detected dropdowns and fuzzy scores
    4. Configure enrichment types, waterfall order, skip cached
    5. Cost estimate display
    6. Running with progress bar, live log, pause / cancel
"""
from __future__ import annotations

import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from config.settings import ProviderName
from cost.tracker import CostTracker
from data.database import Database
from data.io import read_input_file, ColumnMapper, apply_mapping, COLUMN_ALIASES
from data.models import (
    Campaign,
    CampaignStatus,
    EnrichmentType,
)

from ui.app import get_database, get_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    return asyncio.run(coro)


def _init_step():
    """Ensure session_state has the wizard step initialised."""
    if "enrich_step" not in st.session_state:
        st.session_state["enrich_step"] = 1


def _set_step(step: int):
    st.session_state["enrich_step"] = step


def _step_indicator(current: int, total: int = 6):
    """Render a simple step indicator bar."""
    labels = [
        "Upload",
        "Preview",
        "Map Columns",
        "Configure",
        "Cost Estimate",
        "Run",
    ]
    cols = st.columns(total)
    for i, col in enumerate(cols):
        step_num = i + 1
        label = labels[i]
        if step_num < current:
            col.markdown(f":green[**{step_num}. {label}**]")
        elif step_num == current:
            col.markdown(f":blue[**{step_num}. {label}**]")
        else:
            col.markdown(f":gray[{step_num}. {label}]")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Enrichment Wizard")

_init_step()
current_step = st.session_state["enrich_step"]
_step_indicator(current_step)
st.divider()

db = get_database()
settings = get_settings()

# ===== STEP 1: Upload =======================================================

if current_step == 1:
    st.subheader("Step 1: Upload Your File")

    uploaded = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Drag and drop or click to upload. Max 200 MB.",
    )

    if uploaded is not None:
        with st.spinner("Reading file..."):
            try:
                buf = io.BytesIO(uploaded.getvalue())
                df = read_input_file(buf, filename=uploaded.name)
                st.session_state["enrich_df"] = df
                st.session_state["enrich_filename"] = uploaded.name
                st.success(f"Loaded **{len(df):,}** rows and **{len(df.columns)}** columns.")
                if st.button("Next: Preview Data", type="primary"):
                    _set_step(2)
                    st.rerun()
            except Exception as exc:
                st.error(f"Failed to read file: {exc}")

# ===== STEP 2: Preview ======================================================

elif current_step == 2:
    st.subheader("Step 2: Data Preview")

    df: pd.DataFrame = st.session_state.get("enrich_df")
    if df is None:
        st.warning("No data loaded. Please go back to Step 1.")
        if st.button("Back to Upload"):
            _set_step(1)
            st.rerun()
    else:
        st.caption(
            f"Showing first 20 of **{len(df):,}** rows  |  "
            f"**{len(df.columns)}** columns  |  "
            f"File: {st.session_state.get('enrich_filename', 'unknown')}"
        )
        st.dataframe(df.head(20), use_container_width=True, hide_index=True)

        nav_cols = st.columns([1, 1, 4])
        with nav_cols[0]:
            if st.button("Back", icon=":material/arrow_back:"):
                _set_step(1)
                st.rerun()
        with nav_cols[1]:
            if st.button("Next: Map Columns", type="primary", icon=":material/arrow_forward:"):
                # Auto-detect column mapping
                mapper = ColumnMapper(list(df.columns))
                st.session_state["enrich_mapper"] = mapper
                _set_step(3)
                st.rerun()

# ===== STEP 3: Column Mapping ===============================================

elif current_step == 3:
    st.subheader("Step 3: Column Mapping")

    mapper: ColumnMapper = st.session_state.get("enrich_mapper")
    df: pd.DataFrame = st.session_state.get("enrich_df")

    if mapper is None or df is None:
        st.warning("Session expired. Please start over.")
        if st.button("Start Over"):
            _set_step(1)
            st.rerun()
    else:
        summary = mapper.get_mapping_summary()
        st.metric("Mapping Coverage", f"{summary['coverage']:.0f}%")

        canonical_fields = ["(unmapped)"] + sorted(COLUMN_ALIASES.keys())

        st.markdown("**Adjust column mappings below:**")

        changed = False
        for col in df.columns:
            current_canon = mapper.mapping.get(col)
            score = mapper.match_scores.get(col, 0)

            display_cols = st.columns([3, 3, 1])
            with display_cols[0]:
                st.text(col)
            with display_cols[1]:
                default_idx = (
                    canonical_fields.index(current_canon)
                    if current_canon in canonical_fields
                    else 0
                )
                new_canon = st.selectbox(
                    f"Map '{col}' to",
                    options=canonical_fields,
                    index=default_idx,
                    key=f"map_{col}",
                    label_visibility="collapsed",
                )
                if new_canon == "(unmapped)":
                    new_canon_val = None
                else:
                    new_canon_val = new_canon

                if new_canon_val != current_canon:
                    mapper.set_mapping(col, new_canon_val)
                    changed = True

            with display_cols[2]:
                if score >= 90:
                    st.markdown(f":green[{score}%]")
                elif score >= 70:
                    st.markdown(f":orange[{score}%]")
                elif score > 0:
                    st.markdown(f":red[{score}%]")
                else:
                    st.markdown(":gray[--]")

        # Validation
        validation = mapper.validate()
        if not validation["valid"]:
            st.error(f"Missing required fields: {', '.join(validation['missing'])}")
        for w in validation.get("warnings", []):
            st.warning(w)

        st.divider()
        nav_cols = st.columns([1, 1, 4])
        with nav_cols[0]:
            if st.button("Back", icon=":material/arrow_back:"):
                _set_step(2)
                st.rerun()
        with nav_cols[1]:
            if st.button(
                "Next: Configure",
                type="primary",
                icon=":material/arrow_forward:",
                disabled=not validation["valid"],
            ):
                _set_step(4)
                st.rerun()

# ===== STEP 4: Configure ====================================================

elif current_step == 4:
    st.subheader("Step 4: Configure Enrichment")

    config_cols = st.columns(2)

    with config_cols[0]:
        st.markdown("**Enrichment Types**")
        selected_types: list[EnrichmentType] = []
        for etype in EnrichmentType:
            if st.checkbox(etype.value.title(), value=(etype == EnrichmentType.EMAIL), key=f"etype_{etype.value}"):
                selected_types.append(etype)

        st.session_state["enrich_types"] = selected_types

    with config_cols[1]:
        st.markdown("**Waterfall Order**")
        st.caption("Drag to reorder providers (first provider is tried first).")

        available_providers = [
            p for p in settings.waterfall_order
            if settings.providers[p].enabled and settings.providers[p].api_key
        ]

        # Display ordered list with toggles
        ordered_providers: list[ProviderName] = []
        for idx, pname in enumerate(settings.waterfall_order):
            pcfg = settings.providers.get(pname)
            enabled = pcfg.enabled if pcfg else False
            has_key = bool(pcfg.api_key) if pcfg else False
            label = f"{idx + 1}. {pname.value.title()}"
            if not has_key:
                label += "  (no API key)"
            checked = st.checkbox(
                label,
                value=(enabled and has_key),
                key=f"wf_{pname.value}",
                disabled=not has_key,
            )
            if checked:
                ordered_providers.append(pname)

        st.session_state["enrich_waterfall"] = ordered_providers

    st.divider()

    st.markdown("**Options**")
    skip_cached = st.checkbox("Skip previously cached results", value=True, key="skip_cached")
    st.session_state["enrich_skip_cached"] = skip_cached

    campaign_name = st.text_input(
        "Campaign Name",
        value=f"Enrich - {st.session_state.get('enrich_filename', 'upload')}",
        key="enrich_campaign_name",
    )
    st.session_state["enrich_campaign_name_val"] = campaign_name

    st.divider()
    nav_cols = st.columns([1, 1, 4])
    with nav_cols[0]:
        if st.button("Back", icon=":material/arrow_back:"):
            _set_step(3)
            st.rerun()
    with nav_cols[1]:
        if st.button(
            "Next: Cost Estimate",
            type="primary",
            icon=":material/arrow_forward:",
            disabled=len(selected_types) == 0 or len(ordered_providers) == 0,
        ):
            _set_step(5)
            st.rerun()

# ===== STEP 5: Cost Estimate ================================================

elif current_step == 5:
    st.subheader("Step 5: Cost Estimate")

    df: pd.DataFrame = st.session_state.get("enrich_df")
    mapper: ColumnMapper = st.session_state.get("enrich_mapper")
    waterfall = st.session_state.get("enrich_waterfall", [])
    skip_cached = st.session_state.get("enrich_skip_cached", True)

    if df is None or mapper is None:
        st.warning("Session expired. Please start over.")
        if st.button("Start Over"):
            _set_step(1)
            st.rerun()
    else:
        total_rows = len(df)

        # Estimate cached rows (rough heuristic: count rows with existing emails)
        mapped_records = apply_mapping(df, mapper.mapping)
        cached_rows = 0
        if skip_cached:
            for rec in mapped_records:
                email = rec.get("email")
                if email and "@" in email:
                    cached_rows += 1

        tracker = CostTracker(db)
        estimate = tracker.estimate_campaign_cost(
            total_rows=total_rows,
            cached_rows=cached_rows,
            waterfall_order=waterfall,
        )

        # Display summary
        summary_cols = st.columns(4)
        summary_cols[0].metric("Total Rows", f"{estimate['total_rows']:,}")
        summary_cols[1].metric("Cached (skip)", f"{estimate['cached_rows']:,}")
        summary_cols[2].metric("To Enrich", f"{estimate['rows_to_enrich']:,}")
        summary_cols[3].metric("Est. Unfound", f"{estimate['estimated_unfound_rows']:,}")

        st.divider()

        # Per-provider breakdown
        st.markdown("**Per-Provider Estimate**")
        for prov, pdata in estimate.get("per_provider", {}).items():
            with st.expander(f"**{prov.title()}**", expanded=True):
                pcols = st.columns(4)
                pcols[0].metric("Lookups", f"{pdata['estimated_lookups']:,}")
                pcols[1].metric("Est. Finds", f"{pdata['estimated_finds']:,}")
                pcols[2].metric("Credits", f"{pdata['estimated_credits']:,.1f}")
                pcols[3].metric("Cost (USD)", f"${pdata['estimated_cost_usd']:,.4f}")
                st.caption(f"Hit rate used: {pdata['hit_rate_used']}%")

        st.divider()

        # Totals
        total_cols = st.columns(2)
        total_cols[0].metric("Total Estimated Credits", f"{estimate['total_estimated_credits']:,.1f}")
        total_cols[1].metric("Total Estimated Cost (USD)", f"${estimate['total_estimated_cost_usd']:,.4f}")

        st.divider()
        nav_cols = st.columns([1, 1, 4])
        with nav_cols[0]:
            if st.button("Back", icon=":material/arrow_back:"):
                _set_step(4)
                st.rerun()
        with nav_cols[1]:
            if st.button(
                "Start Enrichment",
                type="primary",
                icon=":material/rocket_launch:",
            ):
                # Create campaign
                campaign = Campaign(
                    name=st.session_state.get("enrich_campaign_name_val", "Enrichment"),
                    input_file=st.session_state.get("enrich_filename"),
                    input_row_count=total_rows,
                    enrichment_types=st.session_state.get("enrich_types", [EnrichmentType.EMAIL]),
                    waterfall_order=waterfall,
                    column_mapping=mapper.mapping,
                    status=CampaignStatus.CREATED,
                    total_rows=len(mapped_records),
                    estimated_cost_usd=estimate["total_estimated_cost_usd"],
                )
                campaign = db.create_campaign(campaign)
                db.create_campaign_rows(campaign.id, mapped_records)
                st.session_state["enrich_campaign_id"] = campaign.id
                _set_step(6)
                st.rerun()

# ===== STEP 6: Running ======================================================

elif current_step == 6:
    st.subheader("Step 6: Enrichment Running")

    campaign_id = st.session_state.get("enrich_campaign_id")
    if not campaign_id:
        st.warning("No active campaign. Please start over.")
        if st.button("Start Over"):
            _set_step(1)
            st.rerun()
    else:
        # ---- Control buttons ------------------------------------------------

        control_cols = st.columns([1, 1, 4])

        with control_cols[0]:
            if st.button("Pause", icon=":material/pause:", use_container_width=True):
                db.update_campaign_status(campaign_id, CampaignStatus.PAUSED)
                st.toast("Campaign paused.")

        with control_cols[1]:
            if st.button("Cancel", icon=":material/cancel:", type="secondary", use_container_width=True):
                db.update_campaign_status(campaign_id, CampaignStatus.CANCELLED)
                st.toast("Campaign cancelled.")

        st.divider()

        # ---- Progress polling fragment --------------------------------------

        @st.fragment(run_every=2.0)
        def _poll_progress():
            """Auto-refreshing fragment that polls campaign progress."""
            campaign = db.get_campaign(campaign_id)
            if campaign is None:
                st.error("Campaign not found.")
                return

            total = max(campaign.total_rows, 1)
            enriched = campaign.enriched_rows
            found = campaign.found_rows
            failed = campaign.failed_rows
            progress_frac = min(enriched / total, 1.0)

            # Metrics row
            m_cols = st.columns(5)
            m_cols[0].metric("Status", campaign.status.value.upper())
            m_cols[1].metric("Progress", f"{enriched}/{total}")
            m_cols[2].metric("Found", found)
            m_cols[3].metric("Failed", failed)
            m_cols[4].metric("Credits Used", f"{campaign.total_credits_used:,.1f}")

            # Progress bar
            st.progress(progress_frac, text=f"{progress_frac * 100:.1f}% complete")

            # Cost breakdown
            if campaign.cost_by_provider:
                st.markdown("**Cost by Provider**")
                cost_cols = st.columns(len(campaign.cost_by_provider))
                for i, (prov, cost) in enumerate(campaign.cost_by_provider.items()):
                    cost_cols[i].metric(prov.title(), f"{cost:,.1f} credits")

            # Completion state
            if campaign.status in (
                CampaignStatus.COMPLETED,
                CampaignStatus.FAILED,
                CampaignStatus.CANCELLED,
            ):
                if campaign.status == CampaignStatus.COMPLETED:
                    st.success("Enrichment completed successfully!")
                elif campaign.status == CampaignStatus.FAILED:
                    st.error("Enrichment failed.")
                else:
                    st.warning("Enrichment was cancelled.")

                if st.button("View Results", type="primary", icon=":material/table_chart:"):
                    st.switch_page("pages/results.py")

                if st.button("Start New Enrichment", icon=":material/add:"):
                    for key in list(st.session_state.keys()):
                        if key.startswith("enrich_"):
                            del st.session_state[key]
                    _set_step(1)
                    st.rerun()

            # Live log area
            st.markdown("**Live Log**")
            log_container = st.container(height=200)
            with log_container:
                # Show recent enrichment results for this campaign
                recent = db.get_enrichment_results(campaign_id=campaign_id)
                for r in recent[:20]:
                    icon = ":white_check_mark:" if r.found else ":x:"
                    provider = r.source_provider.value if r.source_provider else "?"
                    email_display = r.email if r.found and hasattr(r, "email") else ""
                    result_email = r.result_data.get("email", "") if r.result_data else ""
                    display_email = email_display or result_email
                    st.text(
                        f"{icon} [{provider}] "
                        f"{'Found' if r.found else 'Miss'} "
                        f"{display_email}  "
                        f"({r.response_time_ms or 0}ms, {r.cost_credits} credits)"
                    )

        _poll_progress()

# ===== Fallback ==============================================================
else:
    st.warning("Unknown step. Resetting wizard.")
    _set_step(1)
    st.rerun()
