import os

import pandas as pd
import streamlit as st

from engine.historical_engine import (
    calculate_growth_rates,
    detect_startup_period,
    run_historical_forecast,
    run_historical_forecast_v4,
    yoy_baseline,
)
from engine.revenue_engine import CURRENCY_SYMBOLS, add_revenue, build_full_metrics_table
from engine.seasonality_engine import derive_seasonality_from_baseline
from engine.v5.anomaly_detector import apply_overrides, detect_baseline_anomalies
from utils.chart_builder import historical_comparison_chart, revenue_projection_chart
from utils.data_loader import load_traffic
from utils.export import to_csv, to_html_report, traffic_template_csv
from utils.metric_cards import KPICard, render_kpi_row
from utils.page_base import setup_page
from utils.session import HIST_N_MONTHS, HIST_RESULTS, SCENARIO_RESULTS, SEASONALITY

setup_page(
    "Historical Forecast",
    "Project traffic from your past organic data using statistical models.",
    show_assumptions_banner=False,
)

if SCENARIO_RESULTS not in st.session_state:
    st.info(
        "💡 **Want to compare three scenarios at once?** "
        "Use the **Strategy** page to run a Historical baseline plus three scenario uplifts in one click. "
        "This page is for deep-dive analysis on a single forecast configuration."
    )
else:
    st.success(
        "✅ Three scenarios already run via Strategy. "
        "This page lets you drill into a single forecast configuration in detail. "
        "Download the 3-scenario xlsx from **Deliverables** or the Strategy page."
    )

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Historical Forecast Settings")

months = st.sidebar.slider("Forecast Horizon (months)", 3, 36, 12, key="hist_months")

# ── Smart defaults (collapsible) ──────────────────────────────────────────────
_n_hist_for_default = st.session_state.get(HIST_N_MONTHS, 0)
_yoy_default = _n_hist_for_default >= 12

with st.sidebar.expander("Smart defaults", expanded=False):
    st.caption("These are automatically chosen based on your data. Override if needed.")
    baseline_mode = st.radio(
        "Baseline mode",
        ["YoY replay (recommended)", "Linear trend (Holt's)"],
        index=0 if _yoy_default else 1,
        help=(
            "YoY replay: each forecast month's baseline equals the same calendar month "
            "from the prior year. Recommended when ≥12 months of history is available — "
            "avoids compounding startup-ramp artefacts into the forecast. "
            "Linear trend (Holt's): double exponential smoothing on the full series."
        ),
        key="hist_baseline_mode",
    )
    use_yoy = baseline_mode.startswith("YoY")
    if use_yoy and not _yoy_default:
        st.warning("YoY mode needs ≥12 months of GA4 history. Upload more data or switch to Linear trend.")

st.sidebar.divider()
st.sidebar.subheader("Advanced")
use_v4 = st.sidebar.checkbox(
    "Auto-select model based on data length",
    value=True,
    help="Uses Prophet for ≥24 months, Holt's for 12–23, linear for <12. Recommended.",
    key="hist_use_v4",
)

# Infer prophet-active from previous render's data length (session state)
_n_hist = st.session_state.get(HIST_N_MONTHS, 0)
_prophet_active = use_v4 and _n_hist >= 24

# V4-specific: trend flexibility (only meaningful when Prophet is actually active)
if _prophet_active:
    changepoint_prior_scale = st.sidebar.slider(
        "Trend flexibility",
        0.001, 0.5, 0.05, step=0.005,
        key="hist_changepoint",
        help="Higher = more flexible trend (Prophet only). 0.05 is recommended.",
    )
else:
    changepoint_prior_scale = 0.05

# Legacy controls — only shown when v4 is off
if not use_v4:
    with st.sidebar.expander("Legacy model settings", expanded=False):
        methods = st.multiselect(
            "Forecasting Method",
            ["Linear Regression", "Exponential Smoothing", "Simple Moving Average"],
            default=["Linear Regression", "Exponential Smoothing"],
            key="hist_methods",
        )
        sma_window = st.slider("SMA Window (months)", 2, 6, 3, key="hist_sma_window")
        alpha = st.slider("Smoothing Alpha", 0.1, 0.9, 0.3, step=0.05, key="hist_alpha")
        confidence = st.slider("Confidence Band (%)", 5, 30, 15, key="hist_confidence")
else:
    methods = ["Linear Regression"]
    sma_window = 3
    alpha = 0.3
    confidence = 15

with st.sidebar.expander("Revenue projection", expanded=False):
    enable_revenue = st.checkbox("Enable revenue projection", key="hist_rev")
    cvr = st.number_input(
        "Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1,
        key="hist_cvr", disabled=not enable_revenue,
    )
    aov = st.number_input(
        "Average Order Value", 1.0, 100000.0, 100.0, step=10.0,
        key="hist_aov", disabled=not enable_revenue,
    )
    currency = st.selectbox(
        "Currency", list(CURRENCY_SYMBOLS.keys()),
        key="hist_cur", disabled=not enable_revenue,
    )

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
    st.session_state[HIST_N_MONTHS] = len(df)
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

    # Startup-period warning
    if detect_startup_period(df["traffic"]):
        st.warning(
            "**Startup ramp detected** — the first 6 months of your GA4 data are substantially "
            "lower than the recent 6 months. Holt's smoothing will pick up this ramp as a growth "
            "trend, inflating the forecast. **YoY replay mode is strongly recommended.**"
        )

    # ── Pre-compute baseline lookup + anomaly detection (YoY mode only) ──────
    # Done BEFORE the button so the quality-check panel can block the run.
    _anomaly_flags: list = []
    _baseline_lookup_raw: dict = {}
    _forecast_dates_yoy = None

    if use_yoy and n_hist_months >= 12:
        _last_date = df["date"].max()
        _forecast_dates_yoy = pd.date_range(
            start=_last_date + pd.DateOffset(months=1),
            periods=months, freq="MS",
        )
        _baseline_lookup_raw = yoy_baseline(df, _forecast_dates_yoy)
        _anomaly_flags = detect_baseline_anomalies(df, _baseline_lookup_raw)

        # Invalidate resolved state when flags change (e.g. new file uploaded)
        _flags_fingerprint = str([
            (f["source_month"], f["flag_type"]) for f in _anomaly_flags
        ])
        if st.session_state.get("_anomaly_flags_key") != _flags_fingerprint:
            st.session_state["anomaly_flags_resolved"] = False
            st.session_state["anomaly_overrides"] = {}
            st.session_state["_anomaly_flags_key"] = _flags_fingerprint

        st.session_state["anomaly_flags"] = _anomaly_flags
        st.session_state["baseline_lookup_raw"] = _baseline_lookup_raw

        # ── Baseline Quality Check panel ──────────────────────────────────────
        st.subheader("Baseline Quality Check")
        st.caption(
            "Each forecast month inherits traffic from the same calendar month one year prior. "
            "Anomalous source months silently propagate into the forecast — review any flags below. "
            "YoY-confirmed flags (two years of data) are high-confidence. "
            "Surrounding-window flags (no T-2 data, or T-2 looked like a startup period) "
            "are lower-confidence and should be reviewed in context."
        )

        if not _anomaly_flags:
            st.success("✓ No anomalies detected in YoY-source months. Baseline is clean.")
            st.session_state["anomaly_flags_resolved"] = True
        else:
            st.session_state.setdefault("anomaly_overrides", {})
            _overrides_ui: dict = {}

            for _flag in _anomaly_flags:
                _is_yoy = _flag["comparison_basis"] == "yoy"
                _flag_label = _flag["flag_type"].replace("_", " ").title()
                _src_key = str(_flag["source_month"])

                if _is_yoy:
                    st.error(
                        f"**{_flag_label}** — {_flag['source_month'].strftime('%b %Y')} "
                        f"(YoY-confirmed: two years of data available)"
                    )
                else:
                    st.warning(
                        f"**{_flag_label}** — {_flag['source_month'].strftime('%b %Y')} "
                        f"(local context only — lower confidence)"
                    )

                _col1, _col2 = st.columns([3, 2])
                with _col1:
                    st.write(_flag["rationale"])
                with _col2:
                    _choice = st.radio(
                        f"Action for {_flag['source_month'].strftime('%b %Y')}",
                        options=["Accept original", "Replace with suggested", "Custom value"],
                        key=f"flag_action_{_src_key}",
                        horizontal=False,
                    )
                    if _choice == "Accept original":
                        _overrides_ui[_flag["forecast_month"]] = "accept"
                    elif _choice == "Replace with suggested":
                        _overrides_ui[_flag["forecast_month"]] = _flag["suggested_replacement"]
                        st.caption(f"→ {_flag['suggested_replacement']:,} sessions")
                    else:
                        _custom = st.number_input(
                            "Custom value (sessions)",
                            min_value=0,
                            value=int(_flag["suggested_replacement"]),
                            key=f"flag_custom_{_src_key}",
                        )
                        _overrides_ui[_flag["forecast_month"]] = int(_custom)

                st.divider()

            if st.button("Confirm baseline decisions", type="primary", key="anomaly_confirm"):
                st.session_state["anomaly_overrides"] = _overrides_ui
                st.session_state["anomaly_flags_resolved"] = True
                st.rerun()

    can_run = use_v4 or bool(methods)
    if not can_run:
        st.warning("Please select at least one forecasting method or enable v4 auto-gating.")
    elif _anomaly_flags and not st.session_state.get("anomaly_flags_resolved"):
        st.error(
            f"⚠ {len(_anomaly_flags)} baseline anomaly flag(s) need review before running forecast. "
            "Confirm your decisions above to proceed."
        )
    elif st.button("Generate Forecast", type="primary", key="hist_run"):
        use_yoy_mode = st.session_state.get("hist_baseline_mode", "YoY replay (recommended)").startswith("YoY")
        with st.spinner("Running historical forecast..."):
            if use_yoy_mode and n_hist_months >= 12:
                # Apply user overrides to the pre-computed baseline lookup
                _overrides = st.session_state.get("anomaly_overrides", {})
                baseline_lookup = apply_overrides(_baseline_lookup_raw, _overrides)
                forecast_dates = _forecast_dates_yoy
                # Store derived seasonality in session for downstream engines
                derived_season = derive_seasonality_from_baseline(baseline_lookup)
                st.session_state[SEASONALITY] = derived_season
                st.session_state["yoy_baseline_lookup"] = baseline_lookup
                # Build a result df from the baseline lookup for display
                result_rows = []
                for _i, row in df.iterrows():
                    result_rows.append({
                        "date": row["date"],
                        "actual": int(row["traffic"]),
                        "linear": int(row["traffic"]),
                        "linear_upper": int(row["traffic"]),
                        "linear_lower": int(row["traffic"]),
                        "is_forecast": False,
                        "primary_method": "yoy_replay",
                    })
                for fdate, bdata in sorted(baseline_lookup.items()):
                    result_rows.append({
                        "date": fdate,
                        "actual": None,
                        "linear": bdata["traffic"],
                        "linear_upper": int(bdata["traffic"] * 1.10),
                        "linear_lower": int(bdata["traffic"] * 0.90),
                        "is_forecast": True,
                        "primary_method": "yoy_replay",
                    })
                result = pd.DataFrame(result_rows)
                result.attrs["chosen_method"] = "yoy_replay"
                result.attrs["method_reason"] = f"YoY replay — each forecast month mirrors the same calendar month one year prior ({n_hist_months} months of history available)"
                result.attrs["prophet_available"] = False
                result.attrs["growth_rates"] = calculate_growth_rates(df["traffic"])
                active_methods = ["Linear Regression"]
                st.info(f"**Baseline mode:** YoY replay — {result.attrs['method_reason']}")
                st.session_state[HIST_RESULTS] = {
                    "result": result,
                    "growth": result.attrs["growth_rates"],
                    "methods": active_methods,
                    "enable_revenue": enable_revenue,
                    "currency": currency,
                    "cvr": cvr,
                    "aov": aov,
                    "raw_df": df,
                }
            elif use_v4:
                seasonality = st.session_state.get(SEASONALITY)
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

            # Save results (YoY mode saves inside its own branch above)
            if not (use_yoy_mode and n_hist_months >= 12):
                growth = calculate_growth_rates(df["traffic"])
                st.session_state[HIST_RESULTS] = {
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
if HIST_RESULTS in st.session_state:
    r = st.session_state[HIST_RESULTS]
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

        yoy_val = growth['latest_yoy']
        render_kpi_row([
            KPICard("Current Monthly Traffic", f"{current_traffic:,}"),
            KPICard("Projected End of Horizon", f"{int(end_traffic):,}"),
            KPICard(
                "Avg MoM Growth",
                f"{growth['avg_mom']:+.1f}%",
                delta=f"{growth['avg_mom']:+.1f}%",
                delta_color="normal",
            ),
            KPICard(
                "Latest YoY Growth",
                f"{yoy_val:+.1f}%" if yoy_val != 0 else "N/A",
                delta=f"{yoy_val:+.1f}%" if yoy_val != 0 else None,
                delta_color="normal",
            ),
        ])

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

st.divider()
st.caption(
    "**Looking for the three-scenario comparison?** "
    "The Strategy page runs Conservative / Moderate / Aggressive in one click and "
    "produces a four-sheet xlsx ready for client presentations. "
    "This deep-dive page is best for analysts tuning a single forecast configuration."
)
