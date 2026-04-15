import streamlit as st

st.set_page_config(
    page_title="SEO Traffic Forecast",
    page_icon="\U0001f4c8",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("SEO Traffic & Revenue Forecasting Engine")

# ── AI Settings (global, persisted in session state) ─────────────────────
with st.sidebar.expander("AI Settings (Bi Frost)", expanded=False):
    st.text_input(
        "Bi Frost API Key",
        type="password",
        key="bifrost_api_key",
        help="Enter your Bi Frost virtual key (sk-bf-...) to enable AI-powered features.",
    )
    st.selectbox(
        "AI Model",
        ["openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-sonnet-4-5-20250929"],
        key="bifrost_model",
        help="Model used for keyword clustering, cannibalization checks, and content roadmap.",
    )

st.markdown("""
Choose a forecasting mode from the sidebar:

- **Keyword Forecast** — Project traffic from target keywords (no historical data needed)
- **Historical Forecast** — Project traffic from your past organic data
- **Combined Forecast** — Layer new content projections onto your existing traffic baseline
- **Seasonality** — Apply monthly modifiers and campaign events to your forecast
- **Content Roadmap** — AI-powered content planning and prioritization
- **Keyword Pipeline** — Track keyword distribution across SERP pages over time
- **Budget Roadmap** — SEO task allocation and monthly budget planning
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
