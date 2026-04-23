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

# Columns serialised from combined_df — order is stable; only append.
_FORECAST_COLS = [
    "baseline", "positional_uplift_p10", "positional_uplift_p50",
    "positional_uplift_p90", "new_content_uplift", "decay",
    "aio_erosion", "combined_p10", "combined_p50", "combined_p90",
    "positional_uplift", "combined",
    # Revenue / conversion fields (added in v4.10)
    "cvr", "aov", "transactions", "revenue",
    "revenue_p10", "revenue_p50", "revenue_p90",
]

# Maps metric selector values → snapshot record fields and actuals_df columns
_METRIC_CONFIG: dict[str, dict] = {
    "traffic": {
        "p50_fields": ["combined_p50", "combined"],
        "p10_field": "combined_p10",
        "p90_field": "combined_p90",
        "actuals_col": "traffic",
    },
    "revenue": {
        "p50_fields": ["revenue"],
        "p10_field": "revenue_p10",
        "p90_field": "revenue_p90",
        "actuals_col": "revenue",
    },
    "transactions": {
        "p50_fields": ["transactions"],
        "p10_field": None,
        "p90_field": None,
        "actuals_col": "transactions",
    },
    "cvr": {
        "p50_fields": ["cvr"],
        "p10_field": None,
        "p90_field": None,
        "actuals_col": "cr",
    },
    "aov": {
        "p50_fields": ["aov"],
        "p10_field": None,
        "p90_field": None,
        "actuals_col": "aov",
    },
}


def build_snapshot(
    client_name: str,
    combined_df: pd.DataFrame,
    parameters: dict,
    engine_versions: dict | None = None,
    metrics_df: pd.DataFrame | None = None,
    assumptions_snapshot: list[dict] | None = None,
) -> dict:
    """Serialise a forecast to a downloadable JSON snapshot.

    Args:
        client_name: Client / brand name.
        combined_df: Output of run_combined_forecast().
        parameters: Sidebar settings dict (effort_level, cvr, aov, etc.).
        engine_versions: Optional engine version overrides.
        metrics_df: Optional per-month CVR/AOV/transactions/revenue DataFrame
                    from forecast_baseline_metrics(). When provided, per-month
                    conversion metrics are merged into the forecast records so
                    variance analysis can grade revenue accuracy.
        assumptions_snapshot: Output of engine.assumptions.assumptions_summary()
                              at snapshot time — captures every assumption and
                              its provenance so later analysis knows what drove
                              the forecast.
    """
    versions = engine_versions or {"snapshot": SNAPSHOT_VERSION}

    forecast = combined_df[combined_df["is_forecast"]].copy().reset_index(drop=True)

    # Build metrics lookup keyed by 1-indexed month position
    metrics_by_month: dict[int, dict] = {}
    if metrics_df is not None and not metrics_df.empty:
        for _, mrow in metrics_df.iterrows():
            m = int(mrow.get("month", 0))
            if m > 0:
                metrics_by_month[m] = mrow.to_dict()

    records = []
    for idx, row in forecast.iterrows():
        record: dict = {"date": row["date"].strftime("%Y-%m-%d")}
        for col in _FORECAST_COLS:
            if col in row.index and pd.notna(row[col]):
                record[col] = float(row[col])

        # Merge per-month conversion metrics when available
        month_num = idx + 1  # forecast rows are 1-indexed
        if month_num in metrics_by_month:
            m = metrics_by_month[month_num]
            for field in ("cvr", "aov", "transactions", "revenue"):
                if field in m and pd.notna(m[field]) and field not in record:
                    record[field] = float(m[field])

        records.append(record)

    snap: dict = {
        "snapshot_version": SNAPSHOT_VERSION,
        "client_name": client_name,
        "snapshot_date": datetime.now(UTC).isoformat(),
        "engine_versions": versions,
        "parameters": parameters,
        "forecast": records,
        "dynamic_metrics": metrics_df is not None and not metrics_df.empty,
    }
    if assumptions_snapshot:
        snap["assumptions_snapshot"] = assumptions_snapshot

    return snap


def snapshot_to_bytes(snapshot: dict) -> bytes:
    return json.dumps(snapshot, indent=2).encode("utf-8")


def load_snapshot(file_content: bytes | str) -> dict:
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8")
    return json.loads(file_content)


def compare_to_actuals(
    snapshot: dict,
    actuals_df: pd.DataFrame,
    metric: str = "traffic",
) -> pd.DataFrame:
    """Compare a snapshot's forecast to actual GA4 data.

    Args:
        snapshot: Loaded snapshot dict (from load_snapshot).
        actuals_df: GA4 monthly data with 'date' and metric-specific columns.
        metric: One of "traffic", "revenue", "transactions", "cvr", "aov".
                Defaults to "traffic" for backward compatibility.

    Returns:
        DataFrame with date, forecast_p50, forecast_p10, forecast_p90,
        actual, variance, variance_pct, within_band.
    """
    cfg = _METRIC_CONFIG.get(metric, _METRIC_CONFIG["traffic"])
    actuals_col = cfg["actuals_col"]
    p10_field = cfg["p10_field"]
    p90_field = cfg["p90_field"]

    if actuals_col not in actuals_df.columns:
        return pd.DataFrame()

    actuals_by_date = dict(zip(
        pd.to_datetime(actuals_df["date"]).dt.strftime("%Y-%m-%d"),
        actuals_df[actuals_col],
        strict=False,
    ))

    rows = []
    for record in snapshot["forecast"]:
        date_str = record["date"]
        actual = actuals_by_date.get(date_str)
        if actual is None or pd.isna(actual):
            continue

        # Resolve p50 from the priority list of field names
        p50 = None
        for field in cfg["p50_fields"]:
            if field in record and record[field] is not None:
                p50 = record[field]
                break
        if p50 is None:
            continue

        p10 = record.get(p10_field) if p10_field else None
        p90 = record.get(p90_field) if p90_field else None

        variance = float(actual) - p50
        variance_pct = (variance / p50 * 100) if p50 > 0 else 0.0
        within_band = (
            p10 is not None and p90 is not None and p10 <= float(actual) <= p90
        )
        rows.append({
            "date": pd.to_datetime(date_str),
            "forecast_p10": p10,
            "forecast_p50": p50,
            "forecast_p90": p90,
            "actual": float(actual),
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
