"""Interactive Review Dashboard for personalized outreach automation."""

import csv
import io
import os
import re
import sys
import urllib.parse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from src.config import load_config
from src.db.database import Database
from src.db.models import Contact, ContactStatus, Draft, DraftStatus, ResearchDossier, SendLog
from src.generation.generator import DraftGenerator
from src.generation.llm_client import GeminiQuotaError
from src.research.dossier import DossierBuilder
from src.sending.sender import OutreachSender
from src.sending.suppression import SuppressionManager
from src.sending.worker import DispatchWorker
from src.db.csv_importer import import_contacts_to_db, parse_any_lead_file


# Streamlit Page Config (Very first call, wide layout, expanded sidebar)
st.set_page_config(
    page_title="Outreach",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ShadCN UI Theme - Zinc Dark Design System
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    /* ==========================================================================
       FIGMA DESIGN SYSTEM SPECIFICATION (Zinc / Charcoal Dark Palette)
       - 8pt Spatial Grid (8px, 16px, 24px, 32px padding/margins)
       - Standardized Radii: Small (6px), Medium (8px), Large (12px), Full (9999px)
       - Strict Typography Hierarchy: 12px captions, 14px body, 16px headings/titles, 24px/32px displays
       - Color Tokens: Surface-0 (#09090b), Surface-1 (#121215), Surface-2 (#18181b), Border (#27272a)
       ========================================================================== */

    :root {
        --figma-bg-primary: #000000;
        --figma-bg-surface: #0a0a0a;
        --figma-bg-surface-elevated: #121212;
        --figma-border: #1e2420;
        --figma-border-subtle: #141815;
        --figma-border-hover: #84cc16;
        --figma-accent: #84cc16;
        --figma-accent-hover: #65a30d;
        --figma-accent-glow: rgba(132, 204, 22, 0.25);
        --figma-text-primary: #f0fdf4;
        --figma-text-secondary: #94a3b8;
        --figma-text-muted: #64748b;
        --figma-radius-sm: 6px;
        --figma-radius-md: 8px;
        --figma-radius-lg: 12px;
        --figma-font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        --figma-font-mono: 'JetBrains Mono', monospace;
    }

    /* Global Typography & Canvas */
    html, body,
    div[data-testid="stAppViewContainer"],
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stHeader"],
    div[data-testid="stSidebar"],
    div[data-testid="stMarkdownContainer"],
    .stMarkdown,
    h1, h2, h3, h4, h5, h6,
    p, label, input, button, select, textarea {
        font-family: var(--figma-font-sans) !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }

    div[data-testid="stAppViewContainer"] {
        background-color: var(--figma-bg-primary) !important;
        color: #f4f4f5 !important;
    }

    div[data-testid="stAppViewBlockContainer"] {
        max-width: 1280px !important;
        padding-top: 2rem !important;
        padding-bottom: 3.5rem !important;
    }

    div[data-testid="stHeader"] {
        background-color: rgba(0, 0, 0, 0.85) !important;
        backdrop-filter: blur(16px) !important;
        border-bottom: 1px solid var(--figma-border) !important;
    }

    /* Headings - Figma Text Hierarchy */
    h1 {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.035em !important;
        color: var(--figma-text-primary) !important;
        line-height: 1.25 !important;
    }

    h2 {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.025em !important;
        color: var(--figma-text-primary) !important;
        line-height: 1.3 !important;
    }

    h3 {
        font-size: 1rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
        color: var(--figma-text-primary) !important;
    }

    p, span, div {
        letter-spacing: -0.01em;
    }

    /* Universal Interactive Clickable Targets */
    button,
    [role="button"],
    [role="tab"],
    [data-baseweb="tab"],
    [data-testid="stExpander"] summary,
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label,
    [data-baseweb="select"],
    [data-testid="stLinkButton"] > a,
    .shadcn-card,
    .shadcn-badge,
    a {
        cursor: pointer !important;
        user-select: none;
    }

    /* Figma Segmented Controls / Tab Bars */
    div[data-testid="stTabs"] {
        border-bottom: none !important;
    }

    div[data-testid="stTabs"] > div:first-child {
        background-color: #121215 !important;
        border: 1px solid var(--figma-border) !important;
        border-radius: var(--figma-radius-md) !important;
        padding: 3px !important;
        gap: 3px !important;
        display: inline-flex !important;
        margin-bottom: 1.25rem !important;
    }

    div[data-testid="stTabs"] button[role="tab"] {
        background: transparent !important;
        color: var(--figma-text-secondary) !important;
        border: none !important;
        border-radius: var(--figma-radius-sm) !important;
        padding: 6px 14px !important;
        font-size: 0.8125rem !important;
        font-weight: 500 !important;
        line-height: 1.25 !important;
        transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1) !important;
        min-height: 30px !important;
    }


    div[data-testid="stTabs"] button[role="tab"]:hover {
        color: #fafafa !important;
        background: rgba(255, 255, 255, 0.07) !important;
        transform: translateY(-0.5px) !important;
    }

    div[data-testid="stTabs"] button[role="tab"]:active {
        transform: scale(0.97) !important;
        transition: all 0.08s ease !important;
    }

    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background-color: var(--figma-accent) !important;
        color: #050505 !important;
        font-weight: 600 !important;
        box-shadow: 0 1px 4px 0 var(--figma-accent-glow) !important;
        transform: none !important;
    }

    div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
    div[data-testid="stTabs"] [data-baseweb="tab-border"] {
        display: none !important;
    }

    /* Lime Green Primary Buttons */
    button[kind="primary"],
    [data-testid="stButton"] > button[kind="primary"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"] {
        background-color: var(--figma-accent) !important;
        border: 1px solid var(--figma-accent) !important;
        color: #050505 !important;
        font-weight: 600 !important;
        font-size: 0.875rem !important;
        border-radius: var(--figma-radius-sm) !important;
        padding: 8px 16px !important;
        box-shadow: 0 1px 3px 0 var(--figma-accent-glow) !important;
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
        min-height: 36px !important;
        will-change: transform, box-shadow, background-color, border-color;
    }

    button[kind="primary"]:hover,
    [data-testid="stButton"] > button[kind="primary"]:hover,
    [data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
        background-color: #a3e635 !important;
        border-color: #a3e635 !important;
        color: #050505 !important;
        transform: translateY(-1.5px) !important;
        box-shadow: 0 4px 14px 0 rgba(132, 204, 22, 0.4) !important;
    }

    button[kind="primary"]:active,
    [data-testid="stButton"] > button[kind="primary"]:active,
    [data-testid="stFormSubmitButton"] > button[kind="primary"]:active {
        transform: translateY(0.5px) scale(0.98) !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.2) !important;
        transition: all 0.08s ease !important;
    }


    /* ShadCN Secondary / Outline Buttons */
    button[kind="secondary"],
    [data-testid="stButton"] > button:not([kind="primary"]),
    [data-testid="stFormSubmitButton"] > button:not([kind="primary"]) {
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
        color: #f4f4f5 !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        border-radius: 0.375rem !important;
        padding: 8px 16px !important;
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
        min-height: 36px !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.15) !important;
        will-change: transform, box-shadow, background-color, border-color;
    }

    [data-testid="stButton"] > button:not([kind="primary"]):hover,
    [data-testid="stFormSubmitButton"] > button:not([kind="primary"]):hover {
        background-color: #27272a !important;
        border-color: #3f3f46 !important;
        color: #ffffff !important;
        transform: translateY(-1.5px) !important;
        box-shadow: 0 4px 14px 0 rgba(0, 0, 0, 0.35) !important;
    }

    [data-testid="stButton"] > button:not([kind="primary"]):active,
    [data-testid="stFormSubmitButton"] > button:not([kind="primary"]):active {
        transform: translateY(0.5px) scale(0.98) !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.2) !important;
        transition: all 0.08s ease !important;
    }

    /* ShadCN Link Button */
    [data-testid="stLinkButton"] > a {
        background-color: transparent !important;
        border: 1px solid #27272a !important;
        color: #f4f4f5 !important;
        border-radius: 0.375rem !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        padding: 8px 16px !important;
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
        min-height: 36px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        will-change: transform, box-shadow, background-color, border-color;
    }

    [data-testid="stLinkButton"] > a:hover {
        background-color: #18181b !important;
        border-color: #3f3f46 !important;
        color: #ffffff !important;
        transform: translateY(-1.5px) !important;
        box-shadow: 0 4px 12px 0 rgba(0, 0, 0, 0.25) !important;
    }

    [data-testid="stLinkButton"] > a:active {
        transform: translateY(0.5px) scale(0.98) !important;
        transition: all 0.08s ease !important;
    }

    /* ShadCN Inputs, Textareas, Selectboxes */
    input, textarea, [data-baseweb="select"] > div {
        background-color: #09090b !important;
        border: 1px solid #27272a !important;
        border-radius: 0.375rem !important;
        color: #f4f4f5 !important;
        font-size: 0.875rem !important;
        transition: border-color 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease, background-color 0.2s ease !important;
    }

    input:hover, textarea:hover, [data-baseweb="select"] > div:hover {
        border-color: #3f3f46 !important;
    }

    input:focus, textarea:focus, [data-baseweb="select"] > div:focus-within {
        border-color: #71717a !important;
        box-shadow: 0 0 0 2px rgba(113, 113, 122, 0.25) !important;
        outline: none !important;
    }

    /* Dropdown options item hover */
    ul[role="listbox"] li {
        transition: background-color 0.15s ease, color 0.15s ease !important;
        cursor: pointer !important;
    }
    ul[role="listbox"] li:hover {
        background-color: #27272a !important;
        color: #ffffff !important;
    }

    /* Radios & Checkboxes */
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        cursor: pointer !important;
        transition: color 0.15s ease, transform 0.15s ease !important;
    }

    [data-testid="stRadio"] label:hover,
    [data-testid="stCheckbox"] label:hover {
        color: #ffffff !important;
    }

    [data-testid="stCheckbox"] div[data-baseweb="checkbox"] span {
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    [data-testid="stCheckbox"] label:active div[data-baseweb="checkbox"] span {
        transform: scale(0.9) !important;
    }

    /* ShadCN Card & Accordion (st.expander) */
    div[data-testid="stExpander"] {
        background-color: #09090b !important;
        border: 1px solid #27272a !important;
        border-radius: 0.5rem !important;
        margin-bottom: 0.75rem !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1) !important;
        overflow: hidden !important;
        transition: border-color 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    div[data-testid="stExpander"]:hover {
        border-color: #3f3f46 !important;
        box-shadow: 0 3px 12px 0 rgba(0, 0, 0, 0.25) !important;
    }

    div[data-testid="stExpander"] details {
        border: none !important;
    }

    div[data-testid="stExpander"] summary {
        background-color: var(--figma-bg-surface) !important;
        border-bottom: 1px solid transparent !important;
        padding: 0.75rem 1rem !important;
        color: #f4f4f5 !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        transition: background-color 0.15s ease, color 0.15s ease !important;
        cursor: pointer !important;
    }

    div[data-testid="stExpander"] details[open] summary {
        border-bottom: 1px solid var(--figma-border) !important;
    }

    div[data-testid="stExpander"] summary:hover {
        background-color: #202024 !important;
        color: #ffffff !important;
    }

    div[data-testid="stExpander"] summary:active {
        background-color: var(--figma-bg-surface-elevated) !important;
    }

    div[data-testid="stExpander"] summary svg {
        transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    /* Sidebar - Scrollable Workspace Pane */
    [data-testid="stSidebar"],
    [data-testid="stSidebarNav"],
    section[data-testid="stSidebar"] > div {
        background-color: var(--figma-bg-primary) !important;
    }

    [data-testid="stSidebarContent"] {
        background-color: var(--figma-bg-primary) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding-top: 1.25rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1.15rem !important;
        padding-right: 1.15rem !important;
        scrollbar-width: thin !important;
        scrollbar-color: var(--figma-border) transparent !important;
    }

    [data-testid="stSidebarContent"]::-webkit-scrollbar {
        width: 5px !important;
    }

    [data-testid="stSidebarContent"]::-webkit-scrollbar-track {
        background: transparent !important;
    }

    [data-testid="stSidebarContent"]::-webkit-scrollbar-thumb {
        background: var(--figma-border) !important;
        border-radius: 9999px !important;
    }

    [data-testid="stSidebarContent"]::-webkit-scrollbar-thumb:hover {
        background: var(--figma-accent) !important;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid var(--figma-border) !important;
    }


    /* Compact sidebar elements so everything fits within standard viewport height */
    [data-testid="stSidebar"] .shadcn-card {
        padding: 0.6rem 0.8rem !important;
        margin-bottom: 0.35rem !important;
    }

    [data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
        gap: 0.45rem !important;
    }

    [data-testid="stSidebar"] hr {
        margin: 0.45rem 0 !important;
    }



    /* Figma Component: Surface Cards */
    .shadcn-card {
        background-color: var(--figma-bg-surface);
        border: 1px solid var(--figma-border);
        border-radius: var(--figma-radius-md);
        padding: 1rem 1.25rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.2);
        transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1),
                    border-color 0.18s ease,
                    box-shadow 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        will-change: transform, box-shadow, border-color;
    }
    .shadcn-card:hover {
        border-color: var(--figma-border-hover);
        transform: translateY(-2px);
        box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.4);
    }
    .shadcn-card-title {
        font-size: 0.6875rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--figma-text-muted);
    }
    .shadcn-card-value {
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: var(--figma-text-primary);
        margin-top: 0.25rem;
        line-height: 1.2;
    }
    .shadcn-card-desc {
        font-size: 0.75rem;
        color: var(--figma-text-muted);
        margin-top: 0.25rem;
    }

    /* ShadCN Badges */
    .shadcn-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 9999px;
        padding: 2px 9px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        line-height: 1.4;
        transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        will-change: transform, filter;
    }
    .shadcn-badge:hover {
        transform: translateY(-1px);
        filter: brightness(1.1);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }

    /* File Uploader drag-and-drop interactive zone */
    [data-testid="stFileUploader"] section {
        border: 1px dashed #27272a !important;
        border-radius: 0.5rem !important;
        background-color: #09090b !important;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
        cursor: pointer !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: #52525b !important;
        background-color: #121215 !important;
        transform: translateY(-1px) !important;
    }

    /* Monospace Code blocks */
    code, pre, .stCode, [data-testid="stCodeBlock"] {
        font-family: 'Geist Mono', ui-monospace, monospace !important;
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
        border-radius: 0.375rem !important;
        color: #e4e4e7 !important;
    }

    /* Alerts */
    div[data-testid="stAlert"] {
        background-color: #18181b !important;
        border: 1px solid #27272a !important;
        border-radius: 0.5rem !important;
        color: #f4f4f5 !important;
        font-size: 0.875rem !important;
    }
    div[data-testid="stAlert"]:has([data-testid="stAlert-error"]) {
        background-color: rgba(239, 68, 68, 0.08) !important;
        border: 1px solid rgba(239, 68, 68, 0.3) !important;
        color: #fca5a5 !important;
    }
    div[data-testid="stAlert"]:has([data-testid="stAlert-warning"]) {
        background-color: rgba(245, 158, 11, 0.08) !important;
        border: 1px solid rgba(245, 158, 11, 0.3) !important;
        color: #fde68a !important;
    }
    div[data-testid="stAlert"]:has([data-testid="stAlert-info"]) {
        background-color: rgba(39, 39, 42, 0.6) !important;
        border: 1px solid #27272a !important;
        color: #d4d4d8 !important;
    }
    div[data-testid="stAlert"]:has([data-testid="stAlert-success"]) {
        background-color: rgba(34, 197, 94, 0.08) !important;
        border: 1px solid rgba(34, 197, 94, 0.3) !important;
        color: #86efac !important;
    }

    /* Material Symbols Rounded Icons */
    [data-testid="stIconMaterial"], [data-testid*="stIcon"], [data-testid*="Icon"] {
        font-family: "Material Symbols Rounded" !important;
    }

    /* Dividers */
    hr {
        border-color: #27272a !important;
        margin: 1.25rem 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def shadcn_badge(label: str, variant: str = "secondary") -> str:
    """Renders a pixel-perfect ShadCN UI badge component."""
    variants = {
        "default": "background-color: #84cc16; color: #050505; border: 1px solid #84cc16; font-weight: 700;",
        "secondary": "background-color: #161917; color: #f0fdf4; border: 1px solid #1e2420;",
        "outline": "background-color: transparent; color: #84cc16; border: 1px solid #84cc16;",
        "success": "background-color: rgba(132, 204, 22, 0.15); color: #a3e635; border: 1px solid rgba(132, 204, 22, 0.4);",
        "warning": "background-color: rgba(245, 158, 11, 0.12); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3);",
        "destructive": "background-color: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);",
        "cloud": "background-color: rgba(132, 204, 22, 0.15); color: #bef264; border: 1px solid rgba(132, 204, 22, 0.35);",
    }
    style = variants.get(variant, variants["secondary"])
    return (
        f'<span class="shadcn-badge" style="{style}">{label}</span>'
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

# Remote Access Security: Dashboard Password Gate
dashboard_password = os.getenv("DASHBOARD_PASSWORD", "").strip()

if dashboard_password:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        _, center_col, _ = st.columns([1, 2, 1])
        with center_col:
            st.markdown(
                """
                <div class="shadcn-card" style="margin-top: 3.5rem; margin-bottom: 1.25rem; text-align: center; padding: 2rem; border-color: rgba(132, 204, 22, 0.3);">
                    <div style="width: 44px; height: 44px; border-radius: 10px; background: #84cc16; color: #050505; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.35rem; margin-bottom: 0.85rem; box-shadow: 0 0 16px rgba(132, 204, 22, 0.4);">✦</div>
                    <div style="font-weight: 600; font-size: 1.35rem; color: #f0fdf4; letter-spacing: -0.025em;">Outreach Studio</div>
                    <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.35rem;">Authentication required to access outreach intelligence.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("shadcn_login_form"):
                pwd_input = st.text_input("Access Password", type="password", placeholder="Enter dashboard password...")
                submit_login = st.form_submit_button("Unlock Studio", type="primary", use_container_width=True)
                if submit_login:
                    if pwd_input == dashboard_password:
                        st.session_state["authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect password. Access denied.")
        st.stop()

# Sidebar
with st.sidebar:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 1.25rem;">
        <div style="width: 32px; height: 32px; border-radius: 8px; background: #84cc16; display: flex; align-items: center; justify-content: center; color: #050505; font-weight: 700; font-size: 1rem; box-shadow: 0 0 10px rgba(132, 204, 22, 0.35);">✦</div>
        <div>
            <div style="font-weight: 600; font-size: 1rem; color: #f0fdf4; letter-spacing: -0.02em; line-height: 1.2;">almost normal</div>
            <div style="font-size: 0.72rem; color: #84cc16; font-weight: 500;">Outreach Studio</div>
        </div>
    </div>


    """, unsafe_allow_html=True)

    # Sender Card
    st.markdown(f"""
    <div class="shadcn-card" style="padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;">
        <div class="shadcn-card-title">Sender Identity</div>
        <div style="font-weight: 600; font-size: 0.875rem; color: #fafafa; margin-top: 4px;">{config.sender.name}</div>
        <div style="font-size: 0.75rem; color: #a1a1aa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{config.sender.email}</div>
    </div>
    """, unsafe_allow_html=True)

    # Database Status Card
    if db.is_supabase:
        db_badge = shadcn_badge("Connected", "cloud")
        db_desc = "Supabase PostgreSQL"
    elif getattr(db, "supabase_schema_pending", False):
        db_badge = shadcn_badge("Pending", "warning")
        db_desc = "SQLite Fallback"
    else:
        db_badge = shadcn_badge("Active", "secondary")
        db_desc = "SQLite Local"

    st.markdown(f"""
    <div class="shadcn-card" style="padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div class="shadcn-card-title">Database</div>
            <div>{db_badge}</div>
        </div>
        <div style="font-size: 0.85rem; font-weight: 500; color: #f4f4f5; margin-top: 4px;">{db_desc}</div>
        <div style="font-size: 0.72rem; color: #71717a; margin-top: 2px;">LLM Engine: {config.llm.provider.upper()}</div>
    </div>
    """, unsafe_allow_html=True)

    if getattr(db, "supabase_schema_pending", False):
        with st.expander("⚡ Activate Supabase Cloud", expanded=False):
            st.caption(
                "Credentials detected! Run `supabase_schema.sql` in your Supabase SQL Editor to initialize tables."
            )

    # Mode Toggle Card
    st.markdown("""
    <div class="shadcn-card-title" style="margin: 0.75rem 0 0.4rem 0;">Delivery Mode</div>
    """, unsafe_allow_html=True)
    dry_run_active = st.toggle("Dry-run mode", value=config.dry_run)
    if dry_run_active:
        st.caption("🔒 Simulated sending — safe for dry testing.")
    else:
        st.warning("⚡ Live mode — real emails will be dispatched.")

    # Quota Progress Card
    today_count = db.get_today_sent_count()
    max_limit = config.limits.emails_per_day
    pct = min(today_count / max(max_limit, 1), 1.0)
    st.markdown(f"""
    <div class="shadcn-card" style="padding: 0.9rem 1.1rem; margin-top: 0.75rem; margin-bottom: 0.4rem;">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <div class="shadcn-card-title">Daily Quota</div>
            <div style="font-weight: 700; font-size: 0.95rem; color: #fafafa;">{today_count} <span style="font-size: 0.75rem; color: #71717a; font-weight: 400;">/ {max_limit}</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.progress(pct)

    # Background Dispatch Queue Worker Card
    st.markdown("""
    <div class="shadcn-card-title" style="margin: 1rem 0 0.4rem 0;">Dispatch Queue Worker</div>
    """, unsafe_allow_html=True)

    worker_instance = st.session_state.get("dispatch_worker")
    is_worker_active = worker_instance is not None and worker_instance.is_running()

    if is_worker_active:
        st.markdown(shadcn_badge("Worker Running (Paced)", "success"), unsafe_allow_html=True)
        if st.button("Stop Dispatch Worker", key="btn_stop_worker", use_container_width=True):
            worker_instance.stop()
            st.session_state["dispatch_worker"] = None
            st.rerun()
    else:
        st.caption("Background service auto-dispatches approved drafts with randomized jitter (90-240s).")
        if st.button("Start Dispatch Worker", key="btn_start_worker", use_container_width=True):
            new_worker = DispatchWorker(
                config=config,
                db=db,
                force_dry_run=dry_run_active,
            )
            new_worker.start()
            st.session_state["dispatch_worker"] = new_worker
            st.rerun()

    st.markdown("""
    <div class="shadcn-card-title" style="margin: 1.25rem 0 0.4rem 0;">Import Leads</div>
    """, unsafe_allow_html=True)

    MAX_UPLOAD_MB = 10
    uploaded_file = st.file_uploader(
        f"Contacts file (.csv, .xlsx, max {MAX_UPLOAD_MB}MB):",
        type=["csv", "xlsx", "xlsm"],
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        fname = uploaded_file.name

        # Enforce maximum upload limit
        if len(file_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"File size exceeds {MAX_UPLOAD_MB}MB limit. Please upload a smaller file.")
            st.stop()


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
                        try:
                            for idx, contact in enumerate(parsed_contacts):
                                cid = db.insert_contact(contact)
                                contact.id = cid
                                imported_count += 1
                                # Research & Draft
                                dossier = dossier_builder.build_dossier(contact)
                                db.save_dossier(dossier)
                                draft_gen.generate_for_contact(contact, dossier)
                                progress_bar.progress((idx + 1) / len(parsed_contacts))
                        except GeminiQuotaError:
                            st.error("⚠️ Daily free Gemini quota reached. Generation stopped. Try again tomorrow.")
                            st.stop()
                    load_all_contacts.clear()
                    st.success(f"Imported and generated drafts for {imported_count} contacts.")
                    st.rerun()


            with col_u2:
                if st.button("Import only", key="btn_import_only"):
                    imported_count = import_contacts_to_db(db, parsed_contacts)
                    load_all_contacts.clear()
                    st.success(f"Imported {imported_count} contacts.")
                    st.rerun()


    if dashboard_password:
        st.markdown("<hr style='margin: 1.5rem 0 1rem 0; border-color: #27272a;'>", unsafe_allow_html=True)
        if st.button("Log out of Studio", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()


# Main Dashboard
all_contacts = load_all_contacts(db.backend_name, config.db_path)
all_drafts_map = db.list_all_drafts()
all_dossiers_map = db.list_all_dossiers()

total_count = len(all_contacts)
approved_count = sum(1 for c in all_contacts if c.status == ContactStatus.APPROVED)
needs_review_count = sum(1 for c in all_contacts if c.status in (ContactStatus.READY_FOR_REVIEW, ContactStatus.NEEDS_MANUAL_REVIEW))
flagged_count = sum(1 for c in all_contacts if (d := all_drafts_map.get(c.id)) and d.status == DraftStatus.FLAGGED)
hot_leads_count = sum(1 for c in all_contacts if c.status == ContactStatus.HOT_LEAD)
replied_count = sum(1 for c in all_contacts if c.status in (ContactStatus.REPLIED, ContactStatus.HOT_LEAD))
follow_up_later_count = sum(1 for c in all_contacts if c.status == ContactStatus.FOLLOW_UP_LATER)
suppressed_all = db.list_suppressed()
suppression_count = len(suppressed_all)
sent_today = db.get_today_sent_count()
limit_today = config.limits.emails_per_day
webhook_configured = bool(config.lead_alert_webhook_url)


# ShadCN Header
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("""
    <div style="margin-bottom: 0.75rem;">
        <h1 style="font-size: 1.85rem; font-weight: 700; letter-spacing: -0.03em; margin: 0; color: #fafafa;">almost normal <span style="font-weight: 400; font-size: 1.25rem; color: #84cc16;">• Outreach Studio</span></h1>
        <p style="font-size: 0.875rem; color: #a1a1aa; margin: 0.25rem 0 0 0;">Autonomous prospect research, verified-fact personalization, and compliant cold messaging.</p>
    </div>

    """, unsafe_allow_html=True)
with col_h2:
    if db.is_supabase:
        db_badge_top = shadcn_badge("Cloud Synced", "cloud")
    else:
        db_badge_top = shadcn_badge("Local Mode", "secondary")
    webhook_badge_top = shadcn_badge("Webhook Connected", "success") if webhook_configured else shadcn_badge("Webhook Offline", "secondary")
    st.markdown(f'<div style="text-align: right; padding-top: 0.5rem; display: flex; justify-content: flex-end; gap: 6px;">{db_badge_top}{webhook_badge_top}</div>', unsafe_allow_html=True)

# ShadCN KPI Stat Cards
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
with kpi1:
    st.markdown(f"""
    <div class="shadcn-card">
        <div class="shadcn-card-title">Total Contacts</div>
        <div class="shadcn-card-value">{total_count}</div>
        <div class="shadcn-card-desc">Active in pipeline</div>
    </div>
    """, unsafe_allow_html=True)
with kpi2:
    st.markdown(f"""
    <div class="shadcn-card">
        <div class="shadcn-card-title">Approved in Queue</div>
        <div class="shadcn-card-value" style="color: #84cc16;">{approved_count}</div>
        <div class="shadcn-card-desc">Ready for dispatch</div>
    </div>
    """, unsafe_allow_html=True)
with kpi3:
    st.markdown(f"""
    <div class="shadcn-card">
        <div class="shadcn-card-title">Dispatched Today</div>
        <div class="shadcn-card-value">{sent_today} <span style="font-size: 0.875rem; color: #71717a; font-weight: 400;">/ {limit_today}</span></div>
        <div class="shadcn-card-desc">Daily cap threshold</div>
    </div>
    """, unsafe_allow_html=True)
with kpi4:
    hot_color = "#84cc16" if hot_leads_count > 0 else "#fafafa"
    st.markdown(f"""
    <div class="shadcn-card">
        <div class="shadcn-card-title">Hot Leads & Replied</div>
        <div class="shadcn-card-value" style="color: {hot_color};">{hot_leads_count} <span style="font-size: 0.875rem; color: #71717a; font-weight: 400;">({replied_count} total)</span></div>
        <div class="shadcn-card-desc">Interested replies</div>
    </div>
    """, unsafe_allow_html=True)
with kpi5:
    st.markdown(f"""
    <div class="shadcn-card">
        <div class="shadcn-card-title">Suppressions</div>
        <div class="shadcn-card-value" style="color: #ef4444;">{suppression_count}</div>
        <div class="shadcn-card-desc">Opt-outs protected</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

# Navigation Tabs: Analytics, Drafts, Sent log, Follow-ups, Suppressed
tab_analytics, tab_drafts, tab_sent, tab_followups, tab_suppression = st.tabs(
    ["Analytics", "Drafts", "Sent Log", "Follow-ups", "Suppression List"]
)

# ----------------- TAB 0: CAMPAIGN ANALYTICS -----------------
with tab_analytics:
    st.markdown("""
    <div style="margin-bottom: 1.25rem;">
        <h2 style="font-size: 1.25rem; font-weight: 600; color: #fafafa; margin: 0;">Campaign Conversion & Reply Intelligence</h2>
        <p style="font-size: 0.825rem; color: #a1a1aa; margin: 0.2rem 0 0 0;">Real-time conversion metrics, reply intent distribution, deliverability safeguards, and webhook indicators.</p>
    </div>
    """, unsafe_allow_html=True)

    all_logs = db.list_send_logs(limit=100)
    total_dispatched_all_time = len(all_logs)
    live_dispatched = sum(1 for l in all_logs if not l.is_dry_run and l.status == "SENT")
    simulated_dispatched = sum(1 for l in all_logs if l.is_dry_run and l.status in ("SENT", "SIMULATED"))
    total_sent_effective = live_dispatched + simulated_dispatched

    # Conversion Rates
    # Open rate benchmark: Gmail API does not inject pixel trackers by default to safeguard deliverability (100% spam-free plain-text reputation)
    reply_rate_pct = (replied_count / max(total_sent_effective, 1) * 100) if total_sent_effective > 0 else 0.0
    hot_lead_rate_pct = (hot_leads_count / max(total_sent_effective, 1) * 100) if total_sent_effective > 0 else 0.0

    # Analytics Cards Row
    a_col1, a_col2, a_col3, a_col4 = st.columns(4)
    with a_col1:
        st.markdown(f"""
        <div class="shadcn-card">
            <div class="shadcn-card-title">Total Dispatched</div>
            <div class="shadcn-card-value">{total_dispatched_all_time}</div>
            <div class="shadcn-card-desc">{live_dispatched} Live • {simulated_dispatched} Dry-run</div>
        </div>
        """, unsafe_allow_html=True)
    with a_col2:
        st.markdown(f"""
        <div class="shadcn-card">
            <div class="shadcn-card-title">Reply Conversion Rate</div>
            <div class="shadcn-card-value" style="color: #84cc16;">{reply_rate_pct:.1f}%</div>
            <div class="shadcn-card-desc">{replied_count} replies / {total_sent_effective} sent</div>
        </div>
        """, unsafe_allow_html=True)
    with a_col3:
        st.markdown(f"""
        <div class="shadcn-card">
            <div class="shadcn-card-title">Hot Lead Conversion</div>
            <div class="shadcn-card-value" style="color: #a3e635;">{hot_lead_rate_pct:.1f}%</div>
            <div class="shadcn-card-desc">{hot_leads_count} high-intent prospects</div>
        </div>
        """, unsafe_allow_html=True)
    with a_col4:
        st.markdown(f"""
        <div class="shadcn-card">
            <div class="shadcn-card-title">Opt-Out Protection</div>
            <div class="shadcn-card-value" style="color: #94a3b8;">{suppression_count}</div>
            <div class="shadcn-card-desc">Suppressed from future touchpoints</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # Reply Intent Breakdown & Webhook Health
    row2_left, row2_right = st.columns([3, 2])
    with row2_left:
        st.markdown("""
        <div style="font-size: 0.95rem; font-weight: 600; color: #fafafa; margin-bottom: 0.6rem;">
            Prospect Reply Intent Breakdown
        </div>
        """, unsafe_allow_html=True)

        # Sentiment breakdown calculation
        # Contacts with status HOT_LEAD => INTERESTED
        # Contacts with status FOLLOW_UP_LATER => NOT_NOW
        # Contacts with status OPTED_OUT => UNSUBSCRIBE
        # Contacts with status REPLIED => PRICE_QUESTION or general
        count_interested = sum(1 for c in all_contacts if c.status == ContactStatus.HOT_LEAD)
        count_not_now = sum(1 for c in all_contacts if c.status == ContactStatus.FOLLOW_UP_LATER)
        count_unsubscribe = sum(1 for c in all_contacts if c.status == ContactStatus.OPTED_OUT)
        count_price_or_general = sum(1 for c in all_contacts if c.status == ContactStatus.REPLIED)

        intent_data = [
            {"Intent Category": "INTERESTED (Hot Lead)", "Count": count_interested, "Target Action": "Schedule demo / Send proposal link"},
            {"Intent Category": "PRICE_QUESTION", "Count": count_price_or_general, "Target Action": "Send pricing breakdown & ROI"},
            {"Intent Category": "NOT_NOW", "Count": count_not_now, "Target Action": "Scheduled automated follow-up"},
            {"Intent Category": "UNSUBSCRIBE", "Count": count_unsubscribe, "Target Action": "Auto-suppressed from campaigns"},
        ]
        st.dataframe(intent_data, use_container_width=True)

    with row2_right:
        st.markdown("""
        <div style="font-size: 0.95rem; font-weight: 600; color: #fafafa; margin-bottom: 0.6rem;">
            Integration & Webhook Status
        </div>
        """, unsafe_allow_html=True)

        if config.lead_alert_webhook_url:
            masked_url = config.lead_alert_webhook_url[:24] + "..." if len(config.lead_alert_webhook_url) > 24 else config.lead_alert_webhook_url
            wh_html = f"""
            <div class="shadcn-card" style="padding: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 0.85rem; font-weight: 600; color: #fafafa;">Lead Alert Webhook</div>
                    <div>{shadcn_badge("CONNECTED", "success")}</div>
                </div>
                <div style="font-size: 0.75rem; color: #a1a1aa; margin-top: 6px; font-family: 'JetBrains Mono', monospace;">{masked_url}</div>
                <div style="font-size: 0.72rem; color: #84cc16; margin-top: 4px;">✓ Instant alerts active on INTERESTED and PRICE_QUESTION replies.</div>
            </div>
            """
        else:
            wh_html = f"""
            <div class="shadcn-card" style="padding: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 0.85rem; font-weight: 600; color: #fafafa;">Lead Alert Webhook</div>
                    <div>{shadcn_badge("NOT CONFIGURED", "secondary")}</div>
                </div>
                <div style="font-size: 0.75rem; color: #71717a; margin-top: 6px;">Set <code>LEAD_ALERT_WEBHOOK_URL</code> in <code>.env</code> or <code>config.yaml</code> to receive instant notifications for hot leads.</div>
            </div>
            """
        st.markdown(wh_html, unsafe_allow_html=True)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # Activity Log
    st.markdown("""
    <div style="font-size: 0.95rem; font-weight: 600; color: #fafafa; margin-bottom: 0.6rem;">
        Recent Activity & Dispatch Stream
    </div>
    """, unsafe_allow_html=True)

    if not all_logs:
        st.info("No dispatch activity recorded yet. Run tests, generate drafts, or launch the background worker.")
    else:
        # Build activity table with contact context if available
        contact_id_map = {c.id: c for c in all_contacts}
        activity_rows = []
        for l in all_logs[:25]:
            contact_obj = contact_id_map.get(l.contact_id)
            classification = contact_obj.status.value if contact_obj else "SENT"
            activity_rows.append({
                "Timestamp": l.sent_at[:19] if l.sent_at else "-",
                "Recipient": l.recipient,
                "Company": contact_obj.company if contact_obj else "-",
                "Channel": l.channel.upper(),
                "Mode": "Dry-run" if l.is_dry_run else "Live",
                "Dispatch Status": l.status,
                "Reply Classification": classification,
                "Error": l.error_message or "None",
            })
        st.dataframe(activity_rows, use_container_width=True)


# ----------------- TAB 1: DRAFTS -----------------
with tab_drafts:
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
                    try:
                        for idx, c in enumerate(unprocessed_contacts):
                            st_text.text(f"Processing ({idx+1}/{len(unprocessed_contacts)}): {c.company}...")
                            d = dossier_builder.build_dossier(c)
                            db.save_dossier(d)
                            draft_gen.generate_for_contact(c, d)
                            p_bar.progress((idx + 1) / len(unprocessed_contacts))
                    except GeminiQuotaError:
                        st.error("⚠️ Daily free Gemini quota reached. Generation stopped. Try again tomorrow.")
                        st.stop()
                    load_all_contacts.clear()
                    st.success(f"Generated drafts for {len(unprocessed_contacts)} contacts.")
                    st.rerun()


    # Filter options
    status_filter = st.selectbox(
        "Filter Prospects:",
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
        c_draft = all_drafts_map.get(c.id)
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
        st.info("No contacts matching this filter.")
    else:
        st.caption(f"Showing {len(filtered_contacts)} prospects")

        for contact in filtered_contacts:
            dossier = all_dossiers_map.get(contact.id)
            draft = all_drafts_map.get(contact.id)
            is_flagged = bool(draft and draft.status == DraftStatus.FLAGGED)
            flagged_tag = " • [FLAGGED]" if is_flagged else ""


            # Expander header
            with st.expander(
                f"**{contact.full_name}** — {contact.job_title or 'Owner'}, **{contact.company}** [{contact.status.value}]{flagged_tag}",
                expanded=False,
            ):
                col_left, col_right = st.columns([1, 1])


                # Left Column: Dossier
                with col_left:
                    st.markdown("<div style='font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #a1a1aa; margin-bottom: 0.5rem;'>Verified Dossier</div>", unsafe_allow_html=True)
                    dossier_container = st.container(height=520)
                    with dossier_container:
                        dossier_box = st.empty()
                        with dossier_box.container():
                            if contact.email.endswith("@linkedin-lead.local"):
                                st.markdown("**Email:** *Not provided in sheet (LinkedIn outreach)*")
                            elif contact.email.endswith("@local-lead.local"):
                                st.markdown("**Email:** *Not provided in sheet (Local Lead - WhatsApp/Phone)*")
                            else:
                                st.markdown(f"**Email:** `{contact.email}`")
                            if contact.linkedin_url:
                                if "google.com/maps" in contact.linkedin_url or "maps.google" in contact.linkedin_url or "goo.gl" in contact.linkedin_url:
                                    st.markdown(f"**Google Maps:** [{contact.linkedin_url}]({contact.linkedin_url})")
                                else:
                                    st.markdown(f"**LinkedIn:** [{contact.linkedin_url}]({contact.linkedin_url})")
                            if contact.notes:
                                with st.expander("Lead Details & Notes", expanded=False):
                                    st.text(contact.notes)

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
                                        try:
                                            new_dossier = dossier_builder.build_dossier(contact, user_pasted_linkedin=pasted_info)
                                            db.save_dossier(new_dossier)
                                            new_draft = draft_gen.generate_for_contact(contact, new_dossier)
                                            load_all_contacts.clear()
                                            st.success("Draft generated.")
                                            st.rerun()
                                        except GeminiQuotaError:
                                            st.error("⚠️ Daily free Gemini quota reached. Generation stopped. Try again tomorrow.")


                # Right Column: Drafts
                with col_right:
                    st.markdown("<div style='font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #a1a1aa; margin-bottom: 0.5rem;'>Personalized Draft</div>", unsafe_allow_html=True)
                    drafts_container = st.container(height=520)
                    with drafts_container:
                        drafts_box = st.empty()
                        with drafts_box.container():
                            if not draft:
                                st.info("No draft generated yet.")
                            else:
                                if is_flagged:
                                    st.error("Flagged: Draft failed validation or fact-grounding. Manual edit and approval required before sending.")

                                # 1-Line Hook with ShadCN Callout styling
                                st.markdown(f"""
                                <div style="background-color: #18181b; border: 1px solid #27272a; border-left: 3px solid #fafafa; border-radius: 6px; padding: 10px 14px; margin-bottom: 12px;">
                                    <div style="font-size: 0.7rem; font-weight: 600; text-transform: uppercase; color: #a1a1aa; letter-spacing: 0.05em;">Fact-Grounded Observation</div>
                                    <div style="font-size: 0.875rem; color: #f4f4f5; margin-top: 4px; font-style: italic;">"{draft.hook}"</div>
                                </div>
                                """, unsafe_allow_html=True)
                                if draft.source_facts:
                                    st.caption(f"Source facts: {', '.join(draft.source_facts)}")


                                # Sub-tabs for Channels
                                tab_email, tab_wa, tab_li = st.tabs(["Email", "WhatsApp", "LinkedIn"])

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
                                                whatsapp_message=draft.whatsapp_message,
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

                                with tab_wa:
                                    st.markdown("Short, casual, friendly mobile message for local owners (< 50 words).")
                                    editable_wa = st.text_area(
                                        "Message:",
                                        value=draft.whatsapp_message,
                                        height=120,
                                        key=f"wa_body_{contact.id}",
                                    )
                                    wa_words = len(editable_wa.split()) if editable_wa else 0
                                    if wa_words > 50:
                                        st.warning(f"Word count: {wa_words}/50 words (exceeds 50-word limit)")
                                    else:
                                        st.caption(f"Word count: {wa_words} / 50 words")

                                    # Parse phone from notes
                                    phone_match = re.search(r"Phone:\s*([+0-9\s\-()]+)", contact.notes or "")
                                    phone_val = phone_match.group(1).strip() if phone_match else ""
                                    clean_phone = re.sub(r"[^\d+]", "", phone_val).lstrip("+")

                                    col_w1, col_w2, col_w3 = st.columns(3)
                                    with col_w1:
                                        if st.button("Save", key=f"save_wa_{contact.id}"):
                                            db.update_draft_content(
                                                draft_id=draft.id,
                                                hook=draft.hook,
                                                email_subject=draft.email_subject,
                                                email_body=draft.email_body,
                                                linkedin_note=draft.linkedin_note,
                                                linkedin_message=draft.linkedin_message,
                                                whatsapp_message=editable_wa,
                                                status=DraftStatus.EDITED,
                                            )
                                            load_all_contacts.clear()
                                            st.success("Saved.")
                                            st.rerun()

                                    with col_w2:
                                        if clean_phone:
                                            encoded_msg = urllib.parse.quote(editable_wa or "")
                                            wa_url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
                                            st.link_button(f"Open WhatsApp Web ({clean_phone})", wa_url)
                                        else:
                                            st.caption("No phone found in lead details.")

                                    with col_w3:
                                        if st.button("Mark as Sent", key=f"mark_wa_{contact.id}"):
                                            db.update_contact_status(contact.id, ContactStatus.WHATSAPP_SENT)
                                            db.update_draft_status(draft.id, DraftStatus.APPROVED)
                                            # Record in send logs so it appears in Sent Messages & Logs tab
                                            send_log = SendLog(
                                                contact_id=contact.id,
                                                draft_id=draft.id,
                                                channel="whatsapp",
                                                recipient=clean_phone or contact.email,
                                                is_dry_run=False,
                                                status="SENT",
                                            )
                                            db.log_send(send_log)
                                            load_all_contacts.clear()
                                            st.success("Marked as WhatsApp sent and logged.")
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
    st.markdown("""
    <div style="margin-bottom: 1rem;">
        <h2 style="font-size: 1.25rem; font-weight: 600; color: #fafafa; margin: 0;">Dispatch Log</h2>
        <p style="font-size: 0.825rem; color: #a1a1aa; margin: 0.2rem 0 0 0;">Audit record of all outreach attempts, simulated dry-runs, and live deliveries.</p>
    </div>
    """, unsafe_allow_html=True)

    logs = db.list_send_logs(limit=50)
    if not logs:
        st.info("No dispatch logs recorded yet.")
    else:
        log_data = []
        for l in logs:
            log_data.append({
                "ID": l.id,
                "Recipient": l.recipient,
                "Channel": l.channel.upper(),
                "Mode": "Dry-run" if l.is_dry_run else "Live",
                "Status": l.status,
                "Message ID": l.gmail_message_id or "-",
                "Sent At": l.sent_at[:19],
                "Error": l.error_message or "None",
            })
        st.dataframe(log_data, use_container_width=True)


# ----------------- TAB 3: FOLLOW-UPS -----------------
with tab_followups:
    st.markdown("""
    <div style="margin-bottom: 1rem;">
        <h2 style="font-size: 1.25rem; font-weight: 600; color: #fafafa; margin: 0;">Automated Follow-ups</h2>
        <p style="font-size: 0.825rem; color: #a1a1aa; margin: 0.2rem 0 0 0;">Scheduled secondary touches for contacted prospects pending replies.</p>
    </div>
    """, unsafe_allow_html=True)

    contacts_for_fu = db.list_contacts(ContactStatus.EMAIL_SENT)
    if not contacts_for_fu:
        st.info("No pending follow-ups right now.")
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
    st.markdown("""
    <div style="margin-bottom: 1rem;">
        <h2 style="font-size: 1.25rem; font-weight: 600; color: #fafafa; margin: 0;">Suppression List</h2>
        <p style="font-size: 0.825rem; color: #a1a1aa; margin: 0.2rem 0 0 0;">Enforce strict opt-out compliance across all email and LinkedIn campaigns.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("add_suppression_form"):
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            sup_email = st.text_input("Email to suppress:")
        with col_s2:
            sup_reason = st.text_input("Reason:", value="Opt-out requested")
        add_sup = st.form_submit_button("Add to Suppression")
        if add_sup and sup_email:
            suppression_mgr.suppress_contact(sup_email, reason=sup_reason)
            st.success(f"Suppressed {sup_email}.")
            st.rerun()

    suppressed = db.list_suppressed()
    if suppressed:
        st.dataframe(
            [{"Email": s.email, "Reason": s.reason, "Opted Out At": s.opted_out_at[:19]} for s in suppressed],
            use_container_width=True,
        )
    else:
        st.info("No suppressed emails recorded.")

