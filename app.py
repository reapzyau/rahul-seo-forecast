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

**Setup**
- **1. Data Upload** — Upload GA4, SEMrush, roadmap; configure seasonality and assumptions
- **2. Strategy** — Portfolio diagnosis + three scenario presets + one-click forecasting

**Deep-Dive Forecasts**
- **3. Historical Forecast** — Project traffic using statistical models
- **4. Positional Forecast** — Monte Carlo uplift bands from improving rankings
- **5. New Content Forecast** — Traffic from new keyword-targeting pages
- **6. Combined Forecast** — baseline + positional + new content − decay

**Outputs & Diagnostics**
- **7. Diagnostics** — AIO exposure, keyword pipeline, decay projection
- **8. Roadmap** — AI content roadmap + GAZMAN SEO task hours
- **9. Deliverables** — Forecast grid XLSX, variance grading, methodology
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
