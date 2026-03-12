"""Settings page -- provider configuration, waterfall order, and cache management."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from config.settings import ProviderName, load_salesforce_config, persist_settings
from providers.apollo import ApolloProvider
from providers.findymail import FindymailProvider
from providers.icypeas import IcypeasProvider
from providers.contactout import ContactOutProvider
from providers.datagma import DatagmaProvider
from providers.salesforce import SalesforceClient

from data.sync import run_sync
from ui.app import get_database, get_settings, get_key_validation_status

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXECUTOR = ThreadPoolExecutor(max_workers=4)

_PROVIDER_CLASSES = {
    ProviderName.APOLLO: ApolloProvider,
    ProviderName.FINDYMAIL: FindymailProvider,
    ProviderName.ICYPEAS: IcypeasProvider,
    ProviderName.CONTACTOUT: ContactOutProvider,
    ProviderName.DATAGMA: DatagmaProvider,
}


def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    return run_sync(coro)


def _mask_key(key: str) -> str:
    """Mask an API key for display, showing only last 4 characters."""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Settings")

db = get_database()
settings = get_settings()

# ---- Salesforce Integration -------------------------------------------------

st.subheader("Salesforce Integration")

sf_config = load_salesforce_config()

with st.container(border=True):
    sf_cols = st.columns(3)
    with sf_cols[0]:
        sf_username = st.text_input(
            "Username",
            value=sf_config.username,
            key="sf_username",
            placeholder="your-sf-login@example.com",
        )
    with sf_cols[1]:
        sf_password = st.text_input(
            "Password",
            value=sf_config.password,
            type="password",
            key="sf_password",
            placeholder="Enter Salesforce password",
        )
    with sf_cols[2]:
        sf_token = st.text_input(
            "Security Token",
            value=sf_config.security_token,
            type="password",
            key="sf_security_token",
            placeholder="Enter security token",
        )

    sf_btn_cols = st.columns([1, 3])
    with sf_btn_cols[0]:
        if st.button(
            "Test Connection",
            key="sf_test_connection",
            disabled=not (sf_username and sf_password and sf_token),
            use_container_width=True,
        ):
            with st.spinner("Connecting to Salesforce..."):
                try:
                    from simple_salesforce.exceptions import SalesforceAuthenticationFailed

                    client = SalesforceClient(sf_username, sf_password, sf_token)
                    result = client.health_check()
                    st.success(
                        f"Connected to **{result['org_name']}** "
                        f"({result['account_count']} accounts)"
                    )
                except SalesforceAuthenticationFailed as exc:
                    st.error(f"Authentication failed: {exc}")
                except Exception as exc:
                    st.error(f"Connection failed: {exc}")
    with sf_btn_cols[1]:
        st.caption(
            "Enter your Salesforce credentials above. "
            "To persist, set SALESFORCE_USERNAME, SALESFORCE_PASSWORD, "
            "and SALESFORCE_SECURITY_TOKEN in your `.env` file."
        )

st.divider()

# ---- Provider Configuration Cards -------------------------------------------

st.subheader("Provider Configuration")

# Re-validate all keys button
key_status = get_key_validation_status()
if st.button(
    "Re-validate All Keys",
    icon=":material/refresh:",
    use_container_width=False,
):
    st.cache_data.clear()
    st.rerun()

for pname in ProviderName:
    pcfg = settings.providers.get(pname)
    if pcfg is None:
        continue

    with st.container(border=True):
        header_cols = st.columns([3, 1])
        with header_cols[0]:
            prov_valid = key_status.get(pname.value, False)
            validity_icon = ":white_check_mark:" if prov_valid else ":x:"
            st.markdown(f"### {pname.value.title()} {validity_icon}")
            if not prov_valid and pcfg.api_key:
                st.caption(":red[API key validation failed]")
        with header_cols[1]:
            enabled = st.toggle(
                "Enabled",
                value=pcfg.enabled,
                key=f"enabled_{pname.value}",
            )
            pcfg.enabled = enabled

        config_cols = st.columns(3)

        # API Key input (masked)
        with config_cols[0]:
            st.markdown("**API Key**")
            current_display = _mask_key(pcfg.api_key)
            new_key = st.text_input(
                "API Key",
                value="",
                type="password",
                placeholder=current_display or "Enter API key...",
                key=f"apikey_{pname.value}",
                label_visibility="collapsed",
            )
            if new_key:
                pcfg.api_key = new_key
                st.caption(":green[Key updated (in memory only)]")
            elif pcfg.api_key:
                st.caption(f"Current: {current_display}")

            # Test Connection button
            if st.button(
                "Test Connection",
                key=f"test_{pname.value}",
                disabled=not pcfg.api_key,
                use_container_width=True,
            ):
                provider_cls = _PROVIDER_CLASSES.get(pname)
                if provider_cls:
                    with st.spinner(f"Testing {pname.value}..."):
                        try:
                            provider = provider_cls(api_key=pcfg.api_key)
                            healthy = _run_async(provider.health_check())
                            if healthy:
                                st.success(f"{pname.value.title()}: Connection OK")
                            else:
                                st.error(f"{pname.value.title()}: Connection failed")
                        except Exception as exc:
                            st.error(f"{pname.value.title()}: {exc}")

        # Budget inputs
        with config_cols[1]:
            st.markdown("**Daily Budget**")
            daily_limit = st.number_input(
                "Daily credit limit",
                min_value=0,
                max_value=1_000_000,
                value=pcfg.daily_credit_limit or 0,
                step=100,
                key=f"daily_{pname.value}",
                label_visibility="collapsed",
            )
            pcfg.daily_credit_limit = daily_limit if daily_limit > 0 else None

        with config_cols[2]:
            st.markdown("**Monthly Budget**")
            monthly_limit = st.number_input(
                "Monthly credit limit",
                min_value=0,
                max_value=10_000_000,
                value=pcfg.monthly_credit_limit or 0,
                step=1000,
                key=f"monthly_{pname.value}",
                label_visibility="collapsed",
            )
            pcfg.monthly_credit_limit = monthly_limit if monthly_limit > 0 else None

st.divider()

# ---- Waterfall Order Configuration ------------------------------------------

st.subheader("Waterfall Order")
st.caption(
    "Configure the order in which providers are tried during enrichment. "
    "Providers higher in the list are tried first."
)

current_order = list(settings.waterfall_order)

# Display current order with move up/down buttons
for idx, pname in enumerate(current_order):
    order_cols = st.columns([1, 4, 1, 1])
    with order_cols[0]:
        st.markdown(f"**{idx + 1}.**")
    with order_cols[1]:
        pcfg = settings.providers.get(pname)
        status = ":green[Enabled]" if (pcfg and pcfg.enabled and pcfg.api_key) else ":red[Disabled]"
        st.markdown(f"**{pname.value.title()}** {status}")
    with order_cols[2]:
        if st.button(
            "Up",
            key=f"up_{pname.value}",
            disabled=idx == 0,
            use_container_width=True,
        ):
            current_order[idx], current_order[idx - 1] = (
                current_order[idx - 1],
                current_order[idx],
            )
            settings.waterfall_order = current_order
            st.rerun()
    with order_cols[3]:
        if st.button(
            "Down",
            key=f"down_{pname.value}",
            disabled=idx == len(current_order) - 1,
            use_container_width=True,
        ):
            current_order[idx], current_order[idx + 1] = (
                current_order[idx + 1],
                current_order[idx],
            )
            settings.waterfall_order = current_order
            st.rerun()

st.divider()

# ---- Cache Management -------------------------------------------------------

st.subheader("Cache Management")

cache_cols = st.columns(3)

with cache_cols[0]:
    st.markdown("**Cache Statistics**")
    async def _fetch_cache_stats():
        async with db._connect() as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM cache")
            total_cached = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at < CURRENT_TIMESTAMP"
            )
            expired = (await cur.fetchone())[0]
            active = total_cached - expired
            cur = await conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM cache")
            total_hits = (await cur.fetchone())[0]
        return active, expired, total_hits

    _active, _expired, _total_hits = run_sync(_fetch_cache_stats())
    st.metric("Active Entries", f"{_active:,}")
    st.metric("Expired Entries", f"{_expired:,}")
    st.metric("Total Cache Hits", f"{_total_hits:,}")

with cache_cols[1]:
    st.markdown("**Cache by Provider**")
    async def _fetch_cache_by_provider():
        async with db._connect() as conn:
            cur = await conn.execute(
                "SELECT provider, COUNT(*) as cnt, SUM(hit_count) as hits "
                "FROM cache WHERE expires_at > CURRENT_TIMESTAMP "
                "GROUP BY provider"
            )
            return await cur.fetchall()

    rows = run_sync(_fetch_cache_by_provider())
    for row in rows:
        st.markdown(f"- **{row['provider'].title()}**: {row['cnt']:,} entries, {row['hits']:,} hits")
    if not rows:
        st.caption("No active cache entries.")

with cache_cols[2]:
    st.markdown("**Actions**")
    if st.button(
        "Purge Expired Entries",
        icon=":material/delete_sweep:",
        use_container_width=True,
    ):
        purged = run_sync(db.cache_purge_expired())
        st.success(f"Purged {purged:,} expired entries.")
        st.rerun()

    if st.button(
        "Clear ALL Cache",
        icon=":material/delete_forever:",
        type="secondary",
        use_container_width=True,
    ):
        async def _clear_cache():
            async with db._connect() as conn:
                await conn.execute("DELETE FROM cache")

        run_sync(_clear_cache())
        st.success("All cache entries cleared.")
        st.rerun()

st.divider()

# ---- General Settings -------------------------------------------------------

st.subheader("General Settings")

general_cols = st.columns(2)

with general_cols[0]:
    cache_ttl = st.number_input(
        "Cache TTL (days)",
        min_value=1,
        max_value=365,
        value=settings.cache_ttl_days,
        step=1,
    )
    settings.cache_ttl_days = cache_ttl

with general_cols[1]:
    max_concurrent = st.number_input(
        "Max Concurrent Requests",
        min_value=1,
        max_value=50,
        value=settings.max_concurrent_requests,
        step=1,
    )
    settings.max_concurrent_requests = max_concurrent

st.divider()

# ---- ICP Profile Management --------------------------------------------------

st.subheader("ICP Profiles")
st.caption(
    "Manage Ideal Customer Profile (ICP) presets used for scoring companies. "
    "Built-in profiles cannot be deleted."
)

from config.settings import ICP_PRESETS, ICPPreset, load_all_icp_profiles
import uuid as _uuid

# Load all profiles
all_profiles = load_all_icp_profiles(db)

# Load custom profile IDs from DB for edit/delete
_custom_db_profiles = run_sync(db.get_icp_profiles())
_custom_names = {row["name"] for row in _custom_db_profiles}
_custom_ids = {row["name"]: row["id"] for row in _custom_db_profiles}

# Display existing profiles
for key, profile in all_profiles.items():
    is_builtin = key in ICP_PRESETS and profile.display_name not in _custom_names
    badge = ":blue[Built-in]" if is_builtin else ":green[Custom]"

    with st.expander(f"{profile.display_name} {badge}"):
        prof_cols = st.columns(2)
        with prof_cols[0]:
            st.markdown(f"**Employees:** {profile.employee_min:,} - {profile.employee_max:,}")
            st.markdown(f"**Countries:** {', '.join(profile.countries)}")
        with prof_cols[1]:
            st.markdown(f"**Industries:** {', '.join(profile.industries[:5])}")
            if profile.keywords:
                st.markdown(f"**Keywords:** {', '.join(profile.keywords[:5])}")

        if not is_builtin:
            edit_cols = st.columns(2)
            with edit_cols[0]:
                if st.button("Edit", key=f"edit_icp_{key}", use_container_width=True):
                    st.session_state["icp_edit_profile"] = key
            with edit_cols[1]:
                if st.button(
                    "Delete", key=f"del_icp_{key}", type="secondary",
                    use_container_width=True,
                ):
                    profile_id = _custom_ids.get(profile.display_name)
                    if profile_id:
                        run_sync(db.delete_icp_profile(profile_id))
                        st.success(f"Deleted profile: {profile.display_name}")
                        st.rerun()

st.divider()

# Create / Edit form
_editing = st.session_state.get("icp_edit_profile")
_edit_preset = all_profiles.get(_editing) if _editing else None
_form_title = f"Edit: {_edit_preset.display_name}" if _edit_preset else "Create Custom Profile"

with st.expander(_form_title, expanded=bool(_edit_preset)):
    icp_name = st.text_input(
        "Profile Name",
        value=_edit_preset.display_name if _edit_preset else "",
        key="icp_form_name",
    )
    emp_cols = st.columns(2)
    with emp_cols[0]:
        icp_emp_min = st.number_input(
            "Min Employees", min_value=0, max_value=1_000_000,
            value=_edit_preset.employee_min if _edit_preset else 10,
            step=10, key="icp_form_emp_min",
        )
    with emp_cols[1]:
        icp_emp_max = st.number_input(
            "Max Employees", min_value=0, max_value=1_000_000,
            value=_edit_preset.employee_max if _edit_preset else 100,
            step=10, key="icp_form_emp_max",
        )

    icp_industries = st.text_area(
        "Industries (one per line)",
        value="\n".join(_edit_preset.industries) if _edit_preset else "",
        key="icp_form_industries",
    )
    icp_keywords = st.text_area(
        "Keywords (one per line)",
        value="\n".join(_edit_preset.keywords) if _edit_preset else "",
        key="icp_form_keywords",
    )
    _country_options = ["US", "CA", "UK", "IE", "DE", "FR", "AU"]
    icp_countries = st.multiselect(
        "Countries",
        options=_country_options,
        default=_edit_preset.countries if _edit_preset else ["US", "CA", "UK"],
        key="icp_form_countries",
    )

    save_cols = st.columns(2)
    with save_cols[0]:
        if st.button("Save Profile", type="primary", use_container_width=True, key="icp_save"):
            if not icp_name.strip():
                st.error("Profile name is required.")
            else:
                config_dict = {
                    "industries": [i.strip() for i in icp_industries.split("\n") if i.strip()],
                    "keywords": [k.strip() for k in icp_keywords.split("\n") if k.strip()],
                    "employee_min": icp_emp_min,
                    "employee_max": icp_emp_max,
                    "countries": icp_countries,
                }
                # Reuse existing ID if editing, else new UUID
                profile_id = _custom_ids.get(icp_name.strip(), str(_uuid.uuid4()))
                run_sync(db.save_icp_profile(
                    profile_id=profile_id,
                    name=icp_name.strip(),
                    config=config_dict,
                    is_default=False,
                ))
                st.success(f"Saved profile: {icp_name.strip()}")
                st.session_state.pop("icp_edit_profile", None)
                st.rerun()
    with save_cols[1]:
        if _edit_preset and st.button("Cancel", use_container_width=True, key="icp_cancel"):
            st.session_state.pop("icp_edit_profile", None)
            st.rerun()

st.divider()

# ---- Save All Settings to .env -----------------------------------------------

st.subheader("Save Settings")
st.caption(
    "Click **Save All Settings** to persist current configuration to the `.env` file. "
    "Changes will survive app restarts."
)

if st.button("Save All Settings", type="primary", icon=":material/save:", use_container_width=False, key="save_all_settings"):
    updates: dict[str, str | None] = {}

    # API keys
    for pname in ProviderName:
        pcfg = settings.providers.get(pname)
        if pcfg is not None and pcfg.api_key:
            updates[f"{pname.value.upper()}_API_KEY"] = pcfg.api_key

    # Waterfall order
    updates["WATERFALL_ORDER"] = ",".join(p.value for p in settings.waterfall_order)

    # Cache TTL
    updates["CACHE_TTL_DAYS"] = str(settings.cache_ttl_days)

    # Salesforce credentials (from current form values)
    if sf_username:
        updates["SALESFORCE_USERNAME"] = sf_username
    if sf_password:
        updates["SALESFORCE_PASSWORD"] = sf_password
    if sf_token:
        updates["SALESFORCE_SECURITY_TOKEN"] = sf_token

    # Anthropic API key
    if settings.anthropic_api_key:
        updates["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    persist_settings(updates)
    settings.reload_api_keys()
    st.success("Settings saved to `.env` file.")
    st.cache_data.clear()
    st.rerun()
