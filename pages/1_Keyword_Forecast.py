import os
import streamlit as st
import pandas as pd

from engine.keyword_engine import run_keyword_forecast
from engine.revenue_engine import add_revenue, keyword_revenue_table, CURRENCY_SYMBOLS
from utils.data_loader import load_keywords
from utils.chart_builder import (
    traffic_projection_chart,
    keyword_schedule_chart,
    scenario_comparison_chart,
    revenue_projection_chart,
)
from utils.export import to_csv, to_html_report
from engine.constants import TIER_COLORS

st.header("Keyword Forecast")
st.caption("Project traffic from target keywords — no historical data needed.")

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Keyword Forecast Settings")

da = st.sidebar.slider("Domain Authority (DA)", 1, 100, 30)
cadence = st.sidebar.number_input("Monthly Content Production", 1, 50, 4)
months = st.sidebar.slider("Forecast Horizon (months)", 6, 36, 18)
seed = st.sidebar.number_input("Random Seed", value=42, step=1)

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
enable_revenue = st.sidebar.checkbox("Enable Revenue Projection")
cvr = st.sidebar.number_input("Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1, disabled=not enable_revenue)
aov = st.sidebar.number_input("Average Order Value", 1.0, 100000.0, 100.0, step=10.0, disabled=not enable_revenue)
currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), disabled=not enable_revenue)

st.sidebar.divider()
st.sidebar.subheader("Scenario Comparison")
enable_scenarios = st.sidebar.checkbox("Compare Multiple Cadences")
cadence_options = st.sidebar.multiselect(
    "Cadences to compare",
    [1, 2, 4, 6, 8, 12],
    default=[2, 4, 8],
    disabled=not enable_scenarios,
)

# ── Upload ───────────────────────────────────────────────────────────────────
st.subheader("Upload Keywords CSV")
st.caption("Required columns: keyword, volume, kd")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Upload your CSV", type=["csv"])
with col2:
    use_sample = st.checkbox("Use sample data to explore the tool")

df = None
if uploaded_file is not None:
    df = load_keywords(uploaded_file)
elif use_sample:
    sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sample-keywords.csv")
    df = load_keywords(sample_path)

if df is not None:
    st.markdown(
        f"**{len(df)} keywords loaded** | "
        f"Avg volume: {df['volume'].mean():,.0f} | "
        f"Avg KD: {df['kd'].mean():.0f} | "
        f"Volume range: {df['volume'].min():,} – {df['volume'].max():,}"
    )
    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

# ── Run Forecast ─────────────────────────────────────────────────────────────
if df is not None:
    if st.button("Generate Forecast", type="primary"):
        with st.spinner("Running keyword forecast..."):
            keyword_df, monthly_df = run_keyword_forecast(df, da, cadence, months, seed)

            # Run scenarios if enabled
            scenarios = {}
            if enable_scenarios and cadence_options:
                for c in cadence_options:
                    _, s_monthly = run_keyword_forecast(df, da, c, months, seed)
                    scenarios[c] = s_monthly

            # Revenue
            if enable_revenue:
                monthly_df = add_revenue(monthly_df, cvr, aov, currency)
                rev_table = keyword_revenue_table(keyword_df, cvr, aov, currency)
            else:
                rev_table = None

            st.session_state["kw_results"] = {
                "keyword_df": keyword_df,
                "monthly_df": monthly_df,
                "scenarios": scenarios,
                "rev_table": rev_table,
                "enable_revenue": enable_revenue,
                "enable_scenarios": enable_scenarios,
                "currency": currency,
                "cvr": cvr,
                "aov": aov,
            }

# ── Results ──────────────────────────────────────────────────────────────────
if "kw_results" in st.session_state:
    r = st.session_state["kw_results"]
    keyword_df = r["keyword_df"]
    monthly_df = r["monthly_df"]

    tab_names = ["Traffic Projection", "Keyword Schedule"]
    if r["enable_revenue"]:
        tab_names.append("Revenue Analysis")
    if r["enable_scenarios"] and r["scenarios"]:
        tab_names.append("Scenario Comparison")
    tab_names.append("Export")

    tabs = st.tabs(tab_names)
    tab_idx = 0

    # ── Tab: Traffic Projection ──────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        # KPI cards
        total_visits = monthly_df["traffic"].sum()
        peak_traffic = monthly_df["traffic"].max()
        peak_month = int(monthly_df.loc[monthly_df["traffic"].idxmax(), "month"])
        n_ranking = keyword_df["will_rank"].sum()
        n_total = len(keyword_df)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Projected Visits", f"{total_visits:,}")
        c2.metric("Peak Monthly Traffic", f"{peak_traffic:,}")
        c3.metric("Month of Peak", f"Month {peak_month}")
        c4.metric("Keywords Ranking", f"{n_ranking} / {n_total}")

        fig = traffic_projection_chart(monthly_df)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Projected monthly organic traffic based on keyword targeting, DA, and content cadence.")

    # ── Tab: Keyword Schedule ────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        display_cols = [
            "rank", "keyword", "volume", "kd", "tier", "efficiency_score",
            "publish_month", "expected_position", "ctr", "estimated_monthly_traffic",
            "time_to_rank", "traffic_starts_month",
        ]
        display_df = keyword_df[display_cols].copy()
        display_df["efficiency_score"] = display_df["efficiency_score"].round(1)

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

        fig_kw = keyword_schedule_chart(keyword_df)
        st.plotly_chart(fig_kw, use_container_width=True)
        st.caption("Top keywords by estimated monthly traffic, coloured by difficulty tier.")

        # Wasted slots callout
        unlikely = keyword_df[~keyword_df["will_rank"]].head(5)
        if not unlikely.empty:
            st.warning("**Keywords unlikely to rank** — consider deferring these:")
            for _, row in unlikely.iterrows():
                st.markdown(f"- **{row['keyword']}** (KD: {row['kd']}, Volume: {row['volume']:,})")

    # ── Tab: Revenue Analysis ────────────────────────────────────────────
    if r["enable_revenue"]:
        with tabs[tab_idx]:
            tab_idx += 1
            sym = CURRENCY_SYMBOLS.get(r["currency"], "$")

            peak_rev = monthly_df["revenue"].max()
            total_rev = monthly_df["revenue"].sum()
            total_leads = monthly_df["leads"].sum()
            annual_rev = peak_rev * 12

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Monthly Revenue at Peak", f"{sym}{peak_rev:,.2f}")
            c2.metric("Annualised Revenue", f"{sym}{annual_rev:,.2f}")
            c3.metric("Total Leads", f"{total_leads:,}")
            c4.metric("Total Revenue", f"{sym}{total_rev:,.2f}")

            if r["rev_table"] is not None and not r["rev_table"].empty:
                st.subheader("Per-Keyword Revenue Breakdown")
                st.dataframe(r["rev_table"], use_container_width=True, hide_index=True)

            fig_rev = revenue_projection_chart(monthly_df, sym)
            st.plotly_chart(fig_rev, use_container_width=True)
            st.caption("Monthly revenue projection based on traffic, conversion rate, and average order value.")

    # ── Tab: Scenario Comparison ─────────────────────────────────────────
    if r["enable_scenarios"] and r["scenarios"]:
        with tabs[tab_idx]:
            tab_idx += 1

            # Comparison table
            rows = []
            for c_val, s_df in sorted(r["scenarios"].items()):
                kw_covered = min(len(keyword_df), c_val * months)
                peak_m = int(s_df.loc[s_df["traffic"].idxmax(), "month"]) if s_df["traffic"].max() > 0 else "-"
                rows.append({
                    "Cadence (posts/mo)": c_val,
                    "Keywords Covered": kw_covered,
                    "Peak Month": peak_m,
                    "Peak Traffic": f"{s_df['traffic'].max():,}",
                    "Total Visits": f"{s_df['traffic'].sum():,}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            fig_sc = scenario_comparison_chart(r["scenarios"])
            st.plotly_chart(fig_sc, use_container_width=True)
            st.caption("Traffic projection under different content production cadences.")

    # ── Tab: Export ──────────────────────────────────────────────────────
    with tabs[tab_idx]:
        ec1, ec2, ec3 = st.columns(3)

        with ec1:
            st.download_button(
                "Download Keyword Forecast CSV",
                to_csv(keyword_df),
                "keyword-forecast.csv",
                "text/csv",
            )
        with ec2:
            st.download_button(
                "Download Monthly Projection CSV",
                to_csv(monthly_df),
                "monthly-projection.csv",
                "text/csv",
            )
        with ec3:
            summary = {
                "Total Visits": f"{monthly_df['traffic'].sum():,}",
                "Peak Traffic": f"{monthly_df['traffic'].max():,}",
                "Keywords Ranking": f"{keyword_df['will_rank'].sum()} / {len(keyword_df)}",
            }
            figs = [traffic_projection_chart(monthly_df), keyword_schedule_chart(keyword_df)]
            html = to_html_report(figs, summary, "Keyword Forecast Report")
            st.download_button(
                "Download HTML Report",
                html,
                "forecast-report.html",
                "text/html",
            )
