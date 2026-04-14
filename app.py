import streamlit as st

st.set_page_config(
    page_title="SEO Traffic Forecast",
    page_icon="\U0001f4c8",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("SEO Traffic & Revenue Forecasting Engine")
st.markdown("""
Choose a forecasting mode from the sidebar:

- **Keyword Forecast** — Project traffic from target keywords (no historical data needed)
- **Historical Forecast** — Project traffic from your past organic data
- **Combined Forecast** — Layer new content projections onto your existing traffic baseline
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
