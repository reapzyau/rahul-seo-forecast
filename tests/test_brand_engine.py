"""Tests for engine/brand_engine.py — Task 2."""

import pandas as pd
import pytest

from engine.brand_engine import (
    classify_keywords_as_branded,
    extract_domain_from_semrush,
    split_branded_vs_non_branded,
)


class TestClassifyKeywordsAsBranded:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "keyword": [
                "nike running shoes",
                "best running shoes",
                "nike air max",
                "running tips",
                "sportswear online",
                "cable melbourne shop",
                "cable",
            ],
            "volume": [5000, 3000, 4000, 2000, 1500, 800, 600],
            "kd": [40, 30, 45, 20, 35, 25, 20],
        })

    def test_substring_matching(self, sample_df):
        result = classify_keywords_as_branded(sample_df, ["nike"])
        assert result.loc[result["keyword"] == "nike running shoes", "is_branded"].iloc[0]
        assert result.loc[result["keyword"] == "nike air max", "is_branded"].iloc[0]
        assert not result.loc[result["keyword"] == "best running shoes", "is_branded"].iloc[0]

    def test_word_boundary_prevents_partial_match(self, sample_df):
        # "cable" should match "cable melbourne shop" but NOT inside "cablecar"
        df = pd.DataFrame({"keyword": ["cable car", "cable-car", "cablecar", "cable melbourne"]})
        result = classify_keywords_as_branded(df, ["cable"])
        assert result.loc[result["keyword"] == "cable car", "is_branded"].iloc[0]
        assert result.loc[result["keyword"] == "cable melbourne", "is_branded"].iloc[0]
        # "cablecar" has no word boundary around "cable" — should still match because
        # the word boundary allows start-of-string; only non-word chars matter
        # The important case: "cablecar" (no space) — "cable" appears at word start → matches
        # but if we had "excable" the prefix char 'e' is [a-z0-9] so it would NOT match
        df2 = pd.DataFrame({"keyword": ["excable shoes", "cable shoes"]})
        result2 = classify_keywords_as_branded(df2, ["cable"])
        assert not result2.loc[result2["keyword"] == "excable shoes", "is_branded"].iloc[0]
        assert result2.loc[result2["keyword"] == "cable shoes", "is_branded"].iloc[0]

    def test_case_insensitive(self):
        df = pd.DataFrame({"keyword": ["Nike Shoes", "NIKE Air", "adidas"]})
        result = classify_keywords_as_branded(df, ["nike"])
        assert result.loc[result["keyword"] == "Nike Shoes", "is_branded"].iloc[0]
        assert result.loc[result["keyword"] == "NIKE Air", "is_branded"].iloc[0]
        assert not result.loc[result["keyword"] == "adidas", "is_branded"].iloc[0]

    def test_empty_brand_terms(self, sample_df):
        result = classify_keywords_as_branded(sample_df, [])
        assert not result["is_branded"].any()
        assert len(result) == len(sample_df)

    def test_classify_empty_brand_terms_returns_all_false(self, sample_df):
        result = classify_keywords_as_branded(sample_df, [])
        assert (~result["is_branded"]).all()

    def test_classify_word_boundary_no_substring_match(self):
        df = pd.DataFrame({"keyword": ["excable shoes", "cable shoes", "cablecar"]})
        result = classify_keywords_as_branded(df, ["cable"])
        assert not result.loc[result["keyword"] == "excable shoes", "is_branded"].iloc[0]
        assert result.loc[result["keyword"] == "cable shoes", "is_branded"].iloc[0]

    def test_classify_case_insensitive(self):
        df = pd.DataFrame({"keyword": ["Nike Shoes", "NIKE Air", "adidas"]})
        result = classify_keywords_as_branded(df, ["nike"])
        assert result.loc[result["keyword"] == "Nike Shoes", "is_branded"].iloc[0]
        assert result.loc[result["keyword"] == "NIKE Air", "is_branded"].iloc[0]
        assert not result.loc[result["keyword"] == "adidas", "is_branded"].iloc[0]

    def test_classify_multiple_brand_terms(self, sample_df):
        result = classify_keywords_as_branded(sample_df, ["nike", "cable"])
        branded = result[result["is_branded"]]["keyword"].tolist()
        assert "nike running shoes" in branded
        assert "cable melbourne shop" in branded

    def test_multiple_brand_terms(self, sample_df):
        result = classify_keywords_as_branded(sample_df, ["nike", "cable"])
        branded = result[result["is_branded"]]["keyword"].tolist()
        assert "nike running shoes" in branded
        assert "cable melbourne shop" in branded

    def test_preserves_original_columns(self, sample_df):
        result = classify_keywords_as_branded(sample_df, ["nike"])
        assert "volume" in result.columns
        assert "kd" in result.columns
        assert len(result) == len(sample_df)

    def test_no_keyword_column(self):
        df = pd.DataFrame({"search_term": ["nike shoes"], "volume": [100]})
        result = classify_keywords_as_branded(df, ["nike"])
        assert not result["is_branded"].any()


class TestSplitBrandedVsNonBranded:
    def test_split_counts(self):
        df = pd.DataFrame({
            "keyword": ["brand kw", "generic kw", "brand product"],
            "is_branded": [True, False, True],
        })
        branded, non_branded = split_branded_vs_non_branded(df)
        assert len(branded) == 2
        assert len(non_branded) == 1

    def test_split_preserves_total_count(self):
        df = pd.DataFrame({
            "keyword": ["brand kw", "generic kw", "brand product", "other"],
            "is_branded": [True, False, True, False],
        })
        branded, non_branded = split_branded_vs_non_branded(df)
        assert len(branded) + len(non_branded) == len(df)

    def test_all_non_branded(self):
        df = pd.DataFrame({
            "keyword": ["generic a", "generic b"],
            "is_branded": [False, False],
        })
        branded, non_branded = split_branded_vs_non_branded(df)
        assert len(branded) == 0
        assert len(non_branded) == 2

    def test_missing_is_branded_raises(self):
        df = pd.DataFrame({"keyword": ["test"]})
        with pytest.raises(ValueError, match="is_branded"):
            split_branded_vs_non_branded(df)


class TestExtractDomainFromSemrush:
    def test_extract_domain_picks_most_common(self):
        df = pd.DataFrame({
            "keyword": ["kw1", "kw2", "kw3", "kw4"],
            "url": [
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
                "https://other.com/page1",
            ],
        })
        assert extract_domain_from_semrush(df) == "example.com"

    def test_extract_domain_returns_none_when_no_url_column(self):
        df = pd.DataFrame({"keyword": ["kw1", "kw2"], "volume": [100, 200]})
        assert extract_domain_from_semrush(df) is None

    def test_extract_domain_returns_none_when_empty_urls(self):
        df = pd.DataFrame({"url": [None, None, ""]})
        assert extract_domain_from_semrush(df) is None
