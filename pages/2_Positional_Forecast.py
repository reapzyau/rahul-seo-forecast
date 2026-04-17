import streamlit as st
import pandas as pd

from engine.positional_engine import run_positional_forecast, quick_wins
from engine.revenue_engine import add_revenue, CURRENCY_SYMBOLS
from utils.chart_builder import positional_uplift_chart, revenue_projection_chart
from utils.export import to_csv, to_html_report
from engine.constants import CTR_MODELS, FORECAST_SCENARIOS, TIER_COLORS
from utils.sidebar import render_ai_settings

st.header("Positional Forecast")
st.caption("Project uplift from moving existing keywords up the SERP.")

render_ai_settings()

# ── Data check ──────────────────────────────────────────────────────────────
kw_existing = st.session_state.get("kw_existing")
if kw_existing is None:
    st.info("Go to **Data Upload** first and load a SEMrush keyword export.")
    st.stop()

ga4_df = st.session_state.get("ga4_df")

# ── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("Positional Forecast Settings")

months = st.sidebar.slider("Forecast Horizon (months)", 6, 36, 12, key="pos_months")
effort = st.sidebar.selectbox(
    "Effort Level",
    ["light", "moderate", "aggressive"],
    index=1,
    key="pos_effort",
    help="How aggressively you plan to optimise existing content.",
)

st.sidebar.divider()
st.sidebar.subheader("Forecast Model")

ctr_model_name = st.sidebar.selectbox(
    "CTR Model",
    list(CTR_MODELS.keys()),
    key="pos_ctr_model",
    help="Standard = traditional CTR. AI-Adjusted = lower CTR reflecting AI Overviews impact.",
)
scenario_name = st.sidebar.selectbox(
    "Forecast Scenario",
    list(FORECAST_SCENARIOS.keys()),
    index=1,  # Default to Moderate
    key="pos_scenario",
    help="Conservative (0.7x), Moderate (1.0x), or Aggressive (1.3x) traffic multiplier.",
)

ctr_model = CTR_MODELS[ctr_model_name]
traffic_multiplier = FORECAST_SCENARIOS[scenario_name]["traffic_multiplier"]

st.sidebar.divider()
st.sidebar.subheader("AI Overview Penalty")

aio_penalty = st.sidebar.slider(
    "AIO CTR Penalty (%)", 0, 80, 40,
    key="pos_aio_penalty",
    help="Estimated CTR reduction for keywords affected by AI Overviews.",
)

st.sidebar.divider()
st.sidebar.subheader("GA4 Anchoring")

anchor_to_ga4 = False
if ga4_df is not None:
    anchor_to_ga4 = st.sidebar.checkbox(
        "Anchor to GA4 traffic",
        key="pos_anchor_ga4",
        help="Rescale SEMrush traffic estimates to match your real GA4 analytics.",
    )

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")

enable_revenue = st.sidebar.checkbox("Enable Revenue Projection", key="pos_rev")
cvr = st.sidebar.number_input(
    "Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1,
    key="pos_cvr", disabled=not enable_revenue,
)
aov = st.sidebar.number_input(
    "Average Order Value", 1.0, 100000.0, 100.0, step=10.0,
    key="pos_aov", disabled=not enable_revenue,
)
currency = st.sidebar.selectbox(
    "Currency", list(CURRENCY_SYMBOLS.keys()),
    key="pos_cur", disabled=not enable_revenue,
)

# ── Run Forecast ────────────────────────────────────────────────────────────
if st.button("Generate Forecast", type="primary", key="pos_run"):
    with st.spinner("Running positional forecast..."):
        ga4_baseline = None
        if anchor_to_ga4 and ga4_df is not None:
            ga4_baseline = int(ga4_df["traffic"].iloc[-1])

        kw_df, monthly = run_positional_forecast(
            kw_existing,
            months=months,
            effort=effort,
            ga4_baseline=ga4_baseline,
            ctr_model=ctr_model,
            traffic_multiplier=traffic_multiplier,
            seed=42,
        )

        # Revenue
        if enable_revenue and not monthly.empty:
            monthly = add_revenue(monthly, cvr, aov, currency)

        st.session_state["pos_result"] = {
            "keyword_df": kw_df,
            "monthly": monthly,
            "enable_revenue": enable_revenue,
            "currency": currency,
            "cvr": cvr,
            "aov": aov,
            "months": months,
            "effort": effort,
            "ctr_model_name": ctr_model_name,
            "scenario_name": scenario_name,
            "aio_penalty": aio_penalty,
        }

# ── Results ─────────────────────────────────────────────────────────────────
if "pos_result" in st.session_state:
    r = st.session_state["pos_result"]
    kw_df = r["keyword_df"]
    monthly = r["monthly"]

    if kw_df.empty:
        st.warning("No keywords with valid positions (1-100) found in the data.")
        st.stop()

    tab_names = ["\U0001f4c8 Projection", "\U0001f511 Per-Keyword Detail", "\u26a1 Quick Wins", "\U0001f4e5 Export"]
    tabs = st.tabs(tab_names)

    # ── Tab: Projection ─────────────────────────────────────────────────
    with tabs[0]:
        baseline = monthly["baseline"].iloc[0]
        projected_end = monthly["traffic"].iloc[-1]
        total_uplift = monthly["uplift"].iloc[-1]
        uplift_pct = (total_uplift / baseline * 100) if baseline > 0 else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Baseline Traffic", f"{baseline:,.0f}")
        c2.metric("Projected End Traffic", f"{projected_end:,.0f}")
        c3.metric("Total Uplift", f"{total_uplift:,.0f}")
        c4.metric("Uplift %", f"{uplift_pct:.1f}%")

        fig = positional_uplift_chart(monthly)
        st.plotly_chart(fig, use_container_width=True)

        if r["enable_revenue"] and "revenue" in monthly.columns:
            sym = CURRENCY_SYMBOLS.get(r["currency"], "$")
            st.divider()
            total_rev = monthly["revenue"].sum()
            peak_rev = monthly["revenue"].max()
            rc1, rc2 = st.columns(2)
            rc1.metric("Total Revenue (Period)", f"{sym}{total_rev:,.2f}")
            rc2.metric("Peak Monthly Revenue", f"{sym}{peak_rev:,.2f}")

            fig_rev = revenue_projection_chart(monthly, sym)
            st.plotly_chart(fig_rev, use_container_width=True)

        st.info(
            "**What does this mean?**\n\n"
            "This forecast estimates the traffic gain from improving keyword positions "
            "based on your current rankings, keyword difficulty, and the selected effort "
            "level. The baseline represents your current estimated organic traffic; the "
            "uplift shows what you could gain by moving keywords closer to position 1. "
            "Results depend heavily on competitive landscape and execution consistency."
        )

    # ── Tab: Per-Keyword Detail ─────────────────────────────────────────
    with tabs[1]:
        display_cols = [
            "keyword", "position", "target_position", "volume", "kd",
            "tier", "uplift", "time_to_move",
        ]
        display_df = kw_df[display_cols].copy()
        display_df["uplift"] = display_df["uplift"].round(1)

        st.dataframe(
            display_df.style.apply(
                lambda row: [
                    f"background-color: {TIER_COLORS.get(row['tier'], '')}20"
                    if col == "tier" else ""
                    for col in row.index
                ],
                axis=1,
            ),
            use_container_width=True,
            hide_index=True,
            height=500,
        )

    # ── Tab: Quick Wins ─────────────────────────────────────────────────
    with tabs[2]:
        qw_df = quick_wins(kw_df, 20)

        if qw_df.empty:
            st.info("No quick-win keywords found in positions 4-20.")
        else:
            st.markdown(
                "Keywords in positions **4-20** with the highest potential uplift. "
                "These are the lowest-effort, highest-impact moves you can make."
            )
            qw_display_cols = [
                "keyword", "position", "target_position", "volume", "kd",
                "tier", "uplift", "time_to_move",
            ]
            qw_display = qw_df[qw_display_cols].copy()
            qw_display["uplift"] = qw_display["uplift"].round(1)
            st.dataframe(qw_display, use_container_width=True, hide_index=True)

    # ── Tab: Export ─────────────────────────────────────────────────────
    with tabs[3]:
        ec1, ec2, ec3 = st.columns(3)

        with ec1:
            st.download_button(
                "Download Keyword Detail CSV",
                to_csv(kw_df),
                "positional-keyword-detail.csv",
                "text/csv",
                key="pos_dl_kw",
            )
        with ec2:
            st.download_button(
                "Download Monthly Projection CSV",
                to_csv(monthly),
                "positional-monthly-projection.csv",
                "text/csv",
                key="pos_dl_monthly",
            )
        with ec3:
            baseline = monthly["baseline"].iloc[0]
            projected_end = monthly["traffic"].iloc[-1]
            total_uplift = monthly["uplift"].iloc[-1]
            summary = {
                "Baseline Traffic": f"{baseline:,.0f}",
                "Projected End Traffic": f"{projected_end:,.0f}",
                "Total Uplift": f"{total_uplift:,.0f}",
            }
            figs = [positional_uplift_chart(monthly)]
            html = to_html_report(figs, summary, "Positional Forecast Report")
            st.download_button(
                "Download HTML Report",
                html,
                "positional-report.html",
                "text/html",
                key="pos_dl_html",
            )
