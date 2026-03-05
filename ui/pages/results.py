"""Results page -- browse, filter, and export enrichment results."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import ProviderName
from data.models import EnrichmentResult, VerificationStatus

from data.sync import run_sync
from ui.app import get_database, get_settings

# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Enrichment Results")

db = get_database()

# ---- Sidebar filters --------------------------------------------------------

with st.sidebar:
    st.subheader("Filters")

    # Campaign filter
    campaigns = run_sync(db.get_recent_campaigns(limit=50))
    campaign_options = {"All": None}
    for c in campaigns:
        label = f"{c.name} ({c.created_at:%Y-%m-%d})"
        campaign_options[label] = c.id
    selected_campaign_label = st.selectbox("Campaign", options=list(campaign_options.keys()))
    selected_campaign_id = campaign_options[selected_campaign_label]

    # Status filter
    found_filter = st.selectbox(
        "Result Status",
        options=["All", "Found", "Not Found"],
    )

    # Provider filter
    provider_options = ["All"] + [p.value for p in ProviderName]
    selected_provider = st.selectbox("Provider", options=provider_options)

    # Confidence threshold
    confidence_threshold = st.slider(
        "Min Confidence Score",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=5.0,
    )

    # Pagination
    page_size = st.selectbox("Rows per page", options=[25, 50, 100, 250], index=1)

# ---- Build query filters ----------------------------------------------------

query_filters: dict = {}
if selected_campaign_id:
    query_filters["campaign_id"] = selected_campaign_id
if found_filter == "Found":
    query_filters["found"] = True
elif found_filter == "Not Found":
    query_filters["found"] = False
if selected_provider != "All":
    query_filters["source_provider"] = selected_provider

# ---- Fetch results -----------------------------------------------------------

results: list[EnrichmentResult] = run_sync(db.get_enrichment_results(**query_filters))

# Apply confidence filter client-side
if confidence_threshold > 0:
    results = [
        r for r in results
        if (r.confidence_score or 0) >= confidence_threshold
    ]

if not results:
    st.info("No results match the current filters. Adjust the sidebar filters or run an enrichment first.")
    st.stop()

st.caption(f"**{len(results):,}** results matching filters")

# ---- Pagination --------------------------------------------------------------

total_pages = max(1, (len(results) + page_size - 1) // page_size)

if "results_page" not in st.session_state:
    st.session_state["results_page"] = 1

page_cols = st.columns([1, 3, 1])
with page_cols[0]:
    if st.button("Previous", disabled=st.session_state["results_page"] <= 1):
        st.session_state["results_page"] -= 1
        st.rerun()
with page_cols[1]:
    st.markdown(
        f"<div style='text-align:center'>Page {st.session_state['results_page']} of {total_pages}</div>",
        unsafe_allow_html=True,
    )
with page_cols[2]:
    if st.button("Next", disabled=st.session_state["results_page"] >= total_pages):
        st.session_state["results_page"] += 1
        st.rerun()

start_idx = (st.session_state["results_page"] - 1) * page_size
end_idx = start_idx + page_size
page_results = results[start_idx:end_idx]

# ---- Build dataframe ---------------------------------------------------------

rows = []
for r in page_results:
    # Extract email from result_data if available
    email = ""
    if r.result_data:
        person_data = r.result_data.get("person", r.result_data)
        email = person_data.get("email", "")

    rows.append({
        "Found": "Yes" if r.found else "No",
        "Provider": r.source_provider.value if r.source_provider else "",
        "Type": r.enrichment_type.value if r.enrichment_type else "",
        "Email": email,
        "Confidence": f"{r.confidence_score:.0f}" if r.confidence_score else "--",
        "Verification": r.verification_status.value if r.verification_status else "",
        "Credits": f"{r.cost_credits:.1f}",
        "Response (ms)": r.response_time_ms or "",
        "Cached": "Yes" if r.from_cache else "No",
        "Time": r.found_at.strftime("%Y-%m-%d %H:%M") if r.found_at else "",
    })

df = pd.DataFrame(rows)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Found": st.column_config.TextColumn(width="small"),
        "Cached": st.column_config.TextColumn(width="small"),
        "Credits": st.column_config.TextColumn(width="small"),
    },
)

# ---- Row detail expanders ----------------------------------------------------

st.divider()
st.subheader("Row Details")

for idx, r in enumerate(page_results[:10]):
    label_parts = []
    if r.found:
        label_parts.append(":green[FOUND]")
    else:
        label_parts.append(":red[MISS]")
    label_parts.append(f"[{r.source_provider.value}]" if r.source_provider else "")
    label_parts.append(f"ID: {r.id[:8]}...")

    with st.expander(" ".join(label_parts)):
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

# ---- Export buttons ----------------------------------------------------------

st.divider()
st.subheader("Export")

export_cols = st.columns(3)

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

with export_cols[0]:
    csv_data = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"Download CSV ({len(results):,} rows)",
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
        label=f"Download Excel ({len(results):,} rows)",
        data=buf.getvalue(),
        file_name="enrichment_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
        use_container_width=True,
    )

with export_cols[2]:
    st.caption(f"Total results: {len(results):,}")
    found_count = sum(1 for r in results if r.found)
    st.caption(f"Found: {found_count:,} ({found_count / len(results) * 100:.1f}%)")
