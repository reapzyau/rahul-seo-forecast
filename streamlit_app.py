import streamlit as st

st.set_page_config(
    page_title="SEO Forecast System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("SEO Traffic & Revenue Forecasting Engine")
st.caption("Pattern Digital — AI-assisted SEO forecasting for e-commerce and retail")

st.markdown("""
### Forecast Dashboard & Data Explorer

| Page | Description |
|------|-------------|
| 🔮 **Forecast Dashboard** | Interactive forecast explorer — full React app |
| 📁 **Data Sources** | Preview and download the four sample data files |
| ℹ️ **About** | Methodology, assumptions, and links |

---

### Python Forecasting Engine

The recommended workflow is **Data Upload → Strategy → Deliverables**.

| Step | Page | What it does |
|------|------|--------------|
| 1 | **Data Upload** | Upload GA4 + SEMrush; configure seasonality and assumptions |
| 2 | **Strategy** | Portfolio diagnosis + three scenario presets + one-click forecasting |
| 3 | **Deliverables** | Download 3-scenario forecast grid XLSX for the client deck |

Deep-dive pages (Historical, Positional, New Content, Combined, Diagnostics, Roadmap)
are available from the sidebar for scenario analysis.
""")
