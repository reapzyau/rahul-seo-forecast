import calendar

import streamlit as st
import pandas as pd

from engine.revenue_engine import add_revenue, CURRENCY_SYMBOLS
from utils.forecast_grid import build_seo_forecast_grid
from utils.export import to_csv
from utils.sidebar import render_ai_settings

st.header("Forecast Grid Export")
st.caption("Download the SEO row for the multi-channel plan in GAZMAN format.")
render_ai_settings()

# -- Source selector ----------------------------------------------------------
sources = []
if "comb_results" in st.session_state:
    sources.append("Combined Forecast")
if "pos_result" in st.session_state:
    sources.append("Positional Forecast")
if "hist_results" in st.session_state:
    sources.append("Historical Forecast")

if not sources:
    st.info("Run a **Positional**, **Historical**, or **Combined** forecast first.")
    st.stop()

source = st.selectbox("Forecast Source", sources, key="grid_source")

# -- Extract monthly traffic based on source ----------------------------------
monthly_traffic = []

if source == "Combined Forecast":
    comb = st.session_state["comb_results"]
    combined_df = comb["combined_df"]
    forecast_rows = combined_df[combined_df["is_forecast"]]
    monthly_traffic = forecast_rows["combined"].tolist()

elif source == "Positional Forecast":
    pos = st.session_state["pos_result"]
    pos_monthly = pos["monthly"]
    monthly_traffic = pos_monthly["traffic"].tolist()

elif source == "Historical Forecast":
    hist = st.session_state["hist_results"]
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

# Auto-populate CVR and AOV from ga4_df if available
ga4_df = st.session_state.get("ga4_df")
default_cvr = 2.5
default_aov = 100.0
if ga4_df is not None:
    if "transactions" in ga4_df.columns and ga4_df["traffic"].sum() > 0:
        default_cvr = round(
            (ga4_df["transactions"].sum() / ga4_df["traffic"].sum()) * 100, 2
        )
    if "aov" in ga4_df.columns and ga4_df["aov"].notna().any():
        default_aov = round(float(ga4_df["aov"].dropna().mean()), 2)

cvr = st.sidebar.number_input(
    "Conversion Rate (%)", 0.1, 100.0, default_cvr, step=0.1, key="grid_cvr"
)
aov = st.sidebar.number_input(
    "Average Order Value", 1.0, 100000.0, default_aov, step=10.0, key="grid_aov"
)
currency = st.sidebar.selectbox(
    "Currency", list(CURRENCY_SYMBOLS.keys()), key="grid_currency"
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
