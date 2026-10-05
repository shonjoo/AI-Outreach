"""Interactive Review Dashboard for personalized outreach automation."""

import csv
import html
import io
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from src.db.csv_importer import get_excel_sheet_info, import_contacts_to_db, parse_any_lead_file


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

    /* Dataframe and Table ShadCN styling */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--figma-border) !important;
        border-radius: var(--figma-radius-md) !important;
        background-color: var(--figma-bg-surface) !important;
        overflow: hidden !important;
    }

    /* ShadCN Callout / Alert Banner */
    .shadcn-callout {
        border-radius: var(--figma-radius-md);
        padding: 0.85rem 1.15rem;
        margin: 0.75rem 0;
        display: flex;
        gap: 0.75rem;
        align-items: flex-start;
        font-size: 0.875rem;
        border: 1px solid var(--figma-border);
        background-color: var(--figma-bg-surface-elevated);
    }
    .shadcn-callout-info {
        border-left: 3px solid #38bdf8;
        background-color: rgba(56, 189, 248, 0.06);
    }
    .shadcn-callout-success {
        border-left: 3px solid #84cc16;
        background-color: rgba(132, 204, 22, 0.08);
    }
    .shadcn-callout-warning {
        border-left: 3px solid #f59e0b;
        background-color: rgba(245, 158, 11, 0.08);
    }
    .shadcn-callout-destructive {
        border-left: 3px solid #ef4444;
        background-color: rgba(239, 68, 68, 0.08);
    }

    /* ShadCN Separator with label */
    .shadcn-separator {
        display: flex;
        align-items: center;
        text-align: center;
        margin: 1.25rem 0;
        color: var(--figma-text-muted);
        font-size: 0.75rem;
        font-weight: 500;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .shadcn-separator::before,
    .shadcn-separator::after {
        content: '';
        flex: 1;
        border-bottom: 1px solid var(--figma-border);
    }
    .shadcn-separator:not(:empty)::before {
        margin-right: 0.85rem;
    }
    .shadcn-separator:not(:empty)::after {
        margin-left: 0.85rem;
    }

    /* ShadCN Avatar / Lead initials circle */
    .shadcn-avatar {
        width: 34px;
        height: 34px;
        border-radius: 9999px;
        background: #18181b;
        border: 1px solid var(--figma-border);
        color: #f4f4f5;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        flex-shrink: 0;
    }
    .shadcn-avatar.accent {
        background: rgba(132, 204, 22, 0.15);
        border-color: rgba(132, 204, 22, 0.35);
        color: #a3e635;
    }

    /* Dividers */
    hr {
        border-color: #27272a !important;
        margin: 1.25rem 0 !important;
    }

    /* Ambient Glow & Glassmorphism Surfaces */
    .glass-panel {
        background: rgba(18, 18, 21, 0.7) !important;
        backdrop-filter: blur(20px) !important;
        -webkit-backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.45) !important;
    }

    .ambient-glow {
        position: relative;
    }
    .ambient-glow::after {
        content: '';
        position: absolute;
        top: -1px;
        left: 15%;
        right: 15%;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.6), transparent);
    }

    /* Smooth Micro-animations & Skeleton Loaders */
    @keyframes pulse-subtle {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.85; transform: scale(1.02); }
    }
    .pulse-glow {
        animation: pulse-subtle 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    @keyframes shimmer-wave {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }
    .skeleton-shimmer {
        background: linear-gradient(90deg, #18181b 25%, #27272a 50%, #18181b 75%);
        background-size: 200% 100%;
        animation: shimmer-wave 1.6s ease-in-out infinite;
        border-radius: var(--figma-radius-sm);
    }

    /* Keyboard Shortcut Hint Tag */
    .kbd-shortcut {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-family: var(--figma-font-mono, monospace);
        font-size: 0.65rem;
        font-weight: 700;
        color: #a1a1aa;
        background: #18181b;
        border: 1px solid #3f3f46;
        border-bottom: 2px solid #52525b;
        border-radius: 4px;
        padding: 1px 5px;
        line-height: 1.1;
        margin-left: 6px;
        letter-spacing: 0.04em;
        vertical-align: middle;
    }

    /* Prospect Card Channel Micro-pill */
    .micro-pill {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 0.6875rem;
        font-weight: 500;
        padding: 2px 7px;
        border-radius: 9999px;
        line-height: 1.3;
        border: 1px solid transparent;
        white-space: nowrap;
    }
    .micro-pill-green {
        background: rgba(132, 204, 22, 0.1);
        color: #bef264;
        border-color: rgba(132, 204, 22, 0.25);
    }
    .micro-pill-blue {
        background: rgba(56, 189, 248, 0.1);
        color: #7dd3fc;
        border-color: rgba(56, 189, 248, 0.25);
    }
    .micro-pill-zinc {
        background: rgba(39, 39, 42, 0.6);
        color: #a1a1aa;
        border-color: #3f3f46;
    }

    /* Stat Card Highlighting with Vibrant Top Gradient */
    .shadcn-card {
        position: relative;
        overflow: hidden;
    }
    .shadcn-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.4), transparent);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    .shadcn-card:hover::before {
        opacity: 1;
    }

    /* Streamlit DataFrame Scrollbar Aesthetic */
    div[data-testid="stDataFrame"] div[tabindex="0"]::-webkit-scrollbar {
        height: 6px !important;
        width: 6px !important;
    }
    div[data-testid="stDataFrame"] div[tabindex="0"]::-webkit-scrollbar-thumb {
        background: #27272a !important;
        border-radius: 9999px !important;
    }
    div[data-testid="stDataFrame"] div[tabindex="0"]::-webkit-scrollbar-thumb:hover {
        background: var(--figma-accent) !important;
    }

    /* ==========================================================================
       HIGH-REFRESH-RATE DISPLAY OPTIMIZATIONS (60Hz, 120Hz, 144Hz, 180Hz, 240Hz)
       ========================================================================== */
    /* Force GPU compositing, hardware rasterization, subpixel antialiasing & zero jank */
    *, *::before, *::after {
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }

    /* Composited GPU layers for interactive components */
    .shadcn-card,
    .shadcn-badge,
    .shadcn-avatar,
    button,
    [data-testid="stButton"] > button,
    [data-testid="stLinkButton"] > a,
    div[data-testid="stTabs"] button[role="tab"],
    div[data-testid="stExpander"],
    div[data-testid="stExpander"] summary {
        transform: translateZ(0);
        backface-visibility: hidden;
        -webkit-backface-visibility: hidden;
        perspective: 1000px;
    }

    /* 60Hz - 240Hz Adaptive Motion:
       Using transform + opacity exclusively allows the browser compositor thread
       to animate at the native display refresh rate without triggering main-thread reflows */
    @media (prefers-reduced-motion: no-preference) {
        .shadcn-card,
        button,
        [data-testid="stButton"] > button,
        div[data-testid="stTabs"] button[role="tab"] {
            transition-timing-function: cubic-bezier(0.16, 1, 0.3, 1) !important;
        }
    }

    /* Accessibility Fallback */
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
            scroll-behavior: auto !important;
        }
    }

    /* ==========================================================================
       RESPONSIVE DISPLAY OPTIMIZATIONS ACROSS ALL SCREEN SIZES
       (UltraWide 1440p/4K, Standard Desktop, Laptop, Tablet, Mobile)
       ========================================================================== */
    /* UltraWide & 4K Displays (>= 1920px) */
    @media (min-width: 1920px) {
        div[data-testid="stAppViewBlockContainer"] {
            max-width: 1600px !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        .shadcn-card-value {
            font-size: 1.75rem !important;
        }
    }

    /* Standard Desktop & 1440p Displays (1280px - 1919px) */
    @media (min-width: 1280px) and (max-width: 1919px) {
        div[data-testid="stAppViewBlockContainer"] {
            max-width: 1360px !important;
        }
    }

    /* Compact Laptops & Tablets (768px - 1279px) */
    @media (max-width: 1279px) {
        div[data-testid="stAppViewBlockContainer"] {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1.25rem !important;
        }
        .shadcn-card {
            padding: 0.85rem 1rem !important;
        }
        .shadcn-card-value {
            font-size: 1.35rem !important;
        }
    }

    /* Mobile Phones (< 768px) */
    @media (max-width: 767px) {
        div[data-testid="stAppViewBlockContainer"] {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
            padding-top: 1rem !important;
        }
        h1 {
            font-size: 1.45rem !important;
        }
        div[data-testid="stTabs"] > div:first-child {
            display: flex !important;
            flex-wrap: wrap !important;
            width: 100% !important;
        }
        div[data-testid="stTabs"] button[role="tab"] {
            flex: 1 1 auto !important;
            text-align: center !important;
        }
        .shadcn-card {
            margin-bottom: 0.5rem !important;
        }
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
    return f'<span class="shadcn-badge" style="{style}">{label}</span>'


def shadcn_status_badge(status: str) -> str:
    """Maps status string to appropriate ShadCN badge variant."""
    status_clean = str(status).upper().strip()
    mapping = {
        "HOT_LEAD": ("Hot Lead", "success"),
        "APPROVED": ("Approved", "success"),
        "READY_FOR_REVIEW": ("Ready for Review", "default"),
        "NEEDS_MANUAL_REVIEW": ("Manual Review", "warning"),
        "FLAGGED": ("Flagged", "destructive"),
        "OPTED_OUT": ("Opted Out", "destructive"),
        "REPLIED": ("Replied", "cloud"),
        "EMAIL_SENT": ("Email Sent", "secondary"),
        "WHATSAPP_SENT": ("WhatsApp Sent", "secondary"),
        "LINKEDIN_SENT": ("LinkedIn Sent", "secondary"),
        "PENDING_RESEARCH": ("Pending Research", "secondary"),
        "SKIPPED": ("Skipped", "secondary"),
    }
    label, variant = mapping.get(status_clean, (status_clean.replace("_", " ").title(), "secondary"))
    return shadcn_badge(label, variant)


def shadcn_callout(text: str, title: str = "", variant: str = "info") -> str:
    """Renders a ShadCN alert callout banner."""
    title_html = f'<div style="font-weight: 600; color: #fafafa; margin-bottom: 2px;">{title}</div>' if title else ""
    return f"""
    <div class="shadcn-callout shadcn-callout-{variant}">
        <div>
            {title_html}
            <div style="color: #d4d4d8; font-size: 0.8125rem; line-height: 1.45;">{text}</div>
        </div>
    </div>
    """


def shadcn_separator(label: str = "") -> str:
    """Renders a ShadCN horizontal separator with optional text label."""
    return f'<div class="shadcn-separator">{label}</div>'


def shadcn_avatar(initials: str, accent: bool = False) -> str:
    """Renders a ShadCN user avatar circle."""
    accent_cls = " accent" if accent else ""
    return f'<div class="shadcn-avatar{accent_cls}">{initials[:2].upper()}</div>'


def get_contact_status_str(contact: Contact) -> str:
    """Safely extracts string representation of contact status."""
    st_val = getattr(contact, "status", "")
    return getattr(st_val, "value", str(st_val))


config = load_config()
db = Database(config.db_path, config=config)
dossier_builder = DossierBuilder()
draft_gen = DraftGenerator(config, db)
sender = OutreachSender(config, db)
suppression_mgr = SuppressionManager(db)

# Cached dashboard data loader (Aggregates and memoizes metadata and contacts to avoid redundant round-trips on every rerun)
@st.cache_data(show_spinner=False, ttl=30)
def load_dashboard_cache(backend_name: str, db_path: str):
    database = Database(db_path, config=config)
    contacts = database.list_contacts()
    drafts = database.list_all_drafts()
    dossiers = database.list_all_dossiers()
    suppressed = database.list_suppressed()
    sent_today = database.get_today_sent_count()
    logs = database.list_send_logs(limit=100)
    return contacts, drafts, dossiers, suppressed, sent_today, logs


def invalidate_dashboard_cache():
    """Clears the memoized dashboard cache when data changes."""
    load_dashboard_cache.clear()


@st.cache_data(show_spinner=False)
def parse_uploaded_lead_file(file_bytes: bytes, filename: str, target_sheet: Optional[str] = None):
    return parse_any_lead_file(file_bytes, filename, target_sheet=target_sheet)


@st.cache_data(show_spinner=False)
def get_cached_excel_sheets(file_bytes: bytes):
    return get_excel_sheet_info(file_bytes)

# Remote Access Security: Secret Link Token & Password Gate
configured_token = getattr(config, "dashboard_access_token", None) or os.getenv("DASHBOARD_ACCESS_TOKEN", "").strip()
configured_password = getattr(config, "dashboard_password", None) or os.getenv("DASHBOARD_PASSWORD", "").strip()
auth_required = bool(configured_token or configured_password)

if auth_required:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    # Check for Secret Link Token in query params (e.g. ?token=secret_key or ?key=secret_key)
    query_params = getattr(st, "query_params", None)
    if query_params and configured_token and not st.session_state["authenticated"]:
        token_in_url = query_params.get("token") or query_params.get("key") or query_params.get("access_token")
        if token_in_url:
            import hmac
            if hmac.compare_digest(str(token_in_url).strip(), configured_token):
                st.session_state["authenticated"] = True
                # Clean token from browser address bar immediately so it isn't leaked in history or shoulder-surfing
                try:
                    for k in ["token", "key", "access_token"]:
                        if k in query_params:
                            del query_params[k]
                except Exception:
                    pass

    # If still not authenticated, display secure access gate
    if not st.session_state["authenticated"]:
        _, center_col, _ = st.columns([1, 2, 1])
        with center_col:
            st.markdown(
                """
                <div class="shadcn-card" style="margin-top: 3.5rem; margin-bottom: 1.25rem; text-align: center; padding: 2rem; border-color: rgba(132, 204, 22, 0.3);">
                    <div style="width: 44px; height: 44px; border-radius: 10px; background: #84cc16; color: #050505; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.35rem; margin-bottom: 0.85rem; box-shadow: 0 0 16px rgba(132, 204, 22, 0.4);">✦</div>
                    <div style="font-weight: 600; font-size: 1.35rem; color: #f0fdf4; letter-spacing: -0.025em;">Outreach Studio</div>
                    <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.35rem;">Protected Workspace. Only authorized team members with the secret link or access key may enter.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("shadcn_login_form"):
                access_input = st.text_input("Access Key or Password", type="password", placeholder="Paste secret access link token or password...")
                submit_login = st.form_submit_button("Unlock Studio", type="primary", use_container_width=True)
                if submit_login:
                    import hmac
                    clean_input = access_input.strip()
                    valid_match = False
                    if configured_token and hmac.compare_digest(clean_input, configured_token):
                        valid_match = True
                    elif configured_password and hmac.compare_digest(clean_input, configured_password):
                        valid_match = True

                    if valid_match:
                        st.session_state["authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Invalid access token or password. Access denied.")
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
            sheet_info = get_cached_excel_sheets(file_bytes)
            if sheet_info:
                # Build formatted options: All Sheets first, then individual sheets with row estimates
                options_map = {"__ALL_SHEETS__": "✨ All Sheets (Combined)"}
                default_idx = 0
                for idx, (s_name, r_count) in enumerate(sheet_info):
                    label = f"{s_name} (~{r_count} rows)" if r_count > 0 else s_name
                    options_map[s_name] = label
                    # Auto-select the first niche/leads/fit sheet
                    if default_idx == 0 and any(w in s_name.lower() for w in ["niche", "fit", "lead", "contact"]):
                        default_idx = idx + 1  # offset by 1 because __ALL_SHEETS__ is at index 0

                selected_label = st.selectbox(
                    "Select Sheet:",
                    options=list(options_map.values()),
                    index=default_idx,
                    help="Choose a specific tab or import leads from all tabs combined."
                )
                # Map back to sheet key
                rev_map = {v: k for k, v in options_map.items()}
                target_sheet = rev_map.get(selected_label, "__ALL_SHEETS__")

        with st.spinner("Analyzing contacts..."):
            parsed_contacts, parse_errors, meta = parse_uploaded_lead_file(
                file_bytes=file_bytes,
                filename=fname,
                target_sheet=target_sheet,
            )

        if parse_errors:
            for err in parse_errors:
                st.error(err)

        if parsed_contacts:
            st.success(f"✓ Found {len(parsed_contacts)} contacts ready to import.")

            # Show preview
            with st.expander(f"Preview contacts ({min(5, len(parsed_contacts))} of {len(parsed_contacts)})", expanded=False):
                preview_data = [
                    {"Name": c.full_name, "Company": c.company, "Title": c.job_title, "Email": c.email, "LinkedIn": bool(c.linkedin_url)}
                    for c in parsed_contacts[:5]
                ]
                st.dataframe(preview_data, use_container_width=True)

            col_u1, col_u2 = st.columns([1, 1])
            with col_u1:
                # Fast direct import (Recommended for bulk leads)
                if st.button("⚡ Fast Import Only (Recommended)", type="primary", key="btn_import_only", use_container_width=True):
                    with st.spinner(f"Importing {len(parsed_contacts)} contacts..."):
                        imported_count = import_contacts_to_db(db, parsed_contacts)
                    invalidate_dashboard_cache()
                    st.success(f"Successfully imported {imported_count} contacts!")
                    st.rerun()

            with col_u2:
                # Batch generation button with safety cap note
                btn_gen_label = "Import + Generate Drafts"
                if len(parsed_contacts) > 10:
                    btn_gen_label = f"Import + Generate Drafts (First 10)"
                
                if st.button(btn_gen_label, key="btn_import_gen", use_container_width=True):
                    contacts_to_generate = parsed_contacts[:10] if len(parsed_contacts) > 10 else parsed_contacts
                    imported_count = 0
                    with st.spinner("Processing research and drafts..."):
                        progress_bar = st.progress(0.0)
                        try:
                            # Pre-import batch to ensure contacts are in DB
                            import_contacts_to_db(db, parsed_contacts)
                            for idx, contact in enumerate(contacts_to_generate):
                                # Ensure we have DB id
                                existing = db.get_contact_by_email(contact.email) if hasattr(db, "get_contact_by_email") else None
                                if existing:
                                    contact.id = existing.id
                                else:
                                    contact.id = db.insert_contact(contact)
                                imported_count += 1
                                # Research & Draft
                                dossier = dossier_builder.build_dossier(contact)
                                db.save_dossier(dossier)
                                draft_gen.generate_for_contact(contact, dossier)
                                progress_bar.progress((idx + 1) / len(contacts_to_generate))
                        except GeminiQuotaError:
                            st.warning("⚠️ Daily Gemini rate/quota limit reached. Remaining contacts were imported safely.")
                        except Exception as e:
                            st.error(f"Error during draft generation: {e}")
                    invalidate_dashboard_cache()
                    st.success(f"Imported contacts and created drafts for {imported_count} prospects.")
                    st.rerun()


    if auth_required:
        st.markdown("<hr style='margin: 1.5rem 0 1rem 0; border-color: #27272a;'>", unsafe_allow_html=True)
        if st.button("Log out of Studio", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()


# Main Dashboard (Memoized fast fetch)
all_contacts, all_drafts_map, all_dossiers_map, suppressed_all, sent_today, all_logs = load_dashboard_cache(
    db.backend_name, config.db_path
)

total_count = len(all_contacts)
approved_count = sum(1 for c in all_contacts if get_contact_status_str(c) == "APPROVED")
needs_review_count = sum(1 for c in all_contacts if get_contact_status_str(c) in ("READY_FOR_REVIEW", "NEEDS_MANUAL_REVIEW"))
flagged_count = sum(1 for c in all_contacts if (d := all_drafts_map.get(c.id)) and getattr(d, "status", None) == DraftStatus.FLAGGED)
hot_leads_count = sum(1 for c in all_contacts if get_contact_status_str(c) == "HOT_LEAD")
replied_count = sum(1 for c in all_contacts if get_contact_status_str(c) in ("REPLIED", "HOT_LEAD"))
follow_up_later_count = sum(1 for c in all_contacts if get_contact_status_str(c) == "FOLLOW_UP_LATER")
suppression_count = len(suppressed_all)
limit_today = getattr(getattr(config, "limits", None), "emails_per_day", 5)
webhook_configured = bool(getattr(config, "lead_alert_webhook_url", None) or os.getenv("LEAD_ALERT_WEBHOOK_URL"))


# Modern Hero Header with Ambient Glow & Badges
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("""
    <div class="ambient-glow" style="margin-bottom: 1rem; padding-top: 0.5rem;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
            <span class="shadcn-badge" style="background: rgba(132, 204, 22, 0.12); color: #84cc16; border: 1px solid rgba(132, 204, 22, 0.3); font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;">B2B Intelligence Suite</span>
            <span style="font-size: 0.72rem; color: #52525b;">•</span>
            <span style="font-size: 0.75rem; color: #71717a; font-family: var(--figma-font-mono);">v2.4 Production</span>
        </div>
        <h1 style="font-size: 2.1rem; font-weight: 800; letter-spacing: -0.04em; margin: 0; color: #fafafa; line-height: 1.15;">
            almost normal <span style="font-weight: 400; font-size: 1.35rem; color: #84cc16;">• Outreach Studio</span>
        </h1>
        <p style="font-size: 0.9rem; color: #a1a1aa; margin: 0.4rem 0 0 0; line-height: 1.5; max-width: 680px;">
            Autonomous prospect discovery, verified-fact personalization, and compliant cold messaging across Email, WhatsApp, and LinkedIn.
        </p>
    </div>
    """, unsafe_allow_html=True)
with col_h2:
    if db.is_supabase:
        db_badge_top = shadcn_badge("Cloud Synced", "cloud")
    else:
        db_badge_top = shadcn_badge("Local Mode", "secondary")
    webhook_badge_top = shadcn_badge("Webhook Connected", "success") if webhook_configured else shadcn_badge("Webhook Offline", "secondary")
    st.markdown(f'<div style="text-align: right; padding-top: 1.5rem; display: flex; justify-content: flex-end; align-items: center; gap: 8px;">{db_badge_top}{webhook_badge_top}</div>', unsafe_allow_html=True)

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

    # Uses memoized all_logs from load_dashboard_cache
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
        count_interested = sum(1 for c in all_contacts if get_contact_status_str(c) == "HOT_LEAD")
        count_not_now = sum(1 for c in all_contacts if get_contact_status_str(c) == "FOLLOW_UP_LATER")
        count_unsubscribe = sum(1 for c in all_contacts if get_contact_status_str(c) == "OPTED_OUT")
        count_price_or_general = sum(1 for c in all_contacts if get_contact_status_str(c) == "REPLIED")

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

        active_wh_url = getattr(config, "lead_alert_webhook_url", None) or os.getenv("LEAD_ALERT_WEBHOOK_URL")
        if active_wh_url:
            masked_url = active_wh_url[:24] + "..." if len(active_wh_url) > 24 else active_wh_url
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
    unprocessed_contacts = [c for c in all_contacts if not all_drafts_map.get(c.id)]

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
                    skeleton_placeholder = st.empty()
                    skeleton_placeholder.markdown("""
                    <div style="background: #09090b; border: 1px solid #27272a; border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem;">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                            <div class="skeleton-shimmer" style="width: 36px; height: 36px; border-radius: 9999px;"></div>
                            <div style="flex: 1;">
                                <div class="skeleton-shimmer" style="width: 40%; height: 14px; margin-bottom: 6px;"></div>
                                <div class="skeleton-shimmer" style="width: 25%; height: 10px;"></div>
                            </div>
                        </div>
                        <div class="skeleton-shimmer" style="width: 100%; height: 40px; margin-bottom: 8px;"></div>
                        <div class="skeleton-shimmer" style="width: 75%; height: 26px;"></div>
                    </div>
                    """, unsafe_allow_html=True)
                    try:
                        for idx, c in enumerate(unprocessed_contacts):
                            st_text.markdown(f"<div style='font-size: 0.825rem; color: #a1a1aa; margin-bottom: 4px;'>Researching & drafting ({idx+1}/{len(unprocessed_contacts)}): <b style='color: #fafafa;'>{html.escape(c.company)}</b></div>", unsafe_allow_html=True)
                            d = dossier_builder.build_dossier(c)
                            db.save_dossier(d)
                            draft_gen.generate_for_contact(c, d)
                            p_bar.progress((idx + 1) / len(unprocessed_contacts))
                    except GeminiQuotaError:
                        skeleton_placeholder.empty()
                        st.error("⚠️ Daily free Gemini quota reached. Generation stopped safely. Remaining contacts queued.")
                        st.stop()
                    skeleton_placeholder.empty()
                    invalidate_dashboard_cache()
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
        c_st_str = get_contact_status_str(c)
        if status_filter == "Pending actions":
            if c_st_str in ("READY_FOR_REVIEW", "NEEDS_MANUAL_REVIEW", "PENDING_RESEARCH"):
                filtered_contacts.append(c)
        elif status_filter == "FLAGGED":
            if c_draft and getattr(c_draft, "status", None) == DraftStatus.FLAGGED:
                filtered_contacts.append(c)
        elif status_filter == "ALL":
            filtered_contacts.append(c)
        elif c_st_str == status_filter:
            filtered_contacts.append(c)

    if not filtered_contacts:
        st.info("No contacts matching this filter.")
    else:
        # High-Performance Pagination: Window rendering to 15 cards per page to prevent UI lag with large lead lists
        PAGE_SIZE = 15
        total_pages = max(1, (len(filtered_contacts) + PAGE_SIZE - 1) // PAGE_SIZE)
        
        col_p1, col_p2 = st.columns([3, 1])
        with col_p1:
            st.caption(f"Showing {len(filtered_contacts)} prospects • Page {st.session_state.get('drafts_page', 1)} of {total_pages}")
        with col_p2:
            current_page = st.selectbox(
                "Page",
                options=list(range(1, total_pages + 1)),
                index=min(st.session_state.get("drafts_page", 1) - 1, total_pages - 1),
                key="drafts_page",
                label_visibility="collapsed",
            )

        start_idx = (current_page - 1) * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        paginated_contacts = filtered_contacts[start_idx:end_idx]

        for contact in paginated_contacts:
            dossier = all_dossiers_map.get(contact.id)
            draft = all_drafts_map.get(contact.id)
            is_flagged = bool(draft and getattr(draft, "status", None) == DraftStatus.FLAGGED)
            flagged_tag = " • [FLAGGED]" if is_flagged else ""
            contact_status_str = get_contact_status_str(contact)

            # ShadCN Prospect Card Preview Banner
            status_badge_html = shadcn_status_badge(contact_status_str)
            flag_badge_html = f" {shadcn_badge('FLAGGED', 'destructive')}" if is_flagged else ""
            initials = "".join([part[0] for part in contact.full_name.split() if part]) or "P"
            avatar_html = shadcn_avatar(initials, accent=(contact_status_str == "HOT_LEAD"))
            title_text = contact.job_title or "Owner / Founder"
            expander_label = f"{contact.full_name} — {title_text}, {contact.company} [{contact_status_str}]{flagged_tag}"

            # Sanitize untrusted user-supplied data for HTML rendering
            safe_name = html.escape(contact.full_name)
            safe_title = html.escape(title_text)
            safe_comp = html.escape(contact.company)
            safe_email = html.escape(contact.email)

            # Channel & Intelligence Micro-Badges
            email_ready = not (contact.email.endswith("@linkedin-lead.local") or contact.email.endswith("@local-lead.local"))
            has_phone = bool(re.search(r"Phone:\s*([+0-9\s\-()]+)", contact.notes or ""))
            has_website = bool(dossier and dossier.website_url) or bool(contact.website)
            
            pills_html = []
            if email_ready:
                pills_html.append('<span class="micro-pill micro-pill-green">✉ Email ready</span>')
            else:
                pills_html.append('<span class="micro-pill micro-pill-zinc">No email</span>')

            if has_phone:
                pills_html.append('<span class="micro-pill micro-pill-blue">📱 Phone/WA</span>')
            else:
                pills_html.append('<span class="micro-pill micro-pill-zinc">No phone</span>')

            if has_website:
                pills_html.append('<span class="micro-pill micro-pill-green">🌐 Website Crawled</span>')

            pills_row_html = "".join(pills_html)

            st.markdown(f"""
            <div style="background-color: #0c0d0e; border: 1px solid var(--figma-border); border-radius: var(--figma-radius-md) var(--figma-radius-md) 0 0; padding: 0.75rem 1rem; display: flex; align-items: center; justify-content: space-between; margin-bottom: -1px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    {avatar_html}
                    <div>
                        <div style="font-weight: 600; font-size: 0.9375rem; color: #fafafa; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                            {safe_name}
                            <span style="font-weight: 400; font-size: 0.8125rem; color: #a1a1aa;">• {safe_title} at {safe_comp}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px; flex-wrap: wrap;">
                            <span style="font-size: 0.75rem; color: #71717a; font-family: var(--figma-font-mono, monospace);">{safe_email}</span>
                            {pills_row_html}
                        </div>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    {status_badge_html}{flag_badge_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("Review Dossier & Outreach Copy", expanded=False):
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
                                            invalidate_dashboard_cache()
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
                                safe_hook = html.escape(draft.hook or "")
                                st.markdown(f"""
                                <div style="background-color: #18181b; border: 1px solid #27272a; border-left: 3px solid #fafafa; border-radius: 6px; padding: 10px 14px; margin-bottom: 12px;">
                                    <div style="font-size: 0.7rem; font-weight: 600; text-transform: uppercase; color: #a1a1aa; letter-spacing: 0.05em;">Fact-Grounded Observation</div>
                                    <div style="font-size: 0.875rem; color: #f4f4f5; margin-top: 4px; font-style: italic;">"{safe_hook}"</div>
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
                                            invalidate_dashboard_cache()
                                            st.success("Saved.")
                                            st.rerun()

                                    with col_e2:
                                        if st.button("Approve [A]", key=f"appr_email_{contact.id}", help="Approve draft (Shortcut: A)"):
                                            db.update_draft_status(draft.id, DraftStatus.APPROVED)
                                            db.update_contact_status(contact.id, ContactStatus.APPROVED)
                                            invalidate_dashboard_cache()
                                            st.success("Approved.")
                                            st.rerun()

                                    with col_e3:
                                        if is_flagged:
                                            st.button("Send [S]", key=f"send_email_{contact.id}", disabled=True, help="Flagged drafts cannot be sent until edited")
                                        else:
                                            if st.button("Send [S]", key=f"send_email_{contact.id}", help="Send email via Gmail API / Dry-run (Shortcut: S)"):
                                                success, msg = sender.send_approved_email(
                                                    contact=contact,
                                                    draft=draft,
                                                    force_dry_run=dry_run_active,
                                                )
                                                invalidate_dashboard_cache()
                                                if success:
                                                    st.success(msg)
                                                else:
                                                    st.error(msg)
                                                st.rerun()

                                    with col_e4:
                                        if st.button("Skip [K]", key=f"skip_{contact.id}", help="Skip prospect (Shortcut: K)"):
                                            db.update_contact_status(contact.id, ContactStatus.SKIPPED)
                                            invalidate_dashboard_cache()
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
                                            invalidate_dashboard_cache()
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
                                            invalidate_dashboard_cache()
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
                                            invalidate_dashboard_cache()
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

    logs = all_logs[:50]
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

    contacts_for_fu = [c for c in all_contacts if getattr(c, "status", None) == ContactStatus.EMAIL_SENT]
    if not contacts_for_fu:
        st.markdown(shadcn_callout("No contacts currently pending secondary follow-up touchpoints.", title="Queue Empty", variant="info"), unsafe_allow_html=True)
    else:
        for contact in contacts_for_fu:
            draft = all_drafts_map.get(contact.id)
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
                            invalidate_dashboard_cache()
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
        add_sup = st.form_submit_button("Add to Suppression", type="primary")
        if add_sup and sup_email:
            suppression_mgr.suppress_contact(sup_email, reason=sup_reason)
            invalidate_dashboard_cache()
            st.success(f"Suppressed {sup_email}.")
            st.rerun()

    suppressed = suppressed_all
    if suppressed:
        st.dataframe(
            [{"Email": s.email, "Reason": s.reason, "Opted Out At": s.opted_out_at[:19]} for s in suppressed],
            use_container_width=True,
        )
    else:
        st.markdown(shadcn_callout("Zero addresses currently suppressed. All future opt-outs will appear here and be permanently blocked.", title="No Suppressed Addresses", variant="success"), unsafe_allow_html=True)

