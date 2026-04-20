import plotly.graph_objects as go
import streamlit as st

from engine.revenue_engine import CURRENCY_SYMBOLS
from engine.roadmap_engine import DEFAULT_SEO_TASKS, FOCUS_COLORS, build_roadmap, build_roadmap_xlsx
from utils.chart_builder import _apply_layout
from utils.page_base import setup_page

setup_page("SEO Roadmap", "Month-by-month task allocation in the GAZMAN format.", show_assumptions_banner=False)

# -- Sidebar Settings --------------------------------------------------------
st.sidebar.header("Roadmap Settings")

currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="road_currency")
sym = CURRENCY_SYMBOLS.get(currency, "$")
hourly_rate = st.sidebar.number_input(
    f"Hourly Rate ({sym})", 50.0, 500.0, 200.0, step=10.0, key="road_rate"
)
months = st.sidebar.slider("Months", 3, 24, 12, key="road_months")
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

# -- Generate Roadmap (lightweight, no button needed) -------------------------
task_df, monthly_df, summary = build_roadmap(custom_tasks, months=months)

# -- KPI Cards ----------------------------------------------------------------
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

# -- Tabs ---------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "\U0001f4cb Task Breakdown",
    "\U0001f4c6 Monthly Matrix",
    "\U0001f4ca Charts",
    "\U0001f4e5 Export",
])

# -- Tab 1: Task Breakdown ----------------------------------------------------
with tab1:
    focus_groups = task_df.groupby("Focus")
    for focus, group in focus_groups:
        total_hrs = group["Hours"].sum()
        with st.expander(f"**{focus}** -- {total_hrs:.1f} total hours", expanded=True):
            for _, row in group.iterrows():
                st.markdown(
                    f"**{row['Task']}** -- {row['Hours']:.1f} hrs | {row['Occurrence']}"
                )

# -- Tab 2: Monthly Matrix ----------------------------------------------------
with tab2:
    st.subheader(f"Monthly Hour Matrix ({months} months)")
    st.dataframe(monthly_df, use_container_width=True, hide_index=True)

# -- Tab 3: Charts ------------------------------------------------------------
with tab3:
    # Pie chart by Focus
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

    # Stacked bar chart: month on x-axis, hours per focus stacked
    month_cols = [c for c in monthly_df.columns if c.startswith("M") and c != "Month"]
    # Exclude the TOTAL row
    data_rows = monthly_df[monthly_df["Task"] != "TOTAL"]

    fig_bar = go.Figure()
    for focus, color in FOCUS_COLORS.items():
        focus_rows = data_rows[data_rows["Focus"] == focus]
        if focus_rows.empty:
            continue
        month_sums = [focus_rows[col].sum() for col in month_cols]
        fig_bar.add_trace(go.Bar(
            x=month_cols,
            y=month_sums,
            name=focus,
            marker_color=color,
        ))

    fig_bar.update_layout(barmode="stack")
    fig_bar = _apply_layout(fig_bar, "Monthly Hours by Focus Area", "Month", "Hours")
    fig_bar.update_layout(height=450)
    st.plotly_chart(fig_bar, use_container_width=True)

# -- Tab 4: Export -------------------------------------------------------------
with tab4:
    col1, col2 = st.columns(2)
    with col1:
        xlsx_buf = build_roadmap_xlsx(
            monthly_df, summary, hourly_rate, client_name, fy_label
        )
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
