"""Prophet-based historical forecasting engine.

Requires prophet>=1.1.5 and cmdstanpy>=1.2.0.
If Prophet is unavailable the module raises ImportError with a clear message;
callers should catch and fall back to Holt's or linear regression.
"""

from __future__ import annotations

import pandas as pd

try:
    from prophet import Prophet
    _PROPHET_AVAILABLE = True
except ImportError:
    _PROPHET_AVAILABLE = False


def is_prophet_available() -> bool:
    """Return True if the Prophet library is installed and importable."""
    return _PROPHET_AVAILABLE


def _require_prophet() -> None:
    if not _PROPHET_AVAILABLE:
        raise ImportError(
            "Facebook Prophet is not installed. "
            "Run: pip install prophet>=1.1.5 cmdstanpy>=1.2.0\n"
            "The historical engine will fall back to Holt's exponential smoothing."
        )


def run_prophet_forecast(
    df: pd.DataFrame,
    months: int,
    holidays_country: str = "AU",
    changepoint_prior_scale: float = 0.05,
) -> pd.DataFrame:
    """Forecast traffic using Facebook Prophet.

    Args:
        df: DataFrame with 'date' (datetime) and 'traffic' (int/float) columns.
        months: Number of future months to forecast.
        holidays_country: ISO country code for built-in holidays (unused when
                          AU_HOLIDAYS DataFrame is injected directly).
        changepoint_prior_scale: Controls trend flexibility (0.001 rigid – 0.5 flexible).

    Returns:
        DataFrame with columns: date, forecast, forecast_lower, forecast_upper, is_forecast.
        Historical rows have is_forecast=False; future rows have is_forecast=True.
    """
    _require_prophet()

    from engine.seasonality_engine import AU_HOLIDAYS

    # Prophet expects columns 'ds' and 'y'
    train = df[["date", "traffic"]].rename(columns={"date": "ds", "traffic": "y"})
    train["ds"] = pd.to_datetime(train["ds"])

    # Build holiday DataFrame with years covering train + forecast period
    future_years = sorted({
        d.year for d in pd.date_range(
            train["ds"].min(), periods=len(train) + months, freq="MS"
        )
    })
    holidays = AU_HOLIDAYS[
        pd.to_datetime(AU_HOLIDAYS["ds"]).dt.year.isin(future_years)
    ].copy()
    holidays["ds"] = pd.to_datetime(holidays["ds"])

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        holidays=holidays,
        changepoint_prior_scale=changepoint_prior_scale,
    )
    model.fit(train)

    last_date = train["ds"].iloc[-1]
    future_dates = [last_date + pd.DateOffset(months=j) for j in range(1, months + 1)]
    future_df = pd.DataFrame({"ds": pd.to_datetime(future_dates)})

    forecast = model.predict(pd.concat([train[["ds"]], future_df], ignore_index=True))

    rows = []
    n_hist = len(train)
    for i, row in forecast.iterrows():
        is_fcast = i >= n_hist
        rows.append({
            "date": row["ds"],
            "forecast": max(0, round(row["yhat"])),
            "forecast_lower": max(0, round(row["yhat_lower"])),
            "forecast_upper": max(0, round(row["yhat_upper"])),
            "is_forecast": is_fcast,
        })

    return pd.DataFrame(rows)
