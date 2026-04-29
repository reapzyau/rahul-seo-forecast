"""Tests for engine/baseline_metrics_engine.py and revenue_engine additions."""
import pandas as pd
import pytest

from engine.baseline_metrics_engine import forecast_baseline_metrics
from engine.revenue_engine import compute_intent_weighted_cvr_per_month


def _make_ga4_df(n_months: int = 18, with_cr: bool = True, with_aov: bool = True):
    """Build a synthetic GA4 DataFrame with n_months of history."""
    dates = pd.date_range("2024-01-01", periods=n_months, freq="MS")
    traffic = pd.Series([10_000 + i * 200 for i in range(n_months)])
    df = pd.DataFrame({"date": dates, "traffic": traffic})
    if with_cr:
        # Rising CVR: 2.0% → ~2.85% over 18 months
        df["cr"] = [2.0 + i * 0.05 for i in range(n_months)]
    if with_aov:
        # Rising AOV: $100 → $117
        df["aov"] = [100.0 + i * 1.0 for i in range(n_months)]
    return df


class TestBaselineMetricsEngine:
    def test_returns_correct_number_of_rows(self):
        ga4_df = _make_ga4_df()
        result = forecast_baseline_metrics(ga4_df, 12)
        assert len(result) == 12

    def test_month_index_is_one_based(self):
        ga4_df = _make_ga4_df()
        result = forecast_baseline_metrics(ga4_df, 6)
        assert list(result["month"]) == [1, 2, 3, 4, 5, 6]

    def test_required_columns_present(self):
        ga4_df = _make_ga4_df()
        result = forecast_baseline_metrics(ga4_df, 6)
        for col in ("month", "date", "traffic", "cvr", "aov", "transactions", "revenue"):
            assert col in result.columns, f"Missing column: {col}"

    def test_cvr_varies_across_months_when_trend_detected(self):
        ga4_df = _make_ga4_df(with_cr=True)
        result = forecast_baseline_metrics(ga4_df, 12, seasonality={})
        # Trend-fit means CVR should not be flat (all identical)
        assert result["cvr"].nunique() > 1, "CVR should vary when historical trend exists"

    def test_fallback_cvr_when_no_cr_column(self):
        ga4_df = _make_ga4_df(with_cr=False, with_aov=False)
        result = forecast_baseline_metrics(
            ga4_df, 6, seasonality={}, fallback_cvr=3.0, fallback_aov=150.0
        )
        # No trend fitting: should use fallback scalar
        assert all(abs(row["cvr"] - 3.0) < 1e-6 for _, row in result.iterrows())

    def test_transactions_derived_from_traffic_and_cvr(self):
        ga4_df = _make_ga4_df()
        # Use empty seasonality to isolate trend logic
        result = forecast_baseline_metrics(ga4_df, 6, seasonality={})
        for _, row in result.iterrows():
            expected = int(round(row["traffic"] * row["cvr"] / 100.0))
            assert row["transactions"] == expected

    def test_revenue_derived_from_transactions_and_aov(self):
        ga4_df = _make_ga4_df()
        result = forecast_baseline_metrics(ga4_df, 6, seasonality={})
        for _, row in result.iterrows():
            expected = round(row["transactions"] * row["aov"], 2)
            assert abs(row["revenue"] - expected) < 0.01

    def test_seasonality_cr_mod_applied(self):
        ga4_df = _make_ga4_df(with_cr=False, with_aov=False)
        # Craft a seasonality with only month 1 having a cr_mod
        custom_season = {i: {"cr_mod": 0.0, "aov_mod": 0.0} for i in range(1, 13)}
        custom_season[1]["cr_mod"] = 0.50  # +50% for January
        result = forecast_baseline_metrics(
            ga4_df, 12, seasonality=custom_season, fallback_cvr=2.0
        )
        jan_row = result[pd.to_datetime(result["date"]).dt.month == 1]
        other_rows = result[pd.to_datetime(result["date"]).dt.month != 1]
        if not jan_row.empty and not other_rows.empty:
            # January CVR should be ~3.0 (2.0 × 1.5), others ~2.0
            assert jan_row.iloc[0]["cvr"] == pytest.approx(3.0, abs=0.01)

    def test_aov_varies_when_trend_detected(self):
        ga4_df = _make_ga4_df(with_aov=True)
        result = forecast_baseline_metrics(ga4_df, 12, seasonality={})
        assert result["aov"].nunique() > 1, "AOV should vary when historical trend exists"

    def test_all_traffic_values_non_negative(self):
        ga4_df = _make_ga4_df()
        result = forecast_baseline_metrics(ga4_df, 12)
        assert (result["traffic"] >= 0).all()
        assert (result["revenue"] >= 0).all()

    def test_dates_advance_monthly(self):
        ga4_df = _make_ga4_df()
        result = forecast_baseline_metrics(ga4_df, 6)
        dates = pd.to_datetime(result["date"])
        for i in range(1, len(dates)):
            delta = (dates.iloc[i].year - dates.iloc[i - 1].year) * 12 + (
                dates.iloc[i].month - dates.iloc[i - 1].month
            )
            assert delta == 1, f"Months should advance by 1, got {delta} at row {i}"


class TestIntentWeightedCvrPerMonth:
    def _make_kw_df(self, intent: str = "transactional", n: int = 10):
        return pd.DataFrame({
            "keyword": [f"kw{i}" for i in range(n)],
            "intent": [intent] * n,
            "volume": [100] * n,
        })

    def test_returns_same_length_as_input(self):
        kw_df = self._make_kw_df()
        base = [2.0, 2.1, 2.2, 2.3]
        result = compute_intent_weighted_cvr_per_month(kw_df, base)
        assert len(result) == 4

    def test_transactional_intent_lifts_cvr(self):
        kw_df = self._make_kw_df(intent="transactional")
        base = [2.0, 2.0]
        result = compute_intent_weighted_cvr_per_month(kw_df, base)
        # Transactional multiplier = 2.0x → intent-weighted CVR > base
        assert all(r > 2.0 for r in result)

    def test_informational_intent_lowers_cvr(self):
        kw_df = self._make_kw_df(intent="informational")
        base = [2.0, 2.0]
        result = compute_intent_weighted_cvr_per_month(kw_df, base)
        # Informational multiplier = 0.3x → intent-weighted CVR < base
        assert all(r < 2.0 for r in result)

    def test_no_intent_column_returns_base_unchanged(self):
        kw_df = pd.DataFrame({"keyword": ["a", "b"], "volume": [100, 100]})
        base = [2.5, 3.0]
        result = compute_intent_weighted_cvr_per_month(kw_df, base)
        assert result == pytest.approx(base)

    def test_empty_series_returns_empty(self):
        kw_df = self._make_kw_df()
        result = compute_intent_weighted_cvr_per_month(kw_df, [])
        assert result == []

    def test_single_month(self):
        kw_df = self._make_kw_df(intent="commercial")
        result = compute_intent_weighted_cvr_per_month(kw_df, [2.0])
        assert len(result) == 1
        assert result[0] > 0


class TestCombinedRevenueDynamic:
    """Integration: revenue varies by month when CVR/AOV trend is present."""

    def _make_ga4_with_revenue_trend(self, n: int = 24):
        dates = pd.date_range("2023-01-01", periods=n, freq="MS")
        traffic = pd.Series([8_000 + i * 100 for i in range(n)])
        cr = pd.Series([1.5 + i * 0.04 for i in range(n)])
        aov = pd.Series([90.0 + i * 0.5 for i in range(n)])
        return pd.DataFrame({"date": dates, "traffic": traffic, "cr": cr, "aov": aov})

    def test_revenue_not_flat_across_12_months(self):
        ga4_df = self._make_ga4_with_revenue_trend()
        result = forecast_baseline_metrics(ga4_df, 12, seasonality={})
        # Revenue should vary due to trending CVR × AOV
        assert result["revenue"].nunique() > 1

    def test_cvr_higher_in_late_months_when_trend_is_positive(self):
        ga4_df = self._make_ga4_with_revenue_trend()
        result = forecast_baseline_metrics(ga4_df, 12, seasonality={})
        # Positive trend: month 12 CVR > month 1 CVR
        assert result["cvr"].iloc[-1] > result["cvr"].iloc[0]

    def test_november_revenue_higher_due_to_black_friday_cr_mod(self):
        # Black Friday month (November, cr_mod=0.15) should lift transactions
        ga4_df = _make_ga4_df(n_months=24, with_cr=False, with_aov=False)
        result = forecast_baseline_metrics(
            ga4_df, 12, fallback_cvr=2.0, fallback_aov=100.0
        )
        nov = result[pd.to_datetime(result["date"]).dt.month == 11]
        oct_ = result[pd.to_datetime(result["date"]).dt.month == 10]
        if not nov.empty and not oct_.empty:
            # November CVR (2.0 × 1.15 = 2.30) > October CVR (2.0 × 1.03 ≈ 2.06)
            assert nov.iloc[0]["cvr"] > oct_.iloc[0]["cvr"]

    def test_output_length_matches_months_param(self):
        ga4_df = self._make_ga4_with_revenue_trend()
        for m in (6, 12, 24):
            result = forecast_baseline_metrics(ga4_df, m, seasonality={})
            assert len(result) == m, f"Expected {m} rows, got {len(result)}"

    def test_per_month_cvr_series_length_for_intent_weighting(self):
        from engine.revenue_engine import compute_intent_weighted_cvr_per_month
        ga4_df = self._make_ga4_with_revenue_trend()
        result = forecast_baseline_metrics(ga4_df, 12, seasonality={})
        kw_df = pd.DataFrame({
            "keyword": ["buy shoes"],
            "intent": ["transactional"],
            "volume": [500],
        })
        per_month = compute_intent_weighted_cvr_per_month(kw_df, result["cvr"].tolist())
        assert len(per_month) == 12
        assert all(v > 0 for v in per_month)
