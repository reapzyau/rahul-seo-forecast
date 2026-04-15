import os
import streamlit as st
import pandas as pd

from engine.historical_engine import run_historical_forecast, calculate_growth_rates
from engine.revenue_engine import add_revenue, CURRENCY_SYMBOLS
from utils.data_loader import load_traffic
from utils.chart_builder import historical_comparison_chart, revenue_projection_chart
from utils.export import to_csv, to_html_report

st.header("Historical Forecast")
st.caption("Project traffic from your past organic data using statistical models.")

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Historical Forecast Settings")

months = st.sidebar.slider("Forecast Horizon (months)", 3, 36, 12)
methods = st.sidebar.multiselect(
    "Forecasting Method",
    ["Linear Regression", "Exponential Smoothing", "Simple Moving Average"],
    default=["Linear Regression", "Exponential Smoothing", "Simple Moving Average"],
)
sma_window = st.sidebar.slider("SMA Window (months)", 2, 6, 3)
alpha = st.sidebar.slider("Smoothing Alpha", 0.1, 0.9, 0.3, step=0.05)
confidence = st.sidebar.slider("Confidence Band (%)", 5, 30, 15)

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
enable_revenue = st.sidebar.checkbox("Enable Revenue Projection", key="hist_rev")
cvr = st.sidebar.number_input("Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1, key="hist_cvr", disabled=not enable_revenue)
aov = st.sidebar.number_input("Average Order Value", 1.0, 100000.0, 100.0, step=10.0, key="hist_aov", disabled=not enable_revenue)
currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="hist_cur", disabled=not enable_revenue)

# ── Upload ───────────────────────────────────────────────────────────────────
st.subheader("Upload Historical Traffic CSV")
st.caption("Required columns: date, traffic")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Upload your CSV", type=["csv"], key="hist_upload")
with col2:
    use_sample = st.checkbox("Use sample data to explore the tool", key="hist_sample")

df = None
if uploaded_file is not None:
    df = load_traffic(uploaded_file)
elif use_sample:
    sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sample-traffic.csv")
    df = load_traffic(sample_path)

if df is not None:
    st.markdown(
        f"**{len(df)} months of data** | "
        f"Range: {df['date'].min().strftime('%b %Y')} – {df['date'].max().strftime('%b %Y')} | "
        f"Avg traffic: {df['traffic'].mean():,.0f}"
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

# ── Run Forecast ─────────────────────────────────────────────────────────────
if df is not None:
    if not methods:
        st.warning("Please select at least one forecasting method.")
    elif st.button("Generate Forecast", type="primary", key="hist_run"):
        with st.spinner("Running historical forecast..."):
            result = run_historical_forecast(df, months, methods, sma_window, alpha, confidence)
            growth = calculate_growth_rates(df["traffic"])

            st.session_state["hist_results"] = {
                "result": result,
                "growth": growth,
                "methods": methods,
                "enable_revenue": enable_revenue,
                "currency": currency,
                "cvr": cvr,
                "aov": aov,
                "raw_df": df,
            }

# ── Results ──────────────────────────────────────────────────────────────────
if "hist_results" in st.session_state:
    r = st.session_state["hist_results"]
    result = r["result"]
    growth = r["growth"]

    tab_names = ["\U0001f4ca Forecast Chart", "\U0001f4cb Data Table"]
    if r["enable_revenue"]:
        tab_names.append("\U0001f4b0 Revenue Analysis")
    tab_names.append("\U0001f4e5 Export")

    tabs = st.tabs(tab_names)
    tab_idx = 0

    # ── Tab: Forecast Chart ──────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        # KPI cards
        current_traffic = r["raw_df"]["traffic"].iloc[-1]

        # Get end-of-horizon traffic from best available method
        forecast_rows = result[result["is_forecast"]]
        if "linear" in result.columns:
            end_traffic = forecast_rows["linear"].iloc[-1]
        elif "exponential_smoothing" in result.columns:
            end_traffic = forecast_rows["exponential_smoothing"].iloc[-1]
        elif "sma" in result.columns:
            end_traffic = forecast_rows["sma"].iloc[-1]
        else:
            end_traffic = current_traffic

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Monthly Traffic", f"{current_traffic:,}")
        c2.metric("Projected (End of Horizon)", f"{int(end_traffic):,}")
        c3.metric("Avg MoM Growth", f"{growth['avg_mom']:.1f}%")
        c4.metric(
            "Latest YoY Growth",
            f"{growth['latest_yoy']:.1f}%" if growth['latest_yoy'] != 0 else "N/A",
        )

        fig = historical_comparison_chart(result, r["methods"])
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Historical data (solid) with forecast projections (dashed). Shaded area shows confidence band.")

    # ── Tab: Data Table ──────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        display_cols = ["date", "actual"]
        if "linear" in result.columns:
            display_cols.append("linear")
        if "exponential_smoothing" in result.columns:
            display_cols.append("exponential_smoothing")
        if "sma" in result.columns:
            display_cols.append("sma")

        display_df = result[display_cols].copy()
        display_df["date"] = display_df["date"].dt.strftime("%b %Y")
        col_rename = {
            "date": "Month",
            "actual": "Actual",
            "linear": "Linear Regression",
            "exponential_smoothing": "Exponential Smoothing",
            "sma": "Simple Moving Average",
        }
        display_df = display_df.rename(columns=col_rename)
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=500)

    # ── Tab: Revenue Analysis ────────────────────────────────────────────
    if r["enable_revenue"]:
        with tabs[tab_idx]:
            tab_idx += 1
            sym = CURRENCY_SYMBOLS.get(r["currency"], "$")

            # Use linear forecast for revenue if available
            rev_col = "linear" if "linear" in result.columns else (
                "exponential_smoothing" if "exponential_smoothing" in result.columns else "sma"
            )

            forecast_only = result[result["is_forecast"]].copy()
            forecast_only = forecast_only.rename(columns={rev_col: "traffic"})
            forecast_only = add_revenue(forecast_only, r["cvr"], r["aov"], r["currency"])

            peak_rev = forecast_only["revenue"].max()
            total_rev = forecast_only["revenue"].sum()
            total_leads = forecast_only["leads"].sum()

            c1, c2, c3 = st.columns(3)
            c1.metric("Peak Monthly Revenue", f"{sym}{peak_rev:,.2f}")
            c2.metric("Total Revenue (Forecast Period)", f"{sym}{total_rev:,.2f}")
            c3.metric("Total Leads", f"{total_leads:,}")

            fig_rev = revenue_projection_chart(forecast_only, sym)
            st.plotly_chart(fig_rev, use_container_width=True)

    # ── Tab: Export ──────────────────────────────────────────────────────
    with tabs[tab_idx]:
        ec1, ec2 = st.columns(2)
        with ec1:
            st.download_button(
                "Download Forecast CSV",
                to_csv(result),
                "historical-forecast.csv",
                "text/csv",
            )
        with ec2:
            summary = {
                "Current Traffic": f"{r['raw_df']['traffic'].iloc[-1]:,}",
                "Projected End Traffic": f"{int(end_traffic):,}",
                "Avg MoM Growth": f"{growth['avg_mom']:.1f}%",
            }
            figs = [historical_comparison_chart(result, r["methods"])]
            html = to_html_report(figs, summary, "Historical Forecast Report")
            st.download_button(
                "Download HTML Report",
                html,
                "historical-report.html",
                "text/html",
            )
