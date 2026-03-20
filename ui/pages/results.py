"""Results page -- browse, filter, and export enrichment results."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from config.settings import ProviderName
from data.models import EnrichmentResult, VerificationStatus

from data.sync import run_sync
from ui.shared import get_database, get_settings
from ui.styles import page_header, empty_state

# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

db = get_database()

# ---- Header ---------------------------------------------------------------

page_header("Data Table", "Browse and export enrichment results")

# ---- Inline filter bar ----------------------------------------------------

campaigns = run_sync(db.get_recent_campaigns(limit=50))
campaign_options = {"All": None}
for c in campaigns:
    label = f"{c.name} ({c.created_at:%Y-%m-%d})"
    campaign_options[label] = c.id

with st.container():
    filter_cols = st.columns([2, 2, 2, 2, 1])
    with filter_cols[0]:
        selected_campaign_label = st.selectbox(
            "Campaign", options=list(campaign_options.keys()), label_visibility="collapsed",
            help="Filter by campaign",
        )
        selected_campaign_id = campaign_options[selected_campaign_label]
    with filter_cols[1]:
        found_filter = st.selectbox(
            "Result Status",
            options=["All", "Found", "Not Found"],
            label_visibility="collapsed",
            help="Filter by result status",
        )
    with filter_cols[2]:
        provider_options = ["All"] + [p.value for p in ProviderName]
        selected_provider = st.selectbox(
            "Provider", options=provider_options,
            label_visibility="collapsed",
            help="Filter by provider",
        )
    with filter_cols[3]:
        confidence_threshold = st.slider(
            "Min Confidence",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=5.0,
            help="Minimum confidence score",
        )
    with filter_cols[4]:
        page_size = st.selectbox(
            "Rows",
            options=[25, 50, 100, 250],
            index=1,
            label_visibility="collapsed",
            help="Rows per page",
        )

# ---- Build query filters ---------------------------------------------------

query_filters: dict = {}
if selected_campaign_id:
    query_filters["campaign_id"] = selected_campaign_id
if found_filter == "Found":
    query_filters["found"] = True
elif found_filter == "Not Found":
    query_filters["found"] = False
if selected_provider != "All":
    query_filters["source_provider"] = selected_provider

# ---- Fetch results ----------------------------------------------------------

results: list[EnrichmentResult] = run_sync(db.get_enrichment_results(**query_filters))

# Apply confidence filter client-side
if confidence_threshold > 0:
    results = [
        r for r in results
        if (r.confidence_score or 0) >= confidence_threshold
    ]

if not results:
    empty_state("No results match the current filters. Adjust filters above or run an enrichment.", "filter_alt_off")
    st.stop()

# ---- Compact pagination -----------------------------------------------------

total_pages = max(1, (len(results) + page_size - 1) // page_size)

if "results_page" not in st.session_state:
    st.session_state["results_page"] = 1
# Clamp page to valid range after filter changes
if st.session_state["results_page"] > total_pages:
    st.session_state["results_page"] = total_pages

page_cols = st.columns([1, 4, 1])
with page_cols[0]:
    if st.button(":material/chevron_left: Prev", disabled=st.session_state["results_page"] <= 1, use_container_width=True):
        st.session_state["results_page"] -= 1
        st.rerun()
with page_cols[1]:
    st.caption(
        f"<div style='text-align:center'>"
        f"**{len(results):,}** results | Page {st.session_state['results_page']} of {total_pages}"
        f"</div>",
        unsafe_allow_html=True,
    )
with page_cols[2]:
    if st.button("Next :material/chevron_right:", disabled=st.session_state["results_page"] >= total_pages, use_container_width=True):
        st.session_state["results_page"] += 1
        st.rerun()

start_idx = (st.session_state["results_page"] - 1) * page_size
end_idx = start_idx + page_size
page_results = results[start_idx:end_idx]

# ---- Build dataframe --------------------------------------------------------

rows = []
for r in page_results:
    # Extract email from result_data if available
    email = ""
    if r.result_data:
        person_data = r.result_data.get("person", r.result_data)
        email = person_data.get("email", "")

    rows.append({
        "Found": r.found,
        "Provider": r.source_provider.value if r.source_provider else "",
        "Type": r.enrichment_type.value if r.enrichment_type else "",
        "Email": email,
        "Confidence": r.confidence_score if r.confidence_score else 0.0,
        "Verification": r.verification_status.value if r.verification_status else "",
        "Credits": f"{r.cost_credits:.1f}",
        "Response (ms)": r.response_time_ms or "",
        "Cached": r.from_cache,
        "Time": r.found_at.strftime("%Y-%m-%d %H:%M") if r.found_at else "",
    })

df = pd.DataFrame(rows)

# ---- Hero table with selection ----------------------------------------------

event = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    height=600,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Found": st.column_config.CheckboxColumn("Found", width="small"),
        "Provider": st.column_config.TextColumn("Provider"),
        "Type": st.column_config.TextColumn("Type"),
        "Email": st.column_config.TextColumn("Email"),
        "Confidence": st.column_config.ProgressColumn(
            "Confidence",
            min_value=0,
            max_value=100,
            format="%.0f",
        ),
        "Verification": st.column_config.TextColumn("Verification"),
        "Credits": st.column_config.TextColumn("Credits", width="small"),
        "Response (ms)": st.column_config.TextColumn("Response (ms)"),
        "Cached": st.column_config.CheckboxColumn("Cached", width="small"),
        "Time": st.column_config.TextColumn("Time"),
    },
)

# ---- Row detail via selection -----------------------------------------------

selected_rows = event.selection.rows if event and event.selection else []

if selected_rows:
    selected_idx = selected_rows[0]
    r = page_results[selected_idx]

    with st.container(border=True):
        st.caption(f"Detail for result `{r.id[:12]}...`")
        detail_cols = st.columns(3)
        with detail_cols[0]:
            st.markdown("**Query Input**")
            st.json(r.query_input)
        with detail_cols[1]:
            st.markdown("**Result Data**")
            st.json(r.result_data)
        with detail_cols[2]:
            st.markdown("**Metadata**")
            st.markdown(f"- **ID:** `{r.id}`")
            st.markdown(f"- **Person ID:** `{r.person_id or 'N/A'}`")
            st.markdown(f"- **Campaign ID:** `{r.campaign_id or 'N/A'}`")
            st.markdown(f"- **Confidence:** {r.confidence_score or 'N/A'}")
            st.markdown(f"- **Verification:** {r.verification_status.value if r.verification_status else 'N/A'}")
            st.markdown(f"- **Waterfall Position:** {r.waterfall_position or 'N/A'}")
            st.markdown(f"- **Credits:** {r.cost_credits}")
            st.markdown(f"- **Cost (USD):** {r.cost_usd or 'N/A'}")
            st.markdown(f"- **From Cache:** {'Yes' if r.from_cache else 'No'}")

# ---- Compact export row -----------------------------------------------------

# Build export dataframe from ALL filtered results (not just current page)
export_rows = []
for r in results:
    email = ""
    if r.result_data:
        person_data = r.result_data.get("person", r.result_data)
        email = person_data.get("email", "")
    export_rows.append({
        "Result ID": r.id,
        "Person ID": r.person_id or "",
        "Campaign ID": r.campaign_id or "",
        "Found": r.found,
        "Provider": r.source_provider.value if r.source_provider else "",
        "Enrichment Type": r.enrichment_type.value if r.enrichment_type else "",
        "Email": email,
        "Confidence Score": r.confidence_score or "",
        "Verification Status": r.verification_status.value if r.verification_status else "",
        "Credits Used": r.cost_credits,
        "Cost USD": r.cost_usd or "",
        "Response Time (ms)": r.response_time_ms or "",
        "From Cache": r.from_cache,
        "Waterfall Position": r.waterfall_position or "",
        "Found At": r.found_at.isoformat() if r.found_at else "",
    })

export_df = pd.DataFrame(export_rows)

found_count = sum(1 for r in results if r.found)
export_cols = st.columns([1, 1, 2])

with export_cols[0]:
    csv_data = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"CSV ({len(results):,})",
        data=csv_data,
        file_name="enrichment_results.csv",
        mime="text/csv",
        icon=":material/download:",
        use_container_width=True,
    )

with export_cols[1]:
    buf = io.BytesIO()
    export_df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        label=f"Excel ({len(results):,})",
        data=buf.getvalue(),
        file_name="enrichment_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
        use_container_width=True,
    )

with export_cols[2]:
    st.caption(
        f"**{len(results):,}** total results &bull; "
        f"**{found_count:,}** found ({found_count / len(results) * 100:.1f}%) &bull; "
        f"**{len(results) - found_count:,}** not found"
    )
