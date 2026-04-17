import streamlit as st
from utils.sidebar import render_ai_settings

st.set_page_config(
    page_title="SEO Traffic Forecast",
    page_icon="\U0001f4c8",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("SEO Traffic & Revenue Forecasting Engine")

render_ai_settings()

st.markdown("""
Choose a forecasting mode from the sidebar:

- **Data Upload** — Upload GA4 organic and SEMrush keyword exports (used across all pages)
- **Positional Forecast** — Project uplift from moving existing keywords up the SERP
- **New Content Forecast** — Project traffic from new content targeting new keywords
- **Historical Forecast** — Project traffic from your past organic data
- **Combined Forecast** — Layer historical baseline + positional + new content
- **Seasonality** — Apply monthly modifiers and campaign events
- **AI Overview Risk** — Traffic at risk from AIO, with action recommendations
- **Keyword Pipeline** — Track keyword distribution across SERP pages over time
- **Content Roadmap** — AI-powered content planning and prioritization
- **SEO Roadmap** — Month-by-month task allocation in the GAZMAN format
- **Forecast Grid Export** — Forecast / Actual / % Variance grid for the multi-channel plan
- **Methodology** — How the models work
""")

st.divider()

st.markdown("""
### Getting Started

1. **Upload a CSV** with your keyword or traffic data (or use the built-in sample data)
2. **Configure settings** in the sidebar (domain authority, forecast horizon, etc.)
3. **Click Generate Forecast** to see your projections
4. **Export results** as CSV or an interactive HTML report

Each mode is designed around a different use case — explore the sidebar to get started.
""")
