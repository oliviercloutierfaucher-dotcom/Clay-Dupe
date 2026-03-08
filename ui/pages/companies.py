"""Companies page -- company management, ICP scoring, and contact discovery.

Provides:
- Company table with filters (status, source, ICP score)
- Manual company add and CSV import
- ICP profile selector and batch scoring
- Contact discovery (single + batch) via Apollo
- Enrichment queue wiring
"""
from __future__ import annotations

import csv
import io
import uuid

import streamlit as st

from config.settings import ICPPreset, ProviderName, load_all_icp_profiles
from data.models import Company
from data.sync import run_sync
from enrichment.icp_scorer import batch_score_companies, score_company
from ui.app import get_database, get_settings, get_key_validation_status

# ---------------------------------------------------------------------------
# Shared resources
# ---------------------------------------------------------------------------

db = get_database()
settings = get_settings()

st.header("Companies")

# ---------------------------------------------------------------------------
# ICP Profile Selector
# ---------------------------------------------------------------------------

all_profiles = load_all_icp_profiles(db)
profile_names = {key: p.display_name for key, p in all_profiles.items()}
profile_keys = list(profile_names.keys())

if profile_keys:
    selected_idx = st.selectbox(
        "ICP Profile",
        range(len(profile_keys)),
        format_func=lambda i: profile_names[profile_keys[i]],
        key="icp_profile_selector",
    )
    selected_profile_key = profile_keys[selected_idx]
    selected_profile = all_profiles[selected_profile_key]
else:
    selected_profile = None
    st.info("No ICP profiles configured. Go to Settings to create one.")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

with st.expander("Filters", expanded=False):
    filter_cols = st.columns(4)
    with filter_cols[0]:
        f_status = st.selectbox(
            "Status", ["All", "new", "contacted", "skipped"], key="co_filter_status"
        )
    with filter_cols[1]:
        f_source = st.selectbox(
            "Source", ["All", "manual", "csv_import", "apollo_search"], key="co_filter_source"
        )
    with filter_cols[2]:
        f_min_icp = st.number_input(
            "Min ICP Score", min_value=0, max_value=100, value=0, step=5,
            key="co_filter_icp",
        )
    with filter_cols[3]:
        f_country = st.text_input("Country Code", value="", key="co_filter_country")

# Build filter kwargs
search_kwargs: dict = {}
if f_status != "All":
    search_kwargs["status"] = f_status
if f_source != "All":
    search_kwargs["source_type"] = f_source
if f_min_icp > 0:
    search_kwargs["min_icp_score"] = f_min_icp
if f_country.strip():
    search_kwargs["country"] = f_country.strip().upper()

companies: list[Company] = run_sync(db.search_companies(**search_kwargs))

# ---------------------------------------------------------------------------
# Action buttons row
# ---------------------------------------------------------------------------

action_cols = st.columns(4)

with action_cols[0]:
    score_btn = st.button(
        "Score All Companies",
        icon=":material/analytics:",
        use_container_width=True,
        disabled=selected_profile is None,
    )

with action_cols[1]:
    add_btn = st.button(
        "Add Company",
        icon=":material/add_business:",
        use_container_width=True,
    )

with action_cols[2]:
    csv_btn = st.button(
        "Import CSV",
        icon=":material/upload_file:",
        use_container_width=True,
    )

with action_cols[3]:
    # Placeholder for contact discovery (Task 2)
    discover_btn = st.button(
        "Discover Contacts",
        icon=":material/person_search:",
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# Score All Companies
# ---------------------------------------------------------------------------

if score_btn and selected_profile is not None:
    with st.spinner("Scoring companies..."):
        scored = batch_score_companies(companies, selected_profile)
        for comp, score_val in scored:
            comp.icp_score = score_val
            run_sync(db.upsert_company(comp))
        st.success(f"Scored {len(scored)} companies with '{selected_profile.display_name}'")
        st.rerun()

# ---------------------------------------------------------------------------
# Manual Add Company dialog
# ---------------------------------------------------------------------------

if add_btn:
    st.session_state["show_add_company"] = True

if st.session_state.get("show_add_company"):
    with st.expander("Add Company", expanded=True):
        add_cols = st.columns(2)
        with add_cols[0]:
            new_name = st.text_input("Company Name", key="new_co_name")
            new_domain = st.text_input("Domain", key="new_co_domain")
            new_industry = st.text_input("Industry", key="new_co_industry")
        with add_cols[1]:
            new_country = st.text_input("Country", value="US", key="new_co_country")
            new_employees = st.number_input(
                "Employee Count", min_value=0, value=0, step=10, key="new_co_emp"
            )

        save_cols = st.columns(2)
        with save_cols[0]:
            if st.button("Save Company", type="primary", use_container_width=True, key="save_new_co"):
                if not new_name.strip():
                    st.error("Company name is required.")
                else:
                    new_company = Company(
                        name=new_name.strip(),
                        domain=new_domain.strip() if new_domain.strip() else None,
                        industry=new_industry.strip() if new_industry.strip() else None,
                        country=new_country.strip() if new_country.strip() else None,
                        employee_count=new_employees if new_employees > 0 else None,
                        source_type="manual",
                    )
                    # Auto-score if profile selected
                    if selected_profile:
                        new_company.icp_score = score_company(new_company, selected_profile)
                    run_sync(db.upsert_company(new_company))
                    st.success(f"Added: {new_name.strip()}")
                    st.session_state["show_add_company"] = False
                    st.rerun()
        with save_cols[1]:
            if st.button("Cancel", use_container_width=True, key="cancel_new_co"):
                st.session_state["show_add_company"] = False
                st.rerun()

# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------

if csv_btn:
    st.session_state["show_csv_import"] = True

if st.session_state.get("show_csv_import"):
    with st.expander("Import CSV", expanded=True):
        uploaded = st.file_uploader(
            "Upload a CSV file",
            type=["csv"],
            key="csv_upload",
        )
        if uploaded is not None:
            try:
                content = uploaded.read().decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)

                if rows:
                    st.info(f"Found {len(rows)} rows with columns: {', '.join(rows[0].keys())}")

                    # Auto-detect column mappings
                    _col_map = {}
                    for col in rows[0].keys():
                        cl = col.lower().strip()
                        if cl in ("company_name", "name", "company"):
                            _col_map["name"] = col
                        elif cl in ("website", "domain", "url"):
                            _col_map["domain"] = col
                        elif cl in ("industry", "sector"):
                            _col_map["industry"] = col
                        elif cl in ("headcount", "employees", "employee_count", "size"):
                            _col_map["employee_count"] = col
                        elif cl in ("country", "location"):
                            _col_map["country"] = col

                    st.markdown("**Detected mappings:** " + ", ".join(
                        f"{k} -> {v}" for k, v in _col_map.items()
                    ))

                    if st.button("Import", type="primary", key="do_csv_import"):
                        imported = 0
                        for row in rows:
                            name = row.get(_col_map.get("name", ""), "").strip()
                            if not name:
                                continue
                            domain = row.get(_col_map.get("domain", ""), "").strip() or None
                            industry = row.get(_col_map.get("industry", ""), "").strip() or None
                            country = row.get(_col_map.get("country", ""), "").strip() or None
                            emp_str = row.get(_col_map.get("employee_count", ""), "").strip()
                            emp = int(emp_str) if emp_str and emp_str.isdigit() else None

                            comp = Company(
                                name=name,
                                domain=domain,
                                industry=industry,
                                country=country,
                                employee_count=emp,
                                source_type="csv_import",
                            )
                            if selected_profile:
                                comp.icp_score = score_company(comp, selected_profile)
                            run_sync(db.upsert_company(comp))
                            imported += 1

                        st.success(f"Imported {imported} companies")
                        st.session_state["show_csv_import"] = False
                        st.rerun()

            except Exception as exc:
                st.error(f"Error reading CSV: {exc}")

        if st.button("Cancel Import", key="cancel_csv"):
            st.session_state["show_csv_import"] = False
            st.rerun()

# ---------------------------------------------------------------------------
# Company Table
# ---------------------------------------------------------------------------

if not companies:
    st.info("No companies found. Add companies manually, import CSV, or search Apollo.")
else:
    # Build table data with contact info
    table_data = []
    for c in companies:
        # Color-code ICP score
        if c.icp_score is not None:
            if c.icp_score >= 70:
                score_display = f":green[{c.icp_score}]"
            elif c.icp_score >= 40:
                score_display = f":orange[{c.icp_score}]"
            else:
                score_display = f":red[{c.icp_score}]"
        else:
            score_display = "---"

        table_data.append({
            "Name": c.name,
            "Domain": c.domain or "---",
            "Industry": c.industry or "---",
            "Employees": c.employee_count if c.employee_count else "---",
            "Country": c.country or "---",
            "ICP Score": score_display,
            "Source": c.source_type or "---",
            "Status": c.status,
            "Contact": "---",  # Populated in Task 2
        })

    # Use st.dataframe for a sortable table
    st.markdown(f"**{len(companies)} companies**")

    # Display as markdown table for color-coded scores
    for i, row in enumerate(table_data):
        if i == 0:
            # Header
            st.markdown(
                "| Name | Domain | Industry | Employees | Country | ICP Score | Source | Status | Contact |"
            )
            st.markdown(
                "|------|--------|----------|-----------|---------|-----------|--------|--------|---------|"
            )
        st.markdown(
            f"| {row['Name']} | {row['Domain']} | {row['Industry']} | "
            f"{row['Employees']} | {row['Country']} | {row['ICP Score']} | "
            f"{row['Source']} | {row['Status']} | {row['Contact']} |"
        )

    # Also provide a download-friendly dataframe view
    with st.expander("Dataframe view"):
        import pandas as pd
        df_data = []
        for c in companies:
            df_data.append({
                "name": c.name,
                "domain": c.domain,
                "industry": c.industry,
                "employees": c.employee_count,
                "country": c.country,
                "icp_score": c.icp_score,
                "source": c.source_type,
                "status": c.status,
            })
        if df_data:
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
