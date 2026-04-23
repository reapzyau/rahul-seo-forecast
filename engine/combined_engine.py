import pandas as pd

from engine.historical_engine import linear_forecast, yoy_growth_forecast
from engine.seasonality_engine import (
    DEFAULT_SEASONALITY,
    deseasonalise_series,
    reseasonalise_values,
)


def run_combined_forecast(
    historical_df: pd.DataFrame | None,
    positional_monthly: pd.DataFrame | None,
    new_content_monthly: pd.DataFrame | None,
    months: int,
    decay_df: pd.DataFrame | None = None,
    seasonality: dict | None = None,
    forecast_start_month: int | None = None,
) -> pd.DataFrame:
    """Layer every component into the canonical forecast.

    Math per month m (v4):
        combined[m] = baseline[m]
                    + positional_uplift[m]   (AIO already baked in via CTR penalty)
                    + new_content_uplift[m]  (AIO already baked in via CTR penalty)
                    - decay[m]               (portfolio-level, stays at combined level)

    P10/P50/P90 bands propagated from positional stream; decay is a deterministic subtraction.

    Args:
        seasonality: Monthly seasonality dict (same schema as DEFAULT_SEASONALITY).
                     When provided, the baseline is deseasonalised before OLS fitting
                     and reseasonalised for forecast months. Positional and new-content
                     streams already carry their own seasonality — do not double-apply.
                     When None, behaviour is identical to the pre-v4.10 baseline.
        forecast_start_month: Calendar month (1-12) of the first forecast month.
                              Overridden when historical_df is provided (derived from
                              last historical date + 1 month).

    Returns:
        DataFrame with actual, baseline, positional bands, new_content,
        decay, combined bands, is_forecast, uplift_pct.
    """
    rows = []
    _yoy_rate: float | None = None

    has_bands = (
        positional_monthly is not None
        and not positional_monthly.empty
        and "uplift_p10" in positional_monthly.columns
    )

    if historical_df is not None:
        dates = historical_df["date"]
        traffic = historical_df["traffic"]

        # Derive forecast_start_month from last historical date (overrides arg)
        forecast_start_month = (
            (pd.Timestamp(dates.iloc[-1]) + pd.DateOffset(months=1)).month
        )

        baseline_df = _seasonalised_baseline(
            dates, traffic, months, seasonality, forecast_start_month
        )

        # Historical portion
        for i in range(len(traffic)):
            rows.append(_hist_row(
                date=baseline_df.iloc[i]["date"],
                actual=int(traffic.iloc[i]),
                baseline=baseline_df.iloc[i]["linear"],
                has_bands=has_bands,
            ))

        baseline_forecast = baseline_df[baseline_df["is_forecast"]].reset_index(drop=True)
        last_date = dates.iloc[-1]
        _yoy_rate = baseline_df.attrs.get("yoy_rate")

        for j in range(1, months + 1):
            forecast_date = last_date + pd.DateOffset(months=j)
            baseline_val = int(baseline_forecast.iloc[j - 1]["linear"])
            rows.append(_forecast_row(
                date=forecast_date,
                baseline_val=baseline_val,
                month=j,
                positional_monthly=positional_monthly,
                new_content_monthly=new_content_monthly,
                decay_df=decay_df,
                has_bands=has_bands,
            ))
    else:
        base_date = pd.Timestamp.now().normalize().replace(day=1)
        for j in range(1, months + 1):
            forecast_date = base_date + pd.DateOffset(months=j)
            rows.append(_forecast_row(
                date=forecast_date,
                baseline_val=0,
                month=j,
                positional_monthly=positional_monthly,
                new_content_monthly=new_content_monthly,
                decay_df=decay_df,
                has_bands=has_bands,
            ))

    result = pd.DataFrame(rows)
    if _yoy_rate is not None:
        result.attrs["yoy_rate"] = _yoy_rate

    # Uplift percentage (P50-based when bands available)
    forecast_mask = result["is_forecast"]
    result["uplift_pct"] = 0.0
    pos_col = "positional_uplift_p50" if has_bands else "positional_uplift"

    result.loc[forecast_mask, "uplift_pct"] = result.loc[forecast_mask].apply(
        lambda r: round(
            (r[pos_col] + r["new_content_uplift"] - r.get("decay", 0))
            / r["baseline"] * 100, 1
        ) if r["baseline"] > 0 else 0.0,
        axis=1,
    )

    # Backward-compat aliases when bands are present
    if has_bands and "combined" not in result.columns:
        result["combined"] = result["combined_p50"]
    if has_bands and "positional_uplift" not in result.columns:
        result["positional_uplift"] = result["positional_uplift_p50"]

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _seasonalised_baseline(
    dates: pd.Series,
    traffic: pd.Series,
    months: int,
    seasonality: dict | None,
    forecast_start_month: int,
) -> pd.DataFrame:
    """Compute the baseline DataFrame with optional seasonality adjustment.

    When seasonality is None: falls back to plain linear_forecast / yoy_growth_forecast
    (identical to pre-v4.10 behaviour).

    When seasonality is provided and history has ≥13 months, uses
    yoy_growth_forecast which anchors each forecast month to the same calendar
    month one year prior — this implicitly captures seasonal shape, so we only
    apply the deseasonalise-fit-reseasonalise pipeline for short histories
    (< 13 months) where yoy anchoring is unavailable.

    For < 13 months with seasonality:
        1. Deseasonalise history (remove seasonal signal from OLS input)
        2. Fit OLS on the clean trend
        3. Reseasonalise forecast months only
    """
    n = len(traffic)

    if seasonality is None:
        # Backward-compat path — no seasonality
        if n >= 13:
            return yoy_growth_forecast(dates, traffic, months)
        return linear_forecast(dates, traffic, months, confidence=15.0)

    if n >= 13:
        # yoy_growth_forecast already anchors to same calendar month, so seasonal
        # shape is preserved without an extra deseasonalise step.
        return yoy_growth_forecast(dates, traffic, months)

    # Short history (< 13 months): deseasonalise → OLS → reseasonalise forecast
    season = seasonality if seasonality is not None else DEFAULT_SEASONALITY
    deseasoned = deseasonalise_series(dates, traffic, season)

    # OLS on the deseasonalised series
    raw_baseline = linear_forecast(dates, deseasoned, months, confidence=15.0)

    # Reseasonalise only the forecast rows
    forecast_mask = raw_baseline["is_forecast"]
    forecast_dates = raw_baseline.loc[forecast_mask, "date"]
    forecast_values = raw_baseline.loc[forecast_mask, "linear"]

    reseasonalised = reseasonalise_values(
        forecast_dates.reset_index(drop=True),
        forecast_values.reset_index(drop=True),
        season,
    )

    # linear_forecast returns int64; cast to float before assigning reseasonalised floats
    raw_baseline["linear"] = raw_baseline["linear"].astype(float)
    raw_baseline.loc[forecast_mask, "linear"] = reseasonalised.values
    return raw_baseline


def _hist_row(date, actual, baseline, has_bands):
    row = {
        "date": date,
        "actual": actual,
        "baseline": baseline,
        "new_content_uplift": 0,
        "decay": 0,
        "is_forecast": False,
    }
    if has_bands:
        row["positional_uplift_p10"] = 0
        row["positional_uplift_p50"] = 0
        row["positional_uplift_p90"] = 0
        row["combined_p10"] = actual
        row["combined_p50"] = actual
        row["combined_p90"] = actual
    else:
        row["positional_uplift"] = 0
        row["combined"] = actual
    return row


def _forecast_row(
    date, baseline_val, month,
    positional_monthly, new_content_monthly,
    decay_df, has_bands,
):
    nc_uplift = _get_monthly_value(new_content_monthly, month, "traffic")
    decay = _get_monthly_value(decay_df, month, "cumulative_decay")

    row = {
        "date": date,
        "actual": None,
        "baseline": baseline_val,
        "new_content_uplift": nc_uplift,
        "decay": decay,
        "is_forecast": True,
    }

    if has_bands:
        p10 = _get_monthly_value(positional_monthly, month, "uplift_p10")
        p50 = _get_monthly_value(positional_monthly, month, "uplift_p50")
        p90 = _get_monthly_value(positional_monthly, month, "uplift_p90")
        row["positional_uplift_p10"] = p10
        row["positional_uplift_p50"] = p50
        row["positional_uplift_p90"] = p90
        row["combined_p10"] = int(max(0, baseline_val + p10 + nc_uplift - decay))
        row["combined_p50"] = int(max(0, baseline_val + p50 + nc_uplift - decay))
        row["combined_p90"] = int(max(0, baseline_val + p90 + nc_uplift - decay))
    else:
        pos_uplift = _get_monthly_value(positional_monthly, month, "uplift")
        row["positional_uplift"] = pos_uplift
        row["combined"] = int(max(0, baseline_val + pos_uplift + nc_uplift - decay))

    return row


def _get_monthly_value(monthly_df: pd.DataFrame | None, month: int, col: str) -> int:
    if monthly_df is None or monthly_df.empty:
        return 0
    if col not in monthly_df.columns:
        return 0
    row = monthly_df[monthly_df["month"] == month]
    if len(row) == 0:
        return 0
    return int(row[col].iloc[0])
