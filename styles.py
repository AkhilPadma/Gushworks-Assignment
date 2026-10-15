"""
styles.py — Custom CSS to make the Streamlit app look like a real SaaS product.
"""

import streamlit as st


def inject_custom_css():
    st.markdown("""
    <style>
    /* ---- Overall page ---- */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    /* ---- Title styling ---- */
    h1 {
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }

    h3 {
        font-weight: 600 !important;
        margin-top: 2rem !important;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
    }

    /* ---- Lead cards ---- */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        transition: all 0.15s ease;
        border-radius: 10px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        transform: translateY(-1px);
    }

    /* ---- Buttons ---- */
    .stButton button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.15s ease;
    }
    .stButton button:hover {
        transform: translateY(-1px);
    }

    /* ---- Primary buttons (Mark as sent, etc.) ---- */
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5, #7c3aed) !important;
        border: none !important;
    }

    /* ---- Form inputs ---- */
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        border-radius: 8px !important;
    }

    /* ---- Progress bar ---- */
    .stProgress > div > div {
        background: linear-gradient(90deg, #4f46e5, #7c3aed) !important;
    }

    /* ---- Sidebar polish ---- */
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.15);
    }

    /* ---- Captions ---- */
    .stCaption, [data-testid="stCaption"] {
        color: rgba(128, 128, 128, 0.85) !important;
    }

    /* ---- Dormant bucket (dimmed) ---- */
    .dormant-section {
        opacity: 0.75;
    }

    /* ---- Hide Streamlit chrome ---- */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)