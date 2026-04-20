import os

import streamlit as st

from utils.page_base import setup_page

setup_page("Methodology", "How the forecasting models work.", show_assumptions_banner=False)

methodology_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "methodology.md")

try:
    with open(methodology_path) as f:
        content = f.read()
    st.markdown(content)
except FileNotFoundError:
    st.error("Methodology document not found. Please ensure methodology.md exists in the project root.")
