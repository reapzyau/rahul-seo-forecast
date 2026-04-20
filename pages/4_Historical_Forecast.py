import os
import streamlit as st
import pandas as pd

from engine.historical_engine import run_historical_forecast, run_historical_forecast_v4, calculate_growth_rates
from engine.revenue_engine import add_revenue, build_full_metrics_table, CURRENCY_SYMBOLS
from utils.data_loader import load_traffic
from utils.chart_builder import historical_comparison_chart, revenue_projection_chart
from utils.export import to_csv, to_html_report, traffic_template_csv
from utils.sidebar import render_ai_settings

st.header("Historical Forecast")
st.caption("Project traffic from your past organic data using statistical models.")

render_ai_settings()

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Historical Forecast Settings")

months = st.sidebar.slider("Forecast Horizon (months)", 3, 36, 12)

st.sidebar.divider()
st.sidebar.subheader("Advanced")
use_v4 = st.sidebar.checkbox(
    "Use v4 auto-gated model selection",
    value=True,
    help="Automatically selects Prophet/Holt's/Linear based on data length.",
    key="hist_use_v4",
)

# Infer prophet-active from previous render's data length (session state)
_n_hist = st.session_state.get("hist_n_months", 0)
_prophet_active = use_v4 and _n_hist >= 24

# V4-specific controls
changepoint_prior_scale = st.sidebar.slider(
    "Trend flexibility (Prophet)",
    0.001, 0.5, 0.05, step=0.005,
    key="hist_changepoint",
    help="Higher = more flexible trend (Prophet only). 0.05 is recommended.",
    disabled=not _prophet_active,
)

# Legacy multi-method controls (shown when v4 is off)
methods = st.sidebar.multiselect(
    "Forecasting Method (legacy)",
    ["Linear Regression", "Exponential Smoothing", "Simple Moving Average"],
    default=["Linear Regression", "Exponential Smoothing"],
    key="hist_methods",
    disabled=use_v4,
)
sma_window = st.sidebar.slider("SMA Window (months)", 2, 6, 3, disabled=use_v4)
alpha = st.sidebar.slider("Smoothing Alpha", 0.1, 0.9, 0.3, step=0.05, disabled=use_v4)
# Prophet provides its own uncertainty intervals; confidence band only applies to linear/Holt's
confidence = st.sidebar.slider("Confidence Band (%)", 5, 30, 15, disabled=_prophet_active)

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
enable_revenue = st.sidebar.checkbox("Enable Revenue Projection", key="hist_rev")
cvr = st.sidebar.number_input("Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1, key="hist_cvr", disabled=not enable_revenue)
aov = st.sidebar.number_input("Average Order Value", 1.0, 100000.0, 100.0, step=10.0, key="hist_aov", disabled=not enable_revenue)
currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="hist_cur", disabled=not enable_revenue)

# ── Upload ───────────────────────────────────────────────────────────────────
st.subheader("Upload Historical Data")
st.caption("Required: date, traffic. Optional: revenue, transactions, aov, cr% — supports CSV, TSV, and Excel.")

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    uploaded_file = st.file_uploader("Upload your file", type=["csv", "tsv", "xlsx", "xls"], key="hist_upload")
with col2:
    use_sample = st.checkbox("Use sample data to explore the tool", key="hist_sample")
with col3:
    st.download_button(
        "Download CSV Template",
        traffic_template_csv(),
        "traffic-template.csv",
        "text/csv",
        key="hist_template_dl",
    )

df = None
if uploaded_file is not None:
    df = load_traffic(uploaded_file)
elif use_sample:
    sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sample-traffic.csv")
    df = load_traffic(sample_path)

if df is not None:
    st.session_state["hist_n_months"] = len(df)
    # Build summary line
    summary_parts = [
        f"**{len(df)} months of data**",
        f"Range: {df['date'].min().strftime('%b %Y')} – {df['date'].max().strftime('%b %Y')}",
        f"Avg traffic: {df['traffic'].mean():,.0f}",
    ]
    optional_cols = [c for c in ["revenue", "transactions", "aov", "cr"] if c in df.columns]
    if optional_cols:
        summary_parts.append(f"Extra metrics: {', '.join(optional_cols)}")
    st.markdown(" | ".join(summary_parts))
    st.dataframe(df, use_container_width=True, hide_index=True)

# ── Run Forecast ─────────────────────────────────────────────────────────────
if df is not None:
    n_hist_months = len(df)
    if use_v4:
        if n_hist_months >= 24:
            st.info(f"**Model selection:** Prophet (primary) + linear reference ({n_hist_months} months ≥ 24).")
        elif n_hist_months >= 12:
            st.info(f"**Model selection:** Holt's Exponential Smoothing — Prophet available but flagged low-confidence ({n_hist_months} months, 12–23).")
        else:
            st.warning(f"**Model selection:** Linear regression only ({n_hist_months} months < 12 — seasonality cannot be detected). Upload more historical data for better forecasts.")

    can_run = use_v4 or bool(methods)
    if not can_run:
        st.warning("Please select at least one forecasting method or enable v4 auto-gating.")
    elif st.button("Generate Forecast", type="primary", key="hist_run"):
        with st.spinner("Running historical forecast..."):
            if use_v4:
                seasonality = st.session_state.get("seasonality")
                result = run_historical_forecast_v4(
                    df, months,
                    changepoint_prior_scale=changepoint_prior_scale,
                    alpha=alpha, confidence=confidence,
                    seasonality=seasonality,
                )
                # Surface method info
                chosen = result.attrs.get("chosen_method", "unknown")
                reason = result.attrs.get("method_reason", "")
                prophet_ok = result.attrs.get("prophet_available", False)
                if not prophet_ok and chosen == "prophet":
                    st.warning("Prophet unavailable — fell back to linear. Install `prophet` for full capability.")
                # Adapt methods list so the chart helper knows what to render
                active_methods = ["Linear Regression"]
                if "exponential_smoothing" in result.columns:
                    active_methods.append("Exponential Smoothing")
                if "prophet" in result.columns:
                    active_methods.append("Prophet")
            else:
                result = run_historical_forecast(df, months, methods, sma_window, alpha, confidence)
                active_methods = methods
            growth = calculate_growth_rates(df["traffic"])

            st.session_state["hist_results"] = {
                "result": result,
                "growth": growth,
                "methods": active_methods,
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
    # Check if we have extended metrics
    has_extended = any(c in result.columns for c in ["revenue_forecast", "transactions_forecast", "aov_forecast", "cr_forecast"])
    if has_extended:
        tab_names.append("\U0001f4c8 Full Metrics")
    if r["enable_revenue"]:
        tab_names.append("\U0001f4b0 Revenue Analysis")
    tab_names.append("\U0001f4e5 Export")

    tabs = st.tabs(tab_names)
    tab_idx = 0
    sym = CURRENCY_SYMBOLS.get(r["currency"], "$")

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

        # Extra KPI cards for extended metrics
        if has_extended:
            ext_cols = st.columns(4)
            col_idx = 0
            if "revenue_forecast" in result.columns:
                end_rev = forecast_rows["revenue_forecast"].iloc[-1]
                ext_cols[col_idx].metric("Projected Revenue", f"{sym}{end_rev:,.0f}")
                col_idx += 1
            if "transactions_forecast" in result.columns:
                end_trans = forecast_rows["transactions_forecast"].iloc[-1]
                ext_cols[col_idx].metric("Projected Transactions", f"{int(end_trans):,}")
                col_idx += 1
            if "aov_forecast" in result.columns:
                end_aov = forecast_rows["aov_forecast"].iloc[-1]
                ext_cols[col_idx].metric("Projected AOV", f"{sym}{end_aov:,.2f}")
                col_idx += 1
            if "cr_forecast" in result.columns:
                end_cr = forecast_rows["cr_forecast"].iloc[-1]
                ext_cols[col_idx].metric("Projected CR%", f"{end_cr:.2f}%")

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

    # ── Tab: Full Metrics ────────────────────────────────────────────────
    if has_extended:
        with tabs[tab_idx]:
            tab_idx += 1

            traffic_col = "linear" if "linear" in result.columns else (
                "exponential_smoothing" if "exponential_smoothing" in result.columns else "sma"
            )
            metrics_df = build_full_metrics_table(result, traffic_col)

            st.subheader("Complete Metrics Dashboard")
            st.caption("All available metrics with YoY comparisons. Forecasted values fill in where actuals are unavailable.")

            # Format for display
            display_metrics = metrics_df.drop(columns=["is_forecast"], errors="ignore").copy()
            display_metrics["Month"] = pd.to_datetime(display_metrics["Month"]).dt.strftime("%b %Y")
            st.dataframe(display_metrics, use_container_width=True, hide_index=True, height=600)

            # Download full metrics
            st.download_button(
                "Download Full Metrics CSV",
                to_csv(metrics_df.drop(columns=["is_forecast"], errors="ignore")),
                "full-metrics.csv",
                "text/csv",
                key="hist_full_metrics_dl",
            )

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
            total_trans = forecast_only["transactions"].sum()

            c1, c2, c3 = st.columns(3)
            c1.metric("Peak Monthly Revenue", f"{sym}{peak_rev:,.2f}")
            c2.metric("Total Revenue (Forecast Period)", f"{sym}{total_rev:,.2f}")
            c3.metric("Total Transactions", f"{total_trans:,}")

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
