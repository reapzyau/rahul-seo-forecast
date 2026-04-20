import plotly.graph_objects as go
import streamlit as st

from engine.keyword_pipeline_engine import (
    build_pipeline_over_time,
    build_pipeline_snapshot,
)
from utils.export import to_csv
from utils.session import NC_RESULT

st.header("Keyword Ranking Pipeline")
st.caption("Track keyword distribution across SERP pages and month-over-month movement.")

# ── Check for keyword forecast data ──────────────────────────────────────────
kw_results = st.session_state.get(NC_RESULT)
if kw_results is None:
    st.info("Run a **Keyword Forecast** first to populate the keyword pipeline.")
    st.stop()
else:
    keyword_df = kw_results["keyword_df"]

    # ── Current Snapshot ─────────────────────────────────────────────────────
    st.subheader("Current Keyword Distribution")

    snapshot = build_pipeline_snapshot(keyword_df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Page 1", snapshot["Page 1"], help="Positions 1-10")
    c2.metric("Page 2", snapshot["Page 2"], help="Positions 11-20")
    c3.metric("Page 3", snapshot["Page 3"], help="Positions 21-30")
    c4.metric("Pages 4-10", snapshot["Pages 4-10"], help="Positions 31-100")
    c5.metric("Not Ranking", snapshot["Not Ranking"])

    # Donut chart
    fig_donut = go.Figure(data=[go.Pie(
        labels=list(snapshot.keys()),
        values=list(snapshot.values()),
        hole=0.5,
        marker_colors=["#22C55E", "#EAB308", "#F97316", "#94A3B8", "#EF4444"],
        textinfo="label+value",
    )])
    fig_donut.update_layout(title="Keyword Distribution by SERP Page", height=350)
    st.plotly_chart(fig_donut, use_container_width=True)

    # ── Pipeline Over Time ───────────────────────────────────────────────────
    st.divider()
    st.subheader("Keyword Pipeline Over Time")

    months = st.slider("Forecast Months", 6, 36, 18, key="pipeline_months")
    pipeline_df = build_pipeline_over_time(keyword_df, months)

    tab1, tab2, tab3 = st.tabs([
        "\U0001f4ca Pipeline Chart",
        "\U0001f4cb Movement Table",
        "\U0001f4e5 Export",
    ])

    with tab1:
        fig = go.Figure()
        colors = {"page_1": "#22C55E", "page_2": "#EAB308", "page_3": "#F97316", "pages_4_10": "#94A3B8"}
        names = {"page_1": "Page 1", "page_2": "Page 2", "page_3": "Page 3", "pages_4_10": "Pages 4-10"}

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

    with tab2:
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

    with tab3:
        st.download_button(
            "Download Pipeline CSV",
            to_csv(pipeline_df),
            "keyword-pipeline.csv",
            "text/csv",
        )
