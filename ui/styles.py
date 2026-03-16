"""Permanent Corp brand theme for the Streamlit app."""
import streamlit as st


def inject_permanent_theme():
    """Inject Permanent Corp-branded CSS theme into the Streamlit app."""
    st.markdown("""
    <style>
    /* ================================================================
       PERMANENT CORP — ENRICHMENT TOOL THEME
       Brand: Dark navy, Permanent blue (#4479c4) accents
       ================================================================ */

    /* ---- CSS Variables ---- */
    :root {
        --perm-navy: #1a2332;
        --perm-navy-light: #243044;
        --perm-navy-hover: #2d3d56;
        --perm-brand: #4479c4;
        --perm-brand-light: #dbe8f7;
        --perm-blue: #4479c4;
        --perm-orange: #f59e0b;
        --perm-bg: #f1f5f9;
        --perm-card: #ffffff;
        --perm-border: #e2e8f0;
        --perm-text-dark: #0f172a;
        --perm-text: #334155;
        --perm-text-muted: #64748b;
        --perm-text-light: #94a3b8;
        --perm-red: #ef4444;
        --perm-green: #22c55e;
        --perm-radius: 8px;
    }

    /* ---- Base ---- */
    .stApp {
        background-color: var(--perm-bg) !important;
    }

    /* ---- Sidebar: Dark Navy ---- */
    [data-testid="stSidebar"] {
        background-color: var(--perm-navy) !important;
        border-right: none !important;
    }
    [data-testid="stSidebar"] * {
        color: #cbd5e1 !important;
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
        transition: all 0.15s ease !important;
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

    /* Sidebar section headers — hidden (flat nav, no groupings) */
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

    /* ---- Metric cards: Permanent style with teal accent ---- */
    [data-testid="stMetric"] {
        background: var(--perm-card);
        border: 1px solid var(--perm-border);
        border-left: 3px solid var(--perm-brand);
        border-radius: var(--perm-radius);
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
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
        transition: all 0.2s ease !important;
        letter-spacing: 0.01em !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background-color: var(--perm-navy-hover) !important;
        box-shadow: 0 2px 8px rgba(26, 35, 50, 0.25) !important;
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
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stButton > button[data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--perm-navy) !important;
        color: var(--perm-navy) !important;
        background-color: #f8fafc !important;
    }

    /* All buttons: shared base */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
    }

    /* ---- DataFrames: clean bordered tables ---- */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--perm-border);
        border-radius: var(--perm-radius);
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    }

    /* ---- Containers with border: card style ---- */
    [data-testid="stExpander"],
    .stAlert {
        border: 1px solid var(--perm-border) !important;
        border-radius: var(--perm-radius) !important;
        background: var(--perm-card) !important;
    }

    /* Bordered containers (st.container(border=True)) */
    [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid var(--perm-border) !important;
        border-radius: var(--perm-radius) !important;
        background: var(--perm-card) !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
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
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--perm-navy) !important;
        font-weight: 600 !important;
        border-bottom-color: var(--perm-navy) !important;
    }

    /* ---- Progress bars: teal ---- */
    .stProgress > div > div > div > div {
        background-color: var(--perm-brand) !important;
    }

    /* ---- Selectbox, text input: clean ---- */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextInput"] > div > div > input,
    [data-testid="stNumberInput"] > div > div > input,
    [data-testid="stTextArea"] > div > div > textarea {
        border-radius: 6px !important;
        border: 1px solid var(--perm-border) !important;
        font-size: 0.95rem !important;
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

    /* ---- File uploader ---- */
    [data-testid="stFileUploader"] {
        border: 2px dashed var(--perm-border) !important;
        border-radius: var(--perm-radius) !important;
        background: var(--perm-card) !important;
    }

    /* ---- Info/Warning/Error/Success: clean corporate ---- */
    .stAlert [data-testid="stAlertContentInfo"] {
        border-left-color: var(--perm-blue) !important;
    }
    .stAlert [data-testid="stAlertContentWarning"] {
        border-left-color: var(--perm-orange) !important;
    }
    .stAlert [data-testid="stAlertContentError"] {
        border-left-color: var(--perm-red) !important;
    }
    .stAlert [data-testid="stAlertContentSuccess"] {
        border-left-color: var(--perm-brand) !important;
    }

    /* ---- Download buttons ---- */
    .stDownloadButton > button {
        background-color: var(--perm-card) !important;
        color: var(--perm-text) !important;
        border: 1px solid var(--perm-border) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
    }
    .stDownloadButton > button:hover {
        border-color: var(--perm-navy) !important;
        color: var(--perm-navy) !important;
    }

    /* ---- Hide Streamlit chrome ---- */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] {
        background-color: var(--perm-bg) !important;
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

    /* ---- Toast notifications ---- */
    [data-testid="stToast"] {
        border-radius: var(--perm-radius) !important;
    }

    /* ---- Slider ---- */
    .stSlider [data-baseweb="slider"] div[role="slider"] {
        background-color: var(--perm-navy) !important;
    }

    /* ---- Main content area padding ---- */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
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


# Keep backward compatibility
inject_clay_theme = inject_permanent_theme
