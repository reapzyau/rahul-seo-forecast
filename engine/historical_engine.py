import numpy as np
import pandas as pd

# Gating thresholds for model selection based on historical data length
_PROPHET_MIN_MONTHS = 24
_HOLTS_MIN_MONTHS = 12

# ──────────────────────────────────────────────────────────────────────────────
# Section 1: YoY (same-calendar-month) baseline
# ──────────────────────────────────────────────────────────────────────────────


def _row_to_baseline(row: pd.Series, source: str) -> dict:
    """Convert a GA4 data row to the baseline dict schema."""
    return {
        "traffic": int(row["traffic"]),
        "transactions": float(row["transactions"]) if "transactions" in row.index and pd.notna(row["transactions"]) else None,
        "revenue": float(row["revenue"]) if "revenue" in row.index and pd.notna(row["revenue"]) else None,
        "aov_actual": float(row["aov"]) if "aov" in row.index and pd.notna(row["aov"]) else None,
        "source": source,
    }


def yoy_baseline(
    ga4_df: pd.DataFrame,
    forecast_dates: pd.DatetimeIndex,
) -> dict:
    """Build month-by-month baseline using prior-year same-calendar-month actuals.

    Each forecast month's baseline equals the same calendar month from the prior
    fiscal year. When the prior-year actual doesn't exist (e.g. forecasting Jun-27
    when GA4 only goes to Mar-26), falls back to the most-recent same-calendar-month
    actual rather than averaging across years — avoids startup-period drag.

    Args:
        ga4_df: DataFrame with 'date' and 'traffic' (and optionally 'transactions',
                'revenue', 'aov') columns, monthly granularity.
        forecast_dates: pd.DatetimeIndex of forecast months (first-of-month).

    Returns:
        Dict[pd.Timestamp, dict] keyed by forecast date. Each value contains:
            {traffic, transactions, revenue, aov_actual, source}
        where source is a human-readable string describing the data origin.
    """
    df = ga4_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    ga4_indexed = df.set_index("date")

    out: dict = {}
    for fdate in forecast_dates:
        fdate_norm = pd.Timestamp(year=fdate.year, month=fdate.month, day=1)
        prior = pd.Timestamp(year=fdate.year - 1, month=fdate.month, day=1)

        if prior in ga4_indexed.index:
            out[fdate_norm] = _row_to_baseline(
                ga4_indexed.loc[prior],
                source=f"GA4 {prior.strftime('%b-%y')} actual",
            )
        else:
            # Fallback: most-recent same-calendar-month (avoids startup-period drag)
            same_month = df[df["date"].dt.month == fdate.month].sort_values("date")
            if len(same_month):
                row = same_month.iloc[-1]
                out[fdate_norm] = _row_to_baseline(
                    row,
                    source=(
                        f"GA4 {row['date'].strftime('%b-%y')} actual "
                        f"(most recent {fdate.strftime('%b')}, no prior-FY data)"
                    ),
                )
            else:
                trailing_avg = int(df["traffic"].tail(6).mean())
                out[fdate_norm] = {
                    "traffic": trailing_avg,
                    "transactions": None,
                    "revenue": None,
                    "aov_actual": None,
                    "source": "6-mo trailing avg (no historical match)",
                }
    return out


def detect_startup_period(
    traffic_series: pd.Series,
    threshold_ratio: float = 0.5,
) -> bool:
    """Return True when the series shows startup/ramp rather than normal variance.

    Compares the first-6-month mean to the last-6-month mean. When the early
    period is less than threshold_ratio × recent, it signals startup-phase growth
    — in which case Holt's avg_mom would be inflated by the ramp, not seasonality.

    Args:
        traffic_series: Historical monthly traffic values.
        threshold_ratio: Early/recent ratio below which ramp is declared (default 0.5).
            0.5 means early average is less than half the recent average.

    Returns:
        True if startup period is detected, False otherwise.
    """
    if len(traffic_series) < 12:
        return False
    early = traffic_series.head(6).mean()
    recent = traffic_series.tail(6).mean()
    if recent == 0:
        return False
    return bool(early < threshold_ratio * recent)


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
    """Holt's linear trend (double exponential smoothing).

    Tracks level and trend as separate components so the forecast
    genuinely diverges from simple linear regression on non-linear data.

    Args:
        traffic: Historical traffic values.
        alpha: Level smoothing factor (0-1).
        future_months: Number of months to forecast.

    Returns:
        List of smoothed historical values + forecasted values.
    """
    values = traffic.values.astype(float)
    n = len(values)
    beta = 0.1  # trend smoothing factor

    level = values[0]
    trend = (values[1] - values[0]) if n > 1 else 0.0

    smoothed = [level]
    for i in range(1, n):
        prev_level = level
        level = alpha * values[i] + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        smoothed.append(level)

    # Forecast h steps ahead: F_{t+h} = L_t + h * T_t
    result = list(smoothed)
    for h in range(1, future_months + 1):
        result.append(max(0.0, level + h * trend))

    return [round(v) for v in result]


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


def run_historical_forecast_v4(
    df: pd.DataFrame,
    months: int,
    changepoint_prior_scale: float = 0.05,
    sma_window: int = 3,
    alpha: float = 0.3,
    confidence: float = 15.0,
    seasonality: dict | None = None,
    aio_intent_penalties: dict | None = None,
) -> pd.DataFrame:
    """Data-length-gated historical forecast (v4).

    Selects the primary model based on available data:
      ≥24 months  → Prophet (primary) + linear reference line
      12–23 months → Holt's exponential smoothing (primary), Prophet attempted
      <12 months   → linear regression only; warns that seasonality can't be detected

    A 'primary_method' column indicates which model was chosen per row.
    Seasonality is applied to the forecast portion when provided.
    AIO erosion doesn't apply to historical directly (history already reflects reality).

    Args:
        df: DataFrame with 'date' and 'traffic' (+ optional metrics).
        months: Forecast horizon in months.
        changepoint_prior_scale: Prophet trend flexibility (0.001–0.5).
        sma_window: Fallback SMA window size.
        alpha: Holt's smoothing factor.
        confidence: Confidence band % for linear/Holt's.
        seasonality: Dict of month_number → {traffic_mod, ...} applied to forecast.
        aio_intent_penalties: Unused here (historical reflects reality); kept for API symmetry.

    Returns:
        DataFrame with all method columns plus 'primary_method' and metadata attrs.
    """
    n_hist = len(df)
    dates = df["date"]
    traffic = df["traffic"]

    # Determine primary method and gatekeeping metadata
    if n_hist >= _PROPHET_MIN_MONTHS:
        chosen_method = "prophet"
        method_reason = f"Prophet selected ({n_hist} months ≥ {_PROPHET_MIN_MONTHS})"
        low_confidence = False
    elif n_hist >= _HOLTS_MIN_MONTHS:
        chosen_method = "holts"
        method_reason = f"Holt's ES selected ({n_hist} months, 12–23 — Prophet low confidence)"
        low_confidence = True
    else:
        chosen_method = "linear"
        method_reason = f"Linear regression only ({n_hist} months < {_HOLTS_MIN_MONTHS} — seasonality undetectable)"
        low_confidence = True

    # Always produce linear as base structure / reference
    result = linear_forecast(dates, traffic, months, confidence)
    result["primary_method"] = chosen_method

    # Holt's ES
    es_values = exponential_smoothing_forecast(traffic, alpha, months)
    result["exponential_smoothing"] = es_values[:len(result)]

    # Prophet
    prophet_ok = False
    if chosen_method in ("prophet", "holts"):
        try:
            from engine.prophet_engine import run_prophet_forecast
            prophet_df = run_prophet_forecast(df, months, changepoint_prior_scale=changepoint_prior_scale)
            result["prophet"] = prophet_df["forecast"].values[:len(result)]
            result["prophet_lower"] = prophet_df["forecast_lower"].values[:len(result)]
            result["prophet_upper"] = prophet_df["forecast_upper"].values[:len(result)]
            prophet_ok = True
        except (ImportError, Exception):
            pass

    # Apply seasonality to forecast portion
    if seasonality:
        forecast_mask = result["is_forecast"]
        for col in ["linear", "exponential_smoothing"] + (["prophet"] if prophet_ok else []):
            if col in result.columns:
                seasonal_mults = result.loc[forecast_mask, "date"].apply(
                    lambda d: 1 + seasonality.get(d.month, {}).get("traffic_mod", 0)
                )
                result.loc[forecast_mask, col] = (
                    result.loc[forecast_mask, col] * seasonal_mults.values
                ).round(0).astype(int)

    # Optional metrics
    optional_metrics = ["revenue", "transactions", "aov", "cr"]
    for metric in optional_metrics:
        if metric in df.columns and df[metric].notna().sum() >= 3:
            series = df[metric].ffill().fillna(0)
            forecasted = forecast_series(series, months, allow_negative=(metric == "cr"))
            result[f"{metric}_actual"] = (list(series.values) + [None] * months)[:len(result)]
            result[f"{metric}_forecast"] = forecasted[:len(result)]

    result.attrs["growth_rates"] = calculate_growth_rates(traffic)
    result.attrs["chosen_method"] = chosen_method
    result.attrs["method_reason"] = method_reason
    result.attrs["low_confidence"] = low_confidence
    result.attrs["prophet_available"] = prophet_ok

    return result


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
