"""Named factories for synthetic test data.

Every test that previously built a DataFrame inline should import from here.
"""
from __future__ import annotations

import pandas as pd


def make_ga4_df(
    months: int = 12,
    starting_traffic: int = 10_000,
    trend: float = 100.0,
    with_revenue: bool = False,
    start_date: str = "2024-01-01",
) -> pd.DataFrame:
    """GA4-style monthly traffic data."""
    dates = pd.date_range(start_date, periods=months, freq="MS")
    traffic = [int(starting_traffic + i * trend) for i in range(months)]
    df = pd.DataFrame({"date": dates, "traffic": traffic})
    if with_revenue:
        df["revenue"] = df["traffic"] * 2.5
        df["transactions"] = (df["traffic"] * 0.025).astype(int)
        df["aov"] = 100.0
        df["cr"] = 2.5
    return df


def make_semrush_kw_df(
    n: int = 50,
    positions: list[int] | None = None,
    volumes: list[int] | None = None,
    kds: list[int] | None = None,
    include_aio: bool = False,
) -> pd.DataFrame:
    """SEMrush-style keyword portfolio with position and traffic columns."""
    positions = positions or [10] * n
    volumes = volumes or [1000] * n
    kds = kds or [30] * n
    return pd.DataFrame({
        "keyword": [f"kw_{i}" for i in range(n)],
        "position": positions[:n],
        "volume": volumes[:n],
        "kd": kds[:n],
        "current_traffic": [80] * n,
        "intent": ["commercial"] * n,
        "has_aio": [include_aio] * n,
    })


def make_new_content_kw_df(n: int = 20) -> pd.DataFrame:
    """Input for run_new_content_forecast — no position column."""
    return pd.DataFrame({
        "keyword": [f"kw_{i}" for i in range(n)],
        "volume": [500 + i * 100 for i in range(n)],
        "kd": [20 + i for i in range(n)],
    })
