import numpy as np
import pandas as pd

from engine.historical_engine import linear_forecast


def run_combined_forecast(
    historical_df: pd.DataFrame | None,
    positional_monthly: pd.DataFrame | None,
    new_content_monthly: pd.DataFrame | None,
    months: int,
    decay_df: pd.DataFrame | None = None,
    aio_erosion_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Layer every component into the canonical forecast.

    Math per month m:
        combined[m] = baseline[m]
                    + positional_uplift[m]
                    + new_content_uplift[m]
                    - decay[m]
                    - aio_erosion[m]

    P10/P50/P90 bands propagated from positional stream; decay and AIO
    erosion are deterministic subtractions.

    Returns:
        DataFrame with actual, baseline, positional bands, new_content,
        decay, aio_erosion, combined bands, is_forecast, uplift_pct.
    """
    rows = []

    has_bands = (
        positional_monthly is not None
        and not positional_monthly.empty
        and "uplift_p10" in positional_monthly.columns
    )

    if historical_df is not None:
        dates = historical_df["date"]
        traffic = historical_df["traffic"]
        baseline_df = linear_forecast(dates, traffic, months, confidence=15.0)

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
                aio_erosion_df=aio_erosion_df,
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
                aio_erosion_df=aio_erosion_df,
                has_bands=has_bands,
            ))

    result = pd.DataFrame(rows)

    # Uplift percentage (P50-based when bands available)
    forecast_mask = result["is_forecast"]
    result["uplift_pct"] = 0.0
    combined_col = "combined_p50" if has_bands else "combined"
    pos_col = "positional_uplift_p50" if has_bands else "positional_uplift"

    result.loc[forecast_mask, "uplift_pct"] = result.loc[forecast_mask].apply(
        lambda r: round(
            (r[pos_col] + r["new_content_uplift"]
             - r.get("decay", 0) - r.get("aio_erosion", 0))
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


def _hist_row(date, actual, baseline, has_bands):
    row = {
        "date": date,
        "actual": actual,
        "baseline": baseline,
        "new_content_uplift": 0,
        "decay": 0,
        "aio_erosion": 0,
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
    decay_df, aio_erosion_df, has_bands,
):
    nc_uplift = _get_monthly_value(new_content_monthly, month, "traffic")
    decay = _get_monthly_value(decay_df, month, "cumulative_decay")
    aio = _get_monthly_value(aio_erosion_df, month, "cumulative_erosion")

    row = {
        "date": date,
        "actual": None,
        "baseline": baseline_val,
        "new_content_uplift": nc_uplift,
        "decay": decay,
        "aio_erosion": aio,
        "is_forecast": True,
    }

    if has_bands:
        p10 = _get_monthly_value(positional_monthly, month, "uplift_p10")
        p50 = _get_monthly_value(positional_monthly, month, "uplift_p50")
        p90 = _get_monthly_value(positional_monthly, month, "uplift_p90")
        row["positional_uplift_p10"] = p10
        row["positional_uplift_p50"] = p50
        row["positional_uplift_p90"] = p90
        row["combined_p10"] = int(max(0, baseline_val + p10 + nc_uplift - decay - aio))
        row["combined_p50"] = int(max(0, baseline_val + p50 + nc_uplift - decay - aio))
        row["combined_p90"] = int(max(0, baseline_val + p90 + nc_uplift - decay - aio))
    else:
        pos_uplift = _get_monthly_value(positional_monthly, month, "uplift")
        row["positional_uplift"] = pos_uplift
        row["combined"] = int(max(0, baseline_val + pos_uplift + nc_uplift - decay - aio))

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
