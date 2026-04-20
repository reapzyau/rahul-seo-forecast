"""Keyword decay engine — models traffic loss on unmaintained pages.

The "do nothing" baseline is not actually flat. Search intent drifts,
competitors publish fresher content, Google re-weights signals, and
unmaintained pages slowly lose position. v2 ignored this; v3 models it.

Decay operates on the existing keyword portfolio (keywords you already rank
for) and is subtracted from the baseline projection.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_DECAY_RATES = {
    "top3": 0.08,
    "top10": 0.12,
    "11_20": 0.18,
    "21_50": 0.25,
    "51_plus": 0.35,
}


def position_bucket(position: int | None) -> str:
    if position is None or pd.isna(position):
        return "51_plus"
    p = int(position)
    if p <= 3:
        return "top3"
    if p <= 10:
        return "top10"
    if p <= 20:
        return "11_20"
    if p <= 50:
        return "21_50"
    return "51_plus"


def monthly_decay_factor(annual_rate: float) -> float:
    """Convert annual decay rate to monthly retention factor."""
    return (1.0 - annual_rate) ** (1.0 / 12.0)


def calculate_portfolio_decay(
    keyword_df: pd.DataFrame,
    months: int,
    decay_rates: dict | None = None,
    maintenance_coverage: float = 0.0,
) -> pd.DataFrame:
    """Project monthly traffic loss from decay across the keyword portfolio.

    Args:
        keyword_df: Portfolio with 'position' and 'current_traffic' columns.
        months: Forecast horizon.
        decay_rates: Override default annual rates by bucket.
        maintenance_coverage: 0.0 = no maintenance, 1.0 = full.

    Returns:
        DataFrame with month, decay_loss, cumulative_decay, retained_traffic.
    """
    if keyword_df.empty or "current_traffic" not in keyword_df.columns:
        return pd.DataFrame({
            "month": range(1, months + 1),
            "decay_loss": [0] * months,
            "cumulative_decay": [0] * months,
            "retained_traffic": [0] * months,
        })

    rates = decay_rates or DEFAULT_DECAY_RATES
    df = keyword_df.copy()
    df["bucket"] = df["position"].apply(position_bucket)
    df["annual_rate"] = df["bucket"].map(rates)
    df["effective_rate"] = df["annual_rate"] * (1.0 - maintenance_coverage)
    df["monthly_retention"] = df["effective_rate"].apply(monthly_decay_factor)

    base_traffic = df["current_traffic"].fillna(0).values.astype(float)
    retentions = df["monthly_retention"].values

    rows = []
    for m in range(1, months + 1):
        retained_per_kw = base_traffic * (retentions ** m)
        retained_total = int(retained_per_kw.sum())
        original_total = int(base_traffic.sum())
        cumulative_decay = original_total - retained_total
        if rows:
            monthly_loss = rows[-1]["retained_traffic"] - retained_total
        else:
            monthly_loss = original_total - retained_total
        rows.append({
            "month": m,
            "decay_loss": int(monthly_loss),
            "cumulative_decay": int(cumulative_decay),
            "retained_traffic": retained_total,
        })

    return pd.DataFrame(rows)


def project_decayed_baseline(
    historical_traffic: pd.Series,
    keyword_df: pd.DataFrame,
    months: int,
    maintenance_coverage: float = 0.0,
) -> pd.DataFrame:
    """Combine linear baseline projection with decay for the honest
    'do nothing' trajectory.

    Returns:
        DataFrame with month, linear_baseline, cumulative_decay, honest_baseline.
    """
    from engine.historical_engine import forecast_series

    values = historical_traffic.values.astype(float)
    linear = forecast_series(pd.Series(values), months)[-months:]
    decay_df = calculate_portfolio_decay(
        keyword_df, months, maintenance_coverage=maintenance_coverage,
    )

    rows = []
    for i in range(months):
        linear_val = linear[i] if i < len(linear) else linear[-1]
        decay_loss = decay_df.iloc[i]["cumulative_decay"]
        honest = max(0, linear_val - decay_loss)
        rows.append({
            "month": i + 1,
            "linear_baseline": int(linear_val),
            "cumulative_decay": int(decay_loss),
            "honest_baseline": int(honest),
        })

    return pd.DataFrame(rows)
