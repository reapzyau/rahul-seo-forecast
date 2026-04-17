import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from engine.seasonality_engine import (
    apply_seasonality,
    build_campaign_list,
    DEFAULT_SEASONALITY,
)
from engine.revenue_engine import add_dynamic_revenue, CURRENCY_SYMBOLS
from utils.export import to_csv

st.header("Seasonality & Campaign Modifiers")
st.caption("Apply monthly seasonal patterns and campaign events to your traffic forecast.")

# ── Check for forecast data ──────────────────────────────────────────────────
kw_results = st.session_state.get("kw_results")
hist_results = st.session_state.get("hist_results")
comb_results = st.session_state.get("comb_results")

if kw_results is None and hist_results is None and comb_results is None:
    st.info("Run a **Keyword Forecast**, **Historical Forecast**, or **Combined Forecast** first to generate base traffic data.")
    st.stop()

# ── Source selection (Combined first) ─────────────────────────────────────
sources = []
if comb_results:
    sources.append("Combined Forecast")
if kw_results:
    sources.append("Keyword Forecast")
if hist_results:
    sources.append("Historical Forecast")

source = st.selectbox("Traffic Source", sources, key="season_source")

if source == "Combined Forecast":
    st.success("Using Combined forecast (baseline + positional + new content \u2212 decay \u2212 AIO erosion).")
else:
    st.warning("Using a single-stream source. Run **Combined Forecast** for the most complete view.")

if source == "Keyword Forecast" and kw_results:
    monthly_df = kw_results["monthly_df"].copy()
elif source == "Historical Forecast" and hist_results:
    result = hist_results["result"]
    forecast_only = result[result["is_forecast"]].copy()
    best_col = "linear" if "linear" in result.columns else (
        "exponential_smoothing" if "exponential_smoothing" in result.columns else "sma"
    )
    monthly_df = forecast_only[["date", best_col]].rename(columns={best_col: "traffic"}).copy()
    monthly_df["month"] = range(1, len(monthly_df) + 1)
elif source == "Combined Forecast" and comb_results:
    combined_df = comb_results["combined_df"]
    forecast_only = combined_df[combined_df["is_forecast"]].copy()
    monthly_df = forecast_only[["date", "combined"]].rename(columns={"combined": "traffic"}).copy()
    monthly_df["month"] = range(1, len(monthly_df) + 1)
else:
    st.error("No forecast data available.")
    st.stop()

# ── Monthly Modifiers (main body, editable table) ─────────────────────────────
st.subheader("Monthly Modifiers")
st.caption("Edit the traffic modifier for each month. Positive = boost, negative = reduction.")

modifier_rows = []
for m in range(1, 13):
    d = DEFAULT_SEASONALITY[m]
    modifier_rows.append({
        "Month": d["label"].split(" (")[0],
        "Description": d["label"],
        "Traffic Modifier (%)": round(d["traffic_mod"] * 100, 1),
    })
modifier_defaults = pd.DataFrame(modifier_rows)

edited_modifiers = st.data_editor(
    modifier_defaults,
    column_config={
        "Month": st.column_config.TextColumn(disabled=True, width="small"),
        "Description": st.column_config.TextColumn(disabled=True),
        "Traffic Modifier (%)": st.column_config.NumberColumn(
            min_value=-50.0, max_value=100.0, step=0.5, format="%.1f",
        ),
    },
    hide_index=True,
    use_container_width=True,
    key="season_modifier_editor",
)

custom_seasonality = {}
for m in range(1, 13):
    default = DEFAULT_SEASONALITY[m]
    mod_pct = float(edited_modifiers.iloc[m - 1]["Traffic Modifier (%)"])
    custom_seasonality[m] = {
        "label": default["label"],
        "traffic_mod": mod_pct / 100,
        "cr_mod": default["cr_mod"],
        "aov_mod": default["aov_mod"],
    }

# ── Sidebar: Campaign Events & Revenue ────────────────────────────────────────
st.sidebar.header("Seasonality Settings")
st.sidebar.subheader("Campaign Events")
st.sidebar.caption("Format: Name | Month | Traffic Boost | CR Boost | AOV Boost")

campaign_text = st.sidebar.text_area(
    "Campaign Definitions",
    "GAZFRENZY | 11 | 0.20 | 0.10 | -0.05\nFather's Day | 9 | 0.15 | 0.08 | 0.03\nChristmas Sale | 12 | 0.10 | 0.05 | 0.08",
    height=120,
    key="season_campaigns",
)
campaigns = build_campaign_list(campaign_text)

# ── Revenue settings ─────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
base_cr = st.sidebar.number_input("Base CR%", 0.1, 20.0, 2.5, step=0.1, key="season_cr")
base_aov = st.sidebar.number_input("Base AOV ($)", 1.0, 1000.0, 150.0, step=5.0, key="season_aov")
currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="season_cur")

st.divider()

# ── Apply seasonality ────────────────────────────────────────────────────────
if st.button("Apply Seasonality", type="primary", key="season_apply"):
    with st.spinner("Applying seasonal modifiers..."):
        adjusted = apply_seasonality(monthly_df, custom_seasonality, campaigns)

        # Build dynamic CR and AOV series
        cr_series = [base_cr * (1 + row["cr_modifier"]) for _, row in adjusted.iterrows()]
        aov_series = [base_aov * (1 + row["aov_modifier"]) for _, row in adjusted.iterrows()]

        adjusted = add_dynamic_revenue(adjusted, cr_series, aov_series, currency)

        st.session_state["season_results"] = adjusted

# ── Display Results ──────────────────────────────────────────────────────────
if "season_results" in st.session_state:
    df = st.session_state["season_results"]
    sym = CURRENCY_SYMBOLS.get(currency, "$")

    tab1, tab2, tab3, tab4 = st.tabs([
        "\U0001f4ca Adjusted Forecast",
        "\U0001f4c5 Monthly Breakdown",
        "\U0001f4b0 Revenue Forecast",
        "\U0001f4e5 Export",
    ])

    with tab1:
        # KPIs
        total_base = df["traffic_base"].sum()
        total_adjusted = df["traffic"].sum()
        uplift = ((total_adjusted - total_base) / total_base * 100) if total_base > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Base Traffic", f"{total_base:,.0f}")
        c2.metric("Adjusted Traffic", f"{total_adjusted:,.0f}")
        c3.metric("Seasonal Uplift", f"{uplift:+.1f}%")
        c4.metric("Total Revenue", f"{sym}{df['revenue'].sum():,.0f}")

        # Chart: base vs adjusted
        fig = go.Figure()
        x_col = "date" if "date" in df.columns else "month"
        fig.add_trace(go.Scatter(
            x=df[x_col], y=df["traffic_base"], mode="lines",
            name="Base Forecast", line=dict(color="#94A3B8", dash="dash", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=df[x_col], y=df["traffic"], mode="lines+markers",
            name="Seasonally Adjusted", line=dict(color="#2563EB", width=3),
            fill="tonexty", fillcolor="rgba(37, 99, 235, 0.1)",
        ))
        fig.update_layout(
            title="Base vs Seasonally Adjusted Traffic",
            xaxis_title="Month", yaxis_title="Traffic",
            plot_bgcolor="white", hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        display_cols = ["season_label", "traffic_base", "traffic_modifier", "traffic"]
        if "cr_used" in df.columns:
            display_cols.extend(["cr_used", "aov_used", "transactions", "revenue"])
        display_df = df[display_cols].copy()
        display_df.columns = [
            "Month / Event", "Base Traffic", "Modifier %", "Adjusted Traffic",
        ] + (["CR%", "AOV", "Transactions", "Revenue"] if "cr_used" in df.columns else [])
        if "Modifier %" in display_df.columns:
            display_df["Modifier %"] = (display_df["Modifier %"] * 100).round(1).astype(str) + "%"
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    with tab3:
        if "revenue" in df.columns:
            fig_rev = go.Figure()
            fig_rev.add_trace(go.Bar(
                x=df[x_col], y=df["revenue"],
                name="Revenue", marker_color="#22C55E",
            ))
            fig_rev.add_trace(go.Scatter(
                x=df[x_col], y=df["transactions"],
                name="Transactions", yaxis="y2",
                line=dict(color="#8B5CF6", width=2),
            ))
            fig_rev.update_layout(
                title="Monthly Revenue & Transactions",
                xaxis_title="Month",
                yaxis=dict(title=f"Revenue ({sym})"),
                yaxis2=dict(title="Transactions", overlaying="y", side="right"),
                plot_bgcolor="white", hovermode="x unified",
            )
            st.plotly_chart(fig_rev, use_container_width=True)

    with tab4:
        st.download_button(
            "Download Seasonality Forecast CSV",
            to_csv(df),
            "seasonality-forecast.csv",
            "text/csv",
        )
