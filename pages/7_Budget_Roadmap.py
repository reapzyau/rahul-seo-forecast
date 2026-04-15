import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from engine.budget_engine import (
    build_budget_roadmap,
    build_monthly_budget_timeline,
    DEFAULT_SEO_TASKS,
)
from utils.export import to_csv

st.header("SEO Budget & Task Roadmap")
st.caption("Plan your SEO investment with task allocation and monthly budgeting.")

# ── Sidebar Settings ─────────────────────────────────────────────────────────
st.sidebar.header("Budget Settings")
hourly_rate = st.sidebar.number_input("Hourly Rate ($)", 50.0, 500.0, 200.0, step=10.0, key="budget_rate")
months = st.sidebar.slider("Project Duration (months)", 3, 24, 12, key="budget_months")

st.sidebar.divider()
st.sidebar.subheader("Task Hours")
st.sidebar.caption("Adjust hours per month for each task")

custom_tasks = []
for i, task in enumerate(DEFAULT_SEO_TASKS):
    hours = st.sidebar.number_input(
        f"{task['task']}",
        0.0, 40.0, task["hours_per_month"], step=0.5,
        key=f"budget_task_{i}",
        help=task["description"],
    )
    custom_tasks.append({**task, "hours_per_month": hours})

# ── Generate Roadmap ─────────────────────────────────────────────────────────
task_df, summary = build_budget_roadmap(custom_tasks, hourly_rate, months)
timeline_df = build_monthly_budget_timeline(custom_tasks, hourly_rate, months)

# ── KPI Cards ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Monthly Investment", f"${summary['total_monthly_cost']:,.0f}")
c2.metric("Hours/Month", f"{summary['total_hours_per_month']:.1f}")
c3.metric("Annual Cost", f"${summary['total_annual_cost']:,.0f}")
c4.metric("Project Total", f"${summary['total_project_cost']:,.0f}")

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "\U0001f4cb Task Breakdown",
    "\U0001f4c5 Monthly Timeline",
    "\U0001f4ca Budget Charts",
    "\U0001f4e5 Export",
])

with tab1:
    st.subheader("Task Allocation")

    # Group by category
    categories = task_df["Category"].unique()
    for cat in categories:
        cat_tasks = task_df[task_df["Category"] == cat]
        cat_hours = cat_tasks["Hours/Month"].sum()
        cat_cost = cat_tasks["Monthly Cost"].sum()

        with st.expander(f"**{cat}** — {cat_hours:.1f} hrs/mo (${cat_cost:,.0f}/mo)", expanded=True):
            for _, row in cat_tasks.iterrows():
                st.markdown(
                    f"**{row['Task']}** — {row['Hours/Month']:.1f} hrs/mo "
                    f"(${row['Monthly Cost']:,.0f}/mo) | {row['Frequency']}"
                )
                st.caption(row["Description"])

with tab2:
    st.subheader(f"Monthly Budget Timeline ({months} months)")
    display_tl = timeline_df.copy()
    # Format currency columns
    for col in display_tl.columns:
        if col != "Month":
            display_tl[col] = display_tl[col].apply(lambda x: f"${x:,.0f}")
    st.dataframe(display_tl, use_container_width=True, hide_index=True)

with tab3:
    # Pie chart by category
    cat_costs = task_df.groupby("Category")["Monthly Cost"].sum().reset_index()
    fig_pie = go.Figure(data=[go.Pie(
        labels=cat_costs["Category"],
        values=cat_costs["Monthly Cost"],
        hole=0.4,
        textinfo="label+percent",
    )])
    fig_pie.update_layout(title="Budget Allocation by Category", height=400)
    st.plotly_chart(fig_pie, use_container_width=True)

    # Stacked bar timeline
    fig_bar = go.Figure()
    cats = [c for c in timeline_df.columns if c not in ["Month", "Total"]]
    colors = ["#2563EB", "#8B5CF6", "#F97316", "#22C55E", "#EF4444", "#EAB308", "#06B6D4"]
    for i, cat in enumerate(cats):
        fig_bar.add_trace(go.Bar(
            x=timeline_df["Month"],
            y=timeline_df[cat],
            name=cat,
            marker_color=colors[i % len(colors)],
        ))
    fig_bar.update_layout(
        barmode="stack",
        title="Monthly Budget by Category",
        xaxis_title="Month",
        yaxis_title="Cost ($)",
        plot_bgcolor="white",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with tab4:
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download Task Breakdown CSV",
            to_csv(task_df),
            "seo-budget-tasks.csv",
            "text/csv",
        )
    with col2:
        st.download_button(
            "Download Monthly Timeline CSV",
            to_csv(timeline_df),
            "seo-budget-timeline.csv",
            "text/csv",
        )
