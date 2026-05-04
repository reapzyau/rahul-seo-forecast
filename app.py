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
- **8. Roadmap** — AI content roadmap + SEO task hours
- **9. Deliverables** — Forecast grid XLSX, variance grading, methodology
""")

st.divider()

st.markdown("""
### Getting Started

1. **Data Upload (page 1)** — Upload your GA4 organic export (xlsx), SEMrush keyword positions
   (csv/xlsx), and an optional roadmap file. Use the sample data checkboxes to try the tool
   without your own files.
2. **Strategy (page 2)** — Review the auto-generated portfolio diagnosis, adjust the three
   scenario presets (Conservative / Moderate / Aggressive), then click **Run All Forecasts**.
3. **Deliverables (page 9)** — Download the three-scenario forecast grid XLSX, ready to paste
   into your multi-channel plan.

Deep-dive pages (3–8) are available for per-stream analysis, diagnostics, and roadmap planning.
The **Methodology** tab on page 9 documents all forecast assumptions and engine logic.
""")
