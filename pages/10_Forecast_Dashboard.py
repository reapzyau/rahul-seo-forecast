"""Forecast Dashboard — live executive summary built from session-state scenario results.

Replaces the old static HTML embed with a real-time view derived from the
three-scenario forecast run on the Strategy page. Shows no controls — it is
a read-only summary intended for client presentations.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.assumptions import get_assumption
from engine.scenario_engine import summarise_scenarios
from utils.chart_builder import _apply_layout
from utils.design_tokens import (
    DANGER,
    FILL_SUBTLE,
    PRIMARY,
    SLATE_400,
    SLATE_900,
    SUCCESS,
    rgba,
)
from utils.metric_cards import KPICard, render_kpi_row
from utils.session import ASSUMPTIONS, GA4_DF, SCENARIO_PRESETS_EDITED, SCENARIO_RESULTS

st.set_page_config(
    page_title="Forecast Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Assumptions store ─────────────────────────────────────────────────────────
store = st.session_state.get(ASSUMPTIONS, {})
client_name = get_assumption(store, "client_name") or ""
currency = get_assumption(store, "currency") or "AUD"

# ── Prerequisite gate ─────────────────────────────────────────────────────────
if SCENARIO_RESULTS not in st.session_state:
    st.title("📊 Forecast Dashboard")
    st.info(
        "No forecast data found. Go to **Strategy (page 2)**, upload your data, "
        "and click **Run All Forecasts** — then return here for the executive summary."
    )
    st.page_link("pages/2_Strategy.py", label="Go to Strategy →", icon="🗺️")
    st.stop()

results = st.session_state[SCENARIO_RESULTS]
ga4_df = st.session_state.get(GA4_DF)
presets = st.session_state.get(SCENARIO_PRESETS_EDITED) or {}

forecast_months = st.session_state.get("strat_months", 12)

SCENARIO_ORDER = ["Conservative", "Moderate", "Aggressive"]
SCENARIO_COLORS = {
    "Conservative": SLATE_400,
    "Moderate": PRIMARY,
    "Aggressive": SUCCESS,
}

# ── Header ────────────────────────────────────────────────────────────────────
title = f"Forecast Dashboard — {client_name}" if client_name else "Forecast Dashboard"
st.title(title)
st.caption(
    f"Executive summary · {forecast_months}-month horizon · "
    "Three scenarios: Conservative / Moderate / Aggressive"
)
st.divider()

# ── Section 1: Scenario summary cards ────────────────────────────────────────
summary_df = summarise_scenarios(results, months=forecast_months)

st.subheader("Scenario Comparison")

cols = st.columns(3)
for col, scenario_name in zip(cols, SCENARIO_ORDER, strict=True):
    scenario = results.get(scenario_name, {})
    with col:
        if "error" in scenario:
            st.error(f"**{scenario_name}** failed: {scenario['error']}")
            continue

        row = summary_df[summary_df["Scenario"] == scenario_name]
        if row.empty:
            continue
        row = row.iloc[0]

        combined_end = int(row["Combined End Traffic (P50)"])
        baseline_end = int(row["Baseline End Traffic"])
        uplift_pct = float(row["Uplift %"])
        retainer = float(row["Retainer"])
        effort = str(row["Effort"])
        cadence = int(row["Cadence"])

        color = SCENARIO_COLORS[scenario_name]
        st.markdown(
            f"<div style='border-left: 4px solid {color}; padding-left: 12px;'>"
            f"<strong style='font-size:1.1rem'>{scenario_name}</strong>"
            f"</div>",
            unsafe_allow_html=True,
        )
        render_kpi_row([
            KPICard("End Traffic (P50)", f"{combined_end:,}"),
            KPICard(
                "Uplift",
                f"{uplift_pct:+.1f}%",
                delta=f"{uplift_pct:+.1f}%",
                delta_color="normal",
            ),
        ])
        st.caption(
            f"Effort: **{effort}** · Cadence: **{cadence} posts/mo** · "
            f"Retainer: **${retainer:,.0f}/mo**"
        )

st.divider()

# ── Section 2: Traffic projection comparison ──────────────────────────────────
st.subheader("Combined Traffic — All Scenarios")
st.caption("P10 = pessimistic · P50 = median (solid line) · P90 = optimistic")

fig = go.Figure()

# Historical actuals
if ga4_df is not None:
    fig.add_trace(go.Scatter(
        x=ga4_df["date"], y=ga4_df["traffic"],
        mode="lines+markers", name="Historical Actual",
        line=dict(color=SLATE_900, width=3),
        hovertemplate="%{x|%b %Y}<br>Actual: %{y:,.0f}<extra></extra>",
    ))

baseline_plotted = False
for scenario_name in SCENARIO_ORDER:
    scenario = results.get(scenario_name, {})
    if "error" in scenario or "combined_df" not in scenario:
        continue
    cdf = scenario["combined_df"]
    fmask = cdf["is_forecast"]
    color = SCENARIO_COLORS[scenario_name]

    if not baseline_plotted:
        fig.add_trace(go.Scatter(
            x=cdf.loc[fmask, "date"], y=cdf.loc[fmask, "baseline"],
            mode="lines", name="Baseline (no SEO)",
            line=dict(color=SLATE_400, dash="dash", width=2),
            hovertemplate="%{x|%b %Y}<br>Baseline: %{y:,.0f}<extra></extra>",
        ))
        baseline_plotted = True

    p50_col = "combined_p50" if "combined_p50" in cdf.columns else "combined"
    p10_col = "combined_p10" if "combined_p10" in cdf.columns else None
    p90_col = "combined_p90" if "combined_p90" in cdf.columns else None

    # P10–P90 band (subtle fill)
    if p10_col and p90_col:
        fig.add_trace(go.Scatter(
            x=cdf.loc[fmask, "date"], y=cdf.loc[fmask, p90_col],
            mode="lines", line=dict(width=0),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=cdf.loc[fmask, "date"], y=cdf.loc[fmask, p10_col],
            mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor=rgba(color, FILL_SUBTLE),
            showlegend=False, hoverinfo="skip",
        ))

    # P50 line
    fig.add_trace(go.Scatter(
        x=cdf.loc[fmask, "date"], y=cdf.loc[fmask, p50_col],
        mode="lines", name=scenario_name,
        line=dict(color=color, width=2),
        hovertemplate=f"%{{x|%b %Y}}<br>{scenario_name} (P50): %{{y:,.0f}}<extra></extra>",
    ))

fig = _apply_layout(fig, "", "Date", "Monthly Organic Sessions")
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Section 3: Stream breakdown per scenario ───────────────────────────────────
st.subheader("Traffic Streams by Scenario")
st.caption("How each component contributes to the total in the final forecast month.")

stream_rows = []
for scenario_name in SCENARIO_ORDER:
    scenario = results.get(scenario_name, {})
    if "error" in scenario or "combined_df" not in scenario:
        continue
    cdf = scenario["combined_df"]
    last = cdf[cdf["is_forecast"]].iloc[-1] if not cdf[cdf["is_forecast"]].empty else None
    if last is None:
        continue

    stream_rows.append({
        "Scenario": scenario_name,
        "Baseline": int(last.get("baseline", 0)),
        "Positional Uplift": int(last.get("positional_uplift_p50", last.get("positional_uplift", 0))),
        "New Content": int(last.get("new_content_uplift", 0)),
        "Decay Loss": -int(last.get("decay", 0)),
    })

if stream_rows:
    stream_df = pd.DataFrame(stream_rows).set_index("Scenario")
    fig_streams = go.Figure()
    stream_cols = {
        "Baseline": SLATE_400,
        "Positional Uplift": PRIMARY,
        "New Content": SUCCESS,
        "Decay Loss": DANGER,
    }
    for col_name, color in stream_cols.items():
        if col_name in stream_df.columns:
            fig_streams.add_trace(go.Bar(
                name=col_name,
                x=stream_df.index.tolist(),
                y=stream_df[col_name].tolist(),
                marker_color=color,
                hovertemplate=f"{col_name}: %{{y:,.0f}}<extra></extra>",
            ))
    fig_streams.update_layout(barmode="relative", hovermode="x unified")
    fig_streams = _apply_layout(
        fig_streams, "", "Scenario", "Sessions in Final Forecast Month"
    )
    st.plotly_chart(fig_streams, use_container_width=True)

st.divider()

# ── Section 4: Retainer / Traffic efficiency ──────────────────────────────────
st.subheader("Investment vs. Uplift")

eff_cols = st.columns(3)
for col, scenario_name in zip(eff_cols, SCENARIO_ORDER, strict=True):
    scenario = results.get(scenario_name, {})
    if "error" in scenario:
        continue
    row = summary_df[summary_df["Scenario"] == scenario_name]
    if row.empty:
        continue
    row = row.iloc[0]

    retainer = float(row["Retainer"])
    total_uplift = int(row["Total Uplift (P50)"])
    total_investment = retainer * forecast_months

    with col:
        st.markdown(f"**{scenario_name}**")
        if total_uplift > 0 and total_investment > 0:
            cost_per_visit = total_investment / total_uplift
            render_kpi_row([
                KPICard(
                    f"Total Investment ({forecast_months}mo)",
                    f"${total_investment:,.0f}",
                ),
                KPICard(
                    "Cost per Incremental Visit",
                    f"${cost_per_visit:.2f}",
                    caption="P50 uplift basis",
                ),
            ])
        else:
            st.caption("No investment or uplift data.")

st.divider()

# ── Section 5: Methodology note ───────────────────────────────────────────────
st.caption(
    "Traffic projections use Monte Carlo simulation (500 trials). "
    "P50 = median outcome; P10/P90 = 10th/90th percentile. "
    "AIO CTR penalties are applied per-stream inside the positional and new content engines. "
    "See the **Methodology** tab on the Deliverables page for full documentation."
)
