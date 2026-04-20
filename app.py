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
Choose a page from the sidebar:

- **Data Upload** — Upload GA4 organic and SEMrush keyword exports; configure seasonality and assumptions
- **Positional Forecast** — Monte Carlo P10/P50/P90 uplift from improving existing rankings
- **New Content Forecast** — Project traffic from new content targeting new keywords
- **Historical Forecast** — Project traffic from your past organic data
- **Combined Forecast** — Canonical hub: baseline + positional + new content \u2212 decay
- **Diagnostics** — AIO risk exposure, keyword pipeline distribution, and decay projection
- **Roadmap** — AI content roadmap and GAZMAN-style SEO task hours grid
- **Deliverables** — Download the forecast grid XLSX, grade a past forecast, and read the methodology
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
