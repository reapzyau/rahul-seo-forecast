"""Tests for utils/roadmap_to_keywords.py."""
import pandas as pd
import pytest

from utils.roadmap_to_keywords import (
    DEFAULT_KD_FOR_UNKNOWN_KEYWORD,
    DEFAULT_VOLUME_FOR_UNKNOWN_KEYWORD,
    build_keyword_df_from_roadmap,
    summarise_roadmap_extraction,
)


@pytest.fixture
def sample_content_plan():
    return [
        {
            "url": "/blog/summer-hats",
            "title": "Summer Hats Guide",
            "content_type": "new_page",
            "month": 1,
            "keywords": ["summer hats", "best summer hats", "womens summer hats"],
        },
        {
            "url": "/products/raffia-hat",
            "title": "Raffia Hat",
            "content_type": "optimisation",
            "month": 2,
            "keywords": ["raffia hat", "raffia"],
        },
        {
            "url": "/blog/hat-care",
            "title": "Hat Care",
            "content_type": "faq",
            "month": 3,
            "keywords": [],  # no target keywords
        },
    ]


@pytest.fixture
def sample_semrush():
    return pd.DataFrame({
        "keyword": ["summer hats", "raffia hat", "winter hats"],
        "volume": [5000, 1500, 3000],
        "kd": [30, 18, 35],
    })


class TestBuildKeywordDf:
    def test_extracts_all_keywords(self, sample_content_plan):
        df = build_keyword_df_from_roadmap(sample_content_plan)
        assert len(df) == 5  # 3 + 2 + 0

    def test_uses_semrush_data_when_available(self, sample_content_plan, sample_semrush):
        df = build_keyword_df_from_roadmap(sample_content_plan, sample_semrush)
        summer = df[df["keyword"] == "summer hats"].iloc[0]
        assert summer["volume"] == 5000
        assert summer["kd"] == 30
        assert summer["_has_semrush_match"]

    def test_falls_back_to_defaults_for_unknown(self, sample_content_plan, sample_semrush):
        df = build_keyword_df_from_roadmap(sample_content_plan, sample_semrush)
        unknown = df[df["keyword"] == "best summer hats"].iloc[0]
        assert unknown["volume"] == DEFAULT_VOLUME_FOR_UNKNOWN_KEYWORD
        assert unknown["kd"] == DEFAULT_KD_FOR_UNKNOWN_KEYWORD
        assert not unknown["_has_semrush_match"]

    def test_carries_url_and_publish_month_metadata(self, sample_content_plan):
        df = build_keyword_df_from_roadmap(sample_content_plan)
        summer = df[df["keyword"] == "summer hats"].iloc[0]
        assert summer["_content_url"] == "/blog/summer-hats"
        assert summer["_publish_month"] == 1
        assert summer["_content_type"] == "new_page"

    def test_deduplicates_repeated_keywords(self):
        plan = [
            {"url": "/a", "month": 1, "keywords": ["foo"], "content_type": "new_page"},
            {"url": "/b", "month": 2, "keywords": ["foo"], "content_type": "optimisation"},
        ]
        df = build_keyword_df_from_roadmap(plan)
        assert len(df) == 1  # foo deduped, first occurrence kept
        assert df.iloc[0]["_content_url"] == "/a"

    def test_empty_plan_returns_empty_df(self):
        df = build_keyword_df_from_roadmap([])
        assert df.empty
        assert list(df.columns) == ["keyword", "volume", "kd"]

    def test_plan_with_no_keywords_returns_empty_df(self):
        plan = [{"url": "/a", "month": 1, "keywords": [], "content_type": "faq"}]
        df = build_keyword_df_from_roadmap(plan)
        assert df.empty

    def test_case_insensitive_semrush_match(self):
        plan = [{"url": "/a", "month": 1, "keywords": ["Summer Hats"], "content_type": "new_page"}]
        semrush = pd.DataFrame({"keyword": ["summer hats"], "volume": [5000], "kd": [30]})
        df = build_keyword_df_from_roadmap(plan, semrush)
        assert df.iloc[0]["volume"] == 5000  # matched despite case difference

    def test_zero_volume_keywords_filtered_out(self):
        plan = [{"url": "/a", "month": 1, "keywords": ["zero kw"], "content_type": "new_page"}]
        semrush = pd.DataFrame({"keyword": ["zero kw"], "volume": [0], "kd": [30]})
        df = build_keyword_df_from_roadmap(plan, semrush)
        assert df.empty


class TestSummary:
    def test_summary_counts_match(self, sample_content_plan, sample_semrush):
        df = build_keyword_df_from_roadmap(sample_content_plan, sample_semrush)
        summary = summarise_roadmap_extraction(sample_content_plan, df)
        assert summary["n_content_pieces"] == 3
        assert summary["n_keywords_total"] == 5
        assert summary["n_keywords_with_semrush"] == 2  # summer hats + raffia hat
        assert summary["n_keywords_default"] == 3
        assert summary["n_unique_urls"] == 2  # 3 plan items but only 2 had keywords

    def test_content_type_breakdown(self, sample_content_plan, sample_semrush):
        df = build_keyword_df_from_roadmap(sample_content_plan, sample_semrush)
        summary = summarise_roadmap_extraction(sample_content_plan, df)
        # 3 keywords from new_page, 2 from optimisation
        assert summary["content_type_breakdown"].get("new_page") == 3
        assert summary["content_type_breakdown"].get("optimisation") == 2
