"""Emails page -- AI email generation, preview/edit, approve/reject, and CSV export.

Flow:
    1. Select a completed campaign and an email template
    2. Generate emails (single or batch) via Claude Haiku 4.5
    3. Preview, inline-edit, approve or reject individual emails
    4. Export approved emails as Outreach.io, Salesforce Lead, or Raw CSV
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Optional

import pandas as pd
import streamlit as st

from data.database import Database
from data.email_engine import (
    generate_single_email,
    run_batch_generation,
    STARTER_TEMPLATES,
)
from data.models import (
    CampaignStatus,
    EmailTemplate,
    GeneratedEmail,
)
from data.sync import run_sync
from ui.app import get_database, get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEQUENCE_STEP_LABELS = {1: "Intro", 2: "Follow-up", 3: "Breakup"}


def _get_campaign_person_ids(db: Database, campaign_id: str) -> list[str]:
    """Return person_ids associated with a campaign via campaign_rows."""

    async def _fetch():
        async with db._connect() as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT person_id FROM campaign_rows "
                "WHERE campaign_id = ? AND person_id IS NOT NULL",
                (campaign_id,),
            )
            rows = await cursor.fetchall()
            return [r["person_id"] for r in rows]

    return run_sync(_fetch())


def _get_persons_map(db: Database, person_ids: list[str]) -> dict:
    """Batch-load Person objects by IDs. Returns {person_id: Person}."""

    async def _fetch():
        result = {}
        for pid in person_ids:
            p = await db.get_person(pid)
            if p:
                result[pid] = p
        return result

    return run_sync(_fetch())


def _build_export_df(
    emails: list[GeneratedEmail],
    persons_map: dict,
    companies_map: dict,
    preset: str,
) -> pd.DataFrame:
    """Build a pandas DataFrame for CSV export based on the selected preset."""
    rows = []
    for email in emails:
        if preset != "Raw" and email.status != "approved":
            continue

        person = persons_map.get(email.person_id)
        company = companies_map.get(email.company_id) if email.company_id else None

        if preset == "Outreach.io":
            rows.append({
                "Email": person.email if person else "",
                "First Name": person.first_name if person else "",
                "Last Name": person.last_name if person else "",
                "Company": (company.name if company else (person.company_name if person else "")),
                "Subject": email.subject or "",
                "Body": email.body or "",
                "Sequence Step": email.sequence_step,
            })
        elif preset == "Salesforce Lead":
            rows.append({
                "Company": (company.name if company else (person.company_name if person else "")),
                "Website": (company.website_url if company and hasattr(company, "website_url") else ""),
                "Quality__c": (str(company.icp_score) if company and company.icp_score is not None else ""),
                "FirstName": person.first_name if person else "",
                "LastName": person.last_name if person else "",
                "Title": person.title if person else "",
                "Email": person.email if person else "",
                "City": (company.city if company else (person.city if person else "")),
                "State": (company.state if company else (person.state if person else "")),
                "Country": (company.country if company else (person.country if person else "")),
            })
        else:
            # Raw - all fields
            rows.append({
                "Email ID": email.id,
                "Campaign ID": email.campaign_id,
                "Person ID": email.person_id,
                "First Name": person.first_name if person else "",
                "Last Name": person.last_name if person else "",
                "Email Address": person.email if person else "",
                "Title": person.title if person else "",
                "Company": (company.name if company else (person.company_name if person else "")),
                "Subject": email.subject or "",
                "Body": email.body or "",
                "Status": email.status,
                "Sequence Step": email.sequence_step,
                "Input Tokens": email.input_tokens,
                "Output Tokens": email.output_tokens,
                "Cost USD": email.cost_usd,
                "Generated At": str(email.generated_at),
                "User Note": email.user_note or "",
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Email Generation")

db = get_database()
settings = get_settings()

# Ensure starter templates exist
run_sync(db.seed_default_templates())

# ---------------------------------------------------------------------------
# Sidebar Controls: Campaign + Template Selection
# ---------------------------------------------------------------------------

# Campaign selector -- only completed campaigns
campaigns = run_sync(db.get_recent_campaigns(limit=50))
completed_campaigns = [c for c in campaigns if c.status == CampaignStatus.COMPLETED]

if not completed_campaigns:
    st.info(
        "No completed campaigns found. Run an enrichment first, then come back "
        "to generate emails for the enriched contacts."
    )
    st.stop()

campaign_options = {f"{c.name} ({c.created_at:%Y-%m-%d})": c.id for c in completed_campaigns}
selected_campaign_label = st.selectbox(
    "Select Campaign",
    options=list(campaign_options.keys()),
    help="Only campaigns with completed enrichment are shown.",
)
selected_campaign_id = campaign_options[selected_campaign_label]

# Template selector
templates = run_sync(db.get_email_templates())
if not templates:
    st.warning("No email templates found.")
    st.stop()

template_options = {
    f"{t.name} (Step {t.sequence_step} - {SEQUENCE_STEP_LABELS.get(t.sequence_step, '?')})": t.id
    for t in templates
}
selected_template_label = st.selectbox(
    "Select Template",
    options=list(template_options.keys()),
    help="Choose a template to use for email generation.",
)
selected_template_id = template_options[selected_template_label]

# ---------------------------------------------------------------------------
# Template Management Expander
# ---------------------------------------------------------------------------

with st.expander("Manage Templates", expanded=False):
    st.markdown(
        "**Available variables:** `{first_name}`, `{last_name}`, `{title}`, "
        "`{company_name}`, `{industry}`, `{employee_count}`, `{city}`, `{state}`, "
        "`{country}`, `{description}`, `{founded_year}`, `{icp_score}`, `{quality_tier}`"
    )

    st.markdown("---")
    st.markdown("**Create New Template**")

    with st.form("new_template_form", clear_on_submit=True):
        tmpl_name = st.text_input("Template Name")
        tmpl_desc = st.text_input("Description (optional)")
        tmpl_step = st.selectbox("Sequence Step", options=[1, 2, 3], format_func=lambda x: f"{x} - {SEQUENCE_STEP_LABELS.get(x, '?')}")
        tmpl_system = st.text_area("System Prompt", height=150)
        tmpl_user = st.text_area("User Prompt Template", height=100, help="Use {variable} syntax for personalization.")
        submitted = st.form_submit_button("Create Template")

        if submitted and tmpl_name and tmpl_system and tmpl_user:
            new_template = EmailTemplate(
                name=tmpl_name,
                description=tmpl_desc or None,
                system_prompt=tmpl_system,
                user_prompt_template=tmpl_user,
                sequence_step=tmpl_step,
                is_default=False,
            )
            run_sync(db.save_email_template(new_template))
            st.success(f"Template '{tmpl_name}' created.")
            st.rerun()

    st.markdown("---")
    st.markdown("**Existing Templates**")
    for tmpl in templates:
        cols = st.columns([4, 1])
        with cols[0]:
            st.text(f"{tmpl.name} (Step {tmpl.sequence_step})")
        with cols[1]:
            if not tmpl.is_default:
                if st.button("Delete", key=f"del_tmpl_{tmpl.id}", type="secondary"):
                    run_sync(db.delete_email_template(tmpl.id))
                    st.rerun()
            else:
                st.caption("Default")

# ---------------------------------------------------------------------------
# API Key Check
# ---------------------------------------------------------------------------

api_key = settings.anthropic_api_key
if not api_key:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

if not api_key:
    st.warning(
        "**ANTHROPIC_API_KEY not configured.** Add it to your `.env` file or "
        "Settings page to enable email generation."
    )

# ---------------------------------------------------------------------------
# Generation Section
# ---------------------------------------------------------------------------

st.subheader("Generate Emails")

person_ids = _get_campaign_person_ids(db, selected_campaign_id)

if not person_ids:
    st.warning("No contacts found for this campaign. Ensure enrichment has completed.")
    st.stop()

st.metric("Contacts in Campaign", len(person_ids))

gen_cols = st.columns([1, 1, 2])

with gen_cols[0]:
    if st.button(
        "Generate All",
        type="primary",
        icon=":material/auto_awesome:",
        use_container_width=True,
        disabled=not api_key,
    ):
        thread_key = f"email_gen_thread_{selected_campaign_id}_{selected_template_id}"
        if thread_key not in st.session_state:
            thread = threading.Thread(
                target=run_batch_generation,
                args=(
                    selected_campaign_id,
                    selected_template_id,
                    person_ids,
                    db.db_path,
                    api_key,
                ),
                daemon=True,
            )
            thread.start()
            st.session_state[thread_key] = True
            st.session_state["email_gen_running"] = True
            st.toast("Batch email generation started!")

with gen_cols[1]:
    if st.button(
        "Generate Single",
        icon=":material/edit_note:",
        use_container_width=True,
        disabled=not api_key,
    ):
        st.session_state["show_single_gen"] = True

# Single generation UI
if st.session_state.get("show_single_gen"):
    persons_map = _get_persons_map(db, person_ids[:50])  # Limit for selectbox
    person_labels = {
        f"{p.first_name or ''} {p.last_name or ''} ({p.email or 'no email'})".strip(): pid
        for pid, p in persons_map.items()
    }
    selected_person_label = st.selectbox("Select Contact", options=list(person_labels.keys()))
    selected_person_id = person_labels[selected_person_label]
    user_note = st.text_input("Additional instruction (optional)", placeholder="e.g., mention their certification")

    if st.button("Generate Email", type="primary"):
        if api_key:
            import anthropic

            with st.spinner("Generating email..."):
                client = anthropic.Anthropic(api_key=api_key)
                template = run_sync(db.get_email_template(selected_template_id))
                person, company = run_sync(db.get_person_with_company(selected_person_id))
                email = generate_single_email(
                    client=client,
                    template=template,
                    person=person,
                    company=company,
                    campaign_id=selected_campaign_id,
                    user_note=user_note or None,
                )
                run_sync(db.save_generated_email(email))

            if email.status == "draft":
                st.success("Email generated successfully!")
            else:
                st.error(f"Generation failed: {email.body}")
            st.rerun()

# ---------------------------------------------------------------------------
# Progress Polling Fragment
# ---------------------------------------------------------------------------


@st.fragment(run_every=2.0)
def _poll_email_progress():
    """Auto-refreshing fragment that polls email generation progress."""
    all_emails = run_sync(db.get_generated_emails(selected_campaign_id))

    if not all_emails:
        return

    total = len(person_ids)
    generated = len(all_emails)
    drafts = sum(1 for e in all_emails if e.status == "draft")
    approved = sum(1 for e in all_emails if e.status == "approved")
    rejected = sum(1 for e in all_emails if e.status == "rejected")
    failed = sum(1 for e in all_emails if e.status == "failed")

    m_cols = st.columns(5)
    m_cols[0].metric("Generated", f"{generated}/{total}")
    m_cols[1].metric("Drafts", drafts)
    m_cols[2].metric("Approved", approved)
    m_cols[3].metric("Rejected", rejected)
    m_cols[4].metric("Failed", failed)

    progress_frac = min(generated / max(total, 1), 1.0)
    st.progress(progress_frac, text=f"{progress_frac * 100:.1f}% complete")

    total_cost = sum(e.cost_usd for e in all_emails)
    if total_cost > 0:
        st.caption(f"Total generation cost: ${total_cost:.4f}")

    if generated >= total:
        st.session_state["email_gen_running"] = False


if st.session_state.get("email_gen_running"):
    _poll_email_progress()

# ---------------------------------------------------------------------------
# Email Table: Preview, Edit, Approve/Reject
# ---------------------------------------------------------------------------

st.subheader("Generated Emails")

# Status filter
status_filter = st.radio(
    "Filter by Status",
    options=["All", "Draft", "Approved", "Rejected", "Failed"],
    horizontal=True,
    label_visibility="collapsed",
)

filter_status = None if status_filter == "All" else status_filter.lower()
emails = run_sync(db.get_generated_emails(selected_campaign_id, status=filter_status))

if not emails:
    st.info("No emails generated yet. Use the Generate buttons above to create emails.")
    st.stop()

# Load person/company data for display
all_person_ids = list({e.person_id for e in emails})
all_company_ids = list({e.company_id for e in emails if e.company_id})

persons_map = _get_persons_map(db, all_person_ids)

# Load companies
companies_map = {}
for cid in all_company_ids:
    async def _get_company(company_id=cid):
        async with db._connect() as conn:
            cursor = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
            row = await cursor.fetchone()
            if row:
                return db._row_to_company(row)
            return None
    c = run_sync(_get_company())
    if c:
        companies_map[cid] = c

# ---------------------------------------------------------------------------
# Bulk Actions
# ---------------------------------------------------------------------------

bulk_cols = st.columns([1, 1, 4])
with bulk_cols[0]:
    if st.button("Approve All Drafts", icon=":material/check_circle:", use_container_width=True):
        draft_emails = [e for e in emails if e.status == "draft"]
        for e in draft_emails:
            run_sync(db.update_email_status(e.id, "approved"))
        if draft_emails:
            st.toast(f"Approved {len(draft_emails)} emails.")
            st.rerun()

with bulk_cols[1]:
    if st.button("Reject All Drafts", icon=":material/cancel:", type="secondary", use_container_width=True):
        draft_emails = [e for e in emails if e.status == "draft"]
        for e in draft_emails:
            run_sync(db.update_email_status(e.id, "rejected"))
        if draft_emails:
            st.toast(f"Rejected {len(draft_emails)} emails.")
            st.rerun()

# ---------------------------------------------------------------------------
# Email List with Expandable Preview/Edit
# ---------------------------------------------------------------------------

for email in emails:
    person = persons_map.get(email.person_id)
    company = companies_map.get(email.company_id) if email.company_id else None

    contact_name = f"{person.first_name or ''} {person.last_name or ''}".strip() if person else "Unknown"
    company_name = company.name if company else (person.company_name if person else "")
    status_icon = {
        "draft": ":material/edit:",
        "approved": ":material/check_circle:",
        "rejected": ":material/cancel:",
        "failed": ":material/error:",
    }.get(email.status, ":material/help:")

    header = f"{status_icon} **{contact_name}** | {company_name} | {email.subject or '(no subject)'} | Step {email.sequence_step} | _{email.status}_"

    with st.expander(header, expanded=False):
        # Preview
        st.markdown(f"**Subject:** {email.subject or '(no subject)'}")
        st.markdown("**Body:**")
        st.text(email.body or "(no body)")

        if email.status != "failed":
            # Inline edit
            st.markdown("---")
            edited_subject = st.text_input(
                "Edit Subject",
                value=email.subject or "",
                key=f"subj_{email.id}",
            )
            edited_body = st.text_area(
                "Edit Body",
                value=email.body or "",
                key=f"body_{email.id}",
                height=150,
            )

            edit_cols = st.columns([1, 1, 1, 3])
            with edit_cols[0]:
                if st.button("Save Edits", key=f"save_{email.id}", use_container_width=True):
                    run_sync(db.update_email_content(email.id, edited_subject, edited_body))
                    st.toast("Email updated.")
                    st.rerun()

            with edit_cols[1]:
                if email.status != "approved":
                    if st.button("Approve", key=f"approve_{email.id}", type="primary", use_container_width=True):
                        run_sync(db.update_email_status(email.id, "approved"))
                        st.toast("Email approved.")
                        st.rerun()

            with edit_cols[2]:
                if email.status != "rejected":
                    if st.button("Reject", key=f"reject_{email.id}", type="secondary", use_container_width=True):
                        run_sync(db.update_email_status(email.id, "rejected"))
                        st.toast("Email rejected.")
                        st.rerun()

            # Regenerate with note
            if api_key:
                regen_note = st.text_input(
                    "Regeneration note",
                    key=f"regen_note_{email.id}",
                    placeholder="e.g., make it shorter",
                )
                if st.button("Regenerate", key=f"regen_{email.id}"):
                    import anthropic

                    with st.spinner("Regenerating..."):
                        client = anthropic.Anthropic(api_key=api_key)
                        template = run_sync(db.get_email_template(email.template_id))
                        person_obj, company_obj = run_sync(
                            db.get_person_with_company(email.person_id)
                        )
                        new_email = generate_single_email(
                            client=client,
                            template=template,
                            person=person_obj,
                            company=company_obj,
                            campaign_id=email.campaign_id,
                            user_note=regen_note or None,
                        )
                        # Update existing email with new content
                        run_sync(db.update_email_content(email.id, new_email.subject or "", new_email.body or ""))
                        run_sync(db.update_email_status(email.id, "draft"))
                    st.toast("Email regenerated.")
                    st.rerun()

# ---------------------------------------------------------------------------
# CAN-SPAM / CASL Compliance Note
# ---------------------------------------------------------------------------

st.info(
    "**Compliance reminder:** When importing emails into Outreach.io or another sending tool, "
    "ensure your emails include a physical mailing address and an unsubscribe link. "
    "For Canadian contacts (CASL), verify that you have prior consent to email."
)

# ---------------------------------------------------------------------------
# Export Section
# ---------------------------------------------------------------------------

st.subheader("Export Emails")

export_preset = st.selectbox(
    "Export Preset",
    options=["Outreach.io", "Salesforce Lead", "Raw"],
    help="Outreach.io and Salesforce exports include only approved emails. Raw includes all.",
)

# Reload all emails for export (unfiltered)
all_emails_for_export = run_sync(db.get_generated_emails(selected_campaign_id))

# Count approved
approved_count = sum(1 for e in all_emails_for_export if e.status == "approved")

if export_preset != "Raw" and approved_count == 0:
    st.warning("No approved emails to export. Approve some emails first.")
else:
    # Build export data
    # Ensure we have all persons and companies loaded
    export_person_ids = list({e.person_id for e in all_emails_for_export})
    export_company_ids = list({e.company_id for e in all_emails_for_export if e.company_id})

    if not persons_map or set(export_person_ids) - set(persons_map.keys()):
        persons_map = _get_persons_map(db, export_person_ids)

    for cid in export_company_ids:
        if cid not in companies_map:
            async def _get_comp(company_id=cid):
                async with db._connect() as conn:
                    cursor = await conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
                    row = await cursor.fetchone()
                    if row:
                        return db._row_to_company(row)
                    return None
            c = run_sync(_get_comp())
            if c:
                companies_map[cid] = c

    export_df = _build_export_df(all_emails_for_export, persons_map, companies_map, export_preset)

    if not export_df.empty:
        # Get campaign name for filename
        campaign_obj = run_sync(db.get_campaign(selected_campaign_id))
        safe_name = (campaign_obj.name if campaign_obj else "export").replace(" ", "_").lower()

        preset_prefix = {
            "Outreach.io": "outreach",
            "Salesforce Lead": "sf",
            "Raw": "raw",
        }[export_preset]

        filename = f"emails_{preset_prefix}_{safe_name}.csv"
        csv_data = export_df.to_csv(index=False).encode("utf-8")

        st.dataframe(export_df, use_container_width=True, height=300)

        st.download_button(
            f"Download {export_preset} CSV ({len(export_df)} rows)",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
            type="primary",
        )
    else:
        st.info("No emails match the export criteria.")
