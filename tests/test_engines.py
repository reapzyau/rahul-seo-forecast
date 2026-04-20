import io

import numpy as np
import pandas as pd
import pytest

from engine.constants import (
    CTR_BY_POSITION, CTR_11_14, CTR_15_20,
    SITE_PRESETS, CTR_MODELS, FORECAST_SCENARIOS, INTENT_PATTERNS,
)
from engine.new_content_engine import (
    classify_difficulty,
    classify_intent,
    ranking_probability,
    expected_position,
    get_ctr,
    time_to_rank_months,
    efficiency_score,
    run_new_content_forecast,
)
from engine.historical_engine import (
    linear_forecast,
    exponential_smoothing_forecast,
    sma_forecast,
    calculate_growth_rates,
    run_historical_forecast,
)
from engine.combined_engine import run_combined_forecast
from engine.revenue_engine import add_revenue, keyword_revenue_table


# ── Keyword Engine ──────────────────────────────────────────────────────────


class TestClassifyDifficulty:
    def test_easy(self):
        assert classify_difficulty(10) == "Easy"
        assert classify_difficulty(20) == "Easy"

    def test_moderate(self):
        assert classify_difficulty(21) == "Moderate"
        assert classify_difficulty(40) == "Moderate"

    def test_hard(self):
        assert classify_difficulty(41) == "Hard"
        assert classify_difficulty(60) == "Hard"

    def test_very_hard(self):
        assert classify_difficulty(61) == "Very Hard"
        assert classify_difficulty(80) == "Very Hard"

    def test_extreme(self):
        assert classify_difficulty(81) == "Extreme"
        assert classify_difficulty(100) == "Extreme"


class TestRankingProbability:
    def test_high_da_low_kd(self):
        prob = ranking_probability(80, 20)
        assert prob == 0.95  # (80-20+50)/100 = 1.10 -> clamped to 0.95

    def test_low_da_high_kd(self):
        prob = ranking_probability(10, 90)
        assert prob == 0.05  # (10-90+50)/100 = -0.30 -> clamped to 0.05

    def test_equal_da_kd(self):
        prob = ranking_probability(50, 50)
        assert prob == 0.5  # (50-50+50)/100 = 0.5

    def test_clamping_upper(self):
        assert ranking_probability(100, 1) == 0.95

    def test_clamping_lower(self):
        assert ranking_probability(1, 100) == 0.05


class TestExpectedPosition:
    def test_high_gap_gives_top_positions(self):
        pos = expected_position(80, 20, seed=42)
        assert 1 <= pos <= 3

    def test_negative_gap_gives_lower_positions(self):
        pos = expected_position(20, 60, seed=42)
        assert 5 <= pos <= 20  # gap is -40, so range is 12-20 or 8-16

    def test_seed_reproducibility(self):
        pos1 = expected_position(50, 30, seed=42)
        pos2 = expected_position(50, 30, seed=42)
        assert pos1 == pos2

    def test_different_seeds_may_differ(self):
        positions = {expected_position(50, 50, seed=i) for i in range(100)}
        assert len(positions) > 1  # Not all the same


class TestClassifyIntent:
    def test_informational_keywords(self):
        assert classify_intent("how to do seo") == "informational"
        assert classify_intent("what is keyword difficulty") == "informational"
        assert classify_intent("why does seo matter") == "informational"
        assert classify_intent("seo tutorial for beginners") == "informational"
        assert classify_intent("link building guide") == "informational"

    def test_commercial_keywords(self):
        assert classify_intent("best seo tool") == "commercial"
        assert classify_intent("seo tool review") == "commercial"
        assert classify_intent("ahrefs alternative") == "commercial"

    def test_transactional_keywords(self):
        assert classify_intent("buy seo software") == "transactional"
        assert classify_intent("seo tool pricing") == "transactional"
        assert classify_intent("ahrefs discount code") == "transactional"

    def test_navigational_keywords(self):
        assert classify_intent("google search console login") == "navigational"

    def test_default_classification(self):
        # Generic keywords with no clear signals default to commercial
        assert classify_intent("seo audit") == "commercial"


class TestGetCtr:
    def test_top_10(self):
        for pos, expected in CTR_BY_POSITION.items():
            assert get_ctr(pos) == expected

    def test_positions_11_14(self):
        for pos in [11, 12, 13, 14]:
            assert get_ctr(pos) == CTR_11_14

    def test_positions_15_20(self):
        for pos in [15, 16, 17, 18, 19, 20]:
            assert get_ctr(pos) == CTR_15_20

    def test_beyond_20(self):
        assert get_ctr(21) == 0.0
        assert get_ctr(50) == 0.0

    def test_ai_adjusted_model(self):
        model = CTR_MODELS["AI-Adjusted"]
        assert get_ctr(1, model) == 16.0
        assert get_ctr(1, model) < get_ctr(1)  # AI-Adjusted < Standard

    def test_standard_model_matches_default(self):
        model = CTR_MODELS["Standard"]
        for pos in range(1, 21):
            assert get_ctr(pos, model) == get_ctr(pos)


class TestTimeToRank:
    def test_easy_tier_range(self):
        for seed in range(20):
            ttr = time_to_rank_months("Easy", 50, seed)
            assert ttr >= 1

    def test_da_adjustment(self):
        # Higher DA should generally produce equal or lower time to rank
        results_high_da = [time_to_rank_months("Moderate", 80, s) for s in range(50)]
        results_low_da = [time_to_rank_months("Moderate", 20, s) for s in range(50)]
        assert np.mean(results_high_da) <= np.mean(results_low_da)


class TestEfficiencyScore:
    def test_basic(self):
        assert efficiency_score(1000, 49) == 1000 / 50

    def test_zero_kd(self):
        assert efficiency_score(500, 0) == 500.0

    def test_high_kd_low_score(self):
        assert efficiency_score(100, 99) == 1.0


class TestRunNewContentForecast:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "keyword": ["easy kw", "hard kw", "medium kw"],
            "volume": [5000, 3000, 4000],
            "kd": [15, 75, 40],
        })

    def test_returns_two_dataframes(self, sample_df):
        kw_df, monthly_df = run_new_content_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        assert isinstance(kw_df, pd.DataFrame)
        assert isinstance(monthly_df, pd.DataFrame)

    def test_sorted_by_efficiency(self, sample_df):
        kw_df, _ = run_new_content_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        scores = kw_df["efficiency_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_monthly_df_has_correct_length(self, sample_df):
        _, monthly_df = run_new_content_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        assert len(monthly_df) == 12

    def test_seed_reproducibility(self, sample_df):
        kw1, m1 = run_new_content_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        kw2, m2 = run_new_content_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        pd.testing.assert_frame_equal(kw1, kw2)
        pd.testing.assert_frame_equal(m1, m2)

    def test_traffic_monotonically_nondecreasing(self, sample_df):
        _, monthly_df = run_new_content_forecast(sample_df, da=50, cadence=2, months=18, seed=42)
        traffic = monthly_df["traffic"].tolist()
        for i in range(1, len(traffic)):
            assert traffic[i] >= traffic[i - 1]


# ── Historical Engine ───────────────────────────────────────────────────────


class TestLinearForecast:
    @pytest.fixture
    def sample_data(self):
        dates = pd.date_range("2023-01-01", periods=12, freq="MS")
        traffic = pd.Series([1000 + i * 100 for i in range(12)])
        return dates, traffic

    def test_output_length(self, sample_data):
        dates, traffic = sample_data
        result = linear_forecast(dates, traffic, future_months=6)
        assert len(result) == 18  # 12 historical + 6 forecast

    def test_forecast_increases_for_upward_trend(self, sample_data):
        dates, traffic = sample_data
        result = linear_forecast(dates, traffic, future_months=6)
        forecast = result[result["is_forecast"]]
        assert forecast["linear"].iloc[-1] > forecast["linear"].iloc[0]

    def test_confidence_bands(self, sample_data):
        dates, traffic = sample_data
        result = linear_forecast(dates, traffic, future_months=6, confidence=15)
        forecast = result[result["is_forecast"]]
        assert (forecast["linear_upper"] >= forecast["linear"]).all()
        assert (forecast["linear_lower"] <= forecast["linear"]).all()


class TestExponentialSmoothing:
    def test_output_length(self):
        traffic = pd.Series([100, 110, 120, 130, 140])
        result = exponential_smoothing_forecast(traffic, alpha=0.3, future_months=3)
        assert len(result) == 8  # 5 historical + 3 forecast

    def test_weights_recent_data(self):
        traffic = pd.Series([100, 100, 100, 100, 200])
        result = exponential_smoothing_forecast(traffic, alpha=0.5, future_months=1)
        assert result[-1] > 100

    def test_upward_trend_extrapolates_upward(self):
        """Holt's method should continue the trend, not plateau."""
        traffic = pd.Series([100, 110, 120, 130, 140, 150])
        result = exponential_smoothing_forecast(traffic, alpha=0.3, future_months=3)
        # Each forecast step should be higher than the previous
        assert result[-1] > result[-2] > result[-3]

    def test_forecast_differs_from_flat(self):
        """Consecutive forecast values must not all be equal (flat-line bug check)."""
        traffic = pd.Series([100, 120, 140, 160, 180])
        result = exponential_smoothing_forecast(traffic, alpha=0.3, future_months=3)
        forecast = result[5:]
        assert len(set(forecast)) > 1  # values are not all identical

    def test_no_negative_values(self):
        traffic = pd.Series([500, 400, 300, 200, 100])
        result = exponential_smoothing_forecast(traffic, alpha=0.5, future_months=6)
        assert all(v >= 0 for v in result)


class TestSmaForecast:
    def test_output_length(self):
        traffic = pd.Series([100, 110, 120, 130, 140])
        result = sma_forecast(traffic, window=3, future_months=3)
        assert len(result) == 8

    def test_window_math(self):
        traffic = pd.Series([100, 200, 300])
        result = sma_forecast(traffic, window=3, future_months=1)
        # The forecast should be the average of the last 3 values
        assert result[3] == round(np.mean([100, 200, 300]))


class TestCalculateGrowthRates:
    def test_basic_growth(self):
        traffic = pd.Series([100, 110, 121])
        rates = calculate_growth_rates(traffic)
        assert rates["avg_mom"] > 0
        assert abs(rates["latest_mom"] - 10.0) < 0.01


class TestRunHistoricalForecast:
    def test_all_methods(self):
        df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [1000 + i * 50 for i in range(12)],
        })
        result = run_historical_forecast(
            df, months=6,
            methods=["Linear Regression", "Exponential Smoothing", "Simple Moving Average"],
        )
        assert "linear" in result.columns
        assert "exponential_smoothing" in result.columns
        assert "sma" in result.columns


# ── Combined Engine ─────────────────────────────────────────────────────────


class TestCombinedForecast:
    def test_combined_equals_baseline_plus_uplifts(self):
        kw_df = pd.DataFrame({
            "keyword": ["test kw"],
            "volume": [5000],
            "kd": [20],
        })
        _, new_content_monthly = run_new_content_forecast(kw_df, da=60, cadence=1, months=12, seed=42)

        historical_df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [10000 + i * 200 for i in range(12)],
        })

        combined = run_combined_forecast(
            historical_df=historical_df,
            positional_monthly=None,
            new_content_monthly=new_content_monthly,
            months=12,
        )
        forecast = combined[combined["is_forecast"]]

        for _, row in forecast.iterrows():
            # v4: combined = baseline + positional_uplift + new_content_uplift - decay
            expected = row["baseline"] + row["positional_uplift"] + row["new_content_uplift"] - row.get("decay", 0)
            assert abs(row["combined"] - expected) < 2

    def test_uplift_only_no_historical(self):
        monthly = pd.DataFrame({
            "month": range(1, 13),
            "uplift": [100] * 12,
            "traffic": [100] * 12,
            "baseline": [0] * 12,
        })
        combined = run_combined_forecast(
            historical_df=None,
            positional_monthly=monthly,
            new_content_monthly=None,
            months=12,
        )
        assert (combined["baseline"] == 0).all()


class TestCombinedHub:
    def test_layered_math_with_bands(self):
        """v4 math: combined = baseline + positional + new_content - decay (no AIO deduction)."""
        historical = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [10000] * 12,
        })
        positional = pd.DataFrame({
            "month": range(1, 13),
            "baseline": [10000] * 12,
            "uplift_p10": [200] * 12,
            "uplift_p50": [500] * 12,
            "uplift_p90": [800] * 12,
        })
        decay = pd.DataFrame({
            "month": range(1, 13),
            "cumulative_decay": [50 * i for i in range(1, 13)],
        })
        combined = run_combined_forecast(
            historical_df=historical,
            positional_monthly=positional,
            new_content_monthly=None,
            months=12,
            decay_df=decay,
        )
        forecast = combined[combined["is_forecast"]]
        m12 = forecast.iloc[-1]
        # v4 math: no AIO deduction at combined level
        expected_p50 = m12["baseline"] + m12["positional_uplift_p50"] - m12["decay"]
        assert abs(m12["combined_p50"] - expected_p50) < 2

    def test_streams_apply_seasonality_internally(self):
        """With a big November boost, positional output in month 11 should be higher."""
        from engine.positional_engine import run_positional_forecast_mc
        seasonality = {m: {"traffic_mod": 0.0} for m in range(1, 13)}
        seasonality[2] = {"traffic_mod": 0.50}  # month 2 = February in forecast starting Jan

        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(20)],
            "position": [10] * 20,
            "volume": [1000] * 20,
            "kd": [30] * 20,
            "current_traffic": [80] * 20,
            "primary_intent": ["commercial"] * 20,
            "has_aio": [False] * 20,
        })
        _, monthly_no_season = run_positional_forecast_mc(df, months=12, n_trials=200, seed=42)
        _, monthly_season = run_positional_forecast_mc(
            df, months=12, n_trials=200, seed=42,
            seasonality=seasonality, forecast_start_month=1,
        )
        # Month 2 (index 1) should be higher with 50% boost
        assert monthly_season.iloc[1]["uplift_p50"] > monthly_no_season.iloc[1]["uplift_p50"]

    def test_combined_math_no_aio_term(self):
        """AIO is per-stream — combined must equal baseline + positional + new_content - decay."""
        positional = pd.DataFrame({
            "month": range(1, 7),
            "baseline": [10000] * 6,
            "uplift_p10": [100] * 6,
            "uplift_p50": [300] * 6,
            "uplift_p90": [500] * 6,
        })
        decay = pd.DataFrame({
            "month": range(1, 7),
            "cumulative_decay": [20 * i for i in range(1, 7)],
        })
        combined = run_combined_forecast(
            historical_df=None,
            positional_monthly=positional,
            new_content_monthly=None,
            months=6,
            decay_df=decay,
        )
        forecast = combined[combined["is_forecast"]]
        for _, row in forecast.iterrows():
            expected = row["baseline"] + row["positional_uplift_p50"] + row["new_content_uplift"] - row["decay"]
            assert abs(row["combined_p50"] - expected) < 2

    def test_bands_preserved_order(self):
        historical = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [10000] * 12,
        })
        positional = pd.DataFrame({
            "month": range(1, 13),
            "baseline": [10000] * 12,
            "uplift_p10": [200] * 12,
            "uplift_p50": [500] * 12,
            "uplift_p90": [800] * 12,
        })
        combined = run_combined_forecast(
            historical_df=historical,
            positional_monthly=positional,
            new_content_monthly=None,
            months=12,
        )
        forecast = combined[combined["is_forecast"]]
        assert (forecast["combined_p10"] <= forecast["combined_p50"]).all()
        assert (forecast["combined_p50"] <= forecast["combined_p90"]).all()

    def test_backward_compat_aliases(self):
        positional = pd.DataFrame({
            "month": range(1, 7),
            "baseline": [10000] * 6,
            "uplift_p10": [200] * 6,
            "uplift_p50": [500] * 6,
            "uplift_p90": [800] * 6,
        })
        combined = run_combined_forecast(
            historical_df=None,
            positional_monthly=positional,
            new_content_monthly=None,
            months=6,
        )
        assert "combined" in combined.columns
        assert "positional_uplift" in combined.columns


# ── Revenue Engine ──────────────────────────────────────────────────────────


class TestAddRevenue:
    def test_basic_math(self):
        df = pd.DataFrame({"month": [1, 2], "traffic": [1000, 2000]})
        result = add_revenue(df, cvr=2.0, aov=50.0)
        assert result["leads"].iloc[0] == 20  # 1000 * 0.02
        assert result["revenue"].iloc[0] == 1000.0  # 20 * 50

    def test_zero_traffic(self):
        df = pd.DataFrame({"month": [1], "traffic": [0]})
        result = add_revenue(df, cvr=5.0, aov=100.0)
        assert result["leads"].iloc[0] == 0
        assert result["revenue"].iloc[0] == 0.0


class TestKeywordRevenueTable:
    def test_filters_ranking_keywords(self):
        kw_df = pd.DataFrame({
            "keyword": ["a", "b", "c"],
            "estimated_monthly_traffic": [100, 200, 0],
            "will_rank": [True, True, False],
        })
        result = keyword_revenue_table(kw_df, cvr=5.0, aov=100.0)
        assert len(result) == 2
        assert result["monthly_revenue"].iloc[0] == 500.0  # 100 * 0.05 * 100


# ── Data Loader (unit-testable parts) ──────────────────────────────────────


class TestNewContentForecastFiltering:
    @pytest.fixture
    def mixed_intent_df(self):
        return pd.DataFrame({
            "keyword": [
                "how to do seo",          # informational
                "best seo tool",          # commercial
                "buy seo software",       # transactional
                "seo tutorial",           # informational
                "seo agency",             # commercial
            ],
            "volume": [5000, 3000, 2000, 4000, 1000],
            "kd": [15, 40, 30, 20, 50],
        })

    def test_intent_column_always_present(self, mixed_intent_df):
        kw_df, _ = run_new_content_forecast(mixed_intent_df, da=50, cadence=2, months=12, seed=42)
        assert "intent" in kw_df.columns

    def test_exclude_informational(self, mixed_intent_df):
        kw_df, _ = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            include_informational=False,
        )
        assert "informational" not in kw_df["intent"].values
        assert len(kw_df) == 3  # 2 informational removed from 5

    def test_ctr_penalty_reduces_traffic(self, mixed_intent_df):
        kw_base, _ = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
        )
        kw_penalty, _ = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            ai_overview_ctr_penalty=50.0,
        )
        # Informational keywords should have less or equal traffic with penalty
        base_info = kw_base[kw_base["intent"] == "informational"]["estimated_monthly_traffic"].sum()
        penalty_info = kw_penalty[kw_penalty["intent"] == "informational"]["estimated_monthly_traffic"].sum()
        assert penalty_info <= base_info

    def test_ctr_model_affects_traffic(self, mixed_intent_df):
        _, monthly_std = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            ctr_model=CTR_MODELS["Standard"],
        )
        _, monthly_ai = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            ctr_model=CTR_MODELS["AI-Adjusted"],
        )
        # AI-Adjusted should produce less or equal total traffic
        assert monthly_ai["traffic"].sum() <= monthly_std["traffic"].sum()

    def test_traffic_multiplier(self, mixed_intent_df):
        _, monthly_base = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            traffic_multiplier=1.0,
        )
        _, monthly_conservative = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            traffic_multiplier=0.7,
        )
        _, monthly_aggressive = run_new_content_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            traffic_multiplier=1.3,
        )
        base_total = monthly_base["traffic"].sum()
        assert monthly_conservative["traffic"].sum() <= base_total
        assert monthly_aggressive["traffic"].sum() >= base_total


class TestPresets:
    def test_site_preset_values_valid(self):
        for name, preset in SITE_PRESETS.items():
            assert "da" in preset
            assert "cadence" in preset
            assert "months" in preset
            assert 1 <= preset["da"] <= 100
            assert preset["cadence"] >= 1
            assert preset["months"] >= 6

    def test_ctr_models_have_required_keys(self):
        for name, model in CTR_MODELS.items():
            assert "ctr_by_position" in model
            assert "ctr_11_14" in model
            assert "ctr_15_20" in model
            assert "label" in model

    def test_forecast_scenarios_have_multiplier(self):
        for name, scenario in FORECAST_SCENARIOS.items():
            assert "traffic_multiplier" in scenario
            assert scenario["traffic_multiplier"] > 0


class TestForecastSeries:
    def test_forecast_series_length(self):
        from engine.historical_engine import forecast_series
        series = pd.Series([100, 110, 120, 130, 140])
        result = forecast_series(series, future_months=3)
        assert len(result) == 8  # 5 historical + 3 forecast

    def test_forecast_series_upward_trend(self):
        from engine.historical_engine import forecast_series
        series = pd.Series([100, 200, 300, 400, 500])
        result = forecast_series(series, future_months=3)
        assert result[-1] > result[4]  # Forecast continues upward


class TestExtendedHistoricalForecast:
    def test_with_optional_metrics(self):
        df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [1000 + i * 50 for i in range(12)],
            "revenue": [5000 + i * 200 for i in range(12)],
            "transactions": [50 + i * 3 for i in range(12)],
            "aov": [100 + i * 0.5 for i in range(12)],
            "cr": [5.0 - i * 0.05 for i in range(12)],
        })
        result = run_historical_forecast(df, months=6, methods=["Linear Regression"])
        assert "revenue_forecast" in result.columns
        assert "transactions_forecast" in result.columns
        assert "aov_forecast" in result.columns
        assert "cr_forecast" in result.columns
        assert len(result) == 18  # 12 historical + 6 forecast

    def test_without_optional_metrics(self):
        df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [1000 + i * 50 for i in range(12)],
        })
        result = run_historical_forecast(df, months=6, methods=["Linear Regression"])
        assert "revenue_forecast" not in result.columns
        assert "aov_forecast" not in result.columns


class TestBuildFullMetrics:
    def test_full_metrics_table(self):
        from engine.revenue_engine import build_full_metrics_table
        df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=18, freq="MS"),
            "traffic": [1000 + i * 50 for i in range(18)],
            "revenue": [5000 + i * 200 for i in range(18)],
            "transactions": [50 + i * 3 for i in range(18)],
            "aov": [100 + i * 0.5 for i in range(18)],
            "cr": [5.0 - i * 0.05 for i in range(18)],
        })
        result = run_historical_forecast(df, months=6, methods=["Linear Regression"])
        metrics = build_full_metrics_table(result)
        assert "Month" in metrics.columns
        assert "Organic Sessions" in metrics.columns
        assert "Organic Sessions Forecasted" in metrics.columns
        # YoY columns should exist for sessions at minimum
        yoy_cols = [c for c in metrics.columns if "YoY" in c]
        assert len(yoy_cols) > 0


class TestAddDynamicRevenue:
    def test_static_values(self):
        from engine.revenue_engine import add_dynamic_revenue
        df = pd.DataFrame({"month": [1, 2, 3], "traffic": [1000, 2000, 3000]})
        result = add_dynamic_revenue(df, cvr_series=5.0, aov_series=100.0)
        assert result["transactions"].iloc[0] == 50  # 1000 * 0.05
        assert result["revenue"].iloc[0] == 5000.0  # 50 * 100

    def test_dynamic_aov(self):
        from engine.revenue_engine import add_dynamic_revenue
        df = pd.DataFrame({"month": [1, 2, 3], "traffic": [1000, 1000, 1000]})
        result = add_dynamic_revenue(df, cvr_series=10.0, aov_series=[50, 100, 150])
        assert result["revenue"].iloc[0] == 5000.0   # 100 * 50
        assert result["revenue"].iloc[2] == 15000.0   # 100 * 150


class TestSeasonality:
    def test_apply_seasonality_modifies_traffic(self):
        from engine.seasonality_engine import apply_seasonality
        df = pd.DataFrame({"month": [1, 2, 3], "traffic": [1000, 1000, 1000]})
        result = apply_seasonality(df)
        # Seasonality should change at least some months
        assert not (result["traffic"] == 1000).all()
        assert "traffic_base" in result.columns
        assert "season_label" in result.columns

    def test_campaign_boost_adds_to_modifier(self):
        from engine.seasonality_engine import apply_seasonality
        df = pd.DataFrame({"month": [11], "traffic": [1000]})
        campaigns = [{"name": "Test Sale", "month": 11, "traffic_boost": 0.50}]
        result = apply_seasonality(df, campaigns=campaigns)
        # November default is 0.25, plus campaign 0.50 = 0.75 total
        assert result["traffic"].iloc[0] > 1500

    def test_build_campaign_list(self):
        from engine.seasonality_engine import build_campaign_list
        text = "GAZFRENZY | 11 | 0.20 | 0.10 | -0.05\nFather's Day | 9 | 0.15"
        campaigns = build_campaign_list(text)
        assert len(campaigns) == 2
        assert campaigns[0]["name"] == "GAZFRENZY"
        assert campaigns[0]["month"] == 11
        assert campaigns[1]["traffic_boost"] == 0.15


class TestKeywordPipeline:
    def test_classify_serp_page(self):
        from engine.keyword_pipeline_engine import classify_serp_page
        assert classify_serp_page(1) == "Page 1"
        assert classify_serp_page(10) == "Page 1"
        assert classify_serp_page(11) == "Page 2"
        assert classify_serp_page(25) == "Page 3"
        assert classify_serp_page(50) == "Pages 4-10"
        assert classify_serp_page(None) == "Not Ranking"

    def test_pipeline_snapshot(self):
        from engine.keyword_pipeline_engine import build_pipeline_snapshot
        kw_df = pd.DataFrame({"expected_position": [1, 5, 15, 25, None]})
        snapshot = build_pipeline_snapshot(kw_df)
        assert snapshot["Page 1"] == 2
        assert snapshot["Page 2"] == 1
        assert snapshot["Page 3"] == 1
        assert snapshot["Not Ranking"] == 1

    def test_pipeline_over_time(self):
        from engine.keyword_pipeline_engine import build_pipeline_over_time
        kw_df = pd.DataFrame({
            "keyword": ["kw1", "kw2"],
            "expected_position": [3, 15],
            "publish_month": [1, 1],
            "will_rank": [True, True],
            "traffic_starts_month": [4, 6],
            "time_to_rank": [3, 5],
        })
        result = build_pipeline_over_time(kw_df, months=12)
        assert len(result) == 12
        assert "page_1" in result.columns
        assert "page_1_mom_change" in result.columns


class TestRoadmapEngine:
    def test_build_roadmap_defaults(self):
        from engine.roadmap_engine import build_roadmap
        task_df, monthly_df, summary = build_roadmap(months=12)
        assert summary["n_tasks"] > 0
        assert summary["total_hours"] > 0
        assert len(task_df) == summary["n_tasks"]
        assert len(monthly_df) == summary["n_tasks"] + 1

    def test_quarterly_occurrence(self):
        from engine.roadmap_engine import build_roadmap
        task = [{"task": "Test Q", "focus": "Content", "occurrence": "Quarterly", "hours": 5.0}]
        _, monthly_df, _ = build_roadmap(task, months=12)
        task_row = monthly_df[monthly_df["Task"] == "Test Q"].iloc[0]
        assert task_row["M1"] == 5.0
        assert task_row["M2"] == 0.0
        assert task_row["M4"] == 5.0
        assert task_row["M7"] == 5.0
        assert task_row["M10"] == 5.0

    def test_xlsx_export_buffer(self):
        from engine.roadmap_engine import build_roadmap, build_roadmap_xlsx
        _, monthly_df, summary = build_roadmap(months=12)
        buf = build_roadmap_xlsx(monthly_df, summary, hourly_rate=200.0)
        data = buf.read()
        assert len(data) > 0
        assert data[:2] == b"PK"


class TestTemplates:
    def test_keyword_template_is_valid_csv(self):
        from utils.export import keyword_template_csv
        df = pd.read_csv(io.StringIO(keyword_template_csv()))
        assert list(df.columns) == ["keyword", "volume", "kd"]
        assert len(df) == 3

    def test_traffic_template_is_valid_csv(self):
        from utils.export import traffic_template_csv
        df = pd.read_csv(io.StringIO(traffic_template_csv()))
        assert "date" in df.columns
        assert "traffic" in df.columns
        assert len(df) == 3
        # Optional metric columns
        for col in ["revenue", "transactions", "aov", "cr"]:
            assert col in df.columns

    def test_keyword_template_has_valid_data(self):
        from utils.export import keyword_template_csv
        df = pd.read_csv(io.StringIO(keyword_template_csv()))
        assert (df["volume"] > 0).all()
        assert (df["kd"] >= 0).all()


class TestModelsConfig:
    def test_config_loads(self):
        from engine.ai_engine import get_model_options, get_default_model, get_fallback_chain
        models = get_model_options()
        assert len(models) > 0
        assert all("id" in m and "label" in m for m in models)

    def test_default_model_in_list(self):
        from engine.ai_engine import get_model_options, get_default_model
        default = get_default_model()
        ids = [m["id"] for m in get_model_options()]
        assert default in ids

    def test_fallback_chain_valid(self):
        from engine.ai_engine import get_model_options, get_fallback_chain
        chain = get_fallback_chain()
        assert len(chain) >= 2
        ids = [m["id"] for m in get_model_options()]
        for model in chain:
            assert model in ids


class TestPromptLoader:
    def test_all_prompts_load(self):
        from engine.ai_engine import _load_prompt
        for name in ["cluster_keywords", "check_cannibalization", "content_roadmap", "transform_data"]:
            system, user_tmpl = _load_prompt(name)
            assert len(system) > 20
            assert user_tmpl.template

    def test_prompt_substitution(self):
        from engine.ai_engine import _load_prompt
        system, user_tmpl = _load_prompt("cluster_keywords")
        result = user_tmpl.substitute(kw_list="- test keyword")
        assert "test keyword" in result


class TestDataLoaderHelpers:
    def test_efficiency_ordering_preserved(self):
        """Verify the new content engine sorts by efficiency."""
        df = pd.DataFrame({
            "keyword": ["low_eff", "high_eff"],
            "volume": [100, 10000],
            "kd": [90, 10],
        })
        kw_df, _ = run_new_content_forecast(df, da=50, cadence=1, months=6, seed=42)
        assert kw_df.iloc[0]["keyword"] == "high_eff"


# ── Positional Engine ──────────────────────────────────────────────────────


class TestPositionalForecast:
    @pytest.fixture
    def sample_existing(self):
        return pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(50)],
            "position": [3, 8, 15, 22] * 12 + [5, 12],
            "volume": [1000] * 50,
            "kd": [30] * 50,
            "current_traffic": [100] * 50,
            "primary_intent": ["commercial"] * 50,
            "has_aio": [False] * 50,
        })

    def test_ga4_anchored_baseline(self, sample_existing):
        from engine.positional_engine import run_positional_forecast
        kw_df, monthly = run_positional_forecast(
            sample_existing, months=12, effort="moderate", ga4_baseline=10000,
        )
        assert abs(monthly.iloc[0]["baseline"] - 10000) / 10000 < 0.01

    def test_month_12_exceeds_baseline(self, sample_existing):
        from engine.positional_engine import run_positional_forecast
        _, monthly = run_positional_forecast(
            sample_existing, months=12, effort="moderate", ga4_baseline=10000,
        )
        assert monthly.iloc[-1]["traffic"] > monthly.iloc[0]["baseline"]

    def test_effort_levels_ordered(self, sample_existing):
        from engine.positional_engine import run_positional_forecast
        _, light = run_positional_forecast(sample_existing, months=12, effort="light")
        _, moderate = run_positional_forecast(sample_existing, months=12, effort="moderate")
        _, aggressive = run_positional_forecast(sample_existing, months=12, effort="aggressive")
        assert aggressive.iloc[-1]["uplift"] >= moderate.iloc[-1]["uplift"] >= light.iloc[-1]["uplift"]

    def test_quick_wins_filter(self, sample_existing):
        from engine.positional_engine import run_positional_forecast, quick_wins
        kw_df, _ = run_positional_forecast(sample_existing, months=12, effort="moderate")
        qw = quick_wins(kw_df, top_n=20)
        if not qw.empty:
            assert (qw["position"] >= 4).all()
            assert (qw["position"] <= 20).all()


# ── Monte Carlo + Attention Curve ──────────────────────────────────────────


class TestPositionalMonteCarlo:
    @pytest.fixture
    def mc_sample(self):
        return pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(30)],
            "position": [10] * 30,
            "volume": [1000] * 30,
            "kd": [30] * 30,
            "current_traffic": [100] * 30,
            "primary_intent": ["commercial"] * 30,
            "has_aio": [False] * 30,
        })

    def test_bands_ordered(self, mc_sample):
        from engine.positional_engine import run_positional_forecast_mc
        _, monthly = run_positional_forecast_mc(mc_sample, months=12, n_trials=200)
        assert (monthly["uplift_p10"] <= monthly["uplift_p50"]).all()
        assert (monthly["uplift_p50"] <= monthly["uplift_p90"]).all()

    def test_band_width_meaningful(self):
        from engine.positional_engine import run_positional_forecast_mc
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(50)],
            "position": [15] * 50,
            "volume": [1000] * 50,
            "kd": [40] * 50,
            "current_traffic": [80] * 50,
            "primary_intent": ["commercial"] * 50,
            "has_aio": [False] * 50,
        })
        _, monthly = run_positional_forecast_mc(df, months=12, n_trials=500)
        m12 = monthly.iloc[-1]
        spread = m12["uplift_p90"] - m12["uplift_p10"]
        assert spread > m12["uplift_p50"] * 0.1

    def test_deterministic_with_seed(self, mc_sample):
        from engine.positional_engine import run_positional_forecast_mc
        _, m1 = run_positional_forecast_mc(mc_sample, months=12, n_trials=200, seed=42)
        _, m2 = run_positional_forecast_mc(mc_sample, months=12, n_trials=200, seed=42)
        pd.testing.assert_frame_equal(m1, m2)

    def test_backward_compat_columns(self, mc_sample):
        from engine.positional_engine import run_positional_forecast_mc
        _, monthly = run_positional_forecast_mc(mc_sample, months=12, n_trials=200)
        assert "uplift" in monthly.columns
        assert "traffic" in monthly.columns
        assert (monthly["uplift"] == monthly["uplift_p50"]).all()


class TestAttentionCurve:
    def test_top_keywords_get_full_weight(self):
        from engine.positional_engine import attention_weight
        assert attention_weight(0.01) == 1.00
        assert attention_weight(0.04) == 1.00

    def test_long_tail_gets_minimal_weight(self):
        from engine.positional_engine import attention_weight
        assert attention_weight(0.99) == 0.05

    def test_weights_decrease_monotonically(self):
        from engine.positional_engine import attention_weight
        weights = [attention_weight(p) for p in [0.01, 0.1, 0.3, 0.8]]
        for i in range(1, len(weights)):
            assert weights[i] <= weights[i - 1]

    def test_apply_attention_curve_assigns_weights(self):
        from engine.positional_engine import apply_attention_curve
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(100)],
            "volume": list(range(100, 0, -1)),
            "kd": [30] * 100,
        })
        result = apply_attention_curve(df)
        assert (result.head(5)["attention_weight"] == 1.00).all()
        assert (result.tail(50)["attention_weight"] == 0.05).all()

    def test_attention_reduces_aggregate_uplift(self):
        from engine.positional_engine import run_positional_forecast_mc
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(200)],
            "position": [15] * 200,
            "volume": [1000] * 200,
            "kd": [35] * 200,
            "current_traffic": [80] * 200,
            "primary_intent": ["commercial"] * 200,
            "has_aio": [False] * 200,
        })
        _, with_attn = run_positional_forecast_mc(
            df, months=12, n_trials=200, use_attention_curve=True, seed=99
        )
        _, no_attn = run_positional_forecast_mc(
            df, months=12, n_trials=200, use_attention_curve=False, seed=99
        )
        assert with_attn.iloc[-1]["uplift_p50"] < no_attn.iloc[-1]["uplift_p50"]


# ── AIO Risk Engine ────────────────────────────────────────────────────────


class TestAioRiskEngine:
    def test_zero_affected(self):
        from engine.aio_risk_engine import calculate_aio_risk
        df = pd.DataFrame({
            "keyword": ["a", "b"], "has_aio": [False, False],
            "volume": [100, 200], "current_traffic": [50, 100],
            "primary_intent": ["commercial", "commercial"],
        })
        risk = calculate_aio_risk(df, ctr_penalty_pct=40.0)
        assert risk["keywords_affected"] == 0
        assert risk["traffic_at_risk"] == 0

    def test_projected_loss_math(self):
        from engine.aio_risk_engine import calculate_aio_risk
        df = pd.DataFrame({
            "keyword": ["a", "b", "c"],
            "has_aio": [True, True, True],
            "volume": [100, 200, 300],
            "current_traffic": [400, 300, 300],
            "primary_intent": ["informational", "commercial", "informational"],
        })
        risk = calculate_aio_risk(df, ctr_penalty_pct=40.0)
        assert risk["traffic_at_risk"] == 1000
        assert risk["projected_loss"] == 400

    def test_intent_breakdown(self):
        from engine.aio_risk_engine import calculate_aio_risk
        df = pd.DataFrame({
            "keyword": ["a", "b"],
            "has_aio": [True, True],
            "volume": [100, 200],
            "current_traffic": [50, 100],
            "primary_intent": ["informational", "commercial"],
        })
        risk = calculate_aio_risk(df, ctr_penalty_pct=40.0)
        assert not risk["intent_breakdown"].empty

    def test_recommendations_nonempty(self):
        from engine.aio_risk_engine import calculate_aio_risk, aio_recommendations
        df = pd.DataFrame({
            "keyword": ["a"], "has_aio": [True],
            "volume": [100], "current_traffic": [50],
            "primary_intent": ["informational"],
        })
        risk = calculate_aio_risk(df)
        assert len(aio_recommendations(risk)) > 0


# ── Snapshot + Variance ────────────────────────────────────────────────────


class TestSnapshot:
    def test_roundtrip(self):
        from engine.snapshot_engine import build_snapshot, snapshot_to_bytes, load_snapshot
        combined = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=12, freq="MS"),
            "actual": [None] * 12,
            "baseline": [10000] * 12,
            "combined_p50": [11000] * 12,
            "is_forecast": [True] * 12,
        })
        snap = build_snapshot("Test Client", combined, {"effort": "moderate"})
        data = snapshot_to_bytes(snap)
        loaded = load_snapshot(data)
        assert loaded["client_name"] == "Test Client"
        assert len(loaded["forecast"]) == 12

    def test_variance_calculation(self):
        from engine.snapshot_engine import compare_to_actuals
        snapshot = {
            "forecast": [
                {"date": "2026-01-01", "combined_p50": 10000, "combined_p10": 8000, "combined_p90": 12000},
                {"date": "2026-02-01", "combined_p50": 10500, "combined_p10": 8500, "combined_p90": 12500},
            ]
        }
        actuals = pd.DataFrame({
            "date": ["2026-01-01", "2026-02-01"],
            "traffic": [10500, 9000],
        })
        result = compare_to_actuals(snapshot, actuals)
        assert len(result) == 2
        assert abs(result.iloc[0]["variance_pct"] - 5.0) < 0.1
        assert result.iloc[0]["within_band"]
        assert result.iloc[1]["variance_pct"] < 0

    def test_summarise_variance(self):
        from engine.snapshot_engine import compare_to_actuals, summarise_variance
        snapshot = {
            "forecast": [
                {"date": "2026-01-01", "combined_p50": 10000, "combined_p10": 8000, "combined_p90": 12000},
            ]
        }
        actuals = pd.DataFrame({"date": ["2026-01-01"], "traffic": [10500]})
        comparison = compare_to_actuals(snapshot, actuals)
        summary = summarise_variance(comparison)
        assert summary["n_months_compared"] == 1
        assert summary["pct_within_band"] == 100.0


# ── AIO Erosion (Time-varying) ─────────────────────────────────────────────


class TestAioErosion:
    def test_erosion_grows_over_time(self):
        from engine.aio_risk_engine import project_aio_erosion
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(100)],
            "primary_intent": ["informational"] * 100,
            "current_traffic": [100] * 100,
            "has_aio": [False] * 100,
        })
        result = project_aio_erosion(df, months=24, monthly_growth=0.03)
        assert result["cumulative_erosion"].is_monotonic_increasing
        assert result.iloc[-1]["cumulative_erosion"] > result.iloc[0]["cumulative_erosion"] * 5

    def test_informational_erodes_more_than_transactional(self):
        from engine.aio_risk_engine import project_aio_erosion
        info_df = pd.DataFrame({
            "keyword": ["a"], "primary_intent": ["informational"],
            "current_traffic": [1000], "has_aio": [True],
        })
        trans_df = pd.DataFrame({
            "keyword": ["a"], "primary_intent": ["transactional"],
            "current_traffic": [1000], "has_aio": [True],
        })
        info_result = project_aio_erosion(info_df, months=12)
        trans_result = project_aio_erosion(trans_df, months=12)
        assert info_result.iloc[-1]["cumulative_erosion"] > trans_result.iloc[-1]["cumulative_erosion"]

    def test_zero_growth_only_hits_pre_affected(self):
        from engine.aio_risk_engine import project_aio_erosion
        df = pd.DataFrame({
            "keyword": ["a", "b"],
            "primary_intent": ["informational", "informational"],
            "current_traffic": [1000, 1000],
            "has_aio": [True, False],
        })
        result = project_aio_erosion(df, months=12, monthly_growth=0.0)
        assert result.iloc[0]["cumulative_erosion"] == result.iloc[-1]["cumulative_erosion"]


# ── Decay Engine ──────────────────────────────────────────────────────────


class TestDecayEngine:
    def test_position_bucketing(self):
        from engine.decay_engine import position_bucket
        assert position_bucket(1) == "top3"
        assert position_bucket(5) == "top10"
        assert position_bucket(15) == "11_20"
        assert position_bucket(30) == "21_50"
        assert position_bucket(75) == "51_plus"
        assert position_bucket(None) == "51_plus"

    def test_monthly_decay_factor(self):
        from engine.decay_engine import monthly_decay_factor
        monthly = monthly_decay_factor(0.12)
        assert 0.98 < monthly < 0.995
        annual = monthly ** 12
        assert abs(annual - 0.88) < 0.01

    def test_decay_cumulative_increases(self):
        from engine.decay_engine import calculate_portfolio_decay
        df = pd.DataFrame({
            "keyword": ["a", "b", "c"],
            "position": [2, 8, 25],
            "current_traffic": [1000, 500, 200],
        })
        result = calculate_portfolio_decay(df, months=12)
        assert result["cumulative_decay"].is_monotonic_increasing

    def test_maintenance_reduces_decay(self):
        from engine.decay_engine import calculate_portfolio_decay
        df = pd.DataFrame({
            "keyword": ["a"],
            "position": [10],
            "current_traffic": [1000],
        })
        no_maint = calculate_portfolio_decay(df, months=12, maintenance_coverage=0.0)
        with_maint = calculate_portfolio_decay(df, months=12, maintenance_coverage=0.7)
        assert with_maint.iloc[-1]["cumulative_decay"] < no_maint.iloc[-1]["cumulative_decay"]

    def test_empty_portfolio(self):
        from engine.decay_engine import calculate_portfolio_decay
        df = pd.DataFrame(columns=["position", "current_traffic"])
        result = calculate_portfolio_decay(df, months=6)
        assert len(result) == 6
        assert result["decay_loss"].sum() == 0

    def test_decayed_baseline_is_lower_than_linear(self):
        from engine.decay_engine import project_decayed_baseline
        historical = pd.Series([10000 + i * 100 for i in range(12)])
        keyword_df = pd.DataFrame({
            "keyword": ["a", "b"],
            "position": [5, 25],
            "current_traffic": [3000, 1500],
        })
        result = project_decayed_baseline(historical, keyword_df, months=12, maintenance_coverage=0.0)
        assert (result["honest_baseline"] <= result["linear_baseline"]).all()


class TestDecayRespectsMaintenance:
    def test_high_maintenance_reduces_decay(self):
        """High maintenance_coverage should meaningfully reduce cumulative decay vs zero."""
        from engine.decay_engine import calculate_portfolio_decay
        df = pd.DataFrame({
            "keyword": ["kw1", "kw2", "kw3"],
            "position": [2, 7, 15],
            "current_traffic": [2000, 1000, 500],
        })
        no_maint = calculate_portfolio_decay(df, months=12, maintenance_coverage=0.0)
        high_maint = calculate_portfolio_decay(df, months=12, maintenance_coverage=0.9)
        cumulative_no = no_maint.iloc[-1]["cumulative_decay"]
        cumulative_hi = high_maint.iloc[-1]["cumulative_decay"]
        assert cumulative_hi < cumulative_no
        # At 0.9 coverage, effective decay should be reduced by at least 50%
        assert cumulative_hi < cumulative_no * 0.5


# ── Intent-Weighted Revenue ───────────────────────────────────────────────


class TestIntentWeightedRevenue:
    def test_commercial_only_boosts_cvr(self):
        from engine.revenue_engine import compute_intent_weighted_cvr
        df = pd.DataFrame({
            "primary_intent": ["commercial"] * 5,
            "uplift": [100] * 5,
        })
        result = compute_intent_weighted_cvr(df, 2.0)
        assert result == pytest.approx(2.0 * 1.5, rel=0.01)

    def test_transactional_highest_multiplier(self):
        from engine.revenue_engine import compute_intent_weighted_cvr
        df = pd.DataFrame({
            "primary_intent": ["transactional"] * 5,
            "volume": [100] * 5,
        })
        result = compute_intent_weighted_cvr(df, 2.0)
        assert result == pytest.approx(2.0 * 2.0, rel=0.01)

    def test_informational_lowers_cvr(self):
        from engine.revenue_engine import compute_intent_weighted_cvr
        df = pd.DataFrame({
            "primary_intent": ["informational"] * 5,
            "uplift": [100] * 5,
        })
        result = compute_intent_weighted_cvr(df, 2.0)
        assert result < 2.0

    def test_mixed_intent_is_between(self):
        from engine.revenue_engine import compute_intent_weighted_cvr
        df = pd.DataFrame({
            "primary_intent": ["commercial", "informational"],
            "uplift": [100, 100],
        })
        result = compute_intent_weighted_cvr(df, 2.0)
        assert 2.0 * 0.3 < result < 2.0 * 1.5

    def test_empty_returns_base(self):
        from engine.revenue_engine import compute_intent_weighted_cvr
        df = pd.DataFrame({"primary_intent": [], "uplift": []})
        assert compute_intent_weighted_cvr(df, 2.5) == 2.5

    def test_intent_col_fallback(self):
        """New content engine uses 'intent' not 'primary_intent'."""
        from engine.revenue_engine import compute_intent_weighted_cvr
        df = pd.DataFrame({
            "intent": ["commercial"] * 3,
            "estimated_monthly_traffic": [200] * 3,
        })
        result = compute_intent_weighted_cvr(df, 2.0)
        assert result == pytest.approx(2.0 * 1.5, rel=0.01)

    def test_breakdown_table(self):
        from engine.revenue_engine import intent_revenue_breakdown
        df = pd.DataFrame({
            "primary_intent": ["commercial", "transactional", "informational"],
            "uplift": [1000, 500, 300],
        })
        table = intent_revenue_breakdown(df, 2.0, 100.0)
        assert not table.empty
        assert "Intent" in table.columns
        assert "Monthly Revenue" in table.columns
        assert len(table) == 4  # one row per intent in INTENT_CVR_MULTIPLIERS


# ── Movement Learning ────────────────────────────────────────────────────────


class TestMovementLearning:
    def test_learn_movement_returns_per_tier_stats(self):
        from engine.positional_engine import learn_movement_from_history
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(40)],
            "kd": [20] * 20 + [50] * 20,
            "previous_position": [15] * 20 + [25] * 20,
            "position": [10] * 20 + [20] * 20,
        })
        stats = learn_movement_from_history(df)
        assert "Easy" in stats
        assert abs(stats["Easy"]["mean_gain"] - 5.0) < 0.01
        assert stats["Easy"]["sample_size"] == 20

    def test_learn_movement_filters_outliers(self):
        from engine.positional_engine import learn_movement_from_history
        # Row 0: previous=70, position=20 → delta=50 (>30, outlier, excluded)
        # Rows 1-14: previous=15, position=10 → delta=5 (valid)
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(15)],
            "kd": [20] * 15,
            "previous_position": [70] + [15] * 14,
            "position": [20] + [10] * 14,
        })
        stats = learn_movement_from_history(df)
        # Only 14 valid samples; the 50-position jump is excluded
        assert stats["Easy"]["sample_size"] == 14
        assert abs(stats["Easy"]["mean_gain"] - 5.0) < 0.01

    def test_learn_movement_skips_small_samples(self):
        from engine.positional_engine import learn_movement_from_history
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(8)],
            "kd": [20] * 8,
            "previous_position": [15] * 8,
            "position": [10] * 8,
        })
        stats = learn_movement_from_history(df)
        assert "Easy" not in stats  # 8 samples < 10 threshold

    def test_learn_movement_missing_column_returns_empty(self):
        from engine.positional_engine import learn_movement_from_history
        df = pd.DataFrame({
            "keyword": ["kw1"], "kd": [20], "position": [10],
        })
        assert learn_movement_from_history(df) == {}

    def test_estimate_target_uses_learned_stats_when_available(self):
        from engine.positional_engine import estimate_target_position
        stats_high = {"Easy": {"mean_gain": 10.0, "std_gain": 1.0, "sample_size": 20}}
        stats_low = {"Easy": {"mean_gain": 2.0, "std_gain": 1.0, "sample_size": 20}}
        target_high = estimate_target_position(20, 15, "moderate", stats_high)
        target_low = estimate_target_position(20, 15, "moderate", stats_low)
        assert target_high < target_low  # Higher learned gain → better (lower) position

    def test_estimate_target_falls_back_when_tier_has_few_samples(self):
        from engine.positional_engine import estimate_target_position
        # Easy: 15 samples → use learned (mean=10); Extreme: 2 samples → fall back to default
        mixed_stats = {
            "Easy": {"mean_gain": 10.0, "std_gain": 1.0, "sample_size": 15},
            "Extreme": {"mean_gain": 99.0, "std_gain": 1.0, "sample_size": 2},
        }
        # Easy keyword (kd=15): should use learned mean=10, giving a bigger gain
        target_easy_learned = estimate_target_position(20, 15, "moderate", mixed_stats)
        target_easy_default = estimate_target_position(20, 15, "moderate", None)
        assert target_easy_learned < target_easy_default  # learned gain > default → better position

        # Extreme keyword (kd=90): 2 samples < 10, falls back to _BASE_GAIN_BY_TIER
        target_extreme_mixed = estimate_target_position(20, 90, "moderate", mixed_stats)
        target_extreme_default = estimate_target_position(20, 90, "moderate", None)
        assert target_extreme_mixed == target_extreme_default  # fallback produces same result

    def test_forecast_with_learned_stats_differs_from_defaults(self):
        from engine.positional_engine import run_positional_forecast_mc
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(30)],
            "position": [15] * 30,
            "volume": [1000] * 30,
            "kd": [20] * 30,
            "current_traffic": [80] * 30,
            "primary_intent": ["commercial"] * 30,
            "has_aio": [False] * 30,
        })
        _, monthly_default = run_positional_forecast_mc(df, months=12, n_trials=200, seed=42)
        big_gain_stats = {
            "Easy": {"mean_gain": 12.0, "std_gain": 1.0, "sample_size": 20}
        }
        _, monthly_learned = run_positional_forecast_mc(
            df, months=12, n_trials=200, seed=42,
            historical_movement_stats=big_gain_stats,
        )
        assert monthly_learned.iloc[-1]["uplift_p50"] != monthly_default.iloc[-1]["uplift_p50"]


# ── Maturation Curve (Task 4) ─────────────────────────────────────────────


class TestMaturationCurve:
    def test_logistic_progress_at_midpoint_is_half(self):
        from engine.maturation_curve import logistic_progress
        # At t == t_mid, sigmoid evaluates to exactly 0.5 regardless of k
        assert abs(logistic_progress(5.0, 5.0, 1.0) - 0.5) < 0.001
        assert abs(logistic_progress(5.0, 5.0, 1.2) - 0.5) < 0.001

    def test_logistic_progress_monotonically_increasing(self):
        from engine.maturation_curve import maturation_schedule
        schedule = maturation_schedule("Moderate", 24, 1)
        assert all(schedule[i] <= schedule[i + 1] for i in range(len(schedule) - 1))

    def test_maturation_schedule_zero_before_publish(self):
        from engine.maturation_curve import maturation_schedule
        # publish_month=3: months 1, 2, 3 are 0 (elapsed ≤ 0); month 4 starts accumulating
        schedule = maturation_schedule("Easy", 12, 3)
        assert schedule[0] == 0.0  # month 1
        assert schedule[1] == 0.0  # month 2
        assert schedule[2] == 0.0  # month 3 (publish month itself: elapsed=0 → 0.0)
        assert schedule[3] > 0.0   # month 4 (elapsed=1, first post-publish month)

    def test_easy_tier_ramps_faster_than_extreme(self):
        from engine.maturation_curve import maturation_schedule
        easy = maturation_schedule("Easy", 12, 1)
        extreme = maturation_schedule("Extreme", 12, 1)
        assert easy[5] > extreme[5]  # by month 6, Easy is meaningfully ahead of Extreme

    def test_80_pct_shape_constraint(self):
        """S-curve should reach ~75%+ by three-quarters of the way through the ramp."""
        from engine.maturation_curve import maturation_schedule
        schedule = maturation_schedule("Easy", 12, 1)
        assert schedule[6] >= 0.75

    def test_new_content_no_discontinuity(self):
        """No single-month jump should exceed 50% of that keyword's final traffic."""
        df = pd.DataFrame({
            "keyword": ["kw1"],
            "volume": [5000],
            "kd": [15],
        })
        _, monthly = run_new_content_forecast(df, da=60, cadence=1, months=18, seed=42)
        traffic = monthly["traffic"].values.astype(float)
        diffs = [abs(traffic[i] - traffic[i - 1]) for i in range(1, len(traffic))]
        final = max(traffic[-1], 1)
        assert all(d / final < 0.5 for d in diffs)

    def test_positional_bands_still_ordered_after_scurve(self):
        from engine.positional_engine import run_positional_forecast_mc
        df = pd.DataFrame({
            "keyword": [f"kw_{i}" for i in range(30)],
            "position": [10] * 30,
            "volume": [1000] * 30,
            "kd": [30] * 30,
            "current_traffic": [100] * 30,
            "primary_intent": ["commercial"] * 30,
            "has_aio": [False] * 30,
        })
        _, monthly = run_positional_forecast_mc(df, months=12, n_trials=200, seed=42)
        assert (monthly["uplift_p10"] <= monthly["uplift_p50"]).all()
        assert (monthly["uplift_p50"] <= monthly["uplift_p90"]).all()


# ── Learned Seasonality (Task 3) ─────────────────────────────────────────


class TestLearnedSeasonality:
    def _make_ga4_df(self, n_years=2, nov_boost=0.25):
        """Synthetic GA4 df where November is artificially high."""
        dates = pd.date_range("2022-01-01", periods=12 * n_years, freq="MS")
        traffic = []
        for d in dates:
            base = 10000
            if d.month == 11:
                base = int(base * (1 + nov_boost))
            traffic.append(base)
        return pd.DataFrame({"date": dates, "traffic": traffic})

    def test_learn_seasonality_with_november_peak(self):
        from engine.seasonality_engine import learn_seasonality_from_ga4
        df = self._make_ga4_df(n_years=2, nov_boost=0.25)
        learned = learn_seasonality_from_ga4(df)
        assert learned is not None
        assert abs(learned[11]["traffic_mod"] - 0.25) < 0.03

    def test_learn_seasonality_requires_12_months(self):
        from engine.seasonality_engine import learn_seasonality_from_ga4
        df = self._make_ga4_df(n_years=1).head(6)
        assert learn_seasonality_from_ga4(df) is None

    def test_blend_weight_zero_returns_defaults(self):
        from engine.seasonality_engine import (
            learn_seasonality_from_ga4,
            blend_learned_and_default_seasonality,
            DEFAULT_SEASONALITY,
        )
        df = self._make_ga4_df()
        learned = learn_seasonality_from_ga4(df)
        blended = blend_learned_and_default_seasonality(learned, DEFAULT_SEASONALITY, 0.0)
        for m in range(1, 13):
            assert blended[m]["traffic_mod"] == DEFAULT_SEASONALITY[m]["traffic_mod"]

    def test_blend_weight_one_returns_learned(self):
        from engine.seasonality_engine import (
            learn_seasonality_from_ga4,
            blend_learned_and_default_seasonality,
            DEFAULT_SEASONALITY,
        )
        df = self._make_ga4_df()
        learned = learn_seasonality_from_ga4(df)
        blended = blend_learned_and_default_seasonality(learned, DEFAULT_SEASONALITY, 1.0)
        for m in range(1, 13):
            assert abs(blended[m]["traffic_mod"] - learned[m]["traffic_mod"]) < 0.001

    def test_blend_weight_half_is_midpoint(self):
        from engine.seasonality_engine import (
            learn_seasonality_from_ga4,
            blend_learned_and_default_seasonality,
            DEFAULT_SEASONALITY,
        )
        df = self._make_ga4_df()
        learned = learn_seasonality_from_ga4(df)
        blended = blend_learned_and_default_seasonality(learned, DEFAULT_SEASONALITY, 0.5)
        for m in range(1, 13):
            expected = round(
                0.5 * learned[m]["traffic_mod"] + 0.5 * DEFAULT_SEASONALITY[m]["traffic_mod"], 4
            )
            assert abs(blended[m]["traffic_mod"] - expected) < 0.001

    def test_au_holidays_df_has_black_friday_2025(self):
        from engine.seasonality_engine import build_au_holidays_df
        df = build_au_holidays_df(2025, 2025)
        bf = df[df["holiday"] == "Black Friday"]
        assert len(bf) == 1
        ds = pd.to_datetime(bf["ds"].iloc[0])
        assert ds.year == 2025
        assert ds.month == 11
        assert ds.weekday() == 4  # Friday

    def test_au_holidays_df_covers_full_year_range(self):
        from engine.seasonality_engine import build_au_holidays_df
        df = build_au_holidays_df(2023, 2028)
        years = pd.to_datetime(df["ds"]).dt.year.unique()
        for y in range(2023, 2029):
            assert y in years

    def test_au_holidays_has_all_required_events(self):
        from engine.seasonality_engine import AU_HOLIDAYS
        required = {
            "EOFY", "Black Friday", "Cyber Monday",
            "Christmas", "Boxing Day Sales", "Back to School",
        }
        found = set(AU_HOLIDAYS["holiday"].unique())
        for r in required:
            assert r in found, f"Missing holiday: {r}"

    def test_au_holidays_has_correct_columns(self):
        from engine.seasonality_engine import AU_HOLIDAYS
        assert set(AU_HOLIDAYS.columns) >= {"holiday", "ds", "lower_window", "upper_window"}


# ── Prophet / v4 Historical (Task 1) ─────────────────────────────────────


class TestHistoricalV4:
    def _make_df(self, n_months: int, trend: float = 100.0):
        dates = pd.date_range("2022-01-01", periods=n_months, freq="MS")
        traffic = [int(5000 + i * trend) for i in range(n_months)]
        return pd.DataFrame({"date": dates, "traffic": traffic})

    def test_24_months_selects_holts_or_prophet(self):
        from engine.historical_engine import run_historical_forecast_v4, _PROPHET_MIN_MONTHS
        df = self._make_df(24)
        result = run_historical_forecast_v4(df, months=6)
        assert result.attrs["chosen_method"] in ("prophet", "holts", "linear")
        # With 24 months, should not be linear
        assert result.attrs["chosen_method"] != "linear"

    def test_18_months_selects_holts(self):
        from engine.historical_engine import run_historical_forecast_v4
        df = self._make_df(18)
        result = run_historical_forecast_v4(df, months=6)
        assert result.attrs["chosen_method"] == "holts"

    def test_6_months_selects_linear(self):
        from engine.historical_engine import run_historical_forecast_v4
        df = self._make_df(6)
        result = run_historical_forecast_v4(df, months=3)
        assert result.attrs["chosen_method"] == "linear"

    def test_fallback_when_prophet_unavailable(self):
        """Mock ImportError to ensure graceful fallback."""
        import sys
        import unittest.mock as mock
        from engine.historical_engine import run_historical_forecast_v4
        df = self._make_df(24)
        with mock.patch.dict(sys.modules, {"prophet": None}):
            result = run_historical_forecast_v4(df, months=6)
        # Should still produce a result with linear
        assert len(result) == 24 + 6
        assert "linear" in result.columns

    def test_output_extends_dates(self):
        from engine.historical_engine import run_historical_forecast_v4
        df = self._make_df(12)
        result = run_historical_forecast_v4(df, months=6)
        assert len(result) == 18
        forecast_rows = result[result["is_forecast"]]
        assert len(forecast_rows) == 6

    def test_trending_data_produces_nonfloat_forecast(self):
        from engine.historical_engine import run_historical_forecast_v4
        df = self._make_df(18, trend=500.0)
        result = run_historical_forecast_v4(df, months=6)
        forecast = result[result["is_forecast"]]
        # A strong upward trend should produce non-flat forecasts
        assert forecast["exponential_smoothing"].iloc[-1] != forecast["exponential_smoothing"].iloc[0]
