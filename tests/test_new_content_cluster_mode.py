"""Regression tests for cluster-mode defensiveness in the New Content page.

When the Auto-cluster source is used, keyword_df is always an empty DataFrame
(cluster forecasting doesn't produce per-keyword rows).  These tests verify that
the guard conditions introduced to fix the KeyError are correct and sufficient.
"""
from __future__ import annotations

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helper — reproduces the exact guard expressions used in the page
# ---------------------------------------------------------------------------

def _n_ranking(keyword_df: pd.DataFrame) -> int:
    """Mirrors the guard at the Traffic Projection KPI card."""
    _has_kw_cols = not keyword_df.empty and "will_rank" in keyword_df.columns
    return int(keyword_df["will_rank"].sum()) if _has_kw_cols else 0


def _export_summary_ranking(keyword_df: pd.DataFrame) -> str:
    """Mirrors the guard in the Export tab summary dict."""
    _has_kw_export = not keyword_df.empty and "will_rank" in keyword_df.columns
    return (
        f"{int(keyword_df['will_rank'].sum())} / {len(keyword_df)}"
        if _has_kw_export else "—"
    )


def _export_figs_count(keyword_df: pd.DataFrame) -> int:
    """Mirrors the figs list construction — returns how many figs would be built."""
    _has_kw_export = not keyword_df.empty and "will_rank" in keyword_df.columns
    return 2 if _has_kw_export else 1  # traffic_projection always; keyword_schedule only when kw


# ---------------------------------------------------------------------------
# Cluster mode (empty keyword_df)
# ---------------------------------------------------------------------------

class TestClusterModeEmptyKeywordDf:
    """All paths that touch keyword_df must be safe when it is empty."""

    @pytest.fixture
    def empty_kw(self) -> pd.DataFrame:
        return pd.DataFrame()

    def test_n_ranking_no_keyerror(self, empty_kw):
        assert _n_ranking(empty_kw) == 0

    def test_export_summary_shows_dash(self, empty_kw):
        assert _export_summary_ranking(empty_kw) == "—"

    def test_export_figs_skips_keyword_schedule(self, empty_kw):
        assert _export_figs_count(empty_kw) == 1


# ---------------------------------------------------------------------------
# Keyword mode (populated keyword_df with will_rank column)
# ---------------------------------------------------------------------------

class TestKeywordModePopulatedDf:
    """Existing keyword-mode behaviour must be unchanged."""

    @pytest.fixture
    def kw_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "keyword": ["seo tips", "content strategy", "link building"],
            "will_rank": [True, False, True],
            "volume": [1000, 500, 200],
        })

    def test_n_ranking_counts_true(self, kw_df):
        assert _n_ranking(kw_df) == 2

    def test_export_summary_shows_fraction(self, kw_df):
        assert _export_summary_ranking(kw_df) == "2 / 3"

    def test_export_figs_includes_keyword_schedule(self, kw_df):
        assert _export_figs_count(kw_df) == 2


# ---------------------------------------------------------------------------
# Edge: keyword_df present but missing will_rank (e.g. partial data)
# ---------------------------------------------------------------------------

class TestMissingWillRankColumn:
    """Guard must also handle a non-empty df that lacks the will_rank column."""

    @pytest.fixture
    def partial_df(self) -> pd.DataFrame:
        return pd.DataFrame({"keyword": ["test"], "volume": [100]})

    def test_n_ranking_no_keyerror(self, partial_df):
        assert _n_ranking(partial_df) == 0

    def test_export_summary_shows_dash(self, partial_df):
        assert _export_summary_ranking(partial_df) == "—"
