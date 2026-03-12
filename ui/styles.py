"""Clay-inspired CSS theme for the Streamlit app."""
import streamlit as st


def inject_clay_theme():
    """Inject Clay.com-inspired CSS theme into the Streamlit app."""
    st.markdown("""
    <style>
    /* ---- Base ---- */
    .stApp { background-color: #fafafa; }

    /* ---- Sidebar ---- */
    [data-testid="stSidebar"] {
        background-color: #f7f7f8;
        border-right: 1px solid #e5e7eb;
    }
    [data-testid="stSidebar"] .stMarkdown h3 {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1a1a1a;
    }

    /* ---- Headers: tighter, professional ---- */
    .stApp h1 { font-size: 1.5rem !important; font-weight: 600 !important; color: #1a1a1a !important; }
    .stApp h2 { font-size: 1.2rem !important; font-weight: 600 !important; color: #1a1a1a !important; }
    .stApp h3 { font-size: 1.0rem !important; font-weight: 600 !important; color: #374151 !important; }

    /* ---- Metric cards: compact with left accent ---- */
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #e5e7eb;
        border-left: 3px solid #4f46e5;
        border-radius: 8px;
        padding: 12px 16px;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6b7280 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
        font-weight: 600 !important;
        color: #1a1a1a !important;
    }

    /* ---- Buttons: flat, professional ---- */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        font-size: 0.85rem;
        transition: all 0.2s;
    }

    /* ---- DataFrames: the hero element ---- */
    [data-testid="stDataFrame"] {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        overflow: hidden;
    }

    /* ---- Containers with border ---- */
    [data-testid="stExpander"] {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        background: white;
    }

    /* ---- Dividers: subtle ---- */
    [data-testid="stDivider"] {
        border-color: #f0f0f0 !important;
    }

    /* ---- Tabs: clean ---- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 2px solid #e5e7eb;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 20px;
        font-weight: 500;
        font-size: 0.85rem;
    }

    /* ---- Progress bars: indigo ---- */
    .stProgress > div > div > div > div {
        background-color: #4f46e5;
    }

    /* ---- Hide Streamlit chrome ---- */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    /* ---- Selectbox, text input: clean borders ---- */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextInput"] > div > div > input {
        border-radius: 6px;
        border: 1px solid #d1d5db;
    }

    /* ---- Toolbar area styling ---- */
    .clay-toolbar {
        padding: 8px 0;
        margin-bottom: 4px;
    }
    .clay-toolbar .credit-badge {
        display: inline-block;
        background: #f0f0f5;
        border-radius: 12px;
        padding: 4px 12px;
        font-size: 0.8rem;
        color: #4f46e5;
        font-weight: 600;
    }

    /* ---- Status badges ---- */
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    .status-running { background: #dbeafe; color: #1d4ed8; }
    .status-completed { background: #dcfce7; color: #166534; }
    .status-failed { background: #fee2e2; color: #991b1b; }
    .status-paused { background: #fef3c7; color: #92400e; }
    </style>
    """, unsafe_allow_html=True)
