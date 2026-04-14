import os
import streamlit as st

st.header("Methodology")
st.caption("How the forecasting models work.")

methodology_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "methodology.md")

try:
    with open(methodology_path, "r") as f:
        content = f.read()
    st.markdown(content)
except FileNotFoundError:
    st.error("Methodology document not found. Please ensure methodology.md exists in the project root.")
