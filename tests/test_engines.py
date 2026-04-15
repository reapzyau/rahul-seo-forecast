import io

import numpy as np
import pandas as pd
import pytest

from engine.constants import (
    CTR_BY_POSITION, CTR_11_14, CTR_15_20,
    SITE_PRESETS, CTR_MODELS, FORECAST_SCENARIOS, INTENT_PATTERNS,
)
from engine.keyword_engine import (
    classify_difficulty,
    classify_intent,
    ranking_probability,
    expected_position,
    get_ctr,
    time_to_rank_months,
    efficiency_score,
    run_keyword_forecast,
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


class TestRunKeywordForecast:
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "keyword": ["easy kw", "hard kw", "medium kw"],
            "volume": [5000, 3000, 4000],
            "kd": [15, 75, 40],
        })

    def test_returns_two_dataframes(self, sample_df):
        kw_df, monthly_df = run_keyword_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        assert isinstance(kw_df, pd.DataFrame)
        assert isinstance(monthly_df, pd.DataFrame)

    def test_sorted_by_efficiency(self, sample_df):
        kw_df, _ = run_keyword_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        scores = kw_df["efficiency_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_monthly_df_has_correct_length(self, sample_df):
        _, monthly_df = run_keyword_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        assert len(monthly_df) == 12

    def test_seed_reproducibility(self, sample_df):
        kw1, m1 = run_keyword_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        kw2, m2 = run_keyword_forecast(sample_df, da=50, cadence=2, months=12, seed=42)
        pd.testing.assert_frame_equal(kw1, kw2)
        pd.testing.assert_frame_equal(m1, m2)

    def test_traffic_monotonically_nondecreasing(self, sample_df):
        _, monthly_df = run_keyword_forecast(sample_df, da=50, cadence=2, months=18, seed=42)
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
        # Sudden jump: smoothed should follow the jump direction
        traffic = pd.Series([100, 100, 100, 100, 200])
        result = exponential_smoothing_forecast(traffic, alpha=0.5, future_months=1)
        assert result[-1] > 100  # Forecast should be above baseline


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
    def test_combined_equals_baseline_plus_incremental(self):
        kw_df = pd.DataFrame({
            "keyword": ["test kw"],
            "volume": [5000],
            "kd": [20],
        })
        keyword_df, monthly_kw_df = run_keyword_forecast(kw_df, da=60, cadence=1, months=12, seed=42)

        historical_df = pd.DataFrame({
            "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
            "traffic": [10000 + i * 200 for i in range(12)],
        })

        combined = run_combined_forecast(keyword_df, monthly_kw_df, historical_df, months=12)
        forecast = combined[combined["is_forecast"]]

        # Combined should equal baseline + new_content for each row
        for _, row in forecast.iterrows():
            assert row["combined"] == row["baseline"] + row["new_content"]


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


class TestKeywordForecastFiltering:
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
        kw_df, _ = run_keyword_forecast(mixed_intent_df, da=50, cadence=2, months=12, seed=42)
        assert "intent" in kw_df.columns

    def test_exclude_informational(self, mixed_intent_df):
        kw_df, _ = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            exclude_informational=True,
        )
        assert "informational" not in kw_df["intent"].values
        assert len(kw_df) == 3  # 2 informational removed from 5

    def test_ctr_penalty_reduces_traffic(self, mixed_intent_df):
        kw_base, _ = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
        )
        kw_penalty, _ = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            informational_ctr_penalty=50.0,
        )
        # Informational keywords should have less or equal traffic with penalty
        base_info = kw_base[kw_base["intent"] == "informational"]["estimated_monthly_traffic"].sum()
        penalty_info = kw_penalty[kw_penalty["intent"] == "informational"]["estimated_monthly_traffic"].sum()
        assert penalty_info <= base_info

    def test_ctr_model_affects_traffic(self, mixed_intent_df):
        _, monthly_std = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            ctr_model=CTR_MODELS["Standard"],
        )
        _, monthly_ai = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            ctr_model=CTR_MODELS["AI-Adjusted"],
        )
        # AI-Adjusted should produce less or equal total traffic
        assert monthly_ai["traffic"].sum() <= monthly_std["traffic"].sum()

    def test_traffic_multiplier(self, mixed_intent_df):
        _, monthly_base = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            traffic_multiplier=1.0,
        )
        _, monthly_conservative = run_keyword_forecast(
            mixed_intent_df, da=50, cadence=2, months=12, seed=42,
            traffic_multiplier=0.7,
        )
        _, monthly_aggressive = run_keyword_forecast(
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


class TestBudgetEngine:
    def test_build_budget_roadmap(self):
        from engine.budget_engine import build_budget_roadmap
        task_df, summary = build_budget_roadmap(hourly_rate=200.0, months=12)
        assert len(task_df) > 0
        assert summary["hourly_rate"] == 200.0
        assert summary["total_monthly_cost"] > 0
        assert summary["total_annual_cost"] == summary["total_monthly_cost"] * 12

    def test_custom_tasks(self):
        from engine.budget_engine import build_budget_roadmap
        tasks = [{"category": "Test", "task": "Test Task", "hours_per_month": 10.0}]
        task_df, summary = build_budget_roadmap(tasks, hourly_rate=100.0)
        assert summary["total_monthly_cost"] == 1000.0

    def test_monthly_timeline(self):
        from engine.budget_engine import build_monthly_budget_timeline
        timeline = build_monthly_budget_timeline(months=6)
        assert len(timeline) == 6
        assert "Total" in timeline.columns


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


class TestDataLoaderHelpers:
    def test_efficiency_ordering_preserved(self):
        """Verify the keyword engine sorts by efficiency."""
        df = pd.DataFrame({
            "keyword": ["low_eff", "high_eff"],
            "volume": [100, 10000],
            "kd": [90, 10],
        })
        kw_df, _ = run_keyword_forecast(df, da=50, cadence=1, months=6, seed=42)
        assert kw_df.iloc[0]["keyword"] == "high_eff"
