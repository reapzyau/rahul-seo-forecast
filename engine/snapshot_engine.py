"""Forecast snapshots for variance analysis.

A snapshot is a JSON-serialisable dict capturing the inputs, engine
versions, and outputs of a forecast run. Snapshots are downloaded by the
analyst and re-uploaded months later (alongside fresh GA4 data) to see
how the forecast compared to reality.

This is the tool's calibration loop: without it, forecasts are guesses
nobody ever grades.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from engine import __version__ as _ENGINE_VERSION

SNAPSHOT_VERSION = _ENGINE_VERSION

_FORECAST_COLS = [
    "baseline", "positional_uplift_p10", "positional_uplift_p50",
    "positional_uplift_p90", "new_content_uplift", "decay",
    "aio_erosion", "combined_p10", "combined_p50", "combined_p90",
    "positional_uplift", "combined",
]


def build_snapshot(
    client_name: str,
    combined_df: pd.DataFrame,
    parameters: dict,
    engine_versions: dict | None = None,
) -> dict:
    """Serialise a forecast to a downloadable JSON snapshot."""
    versions = engine_versions or {"snapshot": SNAPSHOT_VERSION}

    forecast = combined_df[combined_df["is_forecast"]].copy()
    records = []
    for _, row in forecast.iterrows():
        record = {"date": row["date"].strftime("%Y-%m-%d")}
        for col in _FORECAST_COLS:
            if col in row.index and pd.notna(row[col]):
                record[col] = float(row[col])
        records.append(record)

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "client_name": client_name,
        "snapshot_date": datetime.now(UTC).isoformat(),
        "engine_versions": versions,
        "parameters": parameters,
        "forecast": records,
    }


def snapshot_to_bytes(snapshot: dict) -> bytes:
    return json.dumps(snapshot, indent=2).encode("utf-8")


def load_snapshot(file_content: bytes | str) -> dict:
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8")
    return json.loads(file_content)


def compare_to_actuals(
    snapshot: dict,
    actuals_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compare a snapshot's forecast to actual GA4 data.

    Returns:
        DataFrame with date, forecast_p50, forecast_p10, forecast_p90,
        actual, variance, variance_pct, within_band.
    """
    actuals_by_date = dict(zip(
        pd.to_datetime(actuals_df["date"]).dt.strftime("%Y-%m-%d"),
        actuals_df["traffic"],
        strict=False,
    ))

    rows = []
    for record in snapshot["forecast"]:
        date_str = record["date"]
        actual = actuals_by_date.get(date_str)
        if actual is None:
            continue
        p50 = record.get("combined_p50") or record.get("combined")
        p10 = record.get("combined_p10")
        p90 = record.get("combined_p90")
        if p50 is None:
            continue
        variance = actual - p50
        variance_pct = (variance / p50 * 100) if p50 > 0 else 0
        within_band = (
            p10 is not None and p90 is not None and p10 <= actual <= p90
        )
        rows.append({
            "date": pd.to_datetime(date_str),
            "forecast_p10": p10,
            "forecast_p50": p50,
            "forecast_p90": p90,
            "actual": actual,
            "variance": variance,
            "variance_pct": round(variance_pct, 1),
            "within_band": within_band,
        })

    return pd.DataFrame(rows)


def summarise_variance(comparison_df: pd.DataFrame) -> dict:
    if comparison_df.empty:
        return {}
    return {
        "n_months_compared": len(comparison_df),
        "mean_variance_pct": round(float(comparison_df["variance_pct"].mean()), 1),
        "median_variance_pct": round(float(comparison_df["variance_pct"].median()), 1),
        "pct_within_band": round(float(comparison_df["within_band"].mean() * 100), 1),
        "max_overshoot_pct": round(float(comparison_df["variance_pct"].max()), 1),
        "max_undershoot_pct": round(float(comparison_df["variance_pct"].min()), 1),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Section 10: Per-run methodology snapshot
# ──────────────────────────────────────────────────────────────────────────────


def build_methodology_snapshot(
    client_name: str,
    forecast_start: str,
    forecast_end: str,
    months: int,
    ga4_summary: dict,
    baseline_mode: str,
    baseline_mode_rationale: str,
    seasonality_source: str,
    seasonality_rationale: str,
    position_filter: tuple[int, int] | None,
    positional_kw_count: int,
    movement_stats_decision: str,
    brand_config: dict,
    new_content_source: str,
    aio_penalties: dict,
    blended_cr: float,
    weighted_aov: float,
    tier_outputs: list[dict],
    seed: int = 42,
) -> dict:
    """Build a per-run methodology snapshot capturing all key model decisions.

    This snapshot accompanies every XLSX export so that the SEO lead can defend
    specific choices (which baseline mode was chosen, why; whether learned movement
    stats were used or overridden; brand classification config) when presenting
    to the client.

    Args:
        client_name: Client identifier string.
        forecast_start: ISO date string of first forecast month (YYYY-MM-DD).
        forecast_end: ISO date string of last forecast month (YYYY-MM-DD).
        months: Forecast horizon in months.
        ga4_summary: Dict with keys: rows, date_range, latest_6mo_avg.
        baseline_mode: "yoy_replay" or "linear_trend".
        baseline_mode_rationale: Human-readable reason for the baseline mode choice.
        seasonality_source: "derived_from_baseline" | "learned_blend" | "industry_prior".
        seasonality_rationale: Human-readable reason for seasonality approach.
        position_filter: (lo, hi) tuple for positional pool, or None.
        positional_kw_count: Keywords passing the positional pool filter.
        movement_stats_decision: Reason string from _resolve_movement_stats().
        brand_config: Dict with keys: substring_terms, word_boundary_terms,
                      excluded_followers, matched_count, total_kw_count.
        new_content_source: "deterministic_stream" | "gap_analysis".
        aio_penalties: AIO CTR penalties dict {intent: pct}.
        blended_cr: Blended conversion rate used for revenue layer.
        weighted_aov: Weighted AOV used for revenue layer.
        tier_outputs: List of dicts, one per tier:
            {tier_name, retainer, annual_sessions_baseline, annual_sessions_combined,
             uplift_pct, annual_revenue_baseline, annual_revenue_combined,
             revenue_uplift, roi}
        seed: Monte Carlo seed used.

    Returns:
        JSON-serialisable dict — the methodology snapshot.
    """
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "snapshot_type": "methodology",
        "generated_at": datetime.now(UTC).isoformat(),
        "client_name": client_name,
        "forecast_horizon": {
            "start": forecast_start,
            "end": forecast_end,
            "months": months,
        },
        "ga4_input": ga4_summary,
        "baseline": {
            "mode": baseline_mode,
            "rationale": baseline_mode_rationale,
        },
        "seasonality": {
            "source": seasonality_source,
            "rationale": seasonality_rationale,
        },
        "positional_pool": {
            "filter": list(position_filter) if position_filter else None,
            "filter_description": (
                f"positions {position_filter[0]}–{position_filter[1]}"
                if position_filter
                else "no filter (full portfolio)"
            ),
            "keyword_count": positional_kw_count,
        },
        "movement_stats": {
            "decision": movement_stats_decision,
        },
        "brand_classification": brand_config,
        "new_content": {
            "source": new_content_source,
        },
        "aio_penalties": aio_penalties,
        "revenue_assumptions": {
            "blended_cr_pct": blended_cr,
            "weighted_aov": weighted_aov,
        },
        "monte_carlo_seed": seed,
        "tier_outputs": tier_outputs,
    }


def methodology_snapshot_to_human_readable(snapshot: dict) -> str:
    """Convert a methodology snapshot to a human-readable text string.

    Suitable for embedding in an Excel sheet or a PDF methodology appendix.
    """
    lines = [
        "SEO Forecast Methodology Snapshot",
        f"Generated: {snapshot.get('generated_at', 'n/a')}",
        f"Client: {snapshot.get('client_name', 'n/a')}",
        "",
        "── Forecast Horizon ──",
        f"  Start: {snapshot['forecast_horizon']['start']}",
        f"  End:   {snapshot['forecast_horizon']['end']}",
        f"  Months: {snapshot['forecast_horizon']['months']}",
        "",
        "── GA4 Input Summary ──",
    ]
    for k, v in snapshot.get("ga4_input", {}).items():
        lines.append(f"  {k}: {v}")

    lines += [
        "",
        "── Baseline Mode ──",
        f"  Mode: {snapshot['baseline']['mode']}",
        f"  Rationale: {snapshot['baseline']['rationale']}",
        "",
        "── Seasonality ──",
        f"  Source: {snapshot['seasonality']['source']}",
        f"  Rationale: {snapshot['seasonality']['rationale']}",
        "",
        "── Positional Pool ──",
        f"  Filter: {snapshot['positional_pool']['filter_description']}",
        f"  Keyword count: {snapshot['positional_pool']['keyword_count']}",
        "",
        "── Movement Stats Decision ──",
        f"  {snapshot['movement_stats']['decision']}",
        "",
        "── Brand Classification ──",
    ]
    bc = snapshot.get("brand_classification", {})
    lines.append(f"  Substring terms: {bc.get('substring_terms', [])}")
    lines.append(f"  Word-boundary terms: {bc.get('word_boundary_terms', [])}")
    lines.append(f"  Excluded followers: {bc.get('excluded_followers', [])}")
    lines.append(f"  Matched branded keywords: {bc.get('matched_count', 'n/a')} / {bc.get('total_kw_count', 'n/a')}")

    lines += [
        "",
        "── New Content Source ──",
        f"  {snapshot['new_content']['source']}",
        "",
        "── Revenue Assumptions ──",
        f"  Blended CVR: {snapshot['revenue_assumptions']['blended_cr_pct']}%",
        f"  Weighted AOV: ${snapshot['revenue_assumptions']['weighted_aov']:,.0f}",
        "",
        "── Tier Outputs ──",
    ]
    for t in snapshot.get("tier_outputs", []):
        lines.append(
            f"  {t.get('tier_name', 'Tier')}: "
            f"{t.get('annual_sessions_combined', 0):,} sessions "
            f"(+{t.get('uplift_pct', 0):.1f}% vs baseline), "
            f"Revenue ${t.get('annual_revenue_combined', 0):,.0f}"
        )

    return "\n".join(lines)
