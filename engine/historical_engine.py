import numpy as np
import pandas as pd


def linear_forecast(
    dates: pd.Series,
    traffic: pd.Series,
    future_months: int,
    confidence: float = 15.0,
) -> pd.DataFrame:
    """Forecast traffic using linear regression with confidence bands.

    Args:
        dates: Series of datetime values.
        traffic: Series of traffic values.
        future_months: Number of months to forecast.
        confidence: Percentage for upper/lower bounds.

    Returns:
        DataFrame with month index, date, forecast, upper, lower columns.
    """
    x = np.arange(len(traffic))
    y = traffic.values.astype(float)
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = coeffs

    # Build forecast
    rows = []
    dates = pd.Series(dates) if not isinstance(dates, pd.Series) else dates
    last_date = dates.iloc[-1]

    # Historical fitted values
    for i in range(len(traffic)):
        fitted = slope * i + intercept
        rows.append({
            "date": dates.iloc[i],
            "actual": int(traffic.iloc[i]),
            "linear": round(fitted),
            "linear_upper": round(fitted * (1 + confidence / 100)),
            "linear_lower": round(max(0, fitted * (1 - confidence / 100))),
            "is_forecast": False,
        })

    # Future values
    for j in range(1, future_months + 1):
        idx = len(traffic) - 1 + j
        forecast_val = slope * idx + intercept
        forecast_date = last_date + pd.DateOffset(months=j)
        rows.append({
            "date": forecast_date,
            "actual": None,
            "linear": round(max(0, forecast_val)),
            "linear_upper": round(max(0, forecast_val * (1 + confidence / 100))),
            "linear_lower": round(max(0, forecast_val * (1 - confidence / 100))),
            "is_forecast": True,
        })

    return pd.DataFrame(rows)


def exponential_smoothing_forecast(
    traffic: pd.Series,
    alpha: float,
    future_months: int,
) -> list[float]:
    """Simple exponential smoothing with extrapolation.

    Args:
        traffic: Historical traffic values.
        alpha: Smoothing factor (0-1).
        future_months: Number of months to forecast.

    Returns:
        List of smoothed historical values + forecasted values.
    """
    values = traffic.values.astype(float)
    smoothed = [values[0]]

    for i in range(1, len(values)):
        s = alpha * values[i] + (1 - alpha) * smoothed[-1]
        smoothed.append(s)

    # Extrapolate: calculate average trend from smoothed series
    if len(smoothed) >= 2:
        diffs = [smoothed[i] - smoothed[i - 1] for i in range(1, len(smoothed))]
        # Weight recent diffs more heavily
        weights = np.arange(1, len(diffs) + 1, dtype=float)
        avg_trend = np.average(diffs, weights=weights)
    else:
        avg_trend = 0

    last_smoothed = smoothed[-1]
    for j in range(1, future_months + 1):
        next_val = max(0, last_smoothed + avg_trend * j)
        smoothed.append(next_val)

    return [round(v) for v in smoothed]


def sma_forecast(
    traffic: pd.Series,
    window: int,
    future_months: int,
) -> list[float]:
    """Simple Moving Average forecast, feeding predictions back into window.

    Args:
        traffic: Historical traffic values.
        window: Number of months in the moving average window.
        future_months: Number of months to forecast.

    Returns:
        List of historical values + forecasted values.
    """
    values = list(traffic.values.astype(float))
    result = list(values)

    for _ in range(future_months):
        avg = np.mean(result[-window:])
        result.append(round(max(0, avg)))

    return result


def forecast_series(
    series: pd.Series,
    future_months: int,
    method: str = "linear",
    allow_negative: bool = False,
) -> list[float]:
    """Forecast any numeric series using linear regression.

    Args:
        series: Historical numeric values.
        future_months: Number of months to forecast.
        method: Forecasting method ('linear').
        allow_negative: Whether to allow negative forecasted values.

    Returns:
        List of historical fitted values + forecasted values.
    """
    values = series.values.astype(float)
    x = np.arange(len(values))
    coeffs = np.polyfit(x, values, 1)
    slope, intercept = coeffs

    result = []
    for i in range(len(values)):
        fitted = slope * i + intercept
        if not allow_negative:
            fitted = max(0, fitted)
        result.append(round(fitted, 2))

    for j in range(1, future_months + 1):
        idx = len(values) - 1 + j
        forecast_val = slope * idx + intercept
        if not allow_negative:
            forecast_val = max(0, forecast_val)
        result.append(round(forecast_val, 2))

    return result


def calculate_growth_rates(traffic: pd.Series) -> dict:
    """Calculate MoM and YoY growth rates from traffic data."""
    values = traffic.values.astype(float)
    mom_rates = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            rate = (values[i] - values[i - 1]) / values[i - 1] * 100
            mom_rates.append(rate)

    yoy_rates = []
    for i in range(12, len(values)):
        if values[i - 12] > 0:
            rate = (values[i] - values[i - 12]) / values[i - 12] * 100
            yoy_rates.append(rate)

    return {
        "avg_mom": np.mean(mom_rates) if mom_rates else 0.0,
        "latest_mom": mom_rates[-1] if mom_rates else 0.0,
        "avg_yoy": np.mean(yoy_rates) if yoy_rates else 0.0,
        "latest_yoy": yoy_rates[-1] if yoy_rates else 0.0,
    }


def calculate_yoy(
    result_df: pd.DataFrame,
    metric_col: str,
) -> pd.DataFrame:
    """Add YoY difference and % change columns for a metric.

    Args:
        result_df: DataFrame with 'date' and the metric column.
        metric_col: Name of the column to calculate YoY for.

    Returns:
        DataFrame with added yoy_diff and yoy_pct columns.
    """
    df = result_df.copy()
    diff_col = f"{metric_col}_yoy_diff"
    pct_col = f"{metric_col}_yoy_pct"

    df[diff_col] = None
    df[pct_col] = None

    for i in range(len(df)):
        current_date = df.iloc[i]["date"]
        if pd.isna(current_date):
            continue
        # Find row 12 months ago
        target_date = current_date - pd.DateOffset(months=12)
        match = df[df["date"].dt.to_period("M") == target_date.to_period("M")]
        if not match.empty:
            prev_val = match.iloc[0][metric_col]
            curr_val = df.iloc[i][metric_col]
            if pd.notna(prev_val) and pd.notna(curr_val) and prev_val != 0:
                df.at[df.index[i], diff_col] = round(curr_val - prev_val, 2)
                df.at[df.index[i], pct_col] = round((curr_val - prev_val) / prev_val * 100, 1)

    return df


def run_historical_forecast(
    df: pd.DataFrame,
    months: int,
    methods: list[str],
    sma_window: int = 3,
    alpha: float = 0.3,
    confidence: float = 15.0,
) -> pd.DataFrame:
    """Orchestrate historical forecast with selected methods.

    Forecasts traffic (required) and optionally revenue, transactions, aov, cr
    if those columns are present in the input DataFrame.

    Args:
        df: DataFrame with 'date' and 'traffic' columns (+ optional metrics).
        months: Forecast horizon in months.
        methods: List of method names to include.
        sma_window: Window size for SMA.
        alpha: Smoothing factor for exponential smoothing.
        confidence: Confidence band percentage for linear regression.

    Returns:
        Combined DataFrame with all method results.
    """
    dates = df["date"]
    traffic = df["traffic"]
    n_hist = len(traffic)

    # Start with linear forecast as the base (it has the date structure)
    if "Linear Regression" in methods:
        result = linear_forecast(dates, traffic, months, confidence)
    else:
        # Build base structure without linear columns
        rows = []
        last_date = dates.iloc[-1]
        for i in range(n_hist):
            rows.append({
                "date": dates.iloc[i],
                "actual": int(traffic.iloc[i]),
                "is_forecast": False,
            })
        for j in range(1, months + 1):
            rows.append({
                "date": last_date + pd.DateOffset(months=j),
                "actual": None,
                "is_forecast": True,
            })
        result = pd.DataFrame(rows)

    # Add exponential smoothing
    if "Exponential Smoothing" in methods:
        es_values = exponential_smoothing_forecast(traffic, alpha, months)
        result["exponential_smoothing"] = es_values[:len(result)]

    # Add SMA
    if "Simple Moving Average" in methods:
        sma_values = sma_forecast(traffic, sma_window, months)
        result["sma"] = sma_values[:len(result)]

    # Forecast optional metrics using linear trend
    optional_metrics = ["revenue", "transactions", "aov", "cr"]
    for metric in optional_metrics:
        if metric in df.columns and df[metric].notna().sum() >= 3:
            series = df[metric].ffill().fillna(0)
            forecasted = forecast_series(series, months, allow_negative=(metric == "cr"))
            # Store historical actuals + forecast
            actual_col = f"{metric}_actual"
            forecast_col = f"{metric}_forecast"
            actuals = list(series.values) + [None] * months
            result[actual_col] = actuals[:len(result)]
            result[forecast_col] = forecasted[:len(result)]

    # Add growth rates as metadata attribute
    result.attrs["growth_rates"] = calculate_growth_rates(traffic)

    return result
