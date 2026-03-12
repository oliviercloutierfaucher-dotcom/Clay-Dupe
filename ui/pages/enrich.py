"""Enrich page -- Clay-style 2-column panel layout for CSV/Excel enrichment.

Phases:
    A. Upload file (CSV / Excel) at top of page
    B. Configure + Preview in a 2-column layout (left: data table, right: config tabs)
    C. Action bar with Run button
    D. Running state with progress, live log, completion controls
"""
from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from config.settings import ProviderName
from cost.tracker import CostTracker
from data.database import Database
from data.io import read_input_file, ColumnMapper, apply_mapping, deduplicate_rows, COLUMN_ALIASES
from data.models import (
    Campaign,
    CampaignStatus,
    EnrichmentType,
)

from data.sync import run_sync
from ui.app import get_database, get_settings, get_key_validation_status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    return asyncio.run(coro)


def _run_enrichment_bg(campaign_id: str, db_path: str, settings) -> None:
    """Run enrichment in a background daemon thread.

    Creates its own :class:`Database` instance and ``asyncio`` event loop
    to avoid thread-safety issues with aiosqlite connections shared across
    threads.  On success the campaign status is set to COMPLETED; on any
    unhandled exception it is set to FAILED.
    """

    async def _do_enrichment() -> None:
        # Lazy imports to avoid circular dependencies at module level
        from enrichment.waterfall import WaterfallOrchestrator
        from cost.budget import BudgetManager
        from cost.tracker import CostTracker as _CostTracker
        from enrichment.pattern_engine import PatternEngine
        from quality.circuit_breaker import (
            create_circuit_breakers,
            create_rate_limiters,
        )
        from quality.verification import EmailVerifier
        from providers.apollo import ApolloProvider
        from providers.findymail import FindymailProvider
        from providers.icypeas import IcypeasProvider
        from providers.contactout import ContactOutProvider
        from providers.datagma import DatagmaProvider

        # Separate Database instance for this thread
        bg_db = Database(db_path=db_path)

        provider_classes = {
            ProviderName.APOLLO: ApolloProvider,
            ProviderName.FINDYMAIL: FindymailProvider,
            ProviderName.ICYPEAS: IcypeasProvider,
            ProviderName.CONTACTOUT: ContactOutProvider,
            ProviderName.DATAGMA: DatagmaProvider,
        }

        # Build only enabled providers that have API keys
        providers: dict[ProviderName, Any] = {}
        for pname, pcfg in settings.providers.items():
            if pcfg.enabled and pcfg.api_key:
                cls = provider_classes.get(pname)
                if cls is not None:
                    providers[pname] = cls(api_key=pcfg.api_key)

        if not providers:
            logger.error("No providers available for enrichment.")
            await bg_db.update_campaign_status(
                campaign_id, CampaignStatus.FAILED
            )
            return

        budget = BudgetManager(bg_db)
        cost_tracker = _CostTracker(bg_db)
        verifier = EmailVerifier()
        pattern_engine = PatternEngine(bg_db, verifier)
        circuit_breakers = create_circuit_breakers()
        rate_limiters = create_rate_limiters()

        # Apply budget limits from settings
        for pname, pcfg in settings.providers.items():
            if hasattr(pcfg, "daily_credit_limit") and pcfg.daily_credit_limit is not None:
                budget.set_daily_limit(pname, pcfg.daily_credit_limit)
            if hasattr(pcfg, "monthly_credit_limit") and pcfg.monthly_credit_limit is not None:
                budget.set_monthly_limit(pname, pcfg.monthly_credit_limit)

        orchestrator = WaterfallOrchestrator(
            db=bg_db,
            providers=providers,
            pattern_engine=pattern_engine,
            budget=budget,
            circuit_breakers=circuit_breakers,
            rate_limiters=rate_limiters,
            cost_tracker=cost_tracker,
            waterfall_order=settings.waterfall_order,
            verifier=verifier,
        )

        try:
            # Get pending rows for this campaign
            pending = await bg_db.get_pending_rows(campaign_id, limit=10_000)
            row_ids = [r["id"] for r in pending]
            rows = [
                r.get("input_data", r)
                if isinstance(r.get("input_data"), dict)
                else r
                for r in pending
            ]

            # Transition to RUNNING
            await bg_db.update_campaign_status(
                campaign_id, CampaignStatus.RUNNING
            )

            # Execute the waterfall enrichment
            await orchestrator.enrich_batch(
                rows=rows,
                campaign_id=campaign_id,
                campaign_row_ids=row_ids,
            )

            # Mark complete
            await bg_db.update_campaign_status(
                campaign_id, CampaignStatus.COMPLETED
            )
        except Exception:
            logger.exception(
                "Background enrichment failed for campaign %s", campaign_id
            )
            try:
                await bg_db.update_campaign_status(
                    campaign_id, CampaignStatus.FAILED
                )
            except Exception:
                logger.exception(
                    "Failed to mark campaign %s as FAILED", campaign_id
                )
        finally:
            # Gracefully close provider HTTP clients
            for provider in providers.values():
                try:
                    await provider.close()
                except Exception:
                    pass

    asyncio.run(_do_enrichment())


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Enrich")

# Warn if no valid providers exist
_enrich_key_status = get_key_validation_status()
_valid_providers = [k for k, v in _enrich_key_status.items() if v]
if not _valid_providers:
    st.error(
        "**No valid API keys detected.** Enrichment cannot run without at least one "
        "valid provider. Go to Settings to configure and validate your API keys."
    )

db = get_database()
settings = get_settings()

# ===== PHASE D: Running State (takes over the whole page) ==================

campaign_id = st.session_state.get("enrich_campaign_id")
if campaign_id:
    campaign_obj = run_sync(db.get_campaign(campaign_id))
    is_running = campaign_obj and campaign_obj.status in (
        CampaignStatus.CREATED,
        CampaignStatus.RUNNING,
        CampaignStatus.PAUSED,
    )
    is_terminal = campaign_obj and campaign_obj.status in (
        CampaignStatus.COMPLETED,
        CampaignStatus.FAILED,
        CampaignStatus.CANCELLED,
    )
else:
    is_running = False
    is_terminal = False

if campaign_id and (is_running or is_terminal):
    st.subheader("Enrichment In Progress")

    # ---- Start enrichment in background thread (once) ---------------------
    thread_key = f"enrichment_thread_{campaign_id}"
    if thread_key not in st.session_state:
        thread = threading.Thread(
            target=_run_enrichment_bg,
            args=(campaign_id, db.db_path, settings),
            daemon=True,
        )
        thread.start()
        st.session_state[thread_key] = True
        logger.info(
            "Started background enrichment thread for campaign %s",
            campaign_id,
        )

    # ---- Control buttons --------------------------------------------------
    control_cols = st.columns([1, 1, 4])
    with control_cols[0]:
        if st.button("Pause", icon=":material/pause:", use_container_width=True):
            run_sync(db.update_campaign_status(campaign_id, CampaignStatus.PAUSED))
            st.toast("Campaign paused.")
    with control_cols[1]:
        if st.button("Cancel", icon=":material/cancel:", type="secondary", use_container_width=True):
            run_sync(db.update_campaign_status(campaign_id, CampaignStatus.CANCELLED))
            st.toast("Campaign cancelled.")

    st.divider()

    # ---- Progress polling fragment ----------------------------------------
    @st.fragment(run_every=2.0)
    def _poll_progress():
        """Auto-refreshing fragment that polls campaign progress."""
        campaign = run_sync(db.get_campaign(campaign_id))
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
                st.rerun()

        # Live log area
        st.markdown("**Live Log**")
        log_container = st.container(height=200)
        with log_container:
            recent = run_sync(db.get_enrichment_results(campaign_id=campaign_id))
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

    # Stop here -- don't render upload/config below while running
    st.stop()

# ===== PHASE A: Upload =====================================================

uploaded = st.file_uploader(
    "Choose a CSV or Excel file",
    type=["csv", "xlsx", "xls"],
    help="Drag and drop or click to upload. Max 200 MB.",
)

if uploaded is not None:
    # Parse file into session_state (only re-parse when file changes)
    current_filename = st.session_state.get("enrich_filename")
    if current_filename != uploaded.name or "enrich_df" not in st.session_state:
        with st.spinner("Reading file..."):
            try:
                buf = io.BytesIO(uploaded.getvalue())
                df = read_input_file(buf, filename=uploaded.name)
                st.session_state["enrich_df"] = df
                st.session_state["enrich_filename"] = uploaded.name
                # Auto-detect column mapping
                mapper = ColumnMapper(list(df.columns))
                st.session_state["enrich_mapper"] = mapper
            except Exception as exc:
                st.error(f"Failed to read file: {exc}")
                st.stop()

df: pd.DataFrame | None = st.session_state.get("enrich_df")
if df is None:
    st.info("Upload a file to get started.")
    st.stop()

mapper: ColumnMapper = st.session_state.get("enrich_mapper")
if mapper is None:
    mapper = ColumnMapper(list(df.columns))
    st.session_state["enrich_mapper"] = mapper

# ===== PHASE B: Configure + Preview (2-column layout) =====================

left_col, right_col = st.columns([6, 4])

# ----- Left column: Data preview table ------------------------------------
with left_col:
    st.subheader("Data Preview")
    st.dataframe(df, height=500, use_container_width=True)
    st.caption(f"{len(df):,} rows  |  {len(df.columns)} columns  |  {st.session_state.get('enrich_filename', '')}")

# ----- Right column: Configuration tabs -----------------------------------
with right_col:
    tab_configure, tab_mapping, tab_cost = st.tabs(["Configure", "Column Mapping", "Cost Estimate"])

    # --- Tab 1: Configure -------------------------------------------------
    with tab_configure:
        campaign_name = st.text_input(
            "Campaign Name",
            value=st.session_state.get(
                "enrich_campaign_name_val",
                f"Enrich - {st.session_state.get('enrich_filename', 'upload')}",
            ),
            key="enrich_campaign_name",
        )
        st.session_state["enrich_campaign_name_val"] = campaign_name

        st.markdown("**Enrichment Types**")
        selected_types: list[EnrichmentType] = []
        for etype in EnrichmentType:
            if st.checkbox(
                etype.value.title(),
                value=(etype == EnrichmentType.EMAIL),
                key=f"etype_{etype.value}",
            ):
                selected_types.append(etype)
        st.session_state["enrich_types"] = selected_types

        st.markdown("**Waterfall Providers**")
        ordered_providers: list[ProviderName] = []
        for idx, pname in enumerate(settings.waterfall_order):
            pcfg = settings.providers.get(pname)
            enabled = pcfg.enabled if pcfg else False
            has_key = bool(pcfg.api_key) if pcfg else False

            label = pname.value.title()
            if has_key:
                label += "  :green_circle:"
            else:
                label += "  :red_circle: no key"

            checked = st.checkbox(
                label,
                value=(enabled and has_key),
                key=f"wf_{pname.value}",
                disabled=not has_key,
            )
            if checked:
                ordered_providers.append(pname)
        st.session_state["enrich_waterfall"] = ordered_providers

        skip_cached = st.checkbox(
            "Skip cached results",
            value=True,
            key="skip_cached",
        )
        st.session_state["enrich_skip_cached"] = skip_cached

    # --- Tab 2: Column Mapping --------------------------------------------
    with tab_mapping:
        summary = mapper.get_mapping_summary()
        st.metric("Mapping Coverage", f"{summary['coverage']:.0f}%")

        canonical_fields = ["(unmapped)"] + sorted(COLUMN_ALIASES.keys())

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
                new_canon_val = None if new_canon == "(unmapped)" else new_canon
                if new_canon_val != current_canon:
                    mapper.set_mapping(col, new_canon_val)

            with display_cols[2]:
                if score >= 90:
                    st.markdown(f":green[{score}%]")
                elif score >= 70:
                    st.markdown(f":orange[{score}%]")
                elif score > 0:
                    st.markdown(f":red[{score}%]")
                else:
                    st.markdown(":gray[--]")

        # Validation warnings
        validation = mapper.validate()
        if not validation["valid"]:
            st.error(f"Missing required fields: {', '.join(validation['missing'])}")
        for w in validation.get("warnings", []):
            st.warning(w)

    # --- Tab 3: Cost Estimate ---------------------------------------------
    with tab_cost:
        waterfall = st.session_state.get("enrich_waterfall", [])
        skip_cached_val = st.session_state.get("enrich_skip_cached", True)

        total_rows = len(df)

        # Estimate cached rows
        mapped_records = apply_mapping(df, mapper.mapping)
        mapped_records, dupe_count = deduplicate_rows(mapped_records)
        if dupe_count > 0:
            st.info(f"Removed {dupe_count} duplicate rows from input.")

        cached_rows = 0
        if skip_cached_val:
            for rec in mapped_records:
                email = rec.get("email")
                if email and "@" in email:
                    cached_rows += 1

        if waterfall:
            tracker = CostTracker(db)
            estimate = run_sync(tracker.estimate_campaign_cost(
                total_rows=total_rows,
                cached_rows=cached_rows,
                waterfall_order=waterfall,
            ))

            summary_cols = st.columns(3)
            summary_cols[0].metric("Total Rows", f"{estimate['total_rows']:,}")
            summary_cols[1].metric("Cached (skip)", f"{estimate['cached_rows']:,}")
            summary_cols[2].metric("To Enrich", f"{estimate['rows_to_enrich']:,}")

            st.divider()

            # Per-provider breakdown
            for prov, pdata in estimate.get("per_provider", {}).items():
                with st.expander(f"**{prov.title()}**", expanded=True):
                    pcols = st.columns(2)
                    pcols[0].metric("Lookups", f"{pdata['estimated_lookups']:,}")
                    pcols[1].metric("Est. Finds", f"{pdata['estimated_finds']:,}")
                    pcols = st.columns(2)
                    pcols[0].metric("Credits", f"{pdata['estimated_credits']:,.1f}")
                    pcols[1].metric("Cost (USD)", f"${pdata['estimated_cost_usd']:,.4f}")
                    st.caption(f"Hit rate: {pdata['hit_rate_used']}%")

            st.divider()
            total_cols = st.columns(2)
            total_cols[0].metric("Total Credits", f"{estimate['total_estimated_credits']:,.1f}")
            total_cols[1].metric("Total Cost (USD)", f"${estimate['total_estimated_cost_usd']:,.4f}")
        else:
            st.warning("Select at least one provider in the Configure tab to see cost estimates.")

# ===== PHASE C: Action Bar =================================================

st.divider()

# Determine if we can run
validation = mapper.validate()
can_run = (
    validation["valid"]
    and len(st.session_state.get("enrich_types", [])) > 0
    and len(st.session_state.get("enrich_waterfall", [])) > 0
)

action_cols = st.columns([4, 1])
with action_cols[0]:
    if not can_run:
        reasons = []
        if not validation["valid"]:
            reasons.append(f"Missing required column mappings: {', '.join(validation.get('missing', []))}")
        if len(st.session_state.get("enrich_types", [])) == 0:
            reasons.append("Select at least one enrichment type")
        if len(st.session_state.get("enrich_waterfall", [])) == 0:
            reasons.append("Select at least one provider")
        for reason in reasons:
            st.caption(f":orange[{reason}]")

with action_cols[1]:
    run_btn = st.button(
        "Run Enrichment",
        type="primary",
        icon=":material/rocket_launch:",
        use_container_width=True,
        disabled=not can_run,
    )

if run_btn and can_run:
    waterfall = st.session_state.get("enrich_waterfall", [])

    # Apply mapping and deduplicate
    mapped_records = apply_mapping(df, mapper.mapping)
    mapped_records, dupe_count = deduplicate_rows(mapped_records)

    # Build cost estimate for the campaign record
    skip_cached_val = st.session_state.get("enrich_skip_cached", True)
    cached_rows = 0
    if skip_cached_val:
        for rec in mapped_records:
            email = rec.get("email")
            if email and "@" in email:
                cached_rows += 1

    tracker = CostTracker(db)
    estimate = run_sync(tracker.estimate_campaign_cost(
        total_rows=len(df),
        cached_rows=cached_rows,
        waterfall_order=waterfall,
    ))

    # Create campaign
    campaign = Campaign(
        name=st.session_state.get("enrich_campaign_name_val", "Enrichment"),
        input_file=st.session_state.get("enrich_filename"),
        input_row_count=len(df),
        enrichment_types=st.session_state.get("enrich_types", [EnrichmentType.EMAIL]),
        waterfall_order=waterfall,
        column_mapping=mapper.mapping,
        status=CampaignStatus.CREATED,
        total_rows=len(mapped_records),
        estimated_cost_usd=estimate["total_estimated_cost_usd"],
    )
    campaign = run_sync(db.create_campaign(campaign))
    run_sync(db.create_campaign_rows(campaign.id, mapped_records))
    st.session_state["enrich_campaign_id"] = campaign.id
    st.rerun()
