import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from engine.aio_risk_engine import (
    calculate_aio_risk, aio_recommendations, project_aio_erosion,
    DEFAULT_MONTHLY_AIO_GROWTH,
)
from utils.chart_builder import aio_risk_chart, _apply_layout
from utils.export import to_csv
from utils.sidebar import render_ai_settings
from utils.session import KW_DF

st.header("AI Overview Risk")
st.caption("Diagnostic view: understand your portfolio's AIO exposure. Traffic impact is already factored into your Positional and New Content forecasts.")

st.info(
    "**v4 change:** AIO traffic impact is now applied per-stream as a CTR penalty inside the "
    "Positional Forecast and New Content Forecast engines. This page shows *visibility* into "
    "your AIO exposure — use it to understand which keywords are at risk, not to calculate a "
    "separate deduction."
)

render_ai_settings()

# ── Data check ──────────────────────────────────────────────────────────────
kw_df = st.session_state.get(KW_DF)
if kw_df is None:
    st.info("Go to **Data Upload** first and load keyword data with AI Overview flags.")
    st.stop()

# ── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("AI Overview Risk Settings")

ctr_penalty = st.sidebar.slider(
    "AIO CTR Penalty (%)", 0, 80, 40,
    key="aio_penalty",
    help="Estimated CTR reduction when a Google AI Overview appears for a query.",
)

st.sidebar.divider()
st.sidebar.subheader("Projected Erosion")
erosion_months = st.sidebar.slider("Projection horizon (months)", 6, 36, 12, key="aio_erosion_months")
aio_growth_rate = st.sidebar.slider(
    "Monthly AIO growth rate",
    0.0, 0.10, DEFAULT_MONTHLY_AIO_GROWTH, 0.005,
    key="aio_growth_rate",
    help="Fraction of currently-unaffected keywords that become AIO-affected each month.",
)

# ── Analysis (cheap — runs inline) ──────────────────────────────────────────
risk = calculate_aio_risk(kw_df, ctr_penalty_pct=ctr_penalty)

# ── KPI Cards ───────────────────────────────────────────────────────────────
keywords_affected = risk["keywords_affected"]
total_keywords = risk["total_keywords"]
exposure_pct = (keywords_affected / total_keywords * 100) if total_keywords > 0 else 0.0
traffic_at_risk = risk["traffic_at_risk"]

c1, c2, c3 = st.columns(3)
c1.metric("Keywords Affected", f"{keywords_affected:,}")
c2.metric("Exposure %", f"{exposure_pct:.1f}%")
c3.metric("Traffic at Risk (diagnostic)", f"{traffic_at_risk:,.0f}")
st.caption("These are diagnostic exposure estimates — AIO CTR penalties are already applied inside the Positional and New Content forecast engines.")

# ── Recommendations ─────────────────────────────────────────────────────────
recs = aio_recommendations(risk)
if recs:
    st.subheader("Recommendations")
    for rec in recs:
        st.markdown(f"- :warning: {rec}")

st.divider()

# ── Tabs ────────────────────────────────────────────────────────────────────
tab_names = [
    "\U0001f4ca Intent Breakdown",
    "\U0001f4c9 Projected Erosion",
    "\U0001f511 Affected Keywords",
    "\U0001f4e5 Export",
]
tabs = st.tabs(tab_names)

# ── Tab: Intent Breakdown ───────────────────────────────────────────────
with tabs[0]:
    intent_breakdown = risk["intent_breakdown"]

    if intent_breakdown.empty:
        st.info("No AI Overview-affected keywords detected in this dataset.")
    else:
        fig = aio_risk_chart(intent_breakdown, ctr_penalty)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Traffic at risk vs. projected loss by keyword intent. "
            "Informational queries are typically most affected by AI Overviews."
        )

        st.subheader("Intent Breakdown Table")
        display_intent = intent_breakdown.copy()
        display_intent["traffic"] = display_intent["traffic"].round(0)
        display_intent["traffic_loss"] = display_intent["traffic_loss"].round(0)
        st.dataframe(display_intent, use_container_width=True, hide_index=True)

# ── Tab: Projected Erosion ──────────────────────────────────────────────
with tabs[1]:
    erosion_df = project_aio_erosion(kw_df, months=erosion_months, monthly_growth=aio_growth_rate)

    m_end = erosion_df.iloc[-1]
    e1, e2, e3 = st.columns(3)
    e1.metric(f"AIO-Affected (M{erosion_months})", f"{m_end['aio_affected_count']:,}")
    e2.metric(f"Cumulative Erosion (M{erosion_months})", f"{m_end['cumulative_erosion']:,}")
    e3.metric("Growth Rate", f"{aio_growth_rate*100:.1f}%/month")

    fig_erosion = go.Figure()
    fig_erosion.add_trace(go.Scatter(
        x=erosion_df["month"], y=erosion_df["cumulative_erosion"],
        mode="lines+markers", name="Cumulative Erosion",
        line=dict(color="#EF4444", width=3),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.1)",
    ))
    fig_erosion.add_trace(go.Scatter(
        x=erosion_df["month"], y=erosion_df["monthly_erosion"],
        mode="lines", name="Monthly Erosion",
        line=dict(color="#F97316", width=2, dash="dash"),
    ))
    fig_erosion = _apply_layout(fig_erosion, "Projected AIO Traffic Erosion", "Month", "Sessions Lost")
    st.plotly_chart(fig_erosion, use_container_width=True)
    st.caption(
        f"AIO coverage spreading at {aio_growth_rate*100:.1f}% per month. "
        "Informational keywords bear the heaviest CTR penalty (45%); "
        "transactional keywords are largely unaffected."
    )

# ── Tab: Affected Keywords ──────────────────────────────────────────────
with tabs[2]:
    detail_df = risk["detail_df"]

    if detail_df.empty:
        st.info("No AI Overview-affected keywords detected.")
    else:
        st.markdown(
            f"**{len(detail_df)} keywords** flagged with AI Overview presence, "
            f"representing **{exposure_pct:.1f}%** of your tracked portfolio."
        )
        display_detail = detail_df.copy()
        if "projected_loss" in display_detail.columns:
            display_detail["projected_loss"] = display_detail["projected_loss"].round(1)
        st.dataframe(display_detail, use_container_width=True, hide_index=True, height=500)

# ── Tab: Export ─────────────────────────────────────────────────────────
with tabs[3]:
    detail_df = risk["detail_df"]
    if detail_df.empty:
        st.info("No data to export — no AI Overview-affected keywords found.")
    else:
        st.download_button(
            "Download Affected Keywords CSV",
            to_csv(detail_df),
            "aio-risk-detail.csv",
            "text/csv",
            key="aio_dl_csv",
        )
