import numpy as np
import pandas as pd

from engine.historical_engine import linear_forecast


def run_combined_forecast(
    historical_df: pd.DataFrame | None,
    positional_monthly: pd.DataFrame | None,
    new_content_monthly: pd.DataFrame | None,
    months: int,
) -> pd.DataFrame:
    """Merge historical baseline with positional and new-content uplift streams.

    Args:
        historical_df: Raw historical data with 'date' and 'traffic'. None to skip baseline.
        positional_monthly: Monthly positional uplift with 'month' and 'uplift'. None to skip.
        new_content_monthly: Monthly new-content traffic with 'month' and 'traffic'. None to skip.
        months: Forecast horizon in months.

    Returns:
        DataFrame with actual, baseline, positional_uplift, new_content_uplift,
        combined, is_forecast, and uplift_pct columns.
    """
    rows = []

    if historical_df is not None:
        dates = historical_df["date"]
        traffic = historical_df["traffic"]

        baseline_df = linear_forecast(dates, traffic, months, confidence=15.0)
        last_date = dates.iloc[-1]

        # Historical portion
        for i in range(len(traffic)):
            rows.append({
                "date": baseline_df.iloc[i]["date"],
                "actual": int(traffic.iloc[i]),
                "baseline": baseline_df.iloc[i]["linear"],
                "positional_uplift": 0,
                "new_content_uplift": 0,
                "combined": int(traffic.iloc[i]),
                "is_forecast": False,
            })

        # Precompute forecast slice
        baseline_forecast = baseline_df[baseline_df["is_forecast"]].reset_index(drop=True)

        # Forecast portion
        for j in range(1, months + 1):
            forecast_date = last_date + pd.DateOffset(months=j)
            baseline_val = int(baseline_forecast.iloc[j - 1]["linear"])

            pos_uplift = _get_monthly_value(positional_monthly, j, "uplift")
            nc_uplift = _get_monthly_value(new_content_monthly, j, "traffic")

            combined_val = baseline_val + pos_uplift + nc_uplift
            rows.append({
                "date": forecast_date,
                "actual": None,
                "baseline": baseline_val,
                "positional_uplift": pos_uplift,
                "new_content_uplift": nc_uplift,
                "combined": int(combined_val),
                "is_forecast": True,
            })
    else:
        # No historical data — baseline is 0, forecast only
        base_date = pd.Timestamp.now().normalize().replace(day=1)
        for j in range(1, months + 1):
            forecast_date = base_date + pd.DateOffset(months=j)

            pos_uplift = _get_monthly_value(positional_monthly, j, "uplift")
            nc_uplift = _get_monthly_value(new_content_monthly, j, "traffic")

            rows.append({
                "date": forecast_date,
                "actual": None,
                "baseline": 0,
                "positional_uplift": pos_uplift,
                "new_content_uplift": nc_uplift,
                "combined": pos_uplift + nc_uplift,
                "is_forecast": True,
            })

    result = pd.DataFrame(rows)

    # Calculate uplift percentage for forecast period
    forecast_mask = result["is_forecast"]
    result["uplift_pct"] = 0.0
    result.loc[forecast_mask, "uplift_pct"] = result.loc[forecast_mask].apply(
        lambda r: round(
            (r["positional_uplift"] + r["new_content_uplift"]) / r["baseline"] * 100, 1
        ) if r["baseline"] > 0 else 0.0,
        axis=1,
    )

    return result


def _get_monthly_value(monthly_df: pd.DataFrame | None, month: int, col: str) -> int:
    """Extract a monthly value from a projection DataFrame, defaulting to 0."""
    if monthly_df is None or monthly_df.empty:
        return 0
    row = monthly_df[monthly_df["month"] == month]
    if len(row) == 0:
        return 0
    return int(row[col].iloc[0])
