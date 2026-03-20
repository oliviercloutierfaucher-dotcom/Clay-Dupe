"""Permanent Corp brand theme for the Streamlit app."""
import streamlit as st


def inject_permanent_theme():
    """Inject Permanent Corp-branded CSS theme into the Streamlit app."""
    st.markdown("""
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* ================================================================
       PERMANENT CORP -- ENRICHMENT TOOL THEME
       Brand: Premium Light Theme (Next.js IC Dashboard aligned)
       $500/mo SaaS polish pass
       ================================================================ */

    /* ---- CSS Variables ---- */
    :root {
        --perm-navy: #0f1b2d;
        --perm-navy-light: #1a2744;
        --perm-navy-hover: #1e304f;
        --perm-brand: #3069e1;
        --perm-brand-light: #eff6ff;
        --perm-blue: #3069e1;
        --perm-orange: #f59e0b;
        --perm-bg: #f3f4f6;
        --perm-card: #ffffff;
        --perm-border: #e5e7eb;
        --perm-text-dark: #1c1c1c;
        --perm-text: #4b5563;
        --perm-text-muted: #6b7280;
        --perm-text-light: #9ca3af;
        --perm-red: #ef4444;
        --perm-green: #10b981;
        --perm-radius: 8px;
        --perm-shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04);
        --perm-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.07);
        --perm-shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.10);
        --perm-transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* ---- Base ---- */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    .stApp {
        background-color: var(--perm-bg) !important;
    }

    /* ---- Hide ALL Streamlit chrome ---- */
    #MainMenu { display: none !important; }
    footer { display: none !important; }
    header[data-testid="stHeader"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    .viewerBadge_container__r5tak { display: none !important; }
    .stDeployButton { display: none !important; }
    #stDecoration { display: none !important; }
    div[data-testid="stActionButtonIcon"] { display: none !important; }

    /* ---- Sidebar: Dark Navy ---- */
    [data-testid="stSidebar"] {
        background-color: var(--perm-navy) !important;
        border-right: none !important;
        padding-top: 1.5rem !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding: 0 1.25rem !important;
    }
    [data-testid="stSidebar"] * {
        color: #cbd5e1 !important;
        transition: var(--perm-transition) !important;
    }
    [data-testid="stSidebar"] .stMarkdown h3,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h1 {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    [data-testid="stSidebar"] .stMarkdown p {
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stDivider"] {
        border-color: #334155 !important;
    }

    /* Sidebar nav links */
    [data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
    [data-testid="stSidebar"] a {
        color: #cbd5e1 !important;
        border-radius: 6px !important;
        transition: var(--perm-transition) !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover,
    [data-testid="stSidebar"] a:hover {
        background-color: var(--perm-navy-hover) !important;
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-selected="true"],
    [data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
        background-color: var(--perm-navy-light) !important;
        color: #ffffff !important;
        border-left: 3px solid var(--perm-brand) !important;
    }

    /* Sidebar section headers -- hidden (flat nav, no groupings) */
    [data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"],
    [data-testid="stSidebar"] .st-emotion-cache-ue6h4q {
        display: none !important;
    }

    /* ---- Base font size ---- */
    .stApp, .stApp p, .stApp span, .stApp div {
        font-size: 0.95rem;
    }

    /* ---- Headers: Professional, clean ---- */
    .stApp h1 {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        color: var(--perm-text-dark) !important;
        letter-spacing: -0.01em !important;
    }
    .stApp h2 {
        font-size: 1.35rem !important;
        font-weight: 600 !important;
        color: var(--perm-text-dark) !important;
    }
    .stApp h3 {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: var(--perm-text) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.03em !important;
    }

    /* ---- Metric cards: Permanent style with hover effect ---- */
    [data-testid="stMetric"] {
        background: var(--perm-card);
        border: 1px solid var(--perm-border);
        border-left: 3px solid var(--perm-brand);
        border-radius: var(--perm-radius);
        padding: 18px 22px;
        box-shadow: var(--perm-shadow-sm);
        transition: var(--perm-transition);
    }
    [data-testid="stMetric"]:hover {
        box-shadow: var(--perm-shadow-md);
        transform: translateY(-1px);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        color: var(--perm-text-muted) !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        color: var(--perm-text-dark) !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.85rem !important;
    }

    /* ---- Primary buttons: Navy, professional ---- */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background-color: var(--perm-navy) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        padding: 8px 20px !important;
        transition: var(--perm-transition) !important;
        letter-spacing: 0.01em !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background-color: var(--perm-navy-hover) !important;
        box-shadow: 0 2px 8px rgba(26, 35, 50, 0.25) !important;
        transform: translateY(-1px) !important;
    }

    /* Secondary buttons: outlined */
    .stButton > button[kind="secondary"],
    .stButton > button[data-testid="stBaseButton-secondary"] {
        background-color: var(--perm-card) !important;
        color: var(--perm-text) !important;
        border: 1px solid var(--perm-border) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        transition: var(--perm-transition) !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stButton > button[data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--perm-navy) !important;
        color: var(--perm-navy) !important;
        background-color: #f8fafc !important;
        transform: translateY(-1px) !important;
    }

    /* All buttons: shared base */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        transition: var(--perm-transition) !important;
    }

    /* ---- DataFrames: clean bordered tables ---- */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--perm-border);
        border-radius: var(--perm-radius);
        overflow: hidden;
        box-shadow: var(--perm-shadow-sm);
    }

    /* Data table header row: navy background, white text */
    [data-testid="stDataFrame"] [data-testid="glideDataEditor"] .dvn-scroller th,
    [data-testid="stDataFrame"] thead tr th,
    [data-testid="stDataFrame"] .glideHeaderCell {
        background-color: var(--perm-navy) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
    }

    /* Alternating row colors */
    [data-testid="stDataFrame"] tbody tr:nth-child(even),
    [data-testid="stDataFrame"] .dvn-scroller [data-row]:nth-child(even) {
        background-color: #f8fafc !important;
    }
    [data-testid="stDataFrame"] tbody tr:nth-child(odd),
    [data-testid="stDataFrame"] .dvn-scroller [data-row]:nth-child(odd) {
        background-color: #ffffff !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover,
    [data-testid="stDataFrame"] .dvn-scroller [data-row]:hover {
        background-color: var(--perm-brand-light) !important;
    }

    /* ---- Expander: clean with subtle shadow ---- */
    [data-testid="stExpander"] {
        border: 1px solid var(--perm-border) !important;
        border-radius: var(--perm-radius) !important;
        background: var(--perm-card) !important;
        box-shadow: var(--perm-shadow-sm) !important;
        transition: var(--perm-transition) !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"]:hover {
        box-shadow: var(--perm-shadow-md) !important;
    }
    [data-testid="stExpander"] summary {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        color: var(--perm-text-dark) !important;
        padding: 14px 18px !important;
    }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding: 0 18px 14px 18px !important;
    }

    /* ---- Alert banners: softer, professional ---- */
    .stAlert {
        border: none !important;
        border-radius: var(--perm-radius) !important;
        background: var(--perm-card) !important;
        box-shadow: var(--perm-shadow-sm) !important;
    }
    .stAlert [data-testid="stAlertContentInfo"] {
        background-color: #f0f4ff !important;
        border-left: 3px solid var(--perm-blue) !important;
        border-radius: var(--perm-radius) !important;
        color: var(--perm-text) !important;
    }
    .stAlert [data-testid="stAlertContentWarning"] {
        background-color: #fffbeb !important;
        border-left: 3px solid var(--perm-orange) !important;
        border-radius: var(--perm-radius) !important;
        color: var(--perm-text) !important;
    }
    .stAlert [data-testid="stAlertContentError"] {
        background-color: #fef7f7 !important;
        border-left: 3px solid var(--perm-red) !important;
        border-radius: var(--perm-radius) !important;
        color: var(--perm-text) !important;
    }
    .stAlert [data-testid="stAlertContentSuccess"] {
        background-color: #f0fdf8 !important;
        border-left: 3px solid var(--perm-green) !important;
        border-radius: var(--perm-radius) !important;
        color: var(--perm-text) !important;
    }
    .stAlert svg {
        opacity: 0.7 !important;
    }

    /* Bordered containers (st.container(border=True)) */
    [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid var(--perm-border) !important;
        border-radius: var(--perm-radius) !important;
        background: var(--perm-card) !important;
        box-shadow: var(--perm-shadow-sm) !important;
    }

    /* ---- Dividers: very subtle ---- */
    [data-testid="stDivider"] {
        border-color: var(--perm-border) !important;
    }

    /* ---- Tabs: clean underline style ---- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important;
        border-bottom: 2px solid var(--perm-border) !important;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 24px !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        color: var(--perm-text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.03em !important;
        transition: var(--perm-transition) !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--perm-navy) !important;
        font-weight: 600 !important;
        border-bottom-color: var(--perm-navy) !important;
    }

    /* ---- Progress bars: rounded with gradient ---- */
    .stProgress > div > div {
        border-radius: 10px !important;
        overflow: hidden !important;
        background-color: #e8ecf1 !important;
        height: 8px !important;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, var(--perm-brand), #1e50c0) !important;
        border-radius: 10px !important;
    }

    /* ---- Selectbox, text input: clean ---- */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextInput"] > div > div > input,
    [data-testid="stNumberInput"] > div > div > input,
    [data-testid="stTextArea"] > div > div > textarea {
        border-radius: 6px !important;
        border: 1px solid var(--perm-border) !important;
        font-size: 0.95rem !important;
        transition: var(--perm-transition) !important;
    }
    [data-testid="stSelectbox"] > div > div:focus-within,
    [data-testid="stTextInput"] > div > div > input:focus,
    [data-testid="stNumberInput"] > div > div > input:focus {
        border-color: var(--perm-navy) !important;
        box-shadow: 0 0 0 1px var(--perm-navy) !important;
    }

    /* Input labels */
    .stTextInput label,
    .stSelectbox label,
    .stNumberInput label,
    .stTextArea label,
    .stSlider label,
    .stMultiSelect label,
    .stRadio label,
    .stCheckbox label {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: var(--perm-text-muted) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
    }

    /* ---- Toggle: navy when on ---- */
    [data-testid="stToggle"] span[data-checked="true"] {
        background-color: var(--perm-navy) !important;
    }

    /* ---- File uploader: modern solid border ---- */
    [data-testid="stFileUploader"] {
        border: 2px solid var(--perm-border) !important;
        border-radius: var(--perm-radius) !important;
        background: linear-gradient(180deg, #fafbfc 0%, #f3f4f6 100%) !important;
        padding: 24px !important;
        transition: var(--perm-transition) !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: var(--perm-brand) !important;
        background: linear-gradient(180deg, #f8faff 0%, #eff6ff 100%) !important;
    }
    [data-testid="stFileUploader"] button {
        background-color: var(--perm-brand) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }

    /* ---- Download buttons ---- */
    .stDownloadButton > button {
        background-color: var(--perm-card) !important;
        color: var(--perm-text) !important;
        border: 1px solid var(--perm-border) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        transition: var(--perm-transition) !important;
    }
    .stDownloadButton > button:hover {
        border-color: var(--perm-navy) !important;
        color: var(--perm-navy) !important;
        transform: translateY(-1px) !important;
    }

    /* ---- Custom section headers with accent bar ---- */
    .perm-section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 24px 0 12px 0;
        padding: 0;
    }
    .perm-section-header .accent-bar {
        width: 4px;
        height: 22px;
        border-radius: 2px;
        flex-shrink: 0;
    }
    .perm-section-header .accent-blue { background-color: var(--perm-blue); }
    .perm-section-header .accent-teal { background-color: var(--perm-brand); }
    .perm-section-header .accent-orange { background-color: var(--perm-orange); }
    .perm-section-header .accent-navy { background-color: var(--perm-navy); }
    .perm-section-header .section-title {
        font-size: 0.95rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--perm-text-dark);
        margin: 0;
    }

    /* ---- Page header class ---- */
    .perm-page-header {
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 2px solid var(--perm-border);
    }
    .perm-page-header h1 {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        color: var(--perm-text-dark) !important;
        margin: 0 0 4px 0 !important;
        letter-spacing: -0.01em !important;
    }
    .perm-page-header .perm-page-subtitle {
        font-size: 0.92rem;
        color: var(--perm-text-muted);
        margin: 0;
        font-weight: 400;
    }

    /* ---- Empty state class ---- */
    .perm-empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 48px 24px;
        text-align: center;
    }
    .perm-empty-state .perm-empty-icon {
        font-size: 3rem;
        color: var(--perm-text-light);
        margin-bottom: 16px;
        opacity: 0.5;
    }
    .perm-empty-state .perm-empty-message {
        font-size: 0.95rem;
        color: var(--perm-text-muted);
        font-weight: 500;
        max-width: 320px;
        line-height: 1.5;
    }

    /* ---- KPI card class ---- */
    .perm-kpi-card {
        background: var(--perm-card);
        border: 1px solid var(--perm-border);
        border-radius: var(--perm-radius);
        padding: 20px 22px;
        box-shadow: var(--perm-shadow-sm);
        transition: var(--perm-transition);
        display: flex;
        flex-direction: column;
        gap: 6px;
    }
    .perm-kpi-card:hover {
        box-shadow: var(--perm-shadow-md);
        transform: translateY(-1px);
    }
    .perm-kpi-card .kpi-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .perm-kpi-card .kpi-icon {
        width: 36px;
        height: 36px;
        border-radius: 8px;
        background: var(--perm-brand-light);
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--perm-brand);
        font-size: 1.2rem;
    }
    .perm-kpi-card .kpi-delta {
        font-size: 0.78rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 10px;
    }
    .perm-kpi-card .kpi-delta-up {
        background: #ecfdf5;
        color: #059669;
    }
    .perm-kpi-card .kpi-delta-down {
        background: #fef2f2;
        color: #dc2626;
    }
    .perm-kpi-card .kpi-delta-neutral {
        background: #f3f4f6;
        color: var(--perm-text-muted);
    }
    .perm-kpi-card .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--perm-text-dark);
        line-height: 1.1;
        margin-top: 4px;
    }
    .perm-kpi-card .kpi-label {
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--perm-text-muted);
    }

    /* ---- Status badges ---- */
    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.68rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .status-running { background: #dbeafe; color: #1e40af; }
    .status-completed { background: var(--perm-brand-light); color: #065f46; }
    .status-failed { background: #fee2e2; color: #991b1b; }
    .status-paused { background: #fef3c7; color: #92400e; }
    .status-created { background: #f0f0f5; color: #4b5563; }

    /* ---- Toolbar area styling ---- */
    .perm-toolbar {
        padding: 8px 0;
        margin-bottom: 4px;
    }
    .perm-credit-badge {
        display: inline-block;
        background: var(--perm-navy);
        border-radius: 16px;
        padding: 4px 14px;
        font-size: 0.78rem;
        color: #ffffff;
        font-weight: 600;
        letter-spacing: 0.02em;
    }

    /* ---- Permanent logo text in sidebar ---- */
    .perm-logo {
        display: flex;
        align-items: center;
        gap: 2px;
        margin-bottom: 2px;
    }
    .perm-logo-p {
        font-family: 'Georgia', 'Times New Roman', serif;
        font-size: 1.6rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1;
    }
    .perm-logo-text {
        font-family: 'Georgia', 'Times New Roman', serif;
        font-size: 1.1rem;
        font-weight: 400;
        color: #ffffff;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        line-height: 1;
        padding-top: 3px;
    }
    .perm-subtitle {
        font-size: 0.72rem;
        color: #94a3b8;
        letter-spacing: 0.02em;
        margin-top: 4px;
    }

    /* ---- Multiselect tags ---- */
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
        background-color: var(--perm-navy) !important;
        color: #ffffff !important;
        border-radius: 4px !important;
    }

    /* ---- Radio buttons ---- */
    .stRadio [data-testid="stMarkdownContainer"] p {
        font-size: 0.95rem !important;
    }

    /* ---- Checkbox ---- */
    .stCheckbox [data-testid="stCheckbox"] input:checked + div {
        background-color: var(--perm-navy) !important;
        border-color: var(--perm-navy) !important;
    }

    /* ---- Toast notifications: professional ---- */
    [data-testid="stToast"] {
        border-radius: var(--perm-radius) !important;
        box-shadow: var(--perm-shadow-lg) !important;
        border: 1px solid var(--perm-border) !important;
        background: var(--perm-card) !important;
        backdrop-filter: blur(8px) !important;
    }
    [data-testid="stToast"] [data-testid="stToastContent"] {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        color: var(--perm-text-dark) !important;
    }

    /* ---- Slider: brand blue track ---- */
    .stSlider [data-baseweb="slider"] div[role="slider"] {
        background-color: var(--perm-brand) !important;
        border-color: var(--perm-brand) !important;
    }
    .stSlider [data-baseweb="slider"] div[data-testid="stTickBar"] > div {
        background-color: var(--perm-brand) !important;
    }
    .stSlider [data-baseweb="slider"] [role="progressbar"] > div {
        background-color: var(--perm-brand) !important;
    }

    /* ---- Main content area padding ---- */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }

    /* ---- Scrollbar: thin and subtle ---- */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    ::-webkit-scrollbar-thumb {
        background: #c5ccd6;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #9ca3af;
    }
    * {
        scrollbar-width: thin;
        scrollbar-color: #c5ccd6 transparent;
    }

    /* ---- Smooth transitions on interactive elements ---- */
    a, button, input, select, textarea,
    [data-testid="stSidebarNavLink"],
    [data-baseweb="tab"],
    [data-testid="stExpander"],
    .stButton > button,
    .stDownloadButton > button {
        transition: var(--perm-transition) !important;
    }

    </style>
    """, unsafe_allow_html=True)


# Helper for section headers with colored accent bars (matches Permanent dashboard)
def section_header(title: str, color: str = "blue"):
    """Render a section header with a colored left accent bar.

    Args:
        title: Section title text (will be uppercased).
        color: Accent color - 'blue', 'teal', 'orange', or 'navy'.
    """
    st.markdown(
        f'<div class="perm-section-header">'
        f'<div class="accent-bar accent-{color}"></div>'
        f'<span class="section-title">{title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = ""):
    """Render a consistent page header with optional subtitle.

    Args:
        title: Main page title.
        subtitle: Optional subtitle text displayed below the title.
    """
    subtitle_html = (
        f'<p class="perm-page-subtitle">{subtitle}</p>' if subtitle else ""
    )
    st.markdown(
        f'<div class="perm-page-header">'
        f'<h1>{title}</h1>'
        f'{subtitle_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def empty_state(message: str, icon: str = "inbox"):
    """Render a professional empty state with a Material icon and message.

    Args:
        message: Text to display below the icon.
        icon: Material Icons Outlined icon name (e.g. 'inbox', 'search', 'folder_open').
    """
    st.markdown(
        f'<div class="perm-empty-state">'
        f'<span class="material-icons-outlined perm-empty-icon">{icon}</span>'
        f'<p class="perm-empty-message">{message}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


# Keep backward compatibility
inject_clay_theme = inject_permanent_theme
