import pandas as pd


CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "AUD": "A$",
    "CAD": "C$",
}


def add_revenue(
    df: pd.DataFrame,
    cvr: float,
    aov: float,
    currency: str = "USD",
    traffic_col: str = "traffic",
) -> pd.DataFrame:
    """Add transactions and revenue columns to a monthly projection DataFrame.

    Args:
        df: DataFrame with a traffic column.
        cvr: Conversion rate as a percentage (e.g. 2.5 = 2.5%).
        aov: Average order value in the given currency.
        currency: Currency code (USD, EUR, GBP, AUD, CAD).
        traffic_col: Name of the traffic column to use.

    Returns:
        DataFrame with added 'leads', 'transactions', and 'revenue' columns.
    """
    df = df.copy()
    cvr_decimal = cvr / 100.0

    df["leads"] = (df[traffic_col] * cvr_decimal).round(0).astype(int)
    df["transactions"] = df["leads"]  # Alias for clarity
    df["revenue"] = (df["transactions"] * aov).round(2)
    df["aov_used"] = aov
    df["cr_used"] = cvr

    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    df.attrs["currency_symbol"] = symbol
    df.attrs["currency"] = currency

    return df


def add_dynamic_revenue(
    df: pd.DataFrame,
    cvr_series: list[float] | float,
    aov_series: list[float] | float,
    currency: str = "USD",
    traffic_col: str = "traffic",
) -> pd.DataFrame:
    """Add transactions and revenue using per-month CVR and AOV values.

    Args:
        df: DataFrame with a traffic column.
        cvr_series: List of CVR% values per row, or a single static value.
        aov_series: List of AOV values per row, or a single static value.
        currency: Currency code.
        traffic_col: Name of the traffic column.

    Returns:
        DataFrame with transactions, revenue, aov_used, cr_used columns.
    """
    df = df.copy()
    n = len(df)

    if isinstance(cvr_series, (int, float)):
        cvr_values = [cvr_series] * n
    else:
        cvr_values = list(cvr_series)[:n]
        cvr_values += [cvr_values[-1]] * (n - len(cvr_values))

    if isinstance(aov_series, (int, float)):
        aov_values = [aov_series] * n
    else:
        aov_values = list(aov_series)[:n]
        aov_values += [aov_values[-1]] * (n - len(aov_values))

    df["cr_used"] = cvr_values
    df["aov_used"] = aov_values

    traffic = df[traffic_col].values
    transactions = []
    revenues = []
    for i in range(n):
        t = int(round(traffic[i] * cvr_values[i] / 100.0))
        r = round(t * aov_values[i], 2)
        transactions.append(t)
        revenues.append(r)

    df["transactions"] = transactions
    df["leads"] = df["transactions"]
    df["revenue"] = revenues

    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    df.attrs["currency_symbol"] = symbol
    df.attrs["currency"] = currency

    return df


def keyword_revenue_table(
    keyword_df: pd.DataFrame,
    cvr: float,
    aov: float,
    currency: str = "USD",
) -> pd.DataFrame:
    """Build per-keyword revenue breakdown.

    Args:
        keyword_df: Per-keyword results with 'estimated_monthly_traffic'.
        cvr: Conversion rate as a percentage.
        aov: Average order value.
        currency: Currency code.

    Returns:
        DataFrame with keyword, traffic, transactions, and revenue columns.
    """
    df = keyword_df[keyword_df["will_rank"]].copy()
    cvr_decimal = cvr / 100.0

    result = pd.DataFrame({
        "keyword": df["keyword"],
        "monthly_traffic": df["estimated_monthly_traffic"],
        "monthly_leads": (df["estimated_monthly_traffic"] * cvr_decimal).round(0).astype(int),
        "monthly_transactions": (df["estimated_monthly_traffic"] * cvr_decimal).round(0).astype(int),
        "monthly_revenue": (df["estimated_monthly_traffic"] * cvr_decimal * aov).round(2),
    })

    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    result.attrs["currency_symbol"] = symbol

    return result.reset_index(drop=True)


def build_full_metrics_table(
    result_df: pd.DataFrame,
    traffic_col: str = "linear",
) -> pd.DataFrame:
    """Build a comprehensive metrics table matching the requested column format.

    Extracts from a historical forecast result DataFrame all available metrics:
    sessions, revenue, transactions, AOV, CR%, plus YoY comparisons.

    Args:
        result_df: Output from run_historical_forecast().
        traffic_col: Which forecast method to use for sessions.

    Returns:
        DataFrame with all available metrics and YoY columns.
    """
    df = result_df.copy()
    out = pd.DataFrame()

    out["Month"] = df["date"]
    out["is_forecast"] = df["is_forecast"]

    # Sessions
    out["Organic Sessions"] = df["actual"]
    if traffic_col in df.columns:
        out["Organic Sessions Forecasted"] = df[traffic_col]

    # Revenue
    if "revenue_actual" in df.columns:
        out["Organic Revenue"] = df["revenue_actual"]
    if "revenue_forecast" in df.columns:
        out["Organic Revenue Forecasted"] = df["revenue_forecast"]

    # Transactions
    if "transactions_actual" in df.columns:
        out["Organic Transactions"] = df["transactions_actual"]
    if "transactions_forecast" in df.columns:
        out["Organic Transactions Forecasted"] = df["transactions_forecast"]

    # AOV
    if "aov_actual" in df.columns:
        out["AOV"] = df["aov_actual"]
    if "aov_forecast" in df.columns:
        out["AOV Forecasted"] = df["aov_forecast"]

    # CR%
    if "cr_actual" in df.columns:
        out["Organic CR %"] = df["cr_actual"]
    if "cr_forecast" in df.columns:
        out["Organic CR % Forecasted"] = df["cr_forecast"]

    # YoY calculations for available metrics
    yoy_pairs = [
        ("Organic Sessions", "Organic Sessions Forecasted"),
        ("Organic Revenue", "Organic Revenue Forecasted"),
        ("Organic Transactions", "Organic Transactions Forecasted"),
        ("AOV", "AOV Forecasted"),
        ("Organic CR %", "Organic CR % Forecasted"),
    ]

    for actual_col, forecast_col in yoy_pairs:
        # Build a combined series: actuals where available, forecasted for future
        combined_col = actual_col.replace("Organic ", "").replace(" %", "")
        if actual_col in out.columns or forecast_col in out.columns:
            combined = pd.Series([None] * len(out), dtype=float)
            if actual_col in out.columns:
                combined = out[actual_col].copy()
            if forecast_col in out.columns:
                # Fill forecast months
                mask = combined.isna() & out[forecast_col].notna()
                combined[mask] = out.loc[mask, forecast_col]

            # Calculate YoY
            diff_col = f"YoY {combined_col} Difference"
            pct_col = f"YoY {combined_col} % Increase"
            out[diff_col] = None
            out[pct_col] = None

            for i in range(12, len(out)):
                curr = combined.iloc[i]
                prev = combined.iloc[i - 12]
                if pd.notna(curr) and pd.notna(prev) and prev != 0:
                    out.at[out.index[i], diff_col] = round(curr - prev, 2)
                    out.at[out.index[i], pct_col] = round((curr - prev) / prev * 100, 1)

    return out
