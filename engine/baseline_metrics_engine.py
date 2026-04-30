"""Baseline metrics forecasting engine.

Produces per-month CVR, AOV, transactions, and revenue projections by
trend-fitting historical GA4 metric series and applying seasonality.

This is the canonical source for dynamic revenue in the Combined Forecast —
replacing the single-scalar CVR/AOV that was applied uniformly across all
forecast months.
"""

from __future__ import annotations

import pandas as pd

from engine.historical_engine import forecast_series
from engine.seasonality_engine import DEFAULT_SEASONALITY


def forecast_baseline_metrics(
    ga4_df: pd.DataFrame,
    months: int,
    seasonality: dict | None = None,
    forecast_start_month: int | None = None,
    fallback_cvr: float = 2.5,
    fallback_aov: float = 100.0,
) -> pd.DataFrame:
    """Forecast traffic, CVR, AOV, transactions, and revenue per month.

    Fits linear trends to historical GA4 metric series then applies monthly
    seasonality multipliers (cr_mod, aov_mod) from the seasonality dict.

    Args:
        ga4_df: Historical GA4 DataFrame with 'date', 'traffic', and optionally
                'cr', 'aov', 'revenue', 'transactions' columns.
        months: Forecast horizon in months.
        seasonality: Dict of month_number -> {cr_mod, aov_mod, traffic_mod, ...}.
                     Defaults to DEFAULT_SEASONALITY.
        forecast_start_month: Unused (date inferred from ga4_df). Retained for
                              API symmetry with other v4 engines.
        fallback_cvr: CVR% to use when GA4 has no conversion rate history.
        fallback_aov: AOV to use when GA4 has no order-value history.

    Returns:
        DataFrame with columns: month (1-indexed), date, traffic, cvr, aov,
        transactions, revenue.  All rows are forecast-horizon rows only.
    """
    season = seasonality if seasonality is not None else DEFAULT_SEASONALITY
    n_hist = len(ga4_df)
    traffic_series = ga4_df["traffic"]
    last_date = pd.Timestamp(ga4_df["date"].iloc[-1]).replace(day=1)

    # Forecast traffic
    traffic_all = forecast_series(traffic_series, months)
    traffic_future = traffic_all[n_hist:]

    # Forecast CVR — needs ≥3 non-null observations to fit a trend
    has_cr = "cr" in ga4_df.columns and ga4_df["cr"].notna().sum() >= 3
    if has_cr:
        cr_series = ga4_df["cr"].ffill().fillna(fallback_cvr)
        cr_all = forecast_series(cr_series, months, allow_negative=False)
        cr_future = cr_all[n_hist:]
    else:
        cr_future = [fallback_cvr] * months

    # Forecast AOV
    has_aov = "aov" in ga4_df.columns and ga4_df["aov"].notna().sum() >= 3
    if has_aov:
        aov_series = ga4_df["aov"].ffill().fillna(fallback_aov)
        aov_all = forecast_series(aov_series, months)
        aov_future = aov_all[n_hist:]
    else:
        aov_future = [fallback_aov] * months

    rows = []
    for j in range(months):
        forecast_date = last_date + pd.DateOffset(months=j + 1)
        cal_month = pd.Timestamp(forecast_date).month

        traffic_val = max(0.0, float(traffic_future[j]))
        cvr_val = max(0.0, float(cr_future[j]))
        aov_val = max(0.0, float(aov_future[j]))

        # Seasonal modifiers for CVR and AOV
        s = season.get(cal_month, {})
        cvr_val = cvr_val * (1.0 + s.get("cr_mod", 0.0))
        aov_val = aov_val * (1.0 + s.get("aov_mod", 0.0))

        transactions = int(round(traffic_val * cvr_val / 100.0))
        revenue = round(transactions * aov_val, 2)

        rows.append({
            "month": j + 1,
            "date": forecast_date,
            "traffic": int(round(traffic_val)),
            "cvr": round(cvr_val, 4),
            "aov": round(aov_val, 2),
            "transactions": transactions,
            "revenue": revenue,
        })

    return pd.DataFrame(rows)
