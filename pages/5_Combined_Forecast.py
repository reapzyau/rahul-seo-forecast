import os
import streamlit as st
import pandas as pd

from engine.new_content_engine import run_new_content_forecast
from engine.combined_engine import run_combined_forecast
from engine.revenue_engine import add_revenue, CURRENCY_SYMBOLS
from utils.data_loader import load_keywords, load_traffic
from utils.chart_builder import combined_three_stream_chart, combined_scenario_chart, revenue_projection_chart
from utils.export import to_csv, to_html_report, keyword_template_csv, traffic_template_csv
from engine.constants import SITE_PRESETS, CTR_MODELS, FORECAST_SCENARIOS
from utils.sidebar import render_ai_settings

st.header("Combined Forecast")
st.caption("Layer historical baseline + positional uplift + new content into a single projection.")

render_ai_settings()

# Pre-populate revenue inputs from file data on the run after upload
if st.session_state.get("_comb_update_revenue"):
    metrics = st.session_state.pop("_comb_update_revenue")
    if "aov" in metrics:
        st.session_state["comb_aov"] = metrics["aov"]
    if "cvr" in metrics:
        st.session_state["comb_cvr"] = metrics["cvr"]

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Combined Forecast Settings")

# Site Profile Presets
st.sidebar.subheader("Site Profile")
preset_name = st.sidebar.selectbox(
    "Site Profile Preset",
    list(SITE_PRESETS.keys()),
    key="comb_preset",
    help="Select a preset to auto-fill DA, cadence, and horizon.",
)
preset = SITE_PRESETS[preset_name]

da = st.sidebar.slider("Domain Authority (DA)", 1, 100, preset["da"], key="comb_da")
cadence = st.sidebar.number_input("Monthly Content Production", 1, 50, preset["cadence"], key="comb_cadence")
months = st.sidebar.slider("Forecast Horizon (months)", 6, 36, preset["months"], key="comb_months")
seed = st.sidebar.number_input("Random Seed", value=42, step=1, key="comb_seed")

st.sidebar.divider()

# CTR Model & Forecast Scenario
st.sidebar.subheader("Forecast Model")
ctr_model_name = st.sidebar.selectbox(
    "CTR Model",
    list(CTR_MODELS.keys()),
    key="comb_ctr_model",
    help="Standard = traditional CTR. AI-Adjusted = lower CTR reflecting AI Overviews impact.",
)
scenario_name = st.sidebar.selectbox(
    "Forecast Scenario",
    list(FORECAST_SCENARIOS.keys()),
    index=1,  # Default to Moderate
    key="comb_scenario",
    help="Conservative (0.7x), Moderate (1.0x), or Aggressive (1.3x) traffic multiplier.",
)

ctr_model = CTR_MODELS[ctr_model_name]
traffic_multiplier = FORECAST_SCENARIOS[scenario_name]["traffic_multiplier"]

st.sidebar.divider()

# AI Traffic Adjustment
st.sidebar.subheader("AI Traffic Adjustment")
filter_informational = st.sidebar.checkbox(
    "Filter Informational Keywords",
    key="comb_filter_info",
    help="Reduce impact of informational keywords that are losing CTR to AI Overviews.",
)

exclude_informational = False
informational_ctr_penalty = 0.0

if filter_informational:
    filter_mode = st.sidebar.radio(
        "Filter Mode",
        ["Exclude from forecast entirely", "Apply CTR penalty"],
        key="comb_filter_mode",
    )
    if filter_mode == "Exclude from forecast entirely":
        exclude_informational = True
    else:
        informational_ctr_penalty = st.sidebar.slider(
            "CTR Penalty (%)",
            10, 80, 40,
            key="comb_ctr_penalty",
            help="Reduce informational keyword CTR by this percentage.",
        )

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
enable_revenue = st.sidebar.checkbox("Enable Revenue Projection", key="comb_rev")
cvr = st.sidebar.number_input("Conversion Rate (%)", 0.1, 100.0, 2.5, step=0.1, key="comb_cvr", disabled=not enable_revenue)
aov = st.sidebar.number_input("Average Order Value", 1.0, 100000.0, 100.0, step=10.0, key="comb_aov", disabled=not enable_revenue)
currency = st.sidebar.selectbox("Currency", list(CURRENCY_SYMBOLS.keys()), key="comb_cur", disabled=not enable_revenue)

st.sidebar.divider()
st.sidebar.subheader("Scenario Comparison")
enable_scenarios = st.sidebar.checkbox("Compare Multiple Cadences", key="comb_scenarios")
cadence_options = st.sidebar.multiselect(
    "Cadences to compare",
    [1, 2, 4, 6, 8, 12],
    default=[2, 4, 8],
    key="comb_cadence_opts",
    disabled=not enable_scenarios,
)

# ── Upload ───────────────────────────────────────────────────────────────────
st.subheader("Upload Data")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Keywords CSV** (keyword, volume, kd)")
    kw_file = st.file_uploader("Upload keywords file", type=["csv", "tsv", "xlsx", "xls"], key="comb_kw")
    st.download_button(
        "Download Keywords Template",
        keyword_template_csv(),
        "keyword-template.csv",
        "text/csv",
        key="comb_kw_template_dl",
    )
with col2:
    st.markdown("**Historical Traffic CSV** (date, traffic)")
    traffic_file = st.file_uploader("Upload traffic file", type=["csv", "tsv", "xlsx", "xls"], key="comb_traffic")
    st.download_button(
        "Download Traffic Template",
        traffic_template_csv(),
        "traffic-template.csv",
        "text/csv",
        key="comb_traffic_template_dl",
    )

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
        if traffic_df is not None:
            metrics = {}
            if "aov" in traffic_df.columns:
                avg_aov = round(float(traffic_df["aov"].dropna().mean()), 2)
                if avg_aov > 0:
                    metrics["aov"] = avg_aov
            if "transactions" in traffic_df.columns and traffic_df["traffic"].sum() > 0:
                cvr = round((traffic_df["transactions"].sum() / traffic_df["traffic"].sum()) * 100, 2)
                metrics["cvr"] = cvr
            if metrics:
                st.session_state["_comb_update_revenue"] = metrics
                st.rerun()

if kw_df is not None:
    st.success(f"Keywords: {len(kw_df)} loaded")
if traffic_df is not None:
    st.success(f"Historical data: {len(traffic_df)} months loaded")

# ── Run Forecast ─────────────────────────────────────────────────────────────
if kw_df is not None and traffic_df is not None:
    if st.button("Generate Combined Forecast", type="primary", key="comb_run"):
        with st.spinner("Running combined forecast..."):
            keyword_df, monthly_kw_df = run_new_content_forecast(
                kw_df, da, cadence, months, seed,
                ctr_model=ctr_model,
                traffic_multiplier=traffic_multiplier,
                include_informational=not exclude_informational,
                ai_overview_ctr_penalty=informational_ctr_penalty,
            )

            pos_monthly = st.session_state.get("pos_result", {}).get("monthly")

            combined_df = run_combined_forecast(
                historical_df=traffic_df,
                positional_monthly=pos_monthly,
                new_content_monthly=monthly_kw_df,
                months=months,
            )

            # Run scenarios if enabled
            scenarios = {}
            if enable_scenarios and cadence_options:
                for c in cadence_options:
                    _, s_monthly = run_new_content_forecast(
                        kw_df, da, c, months, seed,
                        ctr_model=ctr_model,
                        traffic_multiplier=traffic_multiplier,
                        include_informational=not exclude_informational,
                        ai_overview_ctr_penalty=informational_ctr_penalty,
                    )
                    s_combined = run_combined_forecast(
                        historical_df=traffic_df,
                        positional_monthly=pos_monthly,
                        new_content_monthly=s_monthly,
                        months=months,
                    )
                    scenarios[c] = s_combined

            st.session_state["comb_results"] = {
                "keyword_df": keyword_df,
                "combined_df": combined_df,
                "enable_revenue": enable_revenue,
                "enable_scenarios": enable_scenarios,
                "scenarios": scenarios,
                "currency": currency,
                "cvr": cvr,
                "aov": aov,
                "cadence": cadence,
                "da": da,
                "months": months,
            }
elif kw_df is None and traffic_df is None and not use_sample:
    st.info("Upload both a keywords CSV and a historical traffic CSV to get started, or use sample data.")

# ── Results ──────────────────────────────────────────────────────────────────
if "comb_results" in st.session_state:
    r = st.session_state["comb_results"]
    combined_df = r["combined_df"]

    tab_names = ["\U0001f4ca Combined Chart", "\U0001f4cb Uplift Table"]
    if r["enable_revenue"]:
        tab_names.append("\U0001f4b0 Revenue Analysis")
    if r.get("enable_scenarios") and r.get("scenarios"):
        tab_names.append("\U0001f504 Scenario Comparison")
    tab_names.append("\U0001f4e5 Export")

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
        pos_total = int(forecast_df["positional_uplift"].sum())
        nc_total = int(forecast_df["new_content_uplift"].sum())
        uplift_end = (
            round((combined_end - baseline_end) / baseline_end * 100, 1)
            if baseline_end > 0 else 0
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Baseline (End)", f"{baseline_end:,}")
        c2.metric("Combined (End)", f"{combined_end:,}")
        c3.metric("Positional Uplift", f"{pos_total:,}")
        c4.metric("Uplift at End", f"{uplift_end}%")

        fig = combined_three_stream_chart(combined_df)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Stacked streams: baseline (grey) + positional uplift (blue) + new content (green). Historical actuals shown as solid black line.")

        # What if we do nothing?
        st.divider()
        st.subheader("What if we do nothing?")
        st.info(
            f"Without SEO work, your traffic is projected to reach **{baseline_end:,}** visits/month.\n\n"
            f"With positional improvements (**{pos_total:,}** incremental) and new content at "
            f"{r.get('cadence', 4)} posts/month (**{nc_total:,}** incremental), you could reach "
            f"**{combined_end:,}** visits/month — an uplift of **{uplift_end}%**."
        )

    # ── Tab: Uplift Table ────────────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        display_df = forecast_df[["date", "baseline", "positional_uplift", "new_content_uplift", "combined", "uplift_pct"]].copy()
        display_df["date"] = display_df["date"].dt.strftime("%b %Y")
        display_df = display_df.rename(columns={
            "date": "Month",
            "baseline": "Baseline",
            "positional_uplift": "Positional",
            "new_content_uplift": "New Content",
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
            rev_df["traffic"] = rev_df["positional_uplift"] + rev_df["new_content_uplift"]
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

    # ── Tab: Scenario Comparison ─────────────────────────────────────────
    if r.get("enable_scenarios") and r.get("scenarios"):
        with tabs[tab_idx]:
            tab_idx += 1

            # Comparison table
            rows = []
            for c_val, s_df in sorted(r["scenarios"].items()):
                s_forecast = s_df[s_df["is_forecast"]]
                kw_covered = min(len(r["keyword_df"]), c_val * r.get("months", 18))
                peak_combined = int(s_forecast["combined"].max())
                total_incremental = int(s_forecast["positional_uplift"].sum() + s_forecast["new_content_uplift"].sum())
                baseline_end = int(s_forecast["baseline"].iloc[-1])
                combined_end = int(s_forecast["combined"].iloc[-1])
                uplift = round((combined_end - baseline_end) / baseline_end * 100, 1) if baseline_end > 0 else 0
                rows.append({
                    "Cadence (posts/mo)": c_val,
                    "Keywords Covered": kw_covered,
                    "Peak Combined Traffic": f"{peak_combined:,}",
                    "Total Incremental Visits": f"{total_incremental:,}",
                    "End Uplift %": f"{uplift}%",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            fig_sc = combined_scenario_chart(r["scenarios"])
            st.plotly_chart(fig_sc, use_container_width=True)
            st.caption("Combined traffic projection under different content production cadences.")

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
            figs = [combined_three_stream_chart(combined_df)]
            html = to_html_report(figs, summary, "Combined Forecast Report")
            st.download_button(
                "Download HTML Report",
                html,
                "combined-report.html",
                "text/html",
            )
