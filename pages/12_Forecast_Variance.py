import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from engine.snapshot_engine import load_snapshot, compare_to_actuals, summarise_variance
from utils.chart_builder import _apply_layout
from utils.sidebar import render_ai_settings
from utils.session import GA4_DF

# ── Header ─────────────────────────────────────────────────────────────────
st.header("Forecast Variance")
st.caption("Compare a previous forecast snapshot against actual GA4 data.")

render_ai_settings()

# ── Upload section ─────────────────────────────────────────────────────────
snapshot_file = st.file_uploader(
    "Upload a forecast snapshot JSON",
    type=["json"],
    key="variance_snapshot_upload",
)

ga4_df = st.session_state.get(GA4_DF)
if ga4_df is None:
    st.info("Load GA4 data on the **Data Upload** page first.")
    st.stop()

if snapshot_file is None:
    st.info("Upload a forecast snapshot JSON to begin the variance analysis.")
    st.stop()

# ── Parse snapshot ─────────────────────────────────────────────────────────
try:
    snapshot = load_snapshot(snapshot_file.read())
except Exception as exc:
    st.error(f"Could not parse snapshot file: {exc}")
    st.stop()

# ── Snapshot metadata ──────────────────────────────────────────────────────
st.subheader("Snapshot Metadata")
meta_cols = st.columns(3)
meta_cols[0].metric("Client", snapshot.get("client_name", "Unknown"))
meta_cols[1].metric("Snapshot Date", snapshot.get("snapshot_date", "N/A")[:10])
engine_versions = snapshot.get("engine_versions", {})
meta_cols[2].metric("Engine Version", engine_versions.get("snapshot", "N/A"))

# ── Compare forecast to actuals ────────────────────────────────────────────
comparison = compare_to_actuals(snapshot, ga4_df)

if comparison.empty:
    st.warning("No overlapping months between forecast and actuals.")
    st.stop()

# ── KPI summary ────────────────────────────────────────────────────────────
summary = summarise_variance(comparison)

st.subheader("Variance Summary")
kpi_cols = st.columns(4)
kpi_cols[0].metric("Months Compared", summary["n_months_compared"])
kpi_cols[1].metric("Mean Variance %", f"{summary['mean_variance_pct']:+.1f}%")
kpi_cols[2].metric("Within P10-P90 Band", f"{summary['pct_within_band']:.0f}%")

max_over = summary["max_overshoot_pct"]
max_under = summary["max_undershoot_pct"]
kpi_cols[3].metric(
    "Max Over / Undershoot",
    f"+{max_over:.1f}% / {max_under:.1f}%",
)

# ── Chart: Actual vs Forecast with confidence band ─────────────────────────
st.subheader("Forecast vs Actuals")

fig = go.Figure()

# Shaded P10-P90 band
has_bands = (
    comparison["forecast_p10"].notna().any()
    and comparison["forecast_p90"].notna().any()
)
if has_bands:
    fig.add_trace(go.Scatter(
        x=comparison["date"],
        y=comparison["forecast_p90"],
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=comparison["date"],
        y=comparison["forecast_p10"],
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(37, 99, 235, 0.10)",
        name="P10-P90 Band",
        hoverinfo="skip",
    ))

# P50 forecast line
fig.add_trace(go.Scatter(
    x=comparison["date"],
    y=comparison["forecast_p50"],
    mode="lines",
    name="Forecast P50",
    line=dict(color="#2563EB", width=2, dash="dash"),
    hovertemplate="%{x|%b %Y}<br>Forecast P50: %{y:,.0f}<extra></extra>",
))

# Actual traffic line
fig.add_trace(go.Scatter(
    x=comparison["date"],
    y=comparison["actual"],
    mode="lines+markers",
    name="Actual Traffic",
    line=dict(color="#0F172A", width=3),
    hovertemplate="%{x|%b %Y}<br>Actual: %{y:,.0f}<extra></extra>",
))

fig = _apply_layout(fig, "Forecast vs Actual Traffic", "Date", "Monthly Organic Sessions")
st.plotly_chart(fig, use_container_width=True)

# ── Per-month comparison table ─────────────────────────────────────────────
st.subheader("Monthly Comparison")

display_df = comparison.copy()
display_df["date"] = display_df["date"].dt.strftime("%b %Y")
display_df = display_df.rename(columns={
    "date": "Month",
    "forecast_p10": "Forecast P10",
    "forecast_p50": "Forecast P50",
    "forecast_p90": "Forecast P90",
    "actual": "Actual",
    "variance": "Variance",
    "variance_pct": "Variance %",
    "within_band": "Within Band",
})

# Format numeric columns
format_cols = ["Forecast P10", "Forecast P50", "Forecast P90", "Actual", "Variance"]
for col in format_cols:
    if col in display_df.columns:
        display_df[col] = display_df[col].apply(
            lambda v: f"{v:,.0f}" if pd.notna(v) else "-"
        )
display_df["Variance %"] = display_df["Variance %"].apply(lambda v: f"{v:+.1f}%")
display_df["Within Band"] = display_df["Within Band"].map({True: "Yes", False: "No"})


def _highlight_variance(row):
    """Apply conditional formatting based on variance percentage."""
    styles = [""] * len(row)
    var_idx = row.index.get_loc("Variance %")
    band_idx = row.index.get_loc("Within Band")

    var_str = row["Variance %"]
    try:
        var_val = float(var_str.replace("%", "").replace("+", ""))
    except (ValueError, AttributeError):
        return styles

    if abs(var_val) > 20:
        styles[var_idx] = "background-color: #FEE2E2; color: #991B1B"
    elif abs(var_val) > 10:
        styles[var_idx] = "background-color: #FEF3C7; color: #92400E"
    else:
        styles[var_idx] = "background-color: #DCFCE7; color: #166534"

    if row["Within Band"] == "No":
        styles[band_idx] = "background-color: #FEE2E2; color: #991B1B"
    else:
        styles[band_idx] = "background-color: #DCFCE7; color: #166534"

    return styles


st.dataframe(
    display_df.style.apply(_highlight_variance, axis=1),
    use_container_width=True,
    hide_index=True,
)

# ── Recommendations ────────────────────────────────────────────────────────
st.subheader("Recommendations")

mean_var = summary["mean_variance_pct"]
pct_within = summary["pct_within_band"]

recommendations = []

if mean_var > 15:
    recommendations.append(
        "Forecast was consistently over-optimistic — consider reducing "
        "effort level or using Conservative scenario."
    )
if mean_var < -15:
    recommendations.append(
        "Forecast was too conservative — actuals exceeded projections."
    )
if pct_within >= 80:
    recommendations.append(
        "Good calibration — 80%+ of actuals fell within the predicted range."
    )
if pct_within < 50:
    recommendations.append(
        "Poor calibration — consider widening bands or re-evaluating assumptions."
    )

if not recommendations:
    recommendations.append(
        "Forecast calibration is within acceptable range. Continue monitoring."
    )

for rec in recommendations:
    st.info(rec)
