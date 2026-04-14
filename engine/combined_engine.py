import numpy as np
import pandas as pd

from engine.historical_engine import linear_forecast


def run_combined_forecast(
    keyword_df: pd.DataFrame,
    monthly_kw_df: pd.DataFrame,
    historical_df: pd.DataFrame,
    months: int,
) -> pd.DataFrame:
    """Merge historical baseline with keyword incremental traffic.

    Args:
        keyword_df: Per-keyword results from keyword engine.
        monthly_kw_df: Monthly keyword traffic projection.
        historical_df: Raw historical data with 'date' and 'traffic'.
        months: Forecast horizon in months.

    Returns:
        DataFrame with baseline, new_content, combined, and uplift columns.
    """
    dates = historical_df["date"]
    traffic = historical_df["traffic"]

    # Get linear baseline
    baseline_df = linear_forecast(dates, traffic, months, confidence=15.0)

    # Build combined result
    rows = []
    last_date = dates.iloc[-1]

    # Historical portion
    for i in range(len(traffic)):
        rows.append({
            "date": baseline_df.iloc[i]["date"],
            "actual": int(traffic.iloc[i]),
            "baseline": baseline_df.iloc[i]["linear"],
            "new_content": 0,
            "combined": int(traffic.iloc[i]),
            "is_forecast": False,
        })

    # Forecast portion
    for j in range(1, months + 1):
        forecast_date = last_date + pd.DateOffset(months=j)
        baseline_val = baseline_df[baseline_df["is_forecast"]].iloc[j - 1]["linear"]

        # Get incremental traffic from keyword engine for this month
        kw_row = monthly_kw_df[monthly_kw_df["month"] == j]
        incremental = int(kw_row["traffic"].iloc[0]) if len(kw_row) > 0 else 0

        combined_val = baseline_val + incremental
        rows.append({
            "date": forecast_date,
            "actual": None,
            "baseline": int(baseline_val),
            "new_content": incremental,
            "combined": int(combined_val),
            "is_forecast": True,
        })

    result = pd.DataFrame(rows)

    # Calculate uplift percentage for forecast period
    forecast_mask = result["is_forecast"]
    result["uplift_pct"] = 0.0
    result.loc[forecast_mask, "uplift_pct"] = result.loc[forecast_mask].apply(
        lambda r: round((r["new_content"] / r["baseline"] * 100), 1)
        if r["baseline"] > 0 else 0.0,
        axis=1,
    )

    return result
