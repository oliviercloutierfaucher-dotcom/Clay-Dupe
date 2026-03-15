"""Companies page -- company management, ICP scoring, and contact discovery.

Provides:
- Company table with filters (status, source, ICP score, name/domain search)
- Manual company add and CSV import (with ColumnMapper auto-detection)
- ICP profile selector and batch scoring
- Contact discovery (single + batch) via Apollo
- Bulk status management
- Enrichment queue wiring
"""
from __future__ import annotations

import io
import uuid

import pandas as pd
import streamlit as st

from config.settings import ICPPreset, ProviderName, load_all_icp_profiles
from data.io import ColumnMapper, read_input_file, map_to_companies
from data.models import Company, Person
from data.sync import run_sync
from enrichment.contact_discovery import discover_contact, batch_discover_contacts
from enrichment.icp_scorer import batch_score_companies, score_company
from providers.apollo import ApolloProvider
from ui.shared import get_database, get_settings, get_key_validation_status

# ---------------------------------------------------------------------------
# Shared resources
# ---------------------------------------------------------------------------

db = get_database()
settings = get_settings()

st.header("Companies")

# ---------------------------------------------------------------------------
# Apollo availability check
# ---------------------------------------------------------------------------

key_status = get_key_validation_status()
apollo_available = key_status.get("apollo", False)
apollo_key = settings.providers.get(ProviderName.APOLLO)

if not apollo_available:
    st.warning(
        "Apollo API key is not configured or invalid. "
        "Contact discovery requires a valid Apollo master key. "
        "Go to Settings to configure it."
    )

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

filter_cols = st.columns([2, 2, 2, 2, 2, 3])
with filter_cols[0]:
    f_status = st.selectbox(
        "Status", ["All", "new", "contacted", "skipped"], key="co_filter_status"
    )
with filter_cols[1]:
    f_source = st.selectbox(
        "Source", ["All", "apollo_search", "csv_import", "manual"], key="co_filter_source"
    )
with filter_cols[2]:
    f_min_icp = st.slider(
        "Min ICP Score", min_value=0, max_value=100, value=0,
        key="co_filter_icp",
    )
with filter_cols[3]:
    f_country = st.text_input("Country Code", value="", key="co_filter_country")
with filter_cols[4]:
    f_sf_status = st.selectbox(
        "SF Status", ["All", "In SF", "Not in SF"], key="co_filter_sf_status"
    )
with filter_cols[5]:
    f_search = st.text_input(
        "Search (name/domain)", value="", key="co_filter_search",
    )

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

# Client-side text search (name/domain)
if f_search.strip():
    _search_lower = f_search.strip().lower()
    companies = [
        c for c in companies
        if (c.name and _search_lower in c.name.lower())
        or (c.domain and _search_lower in c.domain.lower())
    ]

# Client-side SF status filter
if f_sf_status == "In SF":
    companies = [c for c in companies if c.sf_status == "in_sf"]
elif f_sf_status == "Not in SF":
    companies = [c for c in companies if c.sf_status is None]

# ---------------------------------------------------------------------------
# Load contacts for display in table
# ---------------------------------------------------------------------------


def _load_contacts_by_company(company_list: list[Company]) -> dict[str, Person]:
    """Load contacts keyed by company_id for display in the table."""
    contacts: dict[str, Person] = {}
    for comp in company_list:
        if comp.domain:
            people = run_sync(db.search_people(company_domain=comp.domain))
            if people:
                contacts[comp.id] = people[0]
    return contacts


contacts_map = _load_contacts_by_company(companies) if companies else {}

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
    discover_btn = st.button(
        "Discover Contacts",
        icon=":material/person_search:",
        use_container_width=True,
        disabled=not apollo_available,
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
# Batch Contact Discovery
# ---------------------------------------------------------------------------

if discover_btn and apollo_available:
    companies_needing_contacts = [
        c for c in companies if c.id not in contacts_map and c.domain
    ]

    if not companies_needing_contacts:
        st.info("All displayed companies already have contacts or lack domains.")
    else:
        with st.container(border=True):
            st.markdown(
                f"**Discover contacts at {len(companies_needing_contacts)} companies**"
            )
            st.caption(
                "This will search Apollo for CEO/Owner/Founder at each company. "
                "Rate-limited to respect Apollo's 50 req/min limit."
            )
            if st.button("Confirm Discovery", type="primary", key="confirm_discover"):
                apollo = ApolloProvider(api_key=apollo_key.api_key)
                progress = st.progress(0, text="Discovering contacts...")

                async def _progress_cb(current: int, total: int):
                    progress.progress(
                        (current + 1) / total,
                        text=f"Processing {current + 1}/{total}..."
                    )

                results = run_sync(
                    batch_discover_contacts(
                        apollo, companies_needing_contacts,
                        progress_callback=_progress_cb,
                    ),
                    timeout=300.0,
                )

                found_count = 0
                for comp, person in results:
                    if person is not None:
                        person.company_id = comp.id
                        person.company_domain = comp.domain
                        person.company_name = comp.name
                        run_sync(db.upsert_person(person))
                        found_count += 1

                progress.empty()
                st.success(
                    f"Found contacts at {found_count}/{len(companies_needing_contacts)} companies"
                )

                if found_count > 0:
                    st.session_state["discovered_contacts"] = True

                st.rerun()

# ---------------------------------------------------------------------------
# Enrich discovered contacts
# ---------------------------------------------------------------------------

if st.session_state.get("discovered_contacts") and contacts_map:
    if st.button(
        "Enrich Discovered Contacts",
        type="primary",
        icon=":material/bolt:",
        use_container_width=False,
    ):
        st.session_state["enrich_person_ids"] = [p.id for p in contacts_map.values()]
        st.session_state["discovered_contacts"] = False
        st.switch_page("pages/enrich.py")

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
            "Upload CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            key="csv_upload",
        )
        if uploaded is not None:
            try:
                buf = io.BytesIO(uploaded.getvalue())
                raw_df = read_input_file(buf, filename=uploaded.name)
                st.info(f"Found **{len(raw_df)}** rows, **{len(raw_df.columns)}** columns")

                # Auto-detect column mapping with ColumnMapper
                mapper = ColumnMapper(list(raw_df.columns))
                summary = mapper.get_mapping_summary()

                # Company-relevant canonical fields for override dropdowns
                _company_fields = [
                    None, "company_name", "company_domain", "industry", "employee_count",
                    "country", "city", "state", "revenue_usd", "ebitda_usd",
                    "founded_year", "description", "linkedin_url", "website_url", "phone",
                ]

                st.markdown("**Column Mapping** (adjust auto-detected mappings if needed)")
                mapping_override: dict[str, str] = {}
                for col in raw_df.columns:
                    auto_mapped = summary["mapped"].get(col)
                    default_idx = 0
                    if auto_mapped and auto_mapped in _company_fields:
                        default_idx = _company_fields.index(auto_mapped)

                    selected = st.selectbox(
                        f"{col}",
                        options=_company_fields,
                        index=default_idx,
                        format_func=lambda x: "(skip)" if x is None else x,
                        key=f"csv_col_map_{col}",
                    )
                    if selected is not None:
                        mapping_override[col] = selected

                import_cols = st.columns(2)
                with import_cols[0]:
                    if st.button("Import", type="primary", key="do_csv_import"):
                        if not mapping_override:
                            st.error("No columns mapped. Please map at least Company Name.")
                        else:
                            with st.spinner("Importing companies..."):
                                imported_companies = map_to_companies(
                                    raw_df, mapping_override, source_type="csv_import"
                                )
                                progress_bar = st.progress(0)
                                imported_count = 0
                                merged_count = 0
                                error_count = 0

                                for i, comp in enumerate(imported_companies):
                                    try:
                                        if selected_profile:
                                            comp.icp_score = score_company(comp, selected_profile)
                                        existing = (
                                            run_sync(db.get_company_by_domain(comp.domain))
                                            if comp.domain else None
                                        )
                                        run_sync(db.upsert_company(comp))
                                        if existing:
                                            merged_count += 1
                                        else:
                                            imported_count += 1
                                    except Exception:
                                        error_count += 1
                                    progress_bar.progress((i + 1) / len(imported_companies))

                                st.success(
                                    f"**{imported_count}** imported, "
                                    f"**{merged_count}** merged (existing domain), "
                                    f"**{error_count}** errors."
                                )
                                st.session_state["show_csv_import"] = False
                                if imported_count > 0 or merged_count > 0:
                                    st.rerun()

                with import_cols[1]:
                    if st.button("Cancel Import", key="cancel_csv"):
                        st.session_state["show_csv_import"] = False
                        st.rerun()

            except Exception as exc:
                st.error(f"Error reading file: {exc}")
        else:
            if st.button("Cancel", key="cancel_csv_no_file"):
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

        # Contact info
        contact = contacts_map.get(c.id)
        if contact:
            contact_display = f"{contact.full_name or ''} ({contact.title or 'N/A'})"
        else:
            contact_display = "---"

        table_data.append({
            "Name": c.name,
            "Domain": c.domain or "---",
            "Industry": c.industry or "---",
            "Employees": c.employee_count if c.employee_count else "---",
            "Country": c.country or "---",
            "ICP Score": score_display,
            "Source": c.source_type or "---",
            "Status": c.status,
            "Contact": contact_display,
        })

    st.caption(f"**{len(companies)}** companies found")

    # Build sortable dataframe
    df_rows = []
    for c in companies:
        contact = contacts_map.get(c.id)
        contact_display = (
            f"{contact.full_name or ''} ({contact.title or 'N/A'})"
            if contact else ""
        )
        # SF Status: build link URL for companies in Salesforce
        if c.sf_status == "in_sf" and c.sf_account_id and c.sf_instance_url:
            sf_link = f"https://{c.sf_instance_url}/{c.sf_account_id}"
        else:
            sf_link = None

        df_rows.append({
            "Name": c.name or "",
            "Domain": c.domain or "",
            "Industry": c.industry or "",
            "Employees": c.employee_count or "",
            "Country": c.country or "",
            "ICP Score": c.icp_score if c.icp_score is not None else "",
            "SF Status": sf_link if sf_link else "",
            "Source": c.source_type or "",
            "Status": c.status or "new",
            "Contact": contact_display,
        })

    df = pd.DataFrame(df_rows)

    # Column config: make SF Status a clickable link
    column_config = {
        "SF Status": st.column_config.LinkColumn(
            "SF Status",
            display_text="In SF",
            help="Click to open Salesforce Account record",
        ),
    }

    event = st.dataframe(
        df,
        use_container_width=True,
        height=400,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config=column_config,
    )

    selected_rows = event.selection.rows if event.selection else []

    # ---- Bulk status update ------------------------------------------------

    if selected_rows:
        bulk_cols = st.columns([2, 2, 4])
        with bulk_cols[0]:
            new_status = st.selectbox(
                "Set status to",
                options=["new", "contacted", "skipped"],
                key="bulk_status_select",
            )
        with bulk_cols[1]:
            st.markdown("")  # vertical alignment
            update_btn = st.button(
                f"Update {len(selected_rows)} companies",
                type="primary",
                icon=":material/edit:",
                key="bulk_status_update",
            )

        if update_btn:
            updated = 0
            for idx in selected_rows:
                if idx < len(companies):
                    company = companies[idx]
                    company.status = new_status
                    run_sync(db.upsert_company(company))
                    updated += 1
            st.success(f"Updated status to **{new_status}** for {updated} companies.")
            st.rerun()

        # ---- Enrich Anyway (SF override) ----------------------------------
        sf_selected = [
            companies[idx] for idx in selected_rows
            if idx < len(companies) and companies[idx].sf_status == "in_sf"
        ]
        if sf_selected:
            if st.button(
                f"Enrich Anyway ({len(sf_selected)} in SF)",
                icon=":material/bolt:",
                key="enrich_anyway_sf",
                type="secondary",
            ):
                # Store force-enrich domains in session state for the waterfall
                force_domains = {
                    c.domain for c in sf_selected if c.domain
                }
                existing = st.session_state.get("force_enrich_domains", set())
                st.session_state["force_enrich_domains"] = existing | force_domains
                # Queue contacts for enrichment (same pattern as contact discovery)
                enrich_ids = []
                for c in sf_selected:
                    contact = contacts_map.get(c.id)
                    if contact:
                        enrich_ids.append(contact.id)
                if enrich_ids:
                    st.session_state["enrich_person_ids"] = enrich_ids
                    st.switch_page("pages/enrich.py")
                else:
                    st.info(
                        "Selected SF companies have no contacts yet. "
                        "Run contact discovery first, then enrich."
                    )

    # ---------------------------------------------------------------------------
    # Single Company Contact Discovery
    # ---------------------------------------------------------------------------

    if apollo_available:
        st.divider()
        st.subheader("Find Contact at Specific Company")

        company_options = {
            c.name: c for c in companies if c.domain and c.id not in contacts_map
        }
        if company_options:
            selected_company_name = st.selectbox(
                "Select company",
                list(company_options.keys()),
                key="single_discover_company",
            )
            if st.button("Find Contact", key="single_find_contact"):
                target = company_options[selected_company_name]
                apollo = ApolloProvider(api_key=apollo_key.api_key)
                with st.spinner(f"Searching for contact at {target.name}..."):
                    person = run_sync(discover_contact(apollo, target))
                if person:
                    person.company_id = target.id
                    person.company_domain = target.domain
                    person.company_name = target.name
                    run_sync(db.upsert_person(person))
                    st.success(
                        f"Found: **{person.full_name}** - {person.title or 'N/A'}"
                    )
                    st.rerun()
                else:
                    st.warning(f"No CEO/Owner/Founder found at {target.domain}")
        else:
            st.caption("All displayed companies already have contacts or lack domains.")

    # Main table above is now a sortable st.dataframe -- no need for separate view
