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

    def test_split_existing_vs_new(self, semrush_sample_path):
        df = load_keyword_portfolio(semrush_sample_path)
        existing, new = split_existing_vs_new(df)
        assert len(existing) + len(new) == len(df)
        assert len(new) < len(df) * 0.05
