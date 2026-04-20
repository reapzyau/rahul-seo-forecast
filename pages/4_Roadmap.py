import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.ai_engine import generate_content_roadmap, get_bifrost_client
from engine.revenue_engine import CURRENCY_SYMBOLS
from engine.roadmap_engine import DEFAULT_SEO_TASKS, FOCUS_COLORS, build_roadmap, build_roadmap_xlsx
from utils.chart_builder import _apply_layout
from utils.export import to_csv
from utils.page_base import setup_page
from utils.session import BIFROST_API_KEY, BIFROST_MODEL, CONTENT_ROADMAP, NC_RESULT

setup_page(
    "Roadmap",
    "AI-powered content planning and hour-by-hour SEO task allocation.",
    show_assumptions_banner=False,
)

# ── Sidebar: SEO Task Roadmap Settings ────────────────────────────────────────
st.sidebar.header("SEO Roadmap Settings")

currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="road_currency")
sym = CURRENCY_SYMBOLS.get(currency, "$")
hourly_rate = st.sidebar.number_input(
    f"Hourly Rate ({sym})", 50.0, 500.0, 200.0, step=10.0, key="road_rate"
)
seo_months = st.sidebar.slider("Months", 3, 24, 12, key="road_months")
fy_label = st.sidebar.text_input("FY Label", value="FY26", key="road_fy")
client_name = st.sidebar.text_input("Client Name", value="", key="road_client")

st.sidebar.divider()
st.sidebar.subheader("Task Hours")

custom_tasks = []
for i, task in enumerate(DEFAULT_SEO_TASKS):
    hours = st.sidebar.number_input(
        f"{task['task']}",
        0.0, 40.0, task["hours"], step=0.5,
        key=f"road_task_{i}",
        help=f"Occurrence: {task['occurrence']}",
    )
    custom_tasks.append({**task, "hours": hours})

# Build roadmap (lightweight — no button guard needed)
task_df, monthly_df, summary = build_roadmap(custom_tasks, months=seo_months)

# ── AI client (for Content Roadmap tab) ───────────────────────────────────────
client = get_bifrost_client(st.session_state.get(BIFROST_API_KEY))
ai_model = st.session_state.get(BIFROST_MODEL, "openai/gpt-4o-mini")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_content, tab_seo = st.tabs([
    "\U0001f4dd Content Roadmap",
    "\u23f1\ufe0f SEO Task Roadmap",
])

# ── Tab: Content Roadmap ───────────────────────────────────────────────────────
with tab_content:
    if client is None:
        st.warning(
            "This tab requires a Bi Frost API key. "
            "Set it in the sidebar under **AI Settings (Bi Frost)** on the home page."
        )
    else:
        st.subheader("Existing Roadmap (Optional)")
        st.caption("Upload your current content roadmap to provide context for AI recommendations.")
        roadmap_file = st.file_uploader(
            "Upload roadmap file", type=["csv", "tsv", "xlsx", "xls"], key="roadmap_upload"
        )

        existing_roadmap_csv = None
        if roadmap_file is not None:
            try:
                existing_roadmap = pd.read_csv(roadmap_file)
                existing_roadmap_csv = existing_roadmap.to_csv(index=False)
                st.success(
                    f"Loaded {len(existing_roadmap)} rows from existing roadmap "
                    "— AI will avoid duplicating these topics"
                )
                st.dataframe(existing_roadmap.head(10), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Could not read roadmap CSV: {e}")

        st.divider()
        st.subheader("Generate Content Roadmap")

        kw_results = st.session_state.get(NC_RESULT)
        if kw_results is None:
            st.info(
                "Run a **Keyword Forecast** first to generate data for the roadmap. "
                "Go to the Keyword Forecast page, upload keywords, and click Generate Forecast."
            )
        else:
            keyword_df = kw_results["keyword_df"]
            st.success(f"Using keyword forecast data: {len(keyword_df)} keywords")

            col1, col2 = st.columns(2)
            with col1:
                roadmap_months = st.slider("Roadmap Duration (months)", 3, 24, 12, key="roadmap_months")
            with col2:
                st.metric("Keywords Available", len(keyword_df))
                st.metric("Keywords Ranking", int(keyword_df["will_rank"].sum()))

            if st.button("Generate AI Content Roadmap", type="primary", key="roadmap_generate"):
                with st.spinner("AI is analyzing your keywords and building a content roadmap..."):
                    try:
                        roadmap, used_model = generate_content_roadmap(
                            client, keyword_df, roadmap_months, ai_model, existing_roadmap_csv,
                        )
                        if used_model != ai_model:
                            st.info(f"Fell back to {used_model} — selected model was unavailable")
                        st.session_state[CONTENT_ROADMAP] = roadmap
                    except Exception as e:
                        st.error(f"Roadmap generation failed: {e}")

            if CONTENT_ROADMAP in st.session_state:
                roadmap = st.session_state[CONTENT_ROADMAP]
                st.divider()
                st.subheader("Content Roadmap")

                flat_rows = []
                for month_plan in roadmap:
                    month_num = month_plan.get("month", "?")
                    pieces = month_plan.get("content_pieces", [])

                    with st.expander(
                        f"**Month {month_num}** — {len(pieces)} content pieces",
                        expanded=month_num <= 3,
                    ):
                        for piece in pieces:
                            priority = piece.get("priority", "medium")
                            icon = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(
                                priority, "\u26aa"
                            )
                            st.markdown(
                                f"{icon} **{piece.get('title', 'Untitled')}** "
                                f"(~{piece.get('estimated_traffic', 0):,} visits/mo, priority: {priority})"
                            )
                            kws = piece.get("target_keywords", [])
                            if kws:
                                st.caption(f"Target keywords: {', '.join(kws)}")
                            notes = piece.get("notes")
                            if notes:
                                st.caption(f"Note: {notes}")
                            flat_rows.append({
                                "Month": month_num,
                                "Title": piece.get("title", ""),
                                "Target Keywords": ", ".join(kws),
                                "Estimated Traffic": piece.get("estimated_traffic", 0),
                                "Priority": priority,
                                "Notes": notes or "",
                            })

                if flat_rows:
                    st.divider()
                    roadmap_df = pd.DataFrame(flat_rows)
                    st.download_button(
                        "Download Roadmap CSV",
                        to_csv(roadmap_df),
                        "content-roadmap.csv",
                        "text/csv",
                        key="roadmap_export",
                    )

# ── Tab: SEO Task Roadmap ──────────────────────────────────────────────────────
with tab_seo:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Hours", f"{summary['total_hours']:,.1f}")
    c2.metric("Avg Hours/Month", f"{summary['avg_hours_per_month']:.1f}")
    c3.metric(
        "Peak Month",
        f"Month {summary['peak_month']}",
        delta=f"{summary['peak_hours']:.1f} hrs",
        delta_color="off",
    )
    total_cost = summary["total_hours"] * hourly_rate
    c4.metric("Total Cost", f"{sym}{total_cost:,.0f}")

    seo_tab1, seo_tab2, seo_tab3, seo_tab4 = st.tabs([
        "\U0001f4cb Task Breakdown",
        "\U0001f4c6 Monthly Matrix",
        "\U0001f4ca Charts",
        "\U0001f4e5 Export",
    ])

    with seo_tab1:
        for focus, group in task_df.groupby("Focus"):
            total_hrs = group["Hours"].sum()
            with st.expander(f"**{focus}** -- {total_hrs:.1f} total hours", expanded=True):
                for _, row in group.iterrows():
                    st.markdown(f"**{row['Task']}** -- {row['Hours']:.1f} hrs | {row['Occurrence']}")

    with seo_tab2:
        st.subheader(f"Monthly Hour Matrix ({seo_months} months)")
        st.dataframe(monthly_df, use_container_width=True, hide_index=True)

    with seo_tab3:
        focus_hours = task_df.groupby("Focus")["Hours"].sum().reset_index()
        pie_colors = [FOCUS_COLORS.get(f, "#94A3B8") for f in focus_hours["Focus"]]
        fig_pie = go.Figure(data=[go.Pie(
            labels=focus_hours["Focus"],
            values=focus_hours["Hours"],
            hole=0.4,
            textinfo="label+percent",
            marker=dict(colors=pie_colors),
        )])
        fig_pie = _apply_layout(fig_pie, "Hours by Focus Area", "", "")
        fig_pie.update_layout(height=420)
        st.plotly_chart(fig_pie, use_container_width=True)

        month_cols = [c for c in monthly_df.columns if c.startswith("M") and c != "Month"]
        data_rows = monthly_df[monthly_df["Task"] != "TOTAL"]
        fig_bar = go.Figure()
        for focus, color in FOCUS_COLORS.items():
            focus_rows = data_rows[data_rows["Focus"] == focus]
            if focus_rows.empty:
                continue
            month_sums = [focus_rows[col].sum() for col in month_cols]
            fig_bar.add_trace(go.Bar(x=month_cols, y=month_sums, name=focus, marker_color=color))
        fig_bar.update_layout(barmode="stack")
        fig_bar = _apply_layout(fig_bar, "Monthly Hours by Focus Area", "Month", "Hours")
        fig_bar.update_layout(height=450)
        st.plotly_chart(fig_bar, use_container_width=True)

    with seo_tab4:
        col1, col2 = st.columns(2)
        with col1:
            xlsx_buf = build_roadmap_xlsx(monthly_df, summary, hourly_rate, client_name, fy_label)
            st.download_button(
                "Download Roadmap XLSX",
                xlsx_buf,
                "seo-roadmap.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="road_xlsx_dl",
            )
        with col2:
            csv_bytes = task_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Task Breakdown CSV",
                csv_bytes,
                "seo-roadmap-tasks.csv",
                "text/csv",
                key="road_csv_dl",
            )
