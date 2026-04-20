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
