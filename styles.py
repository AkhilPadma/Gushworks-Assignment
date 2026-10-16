"""
styles.py — Custom CSS for PackPro Lead Follow-Up app.
Includes mobile viewport fix for narrow screens.
"""

import streamlit as st


def inject_custom_css():
    st.markdown(
        """
        <style>
        /* Hide Streamlit's default chrome */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}

        /* Dormant section — dim */
        .dormant-section {
            opacity: 0.7;
        }

        /* Primary buttons — gradient */
        .stButton button[kind="primary"] {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            border: none;
            color: white;
            font-weight: 600;
            transition: all 0.2s;
        }
        .stButton button[kind="primary"]:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }

        /* Containers with border — hover effect */
        [data-testid="stContainer"]:has([data-testid="stHorizontalBlock"]) {
            transition: border-color 0.2s;
        }

        /* Rounded corners on inputs */
        .stTextInput input, .stTextArea textarea, .stSelectbox > div {
            border-radius: 8px !important;
        }

        /* Mobile viewport fixes */
        @media (max-width: 800px) {
            h1 {
                font-size: 1.5rem !important;
            }
            h3 {
                font-size: 1.1rem !important;
            }
            /* Popover buttons wrap less aggressively */
            [data-testid="stPopover"] button {
                font-size: 0.8rem !important;
                padding: 0.3rem 0.5rem !important;
                white-space: nowrap;
            }
            /* Lead card columns stack better */
            [data-testid="column"] {
                min-width: 0 !important;
            }
            /* Reduce title caption on narrow */
            [data-testid="stCaptionContainer"] {
                font-size: 0.75rem !important;
            }
        }

        @media (max-width: 500px) {
            /* Really narrow — stack action buttons vertically */
            h1 {
                font-size: 1.2rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )