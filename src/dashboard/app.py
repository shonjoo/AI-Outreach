"""Interactive Review Dashboard for personalized outreach automation."""

import csv
import io
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from src.config import load_config
from src.db.database import Database
from src.db.models import Contact, ContactStatus, Draft, DraftStatus, ResearchDossier
from src.generation.generator import DraftGenerator
from src.research.dossier import DossierBuilder
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager

# Streamlit Page Config (Very first call, wide layout, expanded sidebar)
st.set_page_config(
    page_title="Outreach",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Consolidated custom CSS: System font, layout containment, high contrast, and single accent color
st.markdown(
    """
    <style>
    /* System font for standard UI text, inputs, buttons, and markdown */
    html, body,
    div[data-testid="stAppViewContainer"],
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stHeader"],
    div[data-testid="stSidebar"],
    div[data-testid="stMarkdownContainer"],
    .stMarkdown,
    h1, h2, h3, h4, h5, h6,
    p, label, input, button, select, textarea {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }
    /* Fixed container sizing to prevent layout shift */
    div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stContainer"]) {
        contain: layout;
    }
    /* Contrast: High contrast monospace for code blocks */
    code, pre, .stCode, [data-testid="stMarkdownContainer"] code, [data-testid="stCodeBlock"], [data-testid="stCodeBlock"] * {
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace !important;
        color: #E6EDF3 !important;
        background-color: #161B22 !important;
    }
    /* Explicitly preserve and enforce Material Symbols Rounded for Streamlit icons */
    [data-testid="stIconMaterial"],
    [data-testid*="stIcon"],
    [data-testid*="Icon"],
    [data-testid="stExpanderToggleIcon"],
    [data-testid="stExpanderStepChevron"],
    [data-testid="stExpanderStepIcon"],
    [data-testid="stAlertDynamicIcon"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons,
    [class*="e1vmumty0"] {
        font-family: "Material Symbols Rounded" !important;
        font-weight: normal !important;
        font-style: normal !important;
        line-height: 1 !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        display: inline-flex !important;
        white-space: nowrap !important;
        word-wrap: normal !important;
        direction: ltr !important;
        -webkit-font-smoothing: antialiased !important;
        text-rendering: optimizeLegibility !important;
        font-feature-settings: 'liga' 1 !important;
        -webkit-font-feature-settings: 'liga' 1 !important;
        -moz-font-feature-settings: 'liga' 1 !important;
    }
    /* Neutral alerts: No decorative borders except error states */
    div[data-testid="stAlert"] {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
        border: 1px solid #30363D !important;
    }
    div[data-testid="stAlert"] p,
    div[data-testid="stAlert"] div {
        color: #E6EDF3 !important;
    }
    div[data-testid="stAlert"] [data-testid="stIconMaterial"],
    div[data-testid="stAlert"] [data-testid="stAlertDynamicIcon"],
    div[data-testid="stAlert"] svg {
        color: #E6EDF3 !important;
        fill: #E6EDF3 !important;
    }
    /* Error state accent */
    div[data-testid="stAlert"]:has([data-testid="stAlert-error"]) {
        border-left: 3px solid #CF222E !important;
    }
    /* Single accent color used only for primary actions */
    button[kind="primary"],
    [data-testid="stButton"] > button[kind="primary"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"] {
        background-color: #0969DA !important;
        border-color: #0969DA !important;
        color: #FFFFFF !important;
    }
    button[kind="primary"]:hover {
        background-color: #0856B7 !important;
        border-color: #0856B7 !important;
    }
    /* Touch Targets: Minimum 36px height & adequate padding for tabs and buttons */
    button[data-baseweb="tab"],
    [data-testid="stTabs"] button {
        min-height: 36px !important;
        padding: 8px 16px !important;
        font-size: 0.95rem !important;
        line-height: 1.25 !important;
    }
    .stButton > button,
    [data-testid="stButton"] > button,
    [data-testid="stFormSubmitButton"] > button,
    [data-testid="stLinkButton"] > a {
        min-height: 36px !important;
        padding: 8px 16px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 0.95rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

config = load_config()
db = Database(config.db_path, config=config)
dossier_builder = DossierBuilder()
draft_gen = DraftGenerator(config, db)
sender = OutreachSender(config, db)
suppression_mgr = SuppressionManager(db)

# Cached database loader (Requirement 4: Wrap contact loading in st.cache_data)
@st.cache_data(show_spinner=False)
def load_all_contacts(backend_name: str, db_path: str):
    database = Database(db_path, config=config)
    return database.list_contacts()

# Remote Access Security: Optional Dashboard Password Check
import os
dashboard_password = os.getenv("DASHBOARD_PASSWORD", "").strip()

if dashboard_password:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("Login")
        st.write("Password required.")
        pwd_input = st.text_input("Password:", type="password")
        if st.button("Log In"):
            if pwd_input == dashboard_password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

# Sidebar
with st.sidebar:
    st.header("Control panel")
    st.markdown(f"**Sender:** {config.sender.name}")
    st.markdown(f"**From:** `{config.sender.email}`")
    st.markdown(f"**LLM Provider:** `{config.llm.provider.upper()}`")
    backend_display = "SUPABASE (Cloud)" if db.is_supabase else "SQLITE (Local)"
    st.markdown(f"**Database:** `{backend_display}`")

    st.divider()
    dry_run_active = st.toggle("Dry-run mode", value=config.dry_run)
    if dry_run_active:
        st.info("Dry-run active. Sending simulated.")
    else:
        st.warning("Live mode. Real emails will be sent.")

    st.divider()
    today_count = db.get_today_sent_count()
    max_limit = config.limits.emails_per_day
    st.metric("Sent today", f"{today_count} / {max_limit}")
    st.progress(min(today_count / max(max_limit, 1), 1.0))

    st.divider()
    st.subheader("Import contacts")
    uploaded_file = st.file_uploader(
        "Contacts file (.csv, .xlsx):",
        type=["csv", "xlsx", "xlsm"],
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        fname = uploaded_file.name

        # If Excel workbook, check available sheets
        target_sheet = None
        if fname.lower().endswith((".xlsx", ".xlsm")):
            try:
                import openpyxl
                wb_preview = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
                sheets = wb_preview.sheetnames
                default_idx = 0
                for i, s in enumerate(sheets):
                    if any(w in s.lower() for w in ["niche", "fit", "lead", "contact"]):
                        default_idx = i
                        break
                target_sheet = st.selectbox("Sheet:", sheets, index=default_idx)
            except Exception as e:
                st.warning(f"Could not read sheets: {e}")

        from src.db.csv_importer import parse_any_lead_file, import_contacts_to_db

        parsed_contacts, parse_errors, meta = parse_any_lead_file(
            file_bytes=file_bytes,
            filename=fname,
            target_sheet=target_sheet,
        )

        if parse_errors:
            for err in parse_errors:
                st.error(err)

        if parsed_contacts:
            st.success(f"Found {len(parsed_contacts)} contacts.")

            # Show preview
            with st.expander("Preview contacts", expanded=False):
                preview_data = [
                    {"Name": c.full_name, "Company": c.company, "Title": c.job_title, "LinkedIn": bool(c.linkedin_url)}
                    for c in parsed_contacts[:5]
                ]
                st.dataframe(preview_data)

            col_u1, col_u2 = st.columns([1, 1])
            with col_u1:
                if st.button("Import and generate", type="primary", key="btn_import_gen"):
                    imported_count = 0
                    with st.spinner("Processing..."):
                        progress_bar = st.progress(0.0)
                        for idx, contact in enumerate(parsed_contacts):
                            cid = db.insert_contact(contact)
                            contact.id = cid
                            imported_count += 1
                            # Research & Draft
                            dossier = dossier_builder.build_dossier(contact)
                            db.save_dossier(dossier)
                            draft_gen.generate_for_contact(contact, dossier)
                            progress_bar.progress((idx + 1) / len(parsed_contacts))
                    load_all_contacts.clear()
                    st.success(f"Imported and generated drafts for {imported_count} contacts.")
                    st.rerun()

            with col_u2:
                if st.button("Import only", key="btn_import_only"):
                    imported_count = import_contacts_to_db(db, parsed_contacts)
                    load_all_contacts.clear()
                    st.success(f"Imported {imported_count} contacts.")
                    st.rerun()

    if st.button("Load sample contacts"):
        sample_path = Path("data/sample_contacts.csv")
        if sample_path.exists():
            with open(sample_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    contact = Contact(
                        first_name=row.get("first_name", "").strip(),
                        last_name=row.get("last_name", "").strip(),
                        company=row.get("company", "").strip(),
                        job_title=row.get("job_title", "").strip(),
                        linkedin_url=row.get("linkedin_url", "").strip(),
                        email=row.get("email", "").strip(),
                        notes=row.get("notes", "").strip(),
                    )
                    db.insert_contact(contact)
            load_all_contacts.clear()
            st.success("Sample contacts loaded.")
            st.rerun()


# Main Dashboard
st.title("Outreach")

# Navigation Tabs: Dossier and Drafts, Sent log, Follow-ups, Suppressed
tab_drafts, tab_sent, tab_followups, tab_suppression = st.tabs(
    ["Drafts", "Sent log", "Follow-ups", "Suppressed"]
)

# ----------------- TAB 1: DRAFTS -----------------
with tab_drafts:
    st.header("Drafts")
    all_contacts = load_all_contacts(db.backend_name, config.db_path)
    unprocessed_contacts = [c for c in all_contacts if not db.get_draft(c.id)]

    # Persistent toolbar container (prevents vertical layout shift on first load)
    toolbar_container = st.container()
    if unprocessed_contacts:
        with toolbar_container:
            c_b1, c_b2 = st.columns([3, 1])
            with c_b1:
                st.warning(f"{len(unprocessed_contacts)} contacts pending research and draft generation.")
            with c_b2:
                if st.button("Generate pending", type="primary", key="btn_gen_all_pending"):
                    p_bar = st.progress(0.0)
                    st_text = st.empty()
                    for idx, c in enumerate(unprocessed_contacts):
                        st_text.text(f"Processing ({idx+1}/{len(unprocessed_contacts)}): {c.company}...")
                        d = dossier_builder.build_dossier(c)
                        db.save_dossier(d)
                        draft_gen.generate_for_contact(c, d)
                        p_bar.progress((idx + 1) / len(unprocessed_contacts))
                    load_all_contacts.clear()
                    st.success(f"Generated drafts for {len(unprocessed_contacts)} contacts.")
                    st.rerun()

    # Filter options
    status_filter = st.selectbox(
        "Status:",
        [
            "Pending actions",
            "FLAGGED",
            "READY_FOR_REVIEW",
            "NEEDS_MANUAL_REVIEW",
            "APPROVED",
            "PENDING_RESEARCH",
            "ALL",
        ],
        index=0,
    )

    filtered_contacts = []
    for c in all_contacts:
        c_draft = db.get_draft(c.id)
        if status_filter == "Pending actions":
            if c.status in (ContactStatus.READY_FOR_REVIEW, ContactStatus.NEEDS_MANUAL_REVIEW, ContactStatus.PENDING_RESEARCH):
                filtered_contacts.append(c)
        elif status_filter == "FLAGGED":
            if c_draft and c_draft.status == DraftStatus.FLAGGED:
                filtered_contacts.append(c)
        elif status_filter == "ALL":
            filtered_contacts.append(c)
        elif c.status.value == status_filter:
            filtered_contacts.append(c)

    if not filtered_contacts:
        st.info("No contacts found.")
    else:
        st.write(f"{len(filtered_contacts)} contacts")

        for contact in filtered_contacts:
            dossier = db.get_dossier(contact.id)
            draft = db.get_draft(contact.id)
            is_flagged = bool(draft and draft.status == DraftStatus.FLAGGED)
            flagged_badge = " [FLAGGED]" if is_flagged else ""

            # Deterministic expander state (zero conditional page height shifts on load)
            with st.expander(
                f"**{contact.full_name}** — {contact.job_title}, **{contact.company}** [{contact.status.value}]{flagged_badge}",
                expanded=False,
            ):
                col_left, col_right = st.columns([1, 1])

                # Left Column: Dossier
                with col_left:
                    st.subheader("Dossier")
                    dossier_container = st.container(height=520)
                    with dossier_container:
                        dossier_box = st.empty()
                        with dossier_box.container():
                            if contact.email.endswith("@linkedin-lead.local"):
                                st.markdown("**Email:** *Not provided in sheet (LinkedIn outreach)*")
                            else:
                                st.markdown(f"**Email:** `{contact.email}`")
                            if contact.linkedin_url:
                                st.markdown(f"**LinkedIn:** [{contact.linkedin_url}]({contact.linkedin_url})")

                            if dossier:
                                if dossier.website_url:
                                    st.markdown(f"**Website:** [{dossier.website_url}]({dossier.website_url})")
                                st.markdown("**Source facts:**")
                                for fact in dossier.verifiable_facts:
                                    st.markdown(f"- {fact}")

                                if dossier.detected_opportunities:
                                    st.markdown("**Opportunities:**")
                                    for opp in dossier.detected_opportunities:
                                        st.markdown(f"- {opp}")

                                if not dossier.has_strong_hook:
                                    st.warning("Insufficient source facts found. Add notes below.")

                            else:
                                st.info("Not researched yet.")

                            # Add or update notes / LinkedIn post
                            with st.form(key=f"research_form_{contact.id}"):
                                pasted_info = st.text_area(
                                    "Notes or recent post:",
                                    value=dossier.user_pasted_content if dossier else "",
                                    height=70,
                                )
                                run_research = st.form_submit_button("Research and generate")
                                if run_research:
                                    with st.spinner("Generating..."):
                                        new_dossier = dossier_builder.build_dossier(contact, user_pasted_linkedin=pasted_info)
                                        db.save_dossier(new_dossier)
                                        new_draft = draft_gen.generate_for_contact(contact, new_dossier)
                                        load_all_contacts.clear()
                                        st.success("Draft generated.")
                                        st.rerun()

                # Right Column: Drafts
                with col_right:
                    st.subheader("Drafts")
                    drafts_container = st.container(height=520)
                    with drafts_container:
                        drafts_box = st.empty()
                        with drafts_box.container():
                            if not draft:
                                st.info("No draft generated yet.")
                            else:
                                if is_flagged:
                                    st.error("Flagged: Draft failed validation or fact-grounding. Manual edit and approval required before sending.")

                                # 1-Line Hook
                                st.markdown(f"**Hook:**\n> *\"{draft.hook}\"*")
                                if draft.source_facts:
                                    st.caption(f"Source: {', '.join(draft.source_facts)}")

                                # Sub-tabs for LinkedIn vs Email
                                tab_email, tab_li = st.tabs(["Email", "LinkedIn"])

                                with tab_email:
                                    st.markdown(f"**Subject:** `{draft.email_subject}`")
                                    with st.expander("Alternative subjects", expanded=False):
                                        st.markdown(f"1. `{draft.email_subject_alt1}`")
                                        st.markdown(f"2. `{draft.email_subject_alt2}`")

                                    editable_body = st.text_area(
                                        "Body:",
                                        value=draft.email_body,
                                        height=180,
                                        key=f"email_body_{contact.id}",
                                    )

                                    word_count = len(editable_body.split())
                                    st.caption(f"Word count: {word_count} words")

                                    col_e1, col_e2, col_e3, col_e4 = st.columns(4)

                                    with col_e1:
                                        if st.button("Save", key=f"save_email_{contact.id}"):
                                            db.update_draft_content(
                                                draft_id=draft.id,
                                                hook=draft.hook,
                                                email_subject=draft.email_subject,
                                                email_body=editable_body,
                                                linkedin_note=draft.linkedin_note,
                                                linkedin_message=draft.linkedin_message,
                                                status=DraftStatus.EDITED,
                                            )
                                            load_all_contacts.clear()
                                            st.success("Saved.")
                                            st.rerun()

                                    with col_e2:
                                        if st.button("Approve", key=f"appr_email_{contact.id}"):
                                            db.update_draft_status(draft.id, DraftStatus.APPROVED)
                                            db.update_contact_status(contact.id, ContactStatus.APPROVED)
                                            load_all_contacts.clear()
                                            st.success("Approved.")
                                            st.rerun()

                                    with col_e3:
                                        if is_flagged:
                                            st.button("Send", key=f"send_email_{contact.id}", disabled=True)
                                        else:
                                            if st.button("Send", key=f"send_email_{contact.id}"):
                                                success, msg = sender.send_approved_email(
                                                    contact=contact,
                                                    draft=draft,
                                                    force_dry_run=dry_run_active,
                                                )
                                                load_all_contacts.clear()
                                                if success:
                                                    st.success(msg)
                                                else:
                                                    st.error(msg)
                                                st.rerun()

                                    with col_e4:
                                        if st.button("Skip", key=f"skip_{contact.id}"):
                                            db.update_contact_status(contact.id, ContactStatus.SKIPPED)
                                            load_all_contacts.clear()
                                            st.info("Skipped.")
                                            st.rerun()

                                with tab_li:
                                    st.markdown("Manual sending required.")

                                    st.markdown(f"**Connection note ({len(draft.linkedin_note)}/300):**")
                                    st.code(draft.linkedin_note, language="text")

                                    st.markdown(f"**Message ({len(draft.linkedin_message)}/600):**")
                                    st.code(draft.linkedin_message, language="text")

                                    col_li1, col_li2 = st.columns(2)
                                    with col_li1:
                                        if contact.linkedin_url:
                                            st.link_button("Open LinkedIn profile", contact.linkedin_url)
                                        else:
                                            st.caption("No LinkedIn URL.")

                                    with col_li2:
                                        if st.button("Mark sent", key=f"mark_li_{contact.id}"):
                                            db.update_contact_status(contact.id, ContactStatus.LINKEDIN_SENT)
                                            load_all_contacts.clear()
                                            st.success("Marked as sent.")
                                            st.rerun()


# ----------------- TAB 2: SENT LOGS -----------------
with tab_sent:
    st.header("Sent log")
    logs = db.list_send_logs(limit=50)
    if not logs:
        st.info("No logs.")
    else:
        log_data = []
        for l in logs:
            log_data.append({
                "ID": l.id,
                "Recipient": l.recipient,
                "Channel": l.channel,
                "Mode": "Dry-run" if l.is_dry_run else "Live",
                "Status": l.status,
                "Message ID": l.gmail_message_id or "-",
                "Sent At": l.sent_at[:19],
                "Error": l.error_message or "None",
            })
        st.dataframe(log_data, width="stretch")


# ----------------- TAB 3: FOLLOW-UPS -----------------
with tab_followups:
    st.header("Follow-ups")

    contacts_for_fu = db.list_contacts(ContactStatus.EMAIL_SENT)
    if not contacts_for_fu:
        st.info("No pending follow-ups.")
    else:
        for contact in contacts_for_fu:
            draft = db.get_draft(contact.id)
            if draft and draft.followup_body:
                with st.expander(f"**{contact.full_name}** — {contact.company}"):
                    st.markdown(f"**Subject:** `{draft.followup_subject}`")
                    st.text_area(
                        "Body:",
                        value=draft.followup_body,
                        height=120,
                        key=f"fu_body_{contact.id}",
                    )
                    col_fu1, col_fu2 = st.columns(2)
                    with col_fu1:
                        if st.button("Approve", key=f"appr_fu_{contact.id}"):
                            st.success(f"Approved for {contact.email}.")
                    with col_fu2:
                        if st.button("Mark replied", key=f"replied_{contact.id}"):
                            db.update_contact_status(contact.id, ContactStatus.REPLIED)
                            st.success(f"Marked {contact.email} as replied.")
                            st.rerun()


# ----------------- TAB 4: SUPPRESSION LIST -----------------
with tab_suppression:
    st.header("Suppressed")

    with st.form("add_suppression_form"):
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            sup_email = st.text_input("Email:")
        with col_s2:
            sup_reason = st.text_input("Reason:", value="Opt-out")
        add_sup = st.form_submit_button("Suppress email")
        if add_sup and sup_email:
            suppression_mgr.suppress_contact(sup_email, reason=sup_reason)
            st.success(f"Suppressed {sup_email}.")
            st.rerun()

    suppressed = db.list_suppressed()
    if suppressed:
        st.dataframe(
            [{"Email": s.email, "Reason": s.reason, "Opted Out At": s.opted_out_at[:19]} for s in suppressed],
            width="stretch",
        )
    else:
        st.info("No suppressed emails.")
