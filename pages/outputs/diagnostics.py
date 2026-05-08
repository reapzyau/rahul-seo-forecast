import plotly.graph_objects as go
import streamlit as st

from engine.aio_risk_engine import (
    DEFAULT_MONTHLY_AIO_GROWTH,
    aio_recommendations,
    calculate_aio_risk,
    project_aio_erosion,
)
from engine.keyword_pipeline_engine import (
    build_pipeline_over_time,
    build_pipeline_snapshot,
)
from utils.chart_builder import _apply_layout, aio_risk_chart
from utils.design_tokens import (
    DANGER,
    DANGER_ALT,
    FILL_SUBTLE,
    SLATE_400,
    SUCCESS,
    WARNING_COLOR,
    rgba,
)
from utils.export import to_csv
from utils.page_base import setup_page
from utils.session import COMB_RESULTS, KW_DF, NC_RESULT

setup_page(
    "Diagnostics",
    "Diagnostic views into your keyword portfolio. Traffic impact is already baked into Forecast.",
    show_assumptions_banner=False,
    data_requirements=["kw_existing:optional", "comb_results:optional"],
)

st.info(
    "**v4 change:** AIO traffic impact is now applied per-stream as a CTR penalty inside the "
    "Positional Forecast and New Content Forecast engines. This page shows *visibility* into "
    "your AIO exposure — use it to understand which keywords are at risk, not to calculate a "
    "separate deduction."
)

# ── Session data ──────────────────────────────────────────────────────────────
kw_df = st.session_state.get(KW_DF)
kw_results = st.session_state.get(NC_RESULT)
comb_results = st.session_state.get(COMB_RESULTS)

# ── Sidebar: AIO Risk Settings ─────────────────────────────────────────────────
st.sidebar.header("AIO Risk Settings")

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

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_aio, tab_pipeline, tab_decay = st.tabs([
    "\U0001f916 AIO Risk",
    "\U0001f4ca Keyword Pipeline",
    "\U0001f4c9 Decay Projection",
])

# ── Tab: AIO Risk ──────────────────────────────────────────────────────────────
with tab_aio:
    if kw_df is None:
        st.info("Go to **Data Upload** first and load keyword data with AI Overview flags.")
    else:
        risk = calculate_aio_risk(kw_df, ctr_penalty_pct=ctr_penalty)

        keywords_affected = risk["keywords_affected"]
        total_keywords = risk["total_keywords"]
        exposure_pct = (keywords_affected / total_keywords * 100) if total_keywords > 0 else 0.0
        traffic_at_risk = risk["traffic_at_risk"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Keywords Affected", f"{keywords_affected:,}")
        c2.metric("Exposure %", f"{exposure_pct:.1f}%")
        c3.metric("Traffic at Risk (diagnostic)", f"{traffic_at_risk:,.0f}")
        st.caption(
            "These are diagnostic exposure estimates — AIO CTR penalties are already "
            "applied inside the Positional and New Content forecast engines."
        )

        recs = aio_recommendations(risk)
        if recs:
            st.subheader("Recommendations")
            for rec in recs:
                st.markdown(f"- :warning: {rec}")

        st.divider()

        aio_tab1, aio_tab2, aio_tab3, aio_tab4 = st.tabs([
            "\U0001f4ca Intent Breakdown",
            "\U0001f4c9 Projected Erosion",
            "\U0001f511 Affected Keywords",
            "\U0001f4e5 Export",
        ])

        with aio_tab1:
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

        with aio_tab2:
            erosion_df = project_aio_erosion(kw_df, months=erosion_months, monthly_growth=aio_growth_rate)
            m_end = erosion_df.iloc[-1]
            e1, e2, e3 = st.columns(3)
            e1.metric(f"AIO-Affected (M{erosion_months})", f"{m_end['aio_affected_count']:,}")
            e2.metric(f"Cumulative Erosion (M{erosion_months})", f"{m_end['cumulative_erosion']:,}")
            e3.metric("Growth Rate", f"{aio_growth_rate * 100:.1f}%/month")

            fig_erosion = go.Figure()
            fig_erosion.add_trace(go.Scatter(
                x=erosion_df["month"], y=erosion_df["cumulative_erosion"],
                mode="lines+markers", name="Cumulative Erosion",
                line=dict(color=DANGER, width=3),
                fill="tozeroy", fillcolor=rgba(DANGER, FILL_SUBTLE),
            ))
            fig_erosion.add_trace(go.Scatter(
                x=erosion_df["month"], y=erosion_df["monthly_erosion"],
                mode="lines", name="Monthly Erosion",
                line=dict(color=DANGER_ALT, width=2, dash="dash"),
            ))
            fig_erosion = _apply_layout(
                fig_erosion, "Projected AIO Traffic Erosion", "Month", "Sessions Lost"
            )
            st.plotly_chart(fig_erosion, use_container_width=True)
            st.caption(
                f"AIO coverage spreading at {aio_growth_rate * 100:.1f}% per month. "
                "Informational keywords bear the heaviest CTR penalty (45%); "
                "transactional keywords are largely unaffected."
            )

        with aio_tab3:
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

        with aio_tab4:
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

# ── Tab: Keyword Pipeline ──────────────────────────────────────────────────────
with tab_pipeline:
    # Use NC_RESULT if available; fall back to raw KW_DF with current positions
    if kw_results is not None:
        keyword_df = kw_results["keyword_df"]
        has_projection = True
    elif kw_df is not None and "position" in kw_df.columns:
        keyword_df = kw_df.copy()
        keyword_df["expected_position"] = keyword_df["position"]
        has_projection = False
    else:
        keyword_df = None
        has_projection = False

    if keyword_df is None:
        st.info("Go to **Data Upload** and load keyword data to see the pipeline.")
    else:
        st.subheader("Current Keyword Distribution")
        snapshot = build_pipeline_snapshot(keyword_df)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Page 1", snapshot["Page 1"], help="Positions 1-10")
        c2.metric("Page 2", snapshot["Page 2"], help="Positions 11-20")
        c3.metric("Page 3", snapshot["Page 3"], help="Positions 21-30")
        c4.metric("Pages 4-10", snapshot["Pages 4-10"], help="Positions 31-100")
        c5.metric("Not Ranking", snapshot["Not Ranking"])

        fig_donut = go.Figure(data=[go.Pie(
            labels=list(snapshot.keys()),
            values=list(snapshot.values()),
            hole=0.5,
            marker_colors=[SUCCESS, WARNING_COLOR, DANGER_ALT, SLATE_400, DANGER],
            textinfo="label+value",
        )])
        fig_donut.update_layout(title="Keyword Distribution by SERP Page", height=350)
        st.plotly_chart(fig_donut, use_container_width=True)

        st.divider()
        if not has_projection:
            st.info("Run a **New Content Forecast** to see projected pipeline movement over time.")
        else:
            st.subheader("Keyword Pipeline Over Time")

        if has_projection:
            pipeline_months = st.slider("Forecast Months", 6, 36, 18, key="pipeline_months")
            pipeline_df = build_pipeline_over_time(keyword_df, pipeline_months)

            pipe_tab1, pipe_tab2, pipe_tab3 = st.tabs([
                "\U0001f4ca Pipeline Chart",
                "\U0001f4cb Movement Table",
                "\U0001f4e5 Export",
            ])

            with pipe_tab1:
                fig = go.Figure()
                colors = {
                    "page_1": SUCCESS, "page_2": WARNING_COLOR,
                    "page_3": DANGER_ALT, "pages_4_10": SLATE_400,
                }
                names = {
                    "page_1": "Page 1", "page_2": "Page 2",
                    "page_3": "Page 3", "pages_4_10": "Pages 4-10",
                }
                for col, color in colors.items():
                    fig.add_trace(go.Scatter(
                        x=pipeline_df["month"],
                        y=pipeline_df[col],
                        mode="lines+markers",
                        name=names[col],
                        line=dict(color=color, width=2),
                        stackgroup="one",
                        hovertemplate=f"{names[col]}: %{{y}}<extra></extra>",
                    ))
                fig.update_layout(
                    title="Keyword Ranking Pipeline — Stacked Area",
                    xaxis_title="Month",
                    yaxis_title="Number of Keywords",
                    plot_bgcolor="white",
                    hovermode="x unified",
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Shows how keywords move from Pages 4-10 into Page 3, Page 2, and Page 1 over time.")

            with pipe_tab2:
                display_df = pipeline_df[[
                    "month", "page_1", "page_1_mom_change", "page_1_mom_pct",
                    "page_2", "page_2_mom_change", "page_2_mom_pct",
                    "page_3", "page_3_mom_change",
                    "pages_4_10", "total_published",
                ]].copy()
                display_df.columns = [
                    "Month", "Page 1", "P1 MoM +/-", "P1 MoM %",
                    "Page 2", "P2 MoM +/-", "P2 MoM %",
                    "Page 3", "P3 MoM +/-",
                    "Pages 4-10", "Total Published",
                ]
                st.dataframe(display_df, use_container_width=True, hide_index=True, height=500)

            with pipe_tab3:
                st.download_button(
                    "Download Pipeline CSV",
                    to_csv(pipeline_df),
                    "keyword-pipeline.csv",
                    "text/csv",
                    key="pipeline_dl_csv",
                )

# ── Tab: Decay Projection ──────────────────────────────────────────────────────
with tab_decay:
    if comb_results is None:
        st.info("Run a **Combined Forecast** first to see decay projections.")
    else:
        decay_df = comb_results.get("decay_df")
        if decay_df is None:
            st.info(
                "Decay was not included in your Combined Forecast. "
                "Enable **Include Decay** in the Combined Forecast settings and re-run."
            )
        else:
            last = decay_df.iloc[-1]
            d1, d2, d3 = st.columns(3)
            d1.metric("Total Cumulative Decay", f"{int(last['cumulative_decay']):,}")
            d2.metric("Avg Monthly Loss", f"{int(decay_df['decay_loss'].mean()):,}")
            d3.metric("Retained Traffic (final month)", f"{int(last['retained_traffic']):,}")

            fig_decay = go.Figure()
            fig_decay.add_trace(go.Scatter(
                x=decay_df["month"],
                y=decay_df["cumulative_decay"],
                mode="lines+markers",
                name="Cumulative Decay",
                line=dict(color=DANGER, width=3),
                fill="tozeroy",
                fillcolor=rgba(DANGER, FILL_SUBTLE),
            ))
            fig_decay.add_trace(go.Scatter(
                x=decay_df["month"],
                y=decay_df["decay_loss"],
                mode="lines",
                name="Monthly Decay Loss",
                line=dict(color=DANGER_ALT, width=2, dash="dash"),
            ))
            fig_decay = _apply_layout(
                fig_decay, "Portfolio Decay Projection", "Month", "Sessions Lost to Decay"
            )
            st.plotly_chart(fig_decay, use_container_width=True)
            st.caption(
                "Cumulative sessions lost if existing pages receive no maintenance. "
                "This deduction is already applied in the Combined Forecast."
            )

            st.subheader("Decay by Month")
            st.dataframe(decay_df, use_container_width=True, hide_index=True)
