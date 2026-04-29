"""Tests for engine/v5/brand_classifier.py"""

import pandas as pd
import pytest

from engine.v5.brand_classifier import (
    BrandConfig,
    build_classifier,
    detect_collisions,
    suggest_branded_candidates,
)

# ── build_classifier ──────────────────────────────────────────────────────────

class TestSubstringMatch:
    def test_case_insensitive(self):
        f = build_classifier(BrandConfig(substring_terms=["acme corp"]))
        assert f("ACME Corp products") is True
        assert f("acme corp homepage") is True
        assert f("running shoes") is False

    def test_partial_substring_hits(self):
        f = build_classifier(BrandConfig(substring_terms=["csblr"]))
        assert f("csblr dress") is True
        assert f("buy csblr online") is True
        assert f("dress online") is False

    def test_empty_substring_terms(self):
        f = build_classifier(BrandConfig(substring_terms=[]))
        assert f("anything") is False


class TestWordBoundaryMatch:
    def test_whole_word_matches(self):
        f = build_classifier(BrandConfig(word_boundary_terms=["cable"]))
        assert f("cable") is True
        assert f("buy cable") is True
        assert f("cable melbourne") is True

    def test_plural_not_matched(self):
        f = build_classifier(BrandConfig(word_boundary_terms=["cable"]))
        assert f("cables") is False

    def test_substring_of_longer_word_not_matched(self):
        f = build_classifier(BrandConfig(word_boundary_terms=["cable"]))
        assert f("multicable") is False

    def test_case_insensitive(self):
        f = build_classifier(BrandConfig(word_boundary_terms=["Cable"]))
        assert f("Cable Melbourne") is True
        assert f("CABLE") is True


class TestExcludedFollowers:
    def test_follower_after_term_excluded(self):
        config = BrandConfig(word_boundary_terms=["cable"], excluded_followers=["knit"])
        f = build_classifier(config)
        assert f("cable knit sweater") is False
        assert f("cable melbourne") is True

    def test_follower_before_term_excluded(self):
        config = BrandConfig(word_boundary_terms=["cable"], excluded_followers=["knit"])
        f = build_classifier(config)
        assert f("knit cable pattern") is False

    def test_multiple_exclusions(self):
        config = BrandConfig(
            word_boundary_terms=["cable"],
            excluded_followers=["knit", "car", "tv"],
        )
        f = build_classifier(config)
        assert f("cable car tour") is False
        assert f("cable tv provider") is False
        assert f("cable accessories") is True

    def test_unrelated_does_not_cancel(self):
        config = BrandConfig(word_boundary_terms=["cable"], excluded_followers=["knit"])
        f = build_classifier(config)
        assert f("cable brand fashion") is True


class TestNoFalsePositives:
    def test_unrelated_keywords(self):
        config = BrandConfig(
            substring_terms=["acme"],
            word_boundary_terms=["cable"],
        )
        f = build_classifier(config)
        assert f("running shoes nike") is False
        assert f("how to bake bread") is False
        assert f("best laptops 2024") is False


# ── suggest_branded_candidates ────────────────────────────────────────────────

class TestSuggestBrandedCandidates:
    @pytest.fixture
    def semrush_df(self):
        return pd.DataFrame({
            "keyword": [
                "acme corp",
                "acme shoes",
                "best running shoes",
                "running tips online",
                "fitness tracker reviews",
                "sports gear sale",
                "buy trainers online",
                "workout equipment",
            ],
            "volume": [3000, 1500, 800, 600, 500, 450, 400, 350],
            "position": [1, 1, 15, 20, 22, 18, 14, 30],
            "kd": [10, 15, 40, 35, 38, 42, 36, 45],
        })

    def test_returns_dataframe(self, semrush_df):
        result = suggest_branded_candidates(semrush_df)
        assert isinstance(result, pd.DataFrame)

    def test_brand_score_column_present(self, semrush_df):
        result = suggest_branded_candidates(semrush_df)
        assert "brand_score" in result.columns

    def test_suggested_classification_column_present(self, semrush_df):
        result = suggest_branded_candidates(semrush_df)
        assert "suggested_classification" in result.columns

    def test_obvious_brand_scores_highest(self, semrush_df):
        result = suggest_branded_candidates(semrush_df, min_volume=100)
        # "acme corp" at position 1, KD 10, 2 words → high score
        top = result.iloc[0]["keyword"]
        assert top in ("acme corp", "acme shoes"), f"Expected brand keyword on top, got '{top}'"

    def test_high_score_rows_get_include_suggestion(self, semrush_df):
        result = suggest_branded_candidates(semrush_df, min_volume=100)
        high_score = result[result["brand_score"] >= 0.6]
        assert (high_score["suggested_classification"] != "unlikely").all()

    def test_min_volume_filter(self, semrush_df):
        result = suggest_branded_candidates(semrush_df, min_volume=1000)
        assert (result["volume"] >= 1000).all()

    def test_empty_df_returns_empty(self):
        result = suggest_branded_candidates(pd.DataFrame())
        assert result.empty

    def test_missing_columns_returns_empty(self):
        result = suggest_branded_candidates(pd.DataFrame({"keyword": ["test"]}))
        assert result.empty


# ── detect_collisions ─────────────────────────────────────────────────────────

class TestDetectCollisions:
    @pytest.fixture
    def cable_df(self):
        rows = []
        # 15 "cable knit" keywords with high volume — should be top collision
        for i in range(15):
            rows.append({"keyword": f"cable knit sweater {i}", "volume": 500})
        # 8 "cable car" keywords
        for i in range(8):
            rows.append({"keyword": f"cable car tour {i}", "volume": 300})
        # 3 "cable tv" keywords (at the floor)
        for i in range(3):
            rows.append({"keyword": f"cable tv provider {i}", "volume": 200})
        # pure brand keywords
        for i in range(20):
            rows.append({"keyword": f"cable melbourne {i}", "volume": 100})
        return pd.DataFrame(rows)

    def test_returns_dataframe(self, cable_df):
        result = detect_collisions(cable_df, "cable")
        assert isinstance(result, pd.DataFrame)

    def test_knit_surfaces_as_collision(self, cable_df):
        result = detect_collisions(cable_df, "cable", min_follower_count=3, min_volume_share=0.01)
        assert not result.empty
        assert "knit" in result["follower"].values

    def test_top_collision_is_highest_score(self, cable_df):
        result = detect_collisions(cable_df, "cable", min_follower_count=3, min_volume_share=0.01)
        assert result.iloc[0]["follower"] == "knit"

    def test_collision_score_positive(self, cable_df):
        result = detect_collisions(cable_df, "cable")
        assert (result["collision_score"] > 0).all()

    def test_missing_columns_returns_empty(self):
        result = detect_collisions(pd.DataFrame({"keyword": ["cable knit"]}), "cable")
        assert result.empty

    def test_no_matches_returns_empty(self):
        df = pd.DataFrame({"keyword": ["running shoes", "blue trainers"], "volume": [100, 200]})
        result = detect_collisions(df, "cable")
        assert result.empty

    def test_min_follower_count_filter(self, cable_df):
        result = detect_collisions(cable_df, "cable", min_follower_count=100)
        assert result.empty
