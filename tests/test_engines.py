import numpy as np
import pandas as pd
import pytest

from engine.constants import CTR_BY_POSITION, CTR_11_14, CTR_15_20
from engine.keyword_engine import (
    classify_difficulty,
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
