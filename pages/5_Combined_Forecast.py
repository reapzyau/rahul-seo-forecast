import streamlit as st
import pandas as pd

from engine.combined_engine import run_combined_forecast
from engine.decay_engine import calculate_portfolio_decay
from engine.revenue_engine import (
    CURRENCY_SYMBOLS,
    INTENT_CVR_MULTIPLIERS,
    compute_intent_weighted_cvr,
    intent_revenue_breakdown,
)
from utils.chart_builder import combined_three_stream_chart, combined_revenue_chart
from utils.export import to_csv, to_html_report
from utils.sidebar import render_ai_settings
from utils.assumptions_panel import render_assumptions_banner
from engine.assumptions import initialise_assumptions, get_assumption

st.header("Combined Forecast")
st.caption("Layer multiple forecast streams into a single projection with intent-weighted revenue.")

render_ai_settings()

store = st.session_state.setdefault("assumptions", {})
initialise_assumptions(store)
render_assumptions_banner(store)

# ── Data Availability ──────────────────────────────────────────────────────
ga4_df = st.session_state.get("ga4_df")
pos_result = st.session_state.get("pos_result")
nc_result = st.session_state.get("kw_results")

has_ga4 = ga4_df is not None
has_positional = (
    pos_result is not None
    and pos_result.get("monthly") is not None
    and not pos_result["monthly"].empty
)
has_new_content = (
    nc_result is not None
    and nc_result.get("monthly_df") is not None
    and not nc_result["monthly_df"].empty
)

if not has_ga4 and not has_positional and not has_new_content:
    st.info(
        "Load data on **Data Upload**, then run at least one forecast:\n\n"
        "- **Positional Forecast** — uplift from improving existing rankings\n"
        "- **New Content Forecast** — traffic from new keyword-targeting pages\n\n"
        "Come back here to combine them."
    )
    st.stop()

# ── Data Status ────────────────────────────────────────────────────────────
st.subheader("Available Data")
c1, c2, c3 = st.columns(3)

ga4_has_revenue = has_ga4 and "revenue" in ga4_df.columns

with c1:
    if has_ga4:
        extras = []
        if ga4_has_revenue:
            extras.append("revenue")
        if "transactions" in ga4_df.columns:
            extras.append("transactions")
        if "aov" in ga4_df.columns:
            extras.append("AOV")
        detail = f" ({', '.join(extras)})" if extras else ""
        st.success(f"GA4: {len(ga4_df)} months{detail}")
    else:
        st.info("GA4: Not loaded")

with c2:
    if has_positional:
        n = len(pos_result.get("keyword_df", []))
        st.success(f"Positional: {n:,} keywords")
    else:
        st.info("Positional: Not yet run")

with c3:
    if has_new_content:
        n = len(nc_result.get("keyword_df", []))
        st.success(f"New Content: {n:,} keywords")
    else:
        st.info("New Content: Not yet run")

# ── Stream Selection ───────────────────────────────────────────────────────
st.subheader("What would you like to combine?")

include_baseline = st.checkbox(
    "Historical Baseline — do-nothing trajectory from GA4 trend",
    value=has_ga4,
    disabled=not has_ga4,
    key="comb_inc_baseline",
)
include_positional = st.checkbox(
    "Positional Uplift — traffic gain from improving existing rankings",
    value=has_positional,
    disabled=not has_positional,
    key="comb_inc_pos",
)
include_new_content = st.checkbox(
    "New Content — traffic from publishing new keyword-targeting pages",
    value=has_new_content,
    disabled=not has_new_content,
    key="comb_inc_nc",
)

if not include_baseline and not include_positional and not include_new_content:
    st.info("Select at least one stream above.")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.header("Combined Forecast Settings")
months = st.sidebar.slider("Forecast Horizon (months)", 6, 36, 12, key="comb_months")

st.sidebar.divider()
st.sidebar.subheader("Revenue Settings")
enable_revenue = st.sidebar.checkbox("Enable Revenue Projection", value=True, key="comb_rev")

# Pre-populate CVR and AOV from GA4 actuals
default_cvr = 2.5
default_aov = 100.0
default_cur_idx = 0

if has_ga4:
    if "cr" in ga4_df.columns:
        avg_cr = ga4_df["cr"].dropna().mean()
        if avg_cr > 0:
            default_cvr = round(float(avg_cr), 2)
    if "aov" in ga4_df.columns:
        avg_aov = ga4_df["aov"].dropna().mean()
        if avg_aov > 0:
            default_aov = round(float(avg_aov), 2)

currency_keys = list(CURRENCY_SYMBOLS.keys())
if "AUD" in currency_keys:
    default_cur_idx = currency_keys.index("AUD")

cvr = st.sidebar.number_input(
    "Base Conversion Rate (%)", 0.1, 100.0, default_cvr, step=0.1,
    key="comb_cvr", disabled=not enable_revenue,
)
aov = st.sidebar.number_input(
    "Average Order Value", 1.0, 100000.0, default_aov, step=10.0,
    key="comb_aov", disabled=not enable_revenue,
)
currency = st.sidebar.selectbox(
    "Currency", currency_keys, index=default_cur_idx,
    key="comb_cur", disabled=not enable_revenue,
)

if enable_revenue:
    if ga4_has_revenue:
        st.sidebar.caption("CVR and AOV pre-populated from GA4 actuals.")
    st.sidebar.caption(
        "Revenue uses intent-weighted conversion: "
        "commercial/transactional keywords convert higher than informational."
    )
    with st.sidebar.expander("Intent CVR Multipliers"):
        for intent, mult in INTENT_CVR_MULTIPLIERS.items():
            st.text(f"  {intent.title()}: {mult}x base CVR")

st.sidebar.divider()
st.sidebar.subheader("Keyword Decay")
include_decay = st.sidebar.checkbox(
    "Model keyword decay (unmaintained pages)", value=True, key="comb_decay",
)
maintenance_coverage = st.sidebar.slider(
    "Maintenance coverage", 0.0, 1.0, 0.0, 0.1,
    key="comb_maint", disabled=not include_decay,
)
st.sidebar.caption(
    "AIO erosion is applied per-stream inside the Positional and New Content forecasts "
    "as a CTR penalty. Run those pages with AIO settings to include it."
)

# ── Generate ───────────────────────────────────────────────────────────────
if st.button("Generate Combined Forecast", type="primary", key="comb_run"):
    with st.spinner("Running combined forecast..."):
        historical_df = ga4_df if include_baseline else None

        pos_monthly = None
        pos_keyword_df = None
        if include_positional and pos_result:
            pos_monthly = pos_result["monthly"]
            pos_keyword_df = pos_result.get("keyword_df")

        nc_monthly = None
        nc_keyword_df = None
        if include_new_content and nc_result:
            nc_monthly = nc_result["monthly_df"]
            nc_keyword_df = nc_result.get("keyword_df")

        decay_df = None
        if include_decay:
            kw_for_decay = st.session_state.get("kw_existing")
            if kw_for_decay is not None and not kw_for_decay.empty:
                decay_df = calculate_portfolio_decay(
                    kw_for_decay, months, maintenance_coverage=maintenance_coverage,
                )

        combined_df = run_combined_forecast(
            historical_df=historical_df,
            positional_monthly=pos_monthly,
            new_content_monthly=nc_monthly,
            months=months,
            decay_df=decay_df,
        )

        # Build merged keyword set for intent-weighted revenue
        all_kw = []
        if pos_keyword_df is not None and not pos_keyword_df.empty:
            all_kw.append(pos_keyword_df)
        if nc_keyword_df is not None and not nc_keyword_df.empty:
            all_kw.append(nc_keyword_df)

        intent_cvr = cvr
        intent_breakdown = pd.DataFrame()
        if all_kw and enable_revenue:
            merged_kw = pd.concat(all_kw, ignore_index=True)
            intent_cvr = compute_intent_weighted_cvr(merged_kw, cvr)
            intent_breakdown = intent_revenue_breakdown(merged_kw, cvr, aov)

        # Revenue per session from GA4 for baseline projection
        ga4_rev_per_session = None
        if ga4_has_revenue and include_baseline:
            total_rev = ga4_df["revenue"].sum()
            total_traffic = ga4_df["traffic"].sum()
            if total_traffic > 0:
                ga4_rev_per_session = total_rev / total_traffic

        st.session_state["comb_results"] = {
            "combined_df": combined_df,
            "include_baseline": include_baseline,
            "include_positional": include_positional,
            "include_new_content": include_new_content,
            "enable_revenue": enable_revenue,
            "currency": currency,
            "cvr": cvr,
            "intent_cvr": intent_cvr,
            "aov": aov,
            "months": months,
            "intent_breakdown": intent_breakdown,
            "ga4_rev_per_session": ga4_rev_per_session,
            "decay_df": decay_df,
        }

# ── Results ────────────────────────────────────────────────────────────────
if "comb_results" in st.session_state:
    r = st.session_state["comb_results"]
    combined_df = r["combined_df"]
    forecast_mask = combined_df["is_forecast"]
    forecast_df = combined_df[forecast_mask]

    has_bands = "combined_p50" in combined_df.columns
    combined_col = "combined_p50" if has_bands else "combined"
    pos_col = "positional_uplift_p50" if has_bands else "positional_uplift"

    baseline_end = int(forecast_df["baseline"].iloc[-1])
    combined_end = int(forecast_df[combined_col].iloc[-1])
    pos_total = int(forecast_df[pos_col].sum())
    nc_total = int(forecast_df["new_content_uplift"].sum())
    total_decay = int(forecast_df["decay"].sum()) if "decay" in forecast_df.columns else 0
    total_aio = 0  # AIO is now per-stream; no longer tracked at combined level
    uplift_end = (
        round((combined_end - baseline_end) / baseline_end * 100, 1)
        if baseline_end > 0 else 0
    )

    tab_names = ["\U0001f4ca Combined Chart", "\U0001f4cb Uplift Table"]
    if r["enable_revenue"]:
        tab_names.append("\U0001f4b0 Revenue Analysis")
    tab_names.append("\U0001f4e5 Export")
    tabs = st.tabs(tab_names)
    tab_idx = 0

    # ── Tab: Combined Chart ─────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Baseline (End)", f"{baseline_end:,}")
        c2.metric("Combined (End)", f"{combined_end:,}")
        c3.metric("Positional Uplift", f"{pos_total:,}")
        c4.metric("Uplift at End", f"{uplift_end}%")

        fig = combined_three_stream_chart(combined_df)
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        streams_desc = []
        if r["include_baseline"]:
            streams_desc.append("historical baseline")
        if r["include_positional"]:
            streams_desc.append(f"positional uplift (**{pos_total:,}** visits)")
        if r["include_new_content"]:
            streams_desc.append(f"new content (**{nc_total:,}** visits)")
        if total_decay > 0:
            streams_desc.append(f"keyword decay (**-{total_decay:,}** visits)")
        streams_desc.append("AIO impact baked into positional/new-content streams")
        band_note = ""
        if has_bands:
            p10_end = int(forecast_df["combined_p10"].iloc[-1])
            p90_end = int(forecast_df["combined_p90"].iloc[-1])
            band_note = f"\n\nP10/P90 range at end: **{p10_end:,}** — **{p90_end:,}** visits/month."
        st.info(
            f"Combined projection using: {', '.join(streams_desc)}.\n\n"
            f"Projected end traffic: **{combined_end:,}** visits/month"
            + (f" — **{uplift_end}%** uplift over baseline." if baseline_end > 0 else ".")
            + band_note
        )

    # ── Tab: Uplift Table ───────────────────────────────────────────
    with tabs[tab_idx]:
        tab_idx += 1

        table_cols = ["date", "baseline", pos_col, "new_content_uplift"]
        rename_map = {
            "date": "Month",
            "baseline": "Baseline",
            pos_col: "Positional",
            "new_content_uplift": "New Content",
        }
        if "decay" in forecast_df.columns and total_decay > 0:
            table_cols.append("decay")
            rename_map["decay"] = "Decay"
        table_cols += [combined_col, "uplift_pct"]
        rename_map[combined_col] = "Combined"
        rename_map["uplift_pct"] = "Uplift %"
        if has_bands:
            table_cols += ["combined_p10", "combined_p90"]
            rename_map["combined_p10"] = "P10"
            rename_map["combined_p90"] = "P90"

        display_df = forecast_df[table_cols].copy()
        display_df["date"] = display_df["date"].dt.strftime("%b %Y")
        display_df = display_df.rename(columns=rename_map)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Tab: Revenue Analysis ───────────────────────────────────────
    if r["enable_revenue"]:
        with tabs[tab_idx]:
            tab_idx += 1
            sym = CURRENCY_SYMBOLS.get(r["currency"], "$")
            rev_per_session = r.get("ga4_rev_per_session")
            intent_cvr = r["intent_cvr"]
            base_cvr = r["cvr"]
            base_aov = r["aov"]

            rev_df = forecast_df.copy()

            # Baseline revenue: use GA4 revenue-per-session if available
            if rev_per_session and rev_per_session > 0:
                rev_df["baseline_revenue"] = (rev_df["baseline"] * rev_per_session).round(2)
            else:
                rev_df["baseline_revenue"] = (
                    rev_df["baseline"] * (base_cvr / 100) * base_aov
                ).round(2)

            # Uplift revenue: intent-weighted CVR
            uplift_traffic = rev_df["positional_uplift"] + rev_df["new_content_uplift"]
            rev_df["uplift_revenue"] = (
                uplift_traffic * (intent_cvr / 100) * base_aov
            ).round(2)

            rev_df["combined_revenue"] = (
                rev_df["baseline_revenue"] + rev_df["uplift_revenue"]
            )

            total_baseline_rev = rev_df["baseline_revenue"].sum()
            total_uplift_rev = rev_df["uplift_revenue"].sum()
            total_combined_rev = rev_df["combined_revenue"].sum()
            peak_monthly_rev = rev_df["combined_revenue"].max()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Baseline Revenue", f"{sym}{total_baseline_rev:,.0f}")
            c2.metric("Uplift Revenue", f"{sym}{total_uplift_rev:,.0f}")
            c3.metric("Combined Revenue", f"{sym}{total_combined_rev:,.0f}")
            c4.metric("Peak Monthly", f"{sym}{peak_monthly_rev:,.0f}")

            fig_rev = combined_revenue_chart(rev_df, sym)
            st.plotly_chart(fig_rev, use_container_width=True)

            # Intent breakdown table
            breakdown = r.get("intent_breakdown")
            if isinstance(breakdown, pd.DataFrame) and not breakdown.empty:
                st.divider()
                st.subheader("Revenue by Keyword Intent")
                st.caption(
                    f"Base CVR: {base_cvr:.2f}% — "
                    f"Intent-weighted blended CVR: {intent_cvr:.2f}%"
                )
                st.dataframe(breakdown, use_container_width=True, hide_index=True)

            st.divider()
            method_baseline = (
                f"GA4 revenue/session ({sym}{rev_per_session:.2f})"
                if rev_per_session
                else f"CVR ({base_cvr:.2f}%) x AOV ({sym}{base_aov:,.2f})"
            )
            st.info(
                f"**How revenue is calculated:**\n\n"
                f"- **Baseline revenue**: {method_baseline}\n"
                f"- **Uplift revenue**: Intent-weighted CVR ({intent_cvr:.2f}%) "
                f"x AOV ({sym}{base_aov:,.2f})\n"
                f"- Commercial/transactional keywords convert at 1.5–2x; "
                f"informational at 0.3x"
            )

    # ── Tab: Export ──────────────────────────────────────────────────
    with tabs[tab_idx]:
        ec1, ec2 = st.columns(2)
        with ec1:
            st.download_button(
                "Download Combined Forecast CSV",
                to_csv(combined_df),
                "combined-forecast.csv",
                "text/csv",
                key="comb_dl_csv",
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
                key="comb_dl_html",
            )
