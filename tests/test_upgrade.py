"""Tests for the SEO Forecaster v5 upgrade (upgrade guide Sections 1-10).

Covers:
  - Section 6: brand_classifier (two-stage)
  - Sections 1+2: yoy_baseline, detect_startup_period, derive_seasonality_from_baseline
  - Sections 3+4: positional position_filter, _resolve_movement_stats
  - Section 5: run_new_content_forecast_simple
  - Section 10: build_methodology_snapshot, methodology_snapshot_to_human_readable
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# ── Section 6: brand_classifier ──────────────────────────────────────────────


class TestBuildBrandClassifier:
    def test_substring_always_matches(self):
        from engine.brand_classifier import build_brand_classifier

        is_brand = build_brand_classifier(
            substring_terms=["cable melbourne", "csblr"],
        )
        assert is_brand("cable melbourne dresses") is True
        assert is_brand("csblr blouse") is True
        assert is_brand("blue dress") is False

    def test_word_boundary_match(self):
        from engine.brand_classifier import build_brand_classifier

        is_brand = build_brand_classifier(
            substring_terms=[],
            word_boundary_terms=["cable"],
        )
        assert is_brand("cable") is True
        assert is_brand("cable clothing") is True

    def test_excluded_followers_prevent_brand_flag(self):
        from engine.brand_classifier import build_brand_classifier

        is_brand = build_brand_classifier(
            substring_terms=[],
            word_boundary_terms=["cable"],
            excluded_followers=["knit", "tie", "car", "management"],
        )
        assert is_brand("cable knit sweater") is False
        assert is_brand("cable tie") is False
        assert is_brand("cable") is True

    def test_case_insensitive(self):
        from engine.brand_classifier import build_brand_classifier

        is_brand = build_brand_classifier(substring_terms=["Patagonia"])
        assert is_brand("PATAGONIA jacket") is True
        assert is_brand("patagonia fleece") is True

    def test_full_cable_scenario(self):
        """Validates the Cable Melbourne classification described in the upgrade guide."""
        from engine.brand_classifier import build_brand_classifier

        is_brand = build_brand_classifier(
            substring_terms=["cable melbourne", "cable bowral", "cable cottesloe",
                             "cable fashion melbourne", "cable clothing", "csblr"],
            word_boundary_terms=["cable"],
            excluded_followers=["knit", "car", "tv", "tie", "ties", "bay",
                                "stitch", "cars", "management", "knitting", "pull", "rib"],
        )
        # Should be branded
        assert is_brand("cable melbourne dresses") is True
        assert is_brand("csblr clothing") is True
        assert is_brand("cable clothing store") is True
        assert is_brand("cable") is True

        # Should NOT be branded (excluded followers)
        assert is_brand("cable knit sweater") is False
        assert is_brand("cable tie") is False
        assert is_brand("cable car") is False
        assert is_brand("rib cable stitch") is False


class TestClassifyKeywordsWithTwoStage:
    def test_adds_is_branded_column(self):
        from engine.brand_classifier import classify_keywords_with_two_stage

        df = pd.DataFrame({"keyword": ["patagonia jacket", "blue jacket", "plain tee"]})
        result = classify_keywords_with_two_stage(df, substring_terms=["patagonia"])
        assert "is_branded" in result.columns
        assert bool(result.loc[0, "is_branded"]) is True
        assert bool(result.loc[1, "is_branded"]) is False

    def test_empty_substring_terms(self):
        from engine.brand_classifier import classify_keywords_with_two_stage

        df = pd.DataFrame({"keyword": ["anything"]})
        result = classify_keywords_with_two_stage(df, substring_terms=[])
        assert bool(result.loc[0, "is_branded"]) is False


class TestBrandMatchPreview:
    def test_returns_branded_sorted_by_volume(self):
        from engine.brand_classifier import brand_match_preview

        df = pd.DataFrame({
            "keyword": ["patagonia jacket", "blue jacket", "patagonia tee"],
            "volume": [1000, 5000, 200],
        })
        preview = brand_match_preview(df, substring_terms=["patagonia"], top_n=10)
        assert len(preview) == 2
        assert preview.iloc[0]["keyword"] == "patagonia jacket"  # highest volume first


# ── Sections 1+2: YoY baseline + derived seasonality ─────────────────────────


def _make_ga4_df(n_months: int = 24, base_traffic: int = 20000) -> pd.DataFrame:
    """Build a synthetic GA4 monthly DataFrame."""
    dates = pd.date_range("2024-01-01", periods=n_months, freq="MS")
    # Add slight seasonal shape: peaks in Jul/Aug/Nov
    traffic = [
        int(base_traffic * (1 + 0.2 * np.sin(i / 12 * 2 * np.pi)))
        for i in range(n_months)
    ]
    return pd.DataFrame({"date": dates, "traffic": traffic})


class TestYoyBaseline:
    def test_returns_one_entry_per_forecast_month(self):
        from engine.historical_engine import yoy_baseline

        ga4 = _make_ga4_df(24)
        forecast_dates = pd.date_range("2026-01-01", periods=12, freq="MS")
        result = yoy_baseline(ga4, forecast_dates)
        assert len(result) == 12

    def test_ga4_source_when_prior_year_exists(self):
        from engine.historical_engine import yoy_baseline

        ga4 = _make_ga4_df(24)
        forecast_dates = pd.date_range("2026-01-01", periods=12, freq="MS")
        result = yoy_baseline(ga4, forecast_dates)
        for v in result.values():
            assert v["source"].startswith("GA4")

    def test_fallback_source_when_prior_year_missing(self):
        from engine.historical_engine import yoy_baseline

        # Only 12 months — no prior year for future months beyond that
        ga4 = _make_ga4_df(12)  # Jan-Dec 2024
        # Forecast Jan-Dec 2026 — 2 years ahead, no direct prior exists
        forecast_dates = pd.date_range("2026-01-01", periods=12, freq="MS")
        result = yoy_baseline(ga4, forecast_dates)
        # Should use most-recent same-calendar-month fallback
        for v in result.values():
            assert "source" in v
            assert v["traffic"] > 0

    def test_annual_sum_equals_prior_fy(self):
        """When full prior year is available, annual sum should equal prior-year sum."""
        from engine.historical_engine import yoy_baseline

        ga4 = _make_ga4_df(25)  # Jan 2024 – Jan 2026
        # Forecast Jan-Dec 2025 (prior year = Jan-Dec 2024)
        forecast_dates = pd.date_range("2025-01-01", periods=12, freq="MS")
        result = yoy_baseline(ga4, forecast_dates)

        forecast_annual = sum(v["traffic"] for v in result.values())
        prior_year = ga4[ga4["date"].dt.year == 2024]["traffic"].sum()
        # Should be identical (within rounding)
        assert abs(forecast_annual - prior_year) <= 12  # max 1/month rounding error


class TestDetectStartupPeriod:
    def test_detects_startup_ramp(self):
        from engine.historical_engine import detect_startup_period

        # Early months very low (startup), recent months high
        traffic = pd.Series(
            [3000, 4000, 5000, 6000, 7000, 8000,  # early (avg 5500)
             22000, 23000, 24000, 25000, 24000, 23000]  # recent (avg 23500)
        )
        assert detect_startup_period(traffic) is True

    def test_stable_series_not_flagged(self):
        from engine.historical_engine import detect_startup_period

        traffic = pd.Series([20000] * 24)
        assert detect_startup_period(traffic) is False

    def test_short_series_returns_false(self):
        from engine.historical_engine import detect_startup_period

        traffic = pd.Series([1000, 2000, 5000])
        assert detect_startup_period(traffic) is False

    def test_cable_scenario(self):
        """Cable Melbourne traffic pattern — should be detected as startup."""
        from engine.historical_engine import detect_startup_period

        # Approximate Cable Melbourne: ramp from ~7k to ~24k over 12 months, then stable
        traffic = pd.Series([
            7400, 8000, 9500, 12000, 14000, 15000,   # early
            22000, 23000, 24000, 23500, 24000, 24500, # recent
        ])
        assert detect_startup_period(traffic) is True


class TestDeriveSeasonalityFromBaseline:
    def test_returns_12_months(self):
        from engine.historical_engine import yoy_baseline
        from engine.seasonality_engine import derive_seasonality_from_baseline

        ga4 = _make_ga4_df(24)
        forecast_dates = pd.date_range("2026-01-01", periods=12, freq="MS")
        baseline = yoy_baseline(ga4, forecast_dates)
        result = derive_seasonality_from_baseline(baseline)
        assert len(result) == 12
        assert all(m in result for m in range(1, 13))

    def test_multipliers_sum_near_zero(self):
        from engine.historical_engine import yoy_baseline
        from engine.seasonality_engine import derive_seasonality_from_baseline

        ga4 = _make_ga4_df(24)
        forecast_dates = pd.date_range("2026-01-01", periods=12, freq="MS")
        baseline = yoy_baseline(ga4, forecast_dates)
        result = derive_seasonality_from_baseline(baseline)
        total_mod = sum(v["traffic_mod"] for v in result.values())
        assert abs(total_mod) < 0.01  # deviations from mean sum to ~0

    def test_empty_baseline_returns_default(self):
        from engine.seasonality_engine import DEFAULT_SEASONALITY, derive_seasonality_from_baseline

        result = derive_seasonality_from_baseline({})
        assert result == dict(DEFAULT_SEASONALITY)


# ── Sections 3+4: positional pool filter + movement stats switch ───────────────


class TestResolveMovementStats:
    def _positive_learned(self):
        return {
            "Easy": {"mean_gain": 4.0, "std_gain": 1.0, "sample_size": 100},
            "Moderate": {"mean_gain": 3.0, "std_gain": 1.2, "sample_size": 80},
        }

    def _negative_learned(self):
        return {
            "Easy": {"mean_gain": -0.12, "std_gain": 1.0, "sample_size": 6140},
            "Moderate": {"mean_gain": -0.07, "std_gain": 1.2, "sample_size": 2291},
        }

    def test_mode_false_returns_none(self):
        from engine.positional_engine import _resolve_movement_stats

        stats, reason = _resolve_movement_stats(self._positive_learned(), False)
        assert stats is None
        assert "explicit override" in reason

    def test_mode_true_returns_learned(self):
        from engine.positional_engine import _resolve_movement_stats

        learned = self._positive_learned()
        stats, reason = _resolve_movement_stats(learned, True)
        assert stats is learned
        assert "explicit use" in reason

    def test_auto_uses_learned_when_positive(self):
        from engine.positional_engine import _resolve_movement_stats

        learned = self._positive_learned()
        stats, reason = _resolve_movement_stats(learned, "auto")
        assert stats is learned
        assert "positive" in reason

    def test_auto_falls_back_when_decline(self):
        """Cable scenario: all tiers negative → engine defaults."""
        from engine.positional_engine import _resolve_movement_stats

        stats, reason = _resolve_movement_stats(self._negative_learned(), "auto")
        assert stats is None
        assert "decline" in reason or "defaults" in reason

    def test_auto_returns_none_for_empty_learned(self):
        from engine.positional_engine import _resolve_movement_stats

        stats, reason = _resolve_movement_stats({}, "auto")
        assert stats is None
        assert "no learned" in reason.lower()


class TestPositionalFilterIntegration:
    def _make_kw_df(self, n: int = 100) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        return pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(n)],
            "volume": rng.integers(100, 5000, n),
            "kd": rng.integers(10, 90, n),
            "position": rng.integers(1, 101, n),
        })

    def test_default_filter_reduces_pool(self):
        from engine.positional_engine import run_positional_forecast_mc

        kw = self._make_kw_df(200)
        _, monthly = run_positional_forecast_mc(
            kw, months=6, n_trials=50, position_filter=(4, 30), seed=42
        )
        assert monthly.attrs["keyword_count"] < 200

    def test_no_filter_includes_full_portfolio(self):
        from engine.positional_engine import run_positional_forecast_mc

        kw = self._make_kw_df(50)
        _, monthly = run_positional_forecast_mc(
            kw, months=6, n_trials=50, position_filter=None, seed=42
        )
        # All keywords with position 1-100 pass
        expected = (kw["position"].between(1, 100)).sum()
        assert monthly.attrs["keyword_count"] == expected

    def test_monthly_df_has_movement_reason(self):
        from engine.positional_engine import run_positional_forecast_mc

        kw = self._make_kw_df(30)
        _, monthly = run_positional_forecast_mc(kw, months=3, n_trials=20, seed=42)
        assert "movement_stats_reason" in monthly.attrs
        assert isinstance(monthly.attrs["movement_stats_reason"], str)


# ── Section 5: run_new_content_forecast_simple ───────────────────────────────


class TestRunNewContentForecastSimple:
    def test_returns_array_of_correct_length(self):
        from engine.new_content_engine import run_new_content_forecast_simple

        result = run_new_content_forecast_simple(n_posts_total=25, months=12)
        assert len(result) == 12

    def test_annual_total_in_expected_range(self):
        """Sanity check: 25 posts, 2/mo, 400 peak-sessions/post, 55% rank prob.

        Note: per_post_longtail_traffic is the PEAK monthly traffic at maturity.
        Annual total = sum(per_post × maturation_fraction) over all months for all posts.
        With a Moderate S-curve (t_mid=5), a post published at month 1 contributes
        roughly 400 × 6.5 ≈ 2600 sessions over 12 months. With ~14 ranking posts,
        annual totals in the 5,000–20,000 range are expected.
        """
        from engine.new_content_engine import run_new_content_forecast_simple

        result = run_new_content_forecast_simple(
            n_posts_total=25,
            months=12,
            posts_per_month=2,
            per_post_longtail_traffic=400,
            rank_probability=0.55,
            maturation_tier="Moderate",
            seed=42,
        )
        annual = int(result.sum())
        # Sanity floor: at least some traffic given >0 ranking posts
        # Sanity ceiling: hard cap to catch runaway loops
        assert annual > 0, "Expected non-zero annual traffic"
        assert annual < 100_000, f"Annual total {annual} suspiciously high"
        # With 55% rank prob on 25 posts: ~14 ranking; moderate maturation over 12 months
        assert annual > 1_000, f"Annual total {annual} suspiciously low"

    def test_s_curve_maturation_increases_over_time(self):
        """Traffic should grow early on as posts mature (S-curve)."""
        from engine.new_content_engine import run_new_content_forecast_simple

        result = run_new_content_forecast_simple(
            n_posts_total=24, months=12, posts_per_month=2,
            per_post_longtail_traffic=500, rank_probability=0.8,
            maturation_tier="Easy", seed=42,
        )
        # Early months lower than later months (maturation)
        assert result[:3].mean() < result[9:].mean()

    def test_zero_posts_returns_zeros(self):
        from engine.new_content_engine import run_new_content_forecast_simple

        result = run_new_content_forecast_simple(n_posts_total=0, months=6)
        assert result.sum() == 0

    def test_seasonality_applied(self):
        from engine.new_content_engine import run_new_content_forecast_simple

        # Strong Jan peak seasonality
        seasonality = {m: {"traffic_mod": 0.5 if m == 1 else 0.0} for m in range(1, 13)}
        result_with = run_new_content_forecast_simple(
            n_posts_total=12, months=12, posts_per_month=1,
            per_post_longtail_traffic=400, rank_probability=0.9,
            maturation_tier="Easy", seasonality=seasonality, forecast_start_month=1, seed=42,
        )
        result_without = run_new_content_forecast_simple(
            n_posts_total=12, months=12, posts_per_month=1,
            per_post_longtail_traffic=400, rank_probability=0.9,
            maturation_tier="Easy", seed=42,
        )
        # First month should be higher with +50% Jan seasonality
        assert result_with[0] >= result_without[0]

    def test_seed_reproducibility(self):
        from engine.new_content_engine import run_new_content_forecast_simple

        r1 = run_new_content_forecast_simple(n_posts_total=20, months=12, seed=99)
        r2 = run_new_content_forecast_simple(n_posts_total=20, months=12, seed=99)
        assert (r1 == r2).all()


# ── Section 10: methodology snapshot ─────────────────────────────────────────


class TestBuildMethodologySnapshot:
    def _minimal_snapshot(self):
        from engine.snapshot_engine import build_methodology_snapshot

        return build_methodology_snapshot(
            client_name="Test Client",
            forecast_start="2026-07-01",
            forecast_end="2027-06-30",
            months=12,
            ga4_summary={"rows": 24, "date_range": "Jan-24 to Dec-25", "latest_6mo_avg": 23000},
            baseline_mode="yoy_replay",
            baseline_mode_rationale="YoY replay chosen: 24 months of history available",
            seasonality_source="derived_from_baseline",
            seasonality_rationale="Derived from YoY baseline values",
            position_filter=(4, 30),
            positional_kw_count=3286,
            movement_stats_decision="learned stats show decline → using engine defaults",
            brand_config={
                "substring_terms": ["cable melbourne"],
                "word_boundary_terms": ["cable"],
                "excluded_followers": ["knit"],
                "matched_count": 95,
                "total_kw_count": 9793,
            },
            new_content_source="deterministic_stream",
            aio_penalties={"informational": 40.0},
            blended_cr=1.8,
            weighted_aov=180.0,
            tier_outputs=[
                {"tier_name": "4k", "annual_sessions_combined": 305000, "uplift_pct": 5.5,
                 "annual_revenue_combined": 810000, "annual_revenue_baseline": 760000,
                 "revenue_uplift": 50000, "roi": 1.04},
            ],
            seed=42,
        )

    def test_snapshot_has_required_keys(self):
        snap = self._minimal_snapshot()
        required = [
            "snapshot_version", "snapshot_type", "generated_at", "client_name",
            "forecast_horizon", "ga4_input", "baseline", "seasonality",
            "positional_pool", "movement_stats", "brand_classification",
            "new_content", "revenue_assumptions", "monte_carlo_seed", "tier_outputs",
        ]
        for key in required:
            assert key in snap, f"Missing key: {key}"

    def test_snapshot_is_json_serialisable(self):
        import json

        snap = self._minimal_snapshot()
        encoded = json.dumps(snap)
        decoded = json.loads(encoded)
        assert decoded["client_name"] == "Test Client"

    def test_position_filter_serialised_as_list(self):
        snap = self._minimal_snapshot()
        assert snap["positional_pool"]["filter"] == [4, 30]

    def test_human_readable_contains_client_name(self):
        from engine.snapshot_engine import methodology_snapshot_to_human_readable

        snap = self._minimal_snapshot()
        text = methodology_snapshot_to_human_readable(snap)
        assert "Test Client" in text
        assert "yoy_replay" in text
        assert "4k" in text
