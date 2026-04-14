import os
import streamlit as st
import pandas as pd

from engine.keyword_engine import run_keyword_forecast
from engine.combined_engine import run_combined_forecast
from engine.revenue_engine import add_revenue, CURRENCY_SYMBOLS
from utils.data_loader import load_keywords, load_traffic
from utils.chart_builder import combined_forecast_chart, revenue_projection_chart
from utils.export import to_csv, to_html_report

st.header("Combined Forecast")
st.caption("Layer new content projections onto your existing traffic baseline.")

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Combined Forecast Settings")

da = st.sidebar.slider("Domain Authority (DA)", 1, 100, 30, key="comb_da")
cadence = st.sidebar.number_input("Monthly Content Production", 1, 50, 4, key="comb_cadence")
months = st.sidebar.slider("Forecast Horizon (months)", 6, 36, 18, key="comb_months")
seed = st.sidebar.number_input("Random Seed", value=42, step=1, key="comb_seed")

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
enable_revenue = st.sidebar.checkbox("Enable Revenue Projection", key="comb_rev")
cvr = st.sidebar.number_input("Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1, key="comb_cvr", disabled=not enable_revenue)
aov = st.sidebar.number_input("Average Order Value", 1.0, 100000.0, 100.0, step=10.0, key="comb_aov", disabled=not enable_revenue)
currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="comb_cur", disabled=not enable_revenue)

# ── Upload ───────────────────────────────────────────────────────────────────
st.subheader("Upload Data")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Keywords CSV** (keyword, volume, kd)")
    kw_file = st.file_uploader("Upload keywords CSV", type=["csv"], key="comb_kw")
with col2:
    st.markdown("**Historical Traffic CSV** (date, traffic)")
    traffic_file = st.file_uploader("Upload traffic CSV", type=["csv"], key="comb_traffic")

use_sample = st.checkbox("Use sample data for both", key="comb_sample")

kw_df = None
traffic_df = None

if use_sample:
    base_path = os.path.dirname(os.path.dirname(__file__))
    kw_df = load_keywords(os.path.join(base_path, "assets", "sample-keywords.csv"))
    traffic_df = load_traffic(os.path.join(base_path, "assets", "sample-traffic.csv"))
else:
    if kw_file is not None:
        kw_df = load_keywords(kw_file)
    if traffic_file is not None:
        traffic_df = load_traffic(traffic_file)

if kw_df is not None:
    st.success(f"Keywords: {len(kw_df)} loaded")
if traffic_df is not None:
    st.success(f"Historical data: {len(traffic_df)} months loaded")

# ── Run Forecast ─────────────────────────────────────────────────────────────
if kw_df is not None and traffic_df is not None:
    if st.button("Generate Combined Forecast", type="primary", key="comb_run"):
        with st.spinner("Running combined forecast..."):
            keyword_df, monthly_kw_df = run_keyword_forecast(kw_df, da, cadence, months, seed)
            combined_df = run_combined_forecast(keyword_df, monthly_kw_df, traffic_df, months)

            st.session_state["comb_results"] = {
                "keyword_df": keyword_df,
                "combined_df": combined_df,
                "enable_revenue": enable_revenue,
                "currency": currency,
                "cvr": cvr,
                "aov": aov,
            }
elif kw_df is None and traffic_df is None and not use_sample:
    st.info("Upload both a keywords CSV and a historical traffic CSV to get started, or use sample data.")

# ── Results ──────────────────────────────────────────────────────────────────
if "comb_results" in st.session_state:
    r = st.session_state["comb_results"]
    combined_df = r["combined_df"]

    tab_names = ["Combined Chart", "Uplift Table"]
    if r["enable_revenue"]:
        tab_names.append("Revenue Analysis")
    tab_names.append("Export")

    tabs = st.tabs(tab_names)
    tab_idx = 0

    forecast_mask = combined_df["is_forecast"]
    forecast_df = combined_df[forecast_mask]

    # ── Tab: Combined Chart ──────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        # KPI cards
        baseline_end = int(forecast_df["baseline"].iloc[-1])
        combined_end = int(forecast_df["combined"].iloc[-1])
        incremental_total = int(forecast_df["new_content"].sum())
        uplift_end = (
            round((combined_end - baseline_end) / baseline_end * 100, 1)
            if baseline_end > 0 else 0
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Baseline (End)", f"{baseline_end:,}")
        c2.metric("Combined (End)", f"{combined_end:,}")
        c3.metric("Incremental Visits", f"{incremental_total:,}")
        c4.metric("Uplift at End", f"{uplift_end}%")

        fig = combined_forecast_chart(combined_df)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Solid line = actual + combined projection. Dashed grey = baseline without new content. Shaded area = incremental uplift from content.")

        # What if we do nothing?
        st.divider()
        st.subheader("What if we do nothing?")
        st.info(
            f"Without new content, your traffic is projected to reach **{baseline_end:,}** visits/month.\n\n"
            f"With new content at {r.get('cadence', 4)} posts/month, you could reach **{combined_end:,}** visits/month — "
            f"an uplift of **{uplift_end}%** ({incremental_total:,} incremental visits over the forecast period)."
        )

    # ── Tab: Uplift Table ────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        display_df = forecast_df[["date", "baseline", "new_content", "combined", "uplift_pct"]].copy()
        display_df["date"] = display_df["date"].dt.strftime("%b %Y")
        display_df = display_df.rename(columns={
            "date": "Month",
            "baseline": "Baseline",
            "new_content": "New Content",
            "combined": "Combined",
            "uplift_pct": "Uplift %",
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Tab: Revenue Analysis ────────────────────────────────────────────
    if r["enable_revenue"]:
        with tabs[tab_idx]:
            tab_idx += 1
            sym = CURRENCY_SYMBOLS.get(r["currency"], "$")

            rev_df = forecast_df.copy()
            rev_df = rev_df.rename(columns={"new_content": "traffic"})
            rev_df = add_revenue(rev_df, r["cvr"], r["aov"], r["currency"])

            new_content_rev = rev_df["revenue"].sum()
            new_content_leads = rev_df["leads"].sum()
            peak_rev = rev_df["revenue"].max()

            c1, c2, c3 = st.columns(3)
            c1.metric("Revenue from New Content", f"{sym}{new_content_rev:,.2f}")
            c2.metric("Leads from New Content", f"{new_content_leads:,}")
            c3.metric("Peak Monthly Revenue", f"{sym}{peak_rev:,.2f}")

            fig_rev = revenue_projection_chart(rev_df, sym)
            st.plotly_chart(fig_rev, use_container_width=True)
            st.caption("Revenue projection from incremental new content traffic only.")

    # ── Tab: Export ──────────────────────────────────────────────────────
    with tabs[tab_idx]:
        ec1, ec2 = st.columns(2)
        with ec1:
            st.download_button(
                "Download Combined Forecast CSV",
                to_csv(combined_df),
                "combined-forecast.csv",
                "text/csv",
            )
        with ec2:
            summary = {
                "Baseline (End)": f"{baseline_end:,}",
                "Combined (End)": f"{combined_end:,}",
                "Uplift": f"{uplift_end}%",
            }
            figs = [combined_forecast_chart(combined_df)]
            html = to_html_report(figs, summary, "Combined Forecast Report")
            st.download_button(
                "Download HTML Report",
                html,
                "combined-report.html",
                "text/html",
            )
