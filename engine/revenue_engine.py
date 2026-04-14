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
    """Add leads and revenue columns to a monthly projection DataFrame.

    Args:
        df: DataFrame with a traffic column.
        cvr: Conversion rate as a percentage (e.g. 2.5 = 2.5%).
        aov: Average order value in the given currency.
        currency: Currency code (USD, EUR, GBP, AUD, CAD).
        traffic_col: Name of the traffic column to use.

    Returns:
        DataFrame with added 'leads' and 'revenue' columns.
    """
    df = df.copy()
    cvr_decimal = cvr / 100.0

    df["leads"] = (df[traffic_col] * cvr_decimal).round(0).astype(int)
    df["revenue"] = (df["leads"] * aov).round(2)

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
        DataFrame with keyword, traffic, leads, and revenue columns.
    """
    df = keyword_df[keyword_df["will_rank"]].copy()
    cvr_decimal = cvr / 100.0

    result = pd.DataFrame({
        "keyword": df["keyword"],
        "monthly_traffic": df["estimated_monthly_traffic"],
        "monthly_leads": (df["estimated_monthly_traffic"] * cvr_decimal).round(0).astype(int),
        "monthly_revenue": (df["estimated_monthly_traffic"] * cvr_decimal * aov).round(2),
    })

    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    result.attrs["currency_symbol"] = symbol

    return result.reset_index(drop=True)
