import os

import pandas as pd
import pytest

from utils.ga4_loader import load_ga4_organic
from utils.keyword_loader import load_keyword_portfolio, split_existing_vs_new


@pytest.fixture
def ga4_sample_path():
    return os.path.join(os.path.dirname(__file__), "..", "assets", "sample-ga4-organic.xlsx")


@pytest.fixture
def semrush_sample_path():
    return os.path.join(os.path.dirname(__file__), "..", "assets", "sample-semrush-export.xlsx")


class TestGa4Loader:
    def test_reads_sample(self, ga4_sample_path):
        df = load_ga4_organic(ga4_sample_path)
        assert df is not None
        assert len(df) >= 30
        assert "date" in df.columns
        assert "traffic" in df.columns

    def test_no_future_dates(self, ga4_sample_path):
        df = load_ga4_organic(ga4_sample_path)
        assert df["date"].max() <= pd.Timestamp.now()

    def test_traffic_is_positive(self, ga4_sample_path):
        df = load_ga4_organic(ga4_sample_path)
        assert (df["traffic"] > 0).all()


class TestKeywordLoader:
    def test_reads_semrush_sample(self, semrush_sample_path):
        df = load_keyword_portfolio(semrush_sample_path)
        assert df is not None
        assert len(df) > 5000  # Cable Melbourne sample has ~9682 keywords
        assert "keyword" in df.columns
        assert "position" in df.columns
        assert "volume" in df.columns
        assert "kd" in df.columns
        # Canonical intent column — keyword_loader emits `intent`, never `primary_intent`
        assert "intent" in df.columns
        assert "primary_intent" not in df.columns

    def test_split_existing_vs_new(self, semrush_sample_path):
        df = load_keyword_portfolio(semrush_sample_path)
        existing, new = split_existing_vs_new(df)
        assert len(existing) + len(new) == len(df)
        assert len(new) < len(df) * 0.05


class TestFyDateBug:
    """Unit tests for _is_fy_day_bug and _fix_fy_dates."""

    def test_clean_dates_do_not_trigger(self):
        from utils.ga4_loader import _is_fy_day_bug
        # Normal month-start dates — day=1 throughout
        dates = pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01",
                                 "2024-04-01", "2024-05-01", "2024-06-01"])
        assert _is_fy_day_bug(dates) is False

    def test_fy23_day_corrects_calendar_year(self):
        from utils.ga4_loader import _fix_fy_dates
        # day=23 across months → FY23 → calendar years depend on month
        # Jul 2024 with day=23 → FY23 → Jul in FY23 means calendar year 2022
        # Jan 2024 with day=23 → FY23 → Jan in FY23 means calendar year 2023
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-07-23", "2024-01-23",
                                     "2024-08-23", "2024-03-23"]),
            "revenue": [1000, 2000, 1500, 2500],
        })
        result = _fix_fy_dates(df, "date")
        corrected = result["date"]
        # Jul with FY23 → calendar year 2022
        assert corrected.iloc[0] == pd.Timestamp("2022-07-01")
        # Jan with FY23 → calendar year 2023
        assert corrected.iloc[1] == pd.Timestamp("2023-01-01")
        # Aug with FY23 → calendar year 2022
        assert corrected.iloc[2] == pd.Timestamp("2022-08-01")
        # Mar with FY23 → calendar year 2023
        assert corrected.iloc[3] == pd.Timestamp("2023-03-01")

    def test_heuristic_fires_on_days_15_and_28(self):
        from utils.ga4_loader import _is_fy_day_bug
        # Mixed days 15 and 28 — both in 15-35 range, ≤4 unique values
        dates = pd.to_datetime([
            "2024-01-15", "2024-02-28", "2024-03-15", "2024-04-28",
            "2024-05-15", "2024-06-28",
        ])
        assert _is_fy_day_bug(dates) is True
