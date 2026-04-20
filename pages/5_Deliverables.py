import calendar
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.assumptions import get_assumption
from engine.revenue_engine import CURRENCY_SYMBOLS
from engine.snapshot_engine import compare_to_actuals, load_snapshot, summarise_variance
from utils.chart_builder import _apply_layout
from utils.forecast_grid import build_seo_forecast_grid
from utils.page_base import setup_page
from utils.session import COMB_RESULTS, GA4_DF, HIST_RESULTS, POS_RESULT


def _render_variance(snapshot: dict, ga4_df: pd.DataFrame) -> None:
    st.subheader("Snapshot Metadata")
    meta_cols = st.columns(3)
    meta_cols[0].metric("Client", snapshot.get("client_name", "Unknown"))
    meta_cols[1].metric("Snapshot Date", snapshot.get("snapshot_date", "N/A")[:10])
    engine_versions = snapshot.get("engine_versions", {})
    meta_cols[2].metric("Engine Version", engine_versions.get("snapshot", "N/A"))

    comparison = compare_to_actuals(snapshot, ga4_df)

    if comparison.empty:
        st.warning("No overlapping months between forecast and actuals.")
        st.stop()
        return

    summary = summarise_variance(comparison)

    st.subheader("Variance Summary")
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Months Compared", summary["n_months_compared"])
    kpi_cols[1].metric("Mean Variance %", f"{summary['mean_variance_pct']:+.1f}%")
    kpi_cols[2].metric("Within P10-P90 Band", f"{summary['pct_within_band']:.0f}%")
    max_over = summary["max_overshoot_pct"]
    max_under = summary["max_undershoot_pct"]
    kpi_cols[3].metric("Max Over / Undershoot", f"+{max_over:.1f}% / {max_under:.1f}%")

    st.subheader("Forecast vs Actuals")
    fig = go.Figure()
    has_bands = (
        comparison["forecast_p10"].notna().any() and comparison["forecast_p90"].notna().any()
    )
    if has_bands:
        fig.add_trace(go.Scatter(
            x=comparison["date"], y=comparison["forecast_p90"],
            mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=comparison["date"], y=comparison["forecast_p10"],
            mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(37, 99, 235, 0.10)",
            name="P10-P90 Band", hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=comparison["date"], y=comparison["forecast_p50"],
        mode="lines", name="Forecast P50",
        line=dict(color="#2563EB", width=2, dash="dash"),
        hovertemplate="%{x|%b %Y}<br>Forecast P50: %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=comparison["date"], y=comparison["actual"],
        mode="lines+markers", name="Actual Traffic",
        line=dict(color="#0F172A", width=3),
        hovertemplate="%{x|%b %Y}<br>Actual: %{y:,.0f}<extra></extra>",
    ))
    fig = _apply_layout(fig, "Forecast vs Actual Traffic", "Date", "Monthly Organic Sessions")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly Comparison")
    display_df = comparison.copy()
    display_df["date"] = display_df["date"].dt.strftime("%b %Y")
    display_df = display_df.rename(columns={
        "date": "Month", "forecast_p10": "Forecast P10", "forecast_p50": "Forecast P50",
        "forecast_p90": "Forecast P90", "actual": "Actual",
        "variance": "Variance", "variance_pct": "Variance %", "within_band": "Within Band",
    })
    format_cols = ["Forecast P10", "Forecast P50", "Forecast P90", "Actual", "Variance"]
    for col in format_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "-")
    display_df["Variance %"] = display_df["Variance %"].apply(lambda v: f"{v:+.1f}%")
    display_df["Within Band"] = display_df["Within Band"].map({True: "Yes", False: "No"})

    def _highlight_variance(row):
        styles = [""] * len(row)
        var_idx = row.index.get_loc("Variance %")
        band_idx = row.index.get_loc("Within Band")
        var_str = row["Variance %"]
        try:
            var_val = float(var_str.replace("%", "").replace("+", ""))
        except (ValueError, AttributeError):
            return styles
        if abs(var_val) > 20:
            styles[var_idx] = "background-color: #FEE2E2; color: #991B1B"
        elif abs(var_val) > 10:
            styles[var_idx] = "background-color: #FEF3C7; color: #92400E"
        else:
            styles[var_idx] = "background-color: #DCFCE7; color: #166534"
        styles[band_idx] = (
            "background-color: #FEE2E2; color: #991B1B"
            if row["Within Band"] == "No"
            else "background-color: #DCFCE7; color: #166534"
        )
        return styles

    st.dataframe(
        display_df.style.apply(_highlight_variance, axis=1),
        use_container_width=True, hide_index=True,
    )

    st.subheader("Recommendations")
    mean_var = summary["mean_variance_pct"]
    pct_within = summary["pct_within_band"]
    recommendations = []
    if mean_var > 15:
        recommendations.append(
            "Forecast was consistently over-optimistic — consider reducing "
            "effort level or using Conservative scenario."
        )
    if mean_var < -15:
        recommendations.append("Forecast was too conservative — actuals exceeded projections.")
    if pct_within >= 80:
        recommendations.append("Good calibration — 80%+ of actuals fell within the predicted range.")
    if pct_within < 50:
        recommendations.append(
            "Poor calibration — consider widening bands or re-evaluating assumptions."
        )
    if not recommendations:
        recommendations.append("Forecast calibration is within acceptable range. Continue monitoring.")
    for rec in recommendations:
        st.info(rec)


# ── Page header ───────────────────────────────────────────────────────────────
store = setup_page(
    "Deliverables",
    "Export the forecast grid, grade past forecasts, and review methodology.",
)

# ── Sidebar: Grid Export Settings ─────────────────────────────────────────────
st.sidebar.header("Grid Export Settings")

default_cvr = float(get_assumption(store, "blended_cr_pct"))
default_aov = float(get_assumption(store, "aov"))
default_cur = str(get_assumption(store, "currency"))

cvr = st.sidebar.number_input(
    "Conversion Rate (%)", 0.1, 100.0, default_cvr, step=0.1, key="grid_cvr"
)
aov = st.sidebar.number_input(
    "Average Order Value", 1.0, 100000.0, default_aov, step=10.0, key="grid_aov"
)
_cur_options = list(CURRENCY_SYMBOLS.keys())
_cur_idx = _cur_options.index(default_cur) if default_cur in _cur_options else 0
currency = st.sidebar.selectbox("Currency", _cur_options, index=_cur_idx, key="grid_currency")
sym = CURRENCY_SYMBOLS.get(currency, "$")
grid_client = st.sidebar.text_input("Client Name", value="", key="grid_client")
fy_label = st.sidebar.text_input("FY Label", value="FY26", key="grid_fy")
start_month = st.sidebar.selectbox(
    "Start Month", range(1, 13), index=6,
    format_func=lambda m: calendar.month_name[m], key="grid_start_month",
)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_grid, tab_variance, tab_methodology = st.tabs([
    "\U0001f4e5 Forecast Grid",
    "\U0001f4ca Variance Analysis",
    "\U0001f4d6 Methodology",
])

# ── Tab: Forecast Grid ────────────────────────────────────────────────────────
with tab_grid:
    sources = []
    if COMB_RESULTS in st.session_state:
        sources.append("Combined Forecast")
    if POS_RESULT in st.session_state:
        sources.append("Positional Forecast")
    if HIST_RESULTS in st.session_state:
        sources.append("Historical Forecast")

    if not sources:
        st.info("Run a **Positional**, **Historical**, or **Combined** forecast first.")
    else:
        source = st.selectbox("Forecast Source", sources, key="grid_source")

        scenario_options = {"Conservative (P10)": "p10", "Median (P50)": "p50", "Aggressive (P90)": "p90"}
        has_bands = False

        if source == "Combined Forecast":
            comb_df = st.session_state[COMB_RESULTS]["combined_df"]
            has_bands = "combined_p10" in comb_df.columns
        elif source == "Positional Forecast":
            pos_monthly = st.session_state[POS_RESULT]["monthly"]
            has_bands = "traffic_p10" in pos_monthly.columns

        if has_bands:
            scenario_label = st.selectbox(
                "Scenario", list(scenario_options.keys()), index=1, key="grid_scenario"
            )
            scenario = scenario_options[scenario_label]
        else:
            scenario = "p50"

        monthly_traffic = []
        if source == "Combined Forecast":
            comb = st.session_state[COMB_RESULTS]
            combined_df = comb["combined_df"]
            forecast_rows = combined_df[combined_df["is_forecast"]]
            col = f"combined_{scenario}" if f"combined_{scenario}" in forecast_rows.columns else "combined"
            monthly_traffic = forecast_rows[col].tolist()
        elif source == "Positional Forecast":
            pos = st.session_state[POS_RESULT]
            pos_monthly = pos["monthly"]
            col = f"traffic_{scenario}" if f"traffic_{scenario}" in pos_monthly.columns else "traffic"
            monthly_traffic = pos_monthly[col].tolist()
        elif source == "Historical Forecast":
            hist = st.session_state[HIST_RESULTS]
            result = hist["result"]
            forecast_rows = result[result["is_forecast"]]
            best_col = "linear" if "linear" in result.columns else (
                "exponential_smoothing" if "exponential_smoothing" in result.columns else "sma"
            )
            monthly_traffic = forecast_rows[best_col].tolist()

        if not monthly_traffic:
            st.warning("The selected forecast source contains no forecast data.")
        else:
            n_months = len(monthly_traffic)
            cvr_decimal = cvr / 100.0
            monthly_transactions = [round(t * cvr_decimal) for t in monthly_traffic]
            monthly_revenue = [round(t * aov, 2) for t in monthly_transactions]

            total_traffic = sum(monthly_traffic)
            total_transactions = sum(monthly_transactions)
            total_revenue = sum(monthly_revenue)

            c1, c2, c3 = st.columns(3)
            c1.metric("Year 1 Traffic", f"{total_traffic:,.0f}")
            c2.metric("Year 1 Transactions", f"{total_transactions:,.0f}")
            c3.metric("Year 1 Revenue", f"{sym}{total_revenue:,.2f}")

            st.subheader("Monthly Preview")
            preview_data = {
                "Month": [
                    calendar.month_abbr[(start_month - 1 + i) % 12 + 1]
                    for i in range(n_months)
                ],
                "Traffic": [f"{t:,.0f}" for t in monthly_traffic],
                "Transactions": [f"{t:,}" for t in monthly_transactions],
                "Revenue": [f"{sym}{r:,.2f}" for r in monthly_revenue],
            }
            preview_df = pd.DataFrame(preview_data)
            st.dataframe(preview_df, use_container_width=True, hide_index=True)

            st.divider()
            xlsx_buf = build_seo_forecast_grid(
                monthly_traffic=monthly_traffic,
                monthly_transactions=[float(t) for t in monthly_transactions],
                monthly_revenue=[float(r) for r in monthly_revenue],
                months=n_months,
                client_name=grid_client,
                fy_label=fy_label,
                start_month=start_month,
            )
            st.download_button(
                "Download Forecast Grid XLSX",
                xlsx_buf,
                "seo-forecast-grid.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="grid_xlsx_dl",
            )
            st.caption("Matches the SEO row of the Pattern multi-channel plan.")

# ── Tab: Variance Analysis ────────────────────────────────────────────────────
with tab_variance:
    snapshot_file = st.file_uploader(
        "Upload a forecast snapshot JSON", type=["json"], key="variance_snapshot_upload",
    )
    ga4_df = st.session_state.get(GA4_DF)

    if ga4_df is None:
        st.info("Load GA4 data on the **Data Upload** page first.")
    elif snapshot_file is None:
        st.info("Upload a forecast snapshot JSON to begin the variance analysis.")
    else:
        try:
            snapshot = load_snapshot(snapshot_file.read())
        except Exception as exc:
            st.error(f"Could not parse snapshot file: {exc}")
        else:
            _render_variance(snapshot, ga4_df)

# ── Tab: Methodology ──────────────────────────────────────────────────────────
with tab_methodology:
    methodology_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "methodology.md"
    )
    try:
        with open(methodology_path) as f:
            st.markdown(f.read())
    except FileNotFoundError:
        st.error("Methodology document not found. Ensure methodology.md exists in the project root.")
