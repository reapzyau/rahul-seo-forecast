import io
import os

import plotly.graph_objects as go
import streamlit as st

from engine.assumptions import get_assumption, override_assumption, run_detection
from engine.seasonality_engine import (
    DEFAULT_SEASONALITY,
    learn_seasonality_from_ga4,
    seasonality_for_portfolio,
)
from engine.v5.ga4_extractor import extract_organic_metrics, summarize_for_methodology
from utils.assumptions_panel import render_assumptions_banner, render_assumptions_panel
from utils.chart_builder import _apply_layout
from utils.design_tokens import PRIMARY, SLATE_400
from utils.ga4_loader import load_ga4_organic
from utils.page_base import setup_page
from utils.session import (
    GA4_DF,
    KW_DF,
    KW_EXISTING,
    LEARNED_SEASONALITY,
    ROADMAP_BUNDLE,
    ROADMAP_DATA,
    SEASONALITY,
)

store = setup_page(
    "GA4 Organic Traffic",
    "Upload your GA4 organic export. Seasonality is learned from this data and applied to all forecast streams.",
    show_assumptions_banner=False,
)

uploaded_ga4 = st.file_uploader(
    "Upload GA4 organic export",
    type=["xlsx", "xls"],
    key="ga4_upload",
)
use_ga4_sample = st.checkbox("Use sample data (Cable Melbourne)", key="ga4_sample")

ga4_df = None
ga4_metrics = None
if uploaded_ga4 is not None:
    raw_bytes = uploaded_ga4.read()
    ga4_df = load_ga4_organic(io.BytesIO(raw_bytes))
    ga4_metrics = extract_organic_metrics(io.BytesIO(raw_bytes))
elif use_ga4_sample:
    sample_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "sample-ga4-organic.xlsx"
    )
    ga4_df = load_ga4_organic(sample_path)
    ga4_metrics = extract_organic_metrics(sample_path)

if ga4_df is not None:
    st.session_state[GA4_DF] = ga4_df
    run_detection(store, ga4_df=ga4_df)

    # ── Seasonality Detection ─────────────────────────────────────
    seasonality_dict, season_meta = seasonality_for_portfolio(ga4_df)
    source = season_meta["source"]
    blend_weight = season_meta["blend_weight"]
    n_months = season_meta["months_available"]

    st.session_state[SEASONALITY] = seasonality_dict
    st.session_state[LEARNED_SEASONALITY] = learn_seasonality_from_ga4(ga4_df)
    override_assumption(store, "seasonality_source", source, f"GA4 data ({n_months} months)")
    override_assumption(store, "seasonality_blend_weight", blend_weight, f"GA4 data ({n_months} months)")

    date_min = ga4_df["date"].min()
    date_max = ga4_df["date"].max()
    st.success(
        f"{len(ga4_df)} months loaded ({date_min.strftime('%b %Y')} – {date_max.strftime('%b %Y')})"
    )

    # KPI cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Months", f"{len(ga4_df)}")
    c2.metric("Latest Traffic", f"{ga4_df['traffic'].iloc[-1]:,}")
    c3.metric("Avg Traffic", f"{ga4_df['traffic'].mean():,.0f}")
    c4.metric("Date Range", f"{date_min.strftime('%b %Y')} – {date_max.strftime('%b %Y')}")

    # Revenue / transactions KPIs if present
    has_revenue = "revenue" in ga4_df.columns
    has_transactions = "transactions" in ga4_df.columns
    if has_revenue or has_transactions:
        extra_cols = st.columns(4)
        col_idx = 0
        if has_revenue:
            extra_cols[col_idx].metric(
                "Total Revenue", f"${ga4_df['revenue'].sum():,.2f}"
            )
            col_idx += 1
            extra_cols[col_idx].metric(
                "Avg Monthly Revenue", f"${ga4_df['revenue'].mean():,.2f}"
            )
            col_idx += 1
        if has_transactions:
            extra_cols[col_idx].metric(
                "Total Transactions", f"{ga4_df['transactions'].sum():,}"
            )
            col_idx += 1

    # Traffic line chart
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ga4_df["date"],
            y=ga4_df["traffic"],
            mode="lines+markers",
            name="Organic Traffic",
            line=dict(color=PRIMARY, width=3),
            hovertemplate="%{x|%b %Y}<br>Traffic: %{y:,.0f}<extra></extra>",
        )
    )
    fig = _apply_layout(fig, "Monthly Organic Traffic", "Date", "Sessions")
    st.plotly_chart(fig, use_container_width=True)

    # ── Channel-level CR / AOV from v5 extractor ─────────────────
    st.divider()
    st.subheader("Organic Search Metrics")

    if ga4_metrics is not None and not ga4_metrics.get("warnings"):
        cr_organic = ga4_metrics["cr_organic"]
        cr_blended = ga4_metrics["cr_blended"]
        aov_organic = ga4_metrics["aov_organic"]
        aov_blended = ga4_metrics["aov_blended"]
        cr_ratio = ga4_metrics.get("cr_ratio")

        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Organic Search CR",
            f"{cr_organic * 100:.2f}%",
            delta=f"{(cr_organic - cr_blended) * 100:+.2f}% vs blended",
        )
        m2.metric(
            "Organic AOV",
            f"${aov_organic:,.2f}",
            delta=f"${aov_organic - aov_blended:+,.2f} vs blended",
        )
        m3.metric(
            "CR Ratio (organic / blended)",
            f"{cr_ratio:.2f}x" if cr_ratio is not None else "—",
            help="< 1 means organic converts below blended average; > 1 means above.",
        )

        st.session_state["cr_organic"] = cr_organic
        st.session_state["cr_blended"] = cr_blended
        st.session_state["aov_organic"] = aov_organic
        st.session_state["aov_blended"] = aov_blended
        st.session_state["ga4_metrics_summary"] = summarize_for_methodology(ga4_metrics)

        with st.expander("Monthly CR breakdown"):
            cbm = ga4_metrics.get("cr_by_month")
            if cbm is not None and not cbm.empty:
                display_cbm = cbm.copy()
                for col in ["cr_organic", "cr_blended"]:
                    if col in display_cbm.columns:
                        display_cbm[col] = (display_cbm[col] * 100).round(3).astype(str) + "%"
                st.dataframe(display_cbm, use_container_width=True)

    else:
        if ga4_metrics is not None and ga4_metrics.get("warnings"):
            st.warning(
                "Channel breakdown not found in this GA4 export — "
                "the 'Session default channel group' column is missing. "
                "Enter Organic CR and AOV manually below."
            )
        else:
            st.info("Upload a GA4 export to auto-detect Organic Search CR and AOV.")

        col_a, col_b = st.columns(2)
        manual_cr = col_a.number_input(
            "Organic Conversion Rate (%)", min_value=0.01, max_value=100.0,
            value=float(st.session_state.get("cr_organic", 0.0) * 100 or 1.5),
            step=0.01, key="ga4_manual_cr",
        )
        manual_aov = col_b.number_input(
            "Organic AOV ($)", min_value=1.0, max_value=1_000_000.0,
            value=float(st.session_state.get("aov_organic") or 100.0),
            step=1.0, key="ga4_manual_aov",
        )
        st.session_state["cr_organic"] = manual_cr / 100.0
        st.session_state["aov_organic"] = manual_aov

elif uploaded_ga4 is not None:
    st.error("Could not parse the uploaded GA4 file. Please check the format.")

# ── Seasonality Tuning ────────────────────────────────────────────────────
st.divider()
st.subheader("Seasonality Tuning")
st.caption(
    "Monthly modifiers applied to all forecast streams. "
    "Auto-detected from GA4 when ≥12 months available; "
    "falls back to AU retail defaults otherwise."
)

seasonality = st.session_state.get(SEASONALITY, DEFAULT_SEASONALITY)
learned_seasonality = st.session_state.get(LEARNED_SEASONALITY)
source = get_assumption(store, "seasonality_source")
blend_weight = get_assumption(store, "seasonality_blend_weight")

if source == "learned":
    st.success(f"Seasonality fully learned from GA4 data (blend weight: {blend_weight:.0%}).")
elif source == "blended":
    st.info(f"Seasonality blended: {blend_weight:.0%} GA4 data + {1-blend_weight:.0%} AU retail defaults.")
else:
    st.info("Seasonality using AU retail defaults (upload ≥12 months of GA4 data to learn from your data).")

if learned_seasonality:
    with st.expander("Compare learned vs. AU retail defaults"):
        months_labels = [seasonality[m]["label"].split(" ")[0] for m in range(1, 13)]
        learned_vals = [learned_seasonality[m]["traffic_mod"] * 100 for m in range(1, 13)]
        default_vals = [DEFAULT_SEASONALITY[m]["traffic_mod"] * 100 for m in range(1, 13)]
        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(name="Learned from GA4", x=months_labels, y=learned_vals, marker_color=PRIMARY))
        fig_s.add_trace(go.Bar(name="AU Retail Default", x=months_labels, y=default_vals, marker_color=SLATE_400))
        fig_s = _apply_layout(fig_s, "Seasonality: Learned vs Default", "Month", "Traffic Modifier (%)")
        st.plotly_chart(fig_s, use_container_width=True)

# ── Data Status ───────────────────────────────────────────────────────────────
st.divider()
st.subheader("Data Status")
col1, col2, col3 = st.columns(3)
with col1:
    if GA4_DF in st.session_state:
        ga4 = st.session_state[GA4_DF]
        st.success(f"GA4: {len(ga4)} months loaded ({ga4['date'].min().strftime('%b %Y')} – {ga4['date'].max().strftime('%b %Y')})")
    else:
        st.info("GA4: Not loaded")
with col2:
    if KW_DF in st.session_state:
        kw = st.session_state[KW_DF]
        st.success(f"Keywords: {len(kw)} loaded ({len(st.session_state.get(KW_EXISTING, []))} ranking)")
    else:
        st.info("Keywords: Not loaded")
with col3:
    if ROADMAP_BUNDLE in st.session_state:
        _rb_ss = st.session_state[ROADMAP_BUNDLE].get("source_summary", {})
        st.success(f"Roadmap: {_rb_ss.get('total_tasks_detected', '?')} tasks (AI extracted)")
    elif ROADMAP_DATA in st.session_state:
        st.success("Roadmap: loaded (legacy)")
    else:
        st.info("Roadmap: Not loaded")

# ── Assumptions Panel ─────────────────────────────────────────────────────────
st.divider()
render_assumptions_banner(store)
render_assumptions_panel(store)
