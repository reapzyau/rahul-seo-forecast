import streamlit as st
import pandas as pd

from engine.aio_risk_engine import calculate_aio_risk, aio_recommendations
from utils.chart_builder import aio_risk_chart
from utils.export import to_csv
from utils.sidebar import render_ai_settings

st.header("AI Overview Risk")
st.caption("Assess traffic at risk from Google AI Overviews.")

render_ai_settings()

# ── Data check ──────────────────────────────────────────────────────────────
kw_df = st.session_state.get("kw_df")
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

# ── Analysis (cheap — runs inline) ──────────────────────────────────────────
risk = calculate_aio_risk(kw_df, ctr_penalty_pct=ctr_penalty)

# ── KPI Cards ───────────────────────────────────────────────────────────────
keywords_affected = risk["keywords_affected"]
total_keywords = risk["total_keywords"]
exposure_pct = (keywords_affected / total_keywords * 100) if total_keywords > 0 else 0.0
traffic_at_risk = risk["traffic_at_risk"]
projected_loss = risk["projected_loss"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Keywords Affected", f"{keywords_affected:,}")
c2.metric("Exposure %", f"{exposure_pct:.1f}%")
c3.metric("Traffic at Risk", f"{traffic_at_risk:,.0f}")
c4.metric("Projected Monthly Loss", f"{projected_loss:,.0f}")

# ── Recommendations ─────────────────────────────────────────────────────────
recs = aio_recommendations(risk)
if recs:
    st.subheader("Recommendations")
    for rec in recs:
        st.markdown(f"- :warning: {rec}")

st.divider()

# ── Tabs ────────────────────────────────────────────────────────────────────
tab_names = ["\U0001f4ca Intent Breakdown", "\U0001f511 Affected Keywords", "\U0001f4e5 Export"]
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

# ── Tab: Affected Keywords ──────────────────────────────────────────────
with tabs[1]:
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
with tabs[2]:
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
