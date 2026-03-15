"""Search page -- ICP-preset driven company and people search via Apollo."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import streamlit as st

from config.settings import ProviderName, ICP_PRESETS, ICPPreset
from data.models import Company, Person, Campaign, EnrichmentType, CampaignStatus
from providers.apollo import ApolloProvider

from data.sync import run_sync
from ui.shared import get_database, get_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    return run_sync(coro)


def _get_apollo() -> ApolloProvider | None:
    """Return an ApolloProvider if the API key is configured."""
    settings = get_settings()
    cfg = settings.providers.get(ProviderName.APOLLO)
    if cfg and cfg.api_key:
        return ApolloProvider(api_key=cfg.api_key)
    return None


COUNTRIES = [
    "US", "UK", "CA", "AU", "DE", "FR", "NL", "SE", "NO", "DK",
    "CH", "IE", "SG", "IN", "JP", "BR", "MX", "IL", "NZ", "IT",
]

EMPLOYEE_RANGES = [
    "1,10", "11,50", "51,200", "201,500", "501,1000",
    "1001,5000", "5001,10000", "10001,50000",
]

# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Find Leads")

# ---- Search Filters expander -----------------------------------------------

with st.expander("Search Filters", expanded=True):

    # ---- ICP preset selector ------------------------------------------------

    preset_names = list(ICP_PRESETS.keys())
    preset_display = {k: v.display_name for k, v in ICP_PRESETS.items()}

    selected_preset = st.radio(
        "ICP Preset",
        options=["custom"] + preset_names,
        format_func=lambda x: "Custom" if x == "custom" else preset_display.get(x, x),
        horizontal=True,
    )

    # Resolve preset values
    preset: ICPPreset | None = ICP_PRESETS.get(selected_preset) if selected_preset != "custom" else None

    # ---- Filter inputs ------------------------------------------------------

    filter_cols = st.columns(2)

    with filter_cols[0]:
        default_industries = ", ".join(preset.industries) if preset else ""
        industry_input = st.text_input(
            "Industries (comma-separated)",
            value=default_industries,
            help="e.g. aerospace, defense, aviation",
        )

        default_keywords = ", ".join(preset.keywords) if preset else ""
        keywords_input = st.text_input(
            "Keywords (comma-separated)",
            value=default_keywords,
            help="e.g. MRO, avionics, mil-spec",
        )

    with filter_cols[1]:
        default_min = preset.employee_min if preset else 10
        default_max = preset.employee_max if preset else 500
        emp_range = st.slider(
            "Employee Range",
            min_value=1,
            max_value=50000,
            value=(default_min, default_max),
            step=10,
        )

        default_countries = preset.countries if preset else ["US"]
        countries = st.multiselect(
            "Countries",
            options=COUNTRIES,
            default=[c for c in default_countries if c in COUNTRIES],
        )

# ---- Search type + button inline -------------------------------------------

search_row = st.columns([2, 2, 4])
with search_row[0]:
    search_type = st.radio("Search type", ["Companies", "People"], horizontal=True)
with search_row[1]:
    st.markdown("")
    search_btn = st.button("Search", type="primary", icon=":material/search:")

# ---- Build Apollo payload ---------------------------------------------------

def _build_emp_ranges(min_val: int, max_val: int) -> list[str]:
    """Convert the slider range into Apollo-compatible employee range strings."""
    result = []
    for r in EMPLOYEE_RANGES:
        lo, hi = r.split(",")
        if int(hi) >= min_val and int(lo) <= max_val:
            result.append(r)
    return result if result else [f"{min_val},{max_val}"]

# ---- Execute search ---------------------------------------------------------

if search_btn:
    apollo = _get_apollo()
    if apollo is None:
        st.error("Apollo API key is not configured. Go to **Settings** to add it.")
    else:
        emp_ranges = _build_emp_ranges(emp_range[0], emp_range[1])
        keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

        filters: dict[str, Any] = {
            "organization_num_employees_ranges": emp_ranges,
            "per_page": 50,
        }
        if countries:
            filters["organization_locations"] = countries
        if keywords:
            filters["q_organization_keyword_tags"] = keywords

        with st.spinner("Searching Apollo..."):
            try:
                if search_type == "Companies":
                    results = _run_async(apollo.search_companies(**filters))
                    if not results:
                        st.warning("No companies found matching the filters.")
                    else:
                        rows = []
                        for c in results:
                            rows.append({
                                "Name": c.name,
                                "Domain": c.domain or "",
                                "Industry": c.industry or "",
                                "Employees": c.employee_count or "",
                                "Country": c.country or "",
                                "City": c.city or "",
                                "LinkedIn": c.linkedin_url or "",
                                "Description": (c.description or "")[:120],
                            })
                        df = pd.DataFrame(rows)
                        st.session_state["search_results_companies"] = results
                        st.session_state["search_results_df"] = df
                        st.success(f"Found {len(results)} companies.")
                else:
                    results = _run_async(apollo.search_people(**filters))
                    if not results:
                        st.warning("No people found matching the filters.")
                    else:
                        rows = []
                        for p in results:
                            rows.append({
                                "Name": p.full_name or "",
                                "Title": p.title or "",
                                "Company": p.company_name or "",
                                "Domain": p.company_domain or "",
                                "LinkedIn": p.linkedin_url or "",
                                "City": p.city or "",
                                "Country": p.country or "",
                            })
                        df = pd.DataFrame(rows)
                        st.session_state["search_results_people"] = results
                        st.session_state["search_results_df"] = df
                        st.success(f"Found {len(results)} people.")
            except Exception as exc:
                st.error(f"Search failed: {exc}")

# ---- Display results --------------------------------------------------------

if "search_results_df" in st.session_state:
    st.subheader("Search Results")

    df = st.session_state["search_results_df"]

    event = st.dataframe(
        df,
        use_container_width=True,
        height=400,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
    )

    selected_rows = event.selection.rows if event.selection else []

    # ---- Save companies to database ------------------------------------------

    if "search_results_companies" in st.session_state:
        save_cols = st.columns([3, 2])
        with save_cols[1]:
            st.markdown("")  # vertical alignment
            save_db_btn = st.button(
                f"Save Selected to Database ({len(selected_rows)})",
                type="secondary",
                icon=":material/save:",
                disabled=len(selected_rows) == 0,
                key="save_companies_db",
            )

        if save_db_btn and selected_rows:
            db = get_database()
            companies = st.session_state["search_results_companies"]
            saved_count = 0
            merged_count = 0
            for idx in selected_rows:
                if idx < len(companies):
                    c = companies[idx]
                    # Set source_type for Apollo-sourced companies
                    c.source_type = "apollo_search"
                    existing = run_sync(db.get_company_by_domain(c.domain)) if c.domain else None
                    run_sync(db.upsert_company(c))
                    if existing:
                        merged_count += 1
                    else:
                        saved_count += 1
            st.success(
                f"Saved **{saved_count}** companies to database"
                + (f", merged **{merged_count}** existing." if merged_count else ".")
            )

    # ---- Campaign creation bar (compact) ------------------------------------

    create_cols = st.columns([3, 2])

    with create_cols[0]:
        campaign_name = st.text_input(
            "Campaign name",
            value=f"Search - {search_type}",
            key="search_campaign_name",
        )

    with create_cols[1]:
        st.markdown("")  # vertical alignment
        enrich_btn = st.button(
            f"Enrich Selected ({len(selected_rows)})",
            type="primary",
            icon=":material/bolt:",
            disabled=len(selected_rows) == 0,
        )

    if enrich_btn and selected_rows:
        db = get_database()
        settings = get_settings()

        campaign = Campaign(
            name=campaign_name,
            description=f"Created from {search_type.lower()} search",
            enrichment_types=[EnrichmentType.EMAIL],
            waterfall_order=settings.waterfall_order,
            status=CampaignStatus.CREATED,
            total_rows=len(selected_rows),
        )
        campaign = run_sync(db.create_campaign(campaign))

        # Store selected people/companies as campaign rows
        row_dicts = []
        if "search_results_people" in st.session_state:
            people = st.session_state["search_results_people"]
            for idx in selected_rows:
                if idx < len(people):
                    p = people[idx]
                    row_dicts.append({
                        "first_name": p.first_name or "",
                        "last_name": p.last_name or "",
                        "company_name": p.company_name or "",
                        "company_domain": p.company_domain or "",
                        "linkedin_url": p.linkedin_url or "",
                    })
        elif "search_results_companies" in st.session_state:
            companies = st.session_state["search_results_companies"]
            for idx in selected_rows:
                if idx < len(companies):
                    c = companies[idx]
                    row_dicts.append({
                        "company_name": c.name or "",
                        "company_domain": c.domain or "",
                    })

        if row_dicts:
            run_sync(db.create_campaign_rows(campaign.id, row_dicts))
            st.success(
                f"Campaign **{campaign.name}** created with {len(row_dicts)} rows.  "
                f"Go to **Enrich** to configure and run it."
            )
        else:
            st.warning("No valid rows to enrich from selection.")
