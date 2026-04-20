import calendar

import pandas as pd
import streamlit as st

from engine.assumptions import get_assumption, initialise_assumptions
from engine.revenue_engine import CURRENCY_SYMBOLS
from utils.assumptions_panel import render_assumptions_banner
from utils.forecast_grid import build_seo_forecast_grid
from utils.session import ASSUMPTIONS, COMB_RESULTS, HIST_RESULTS, POS_RESULT
from utils.sidebar import render_ai_settings

st.header("Forecast Grid Export")
st.caption("Download the SEO row for the multi-channel plan in GAZMAN format.")
render_ai_settings()

store = st.session_state.setdefault(ASSUMPTIONS, {})
initialise_assumptions(store)
render_assumptions_banner(store)

# -- Source selector ----------------------------------------------------------
sources = []
if COMB_RESULTS in st.session_state:
    sources.append("Combined Forecast")
if POS_RESULT in st.session_state:
    sources.append("Positional Forecast")
if HIST_RESULTS in st.session_state:
    sources.append("Historical Forecast")

if not sources:
    st.info("Run a **Positional**, **Historical**, or **Combined** forecast first.")
    st.stop()

source = st.selectbox("Forecast Source", sources, key="grid_source")

# -- Scenario selector for band-aware sources --------------------------------
scenario_options = {"Conservative (P10)": "p10", "Median (P50)": "p50", "Aggressive (P90)": "p90"}
has_bands = False

if source == "Combined Forecast":
    comb_df = st.session_state[COMB_RESULTS]["combined_df"]
    has_bands = "combined_p10" in comb_df.columns
elif source == "Positional Forecast":
    pos_monthly = st.session_state[POS_RESULT]["monthly"]
    has_bands = "traffic_p10" in pos_monthly.columns

if has_bands:
    scenario_label = st.selectbox("Scenario", list(scenario_options.keys()), index=1, key="grid_scenario")
    scenario = scenario_options[scenario_label]
else:
    scenario = "p50"

# -- Extract monthly traffic based on source ----------------------------------
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
    st.stop()

n_months = len(monthly_traffic)

# -- Sidebar settings ---------------------------------------------------------
st.sidebar.header("Grid Settings")

# Defaults from assumptions store (populated from GA4 detection if data was uploaded)
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
currency = st.sidebar.selectbox(
    "Currency", _cur_options, index=_cur_idx, key="grid_currency"
)
sym = CURRENCY_SYMBOLS.get(currency, "$")
client_name = st.sidebar.text_input("Client Name", value="", key="grid_client")
fy_label = st.sidebar.text_input("FY Label", value="FY26", key="grid_fy")

month_names = [calendar.month_name[m] for m in range(1, 13)]
start_month = st.sidebar.selectbox(
    "Start Month",
    range(1, 13),
    index=6,  # July = index 6 (0-based for list, month 7)
    format_func=lambda m: calendar.month_name[m],
    key="grid_start_month",
)

# -- Compute transactions and revenue ----------------------------------------
cvr_decimal = cvr / 100.0
monthly_transactions = [round(t * cvr_decimal) for t in monthly_traffic]
monthly_revenue = [round(t * aov, 2) for t in monthly_transactions]

# -- KPI cards ----------------------------------------------------------------
total_traffic = sum(monthly_traffic)
total_transactions = sum(monthly_transactions)
total_revenue = sum(monthly_revenue)

c1, c2, c3 = st.columns(3)
c1.metric("Year 1 Traffic", f"{total_traffic:,.0f}")
c2.metric("Year 1 Transactions", f"{total_transactions:,.0f}")
c3.metric("Year 1 Revenue", f"{sym}{total_revenue:,.2f}")

# -- Preview table ------------------------------------------------------------
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

# -- Download buttons ---------------------------------------------------------
st.divider()

xlsx_buf = build_seo_forecast_grid(
    monthly_traffic=monthly_traffic,
    monthly_transactions=[float(t) for t in monthly_transactions],
    monthly_revenue=[float(r) for r in monthly_revenue],
    months=n_months,
    client_name=client_name,
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
