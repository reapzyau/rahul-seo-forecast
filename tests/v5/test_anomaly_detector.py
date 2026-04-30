"""Tests for engine/v5/anomaly_detector.py"""

import pandas as pd
import pytest

from engine.v5.anomaly_detector import apply_overrides, detect_baseline_anomalies


def _build_lookup(forecast_dates, ga4_df):
    """Build a baseline_lookup from a list of forecast dates and a GA4 DataFrame.
    Mirrors how the production code constructs the YoY lookup."""
    lookup = {}
    indexed = ga4_df.set_index("date")
    for fd in forecast_dates:
        prior = pd.Timestamp(year=fd.year - 1, month=fd.month, day=1)
        if prior in indexed.index:
            lookup[fd] = {
                "traffic": int(indexed.loc[prior, "traffic"]),
                "source": f"GA4 {prior.strftime('%b-%y')} actual",
            }
    return lookup


def test_yoy_dip_flagged():
    """T-1 month is -50% vs T-2 same month → flagged as yoy_dip."""
    dates_24 = pd.date_range("2024-01-01", periods=12, freq="MS")
    dates_25 = pd.date_range("2025-01-01", periods=12, freq="MS")
    traffic = [10000] * 12 + [10000] * 8 + [5000] + [10000] * 3
    ga4 = pd.DataFrame({
        "date": list(dates_24) + list(dates_25),
        "traffic": traffic,
    })
    forecast_dates = [pd.Timestamp("2026-09-01")]
    lookup = _build_lookup(forecast_dates, ga4)
    flags = detect_baseline_anomalies(ga4, lookup)
    assert len(flags) == 1
    assert flags[0]["flag_type"] == "yoy_dip"
    assert flags[0]["suggested_replacement"] == 10000


def test_yoy_spike_flagged():
    """T-1 month is +60% vs T-2 → flagged as yoy_spike."""
    dates_24 = pd.date_range("2024-01-01", periods=12, freq="MS")
    dates_25 = pd.date_range("2025-01-01", periods=12, freq="MS")
    traffic = [10000] * 12 + [10000] * 4 + [16000] + [10000] * 7
    ga4 = pd.DataFrame({
        "date": list(dates_24) + list(dates_25),
        "traffic": traffic,
    })
    forecast_dates = [pd.Timestamp("2026-05-01")]
    lookup = _build_lookup(forecast_dates, ga4)
    flags = detect_baseline_anomalies(ga4, lookup)
    assert len(flags) == 1
    assert flags[0]["flag_type"] == "yoy_spike"


def test_startup_period_guard_suppresses_false_flag():
    """If T-2 itself looks like startup (much lower than its neighbors),
    don't flag T-1 against it as a 'spike'."""
    dates_24 = pd.date_range("2024-01-01", periods=12, freq="MS")
    dates_25 = pd.date_range("2025-01-01", periods=12, freq="MS")
    traffic_24 = [10000] * 3 + [1000] + [10000] * 8
    traffic_25 = [10000] * 12
    ga4 = pd.DataFrame({
        "date": list(dates_24) + list(dates_25),
        "traffic": traffic_24 + traffic_25,
    })
    forecast_dates = [pd.Timestamp("2026-04-01")]
    lookup = _build_lookup(forecast_dates, ga4)
    flags = detect_baseline_anomalies(ga4, lookup)
    yoy_flags = [f for f in flags if f["comparison_basis"] == "yoy"]
    assert len(yoy_flags) == 0, f"startup guard should have prevented this: {flags}"


def test_surrounding_window_fallback():
    """If T-2 same month not in data, use surrounding-window check."""
    dates_25 = pd.date_range("2025-01-01", periods=12, freq="MS")
    # Sep 2025 spikes; surrounding months have natural variation so std > 0
    traffic = [9000, 10000, 11000, 9500, 10500, 9800, 10200, 9900, 25000, 10100, 9700, 10300]
    ga4 = pd.DataFrame({"date": list(dates_25), "traffic": traffic})
    forecast_dates = [pd.Timestamp("2026-09-01")]
    lookup = _build_lookup(forecast_dates, ga4)
    flags = detect_baseline_anomalies(ga4, lookup)
    assert len(flags) == 1
    assert flags[0]["comparison_basis"] == "surrounding"


def test_apply_overrides_replaces_traffic():
    lookup = {
        pd.Timestamp("2026-09-01"): {"traffic": 5000, "source": "GA4 Sep-25 actual"},
        pd.Timestamp("2026-10-01"): {"traffic": 10000, "source": "GA4 Oct-25 actual"},
    }
    overrides = {pd.Timestamp("2026-09-01"): 12000}
    corrected = apply_overrides(lookup, overrides)
    assert corrected[pd.Timestamp("2026-09-01")]["traffic"] == 12000
    assert "manually overridden" in corrected[pd.Timestamp("2026-09-01")]["source"] or \
           "overridden" in corrected[pd.Timestamp("2026-09-01")]["source"]
    assert corrected[pd.Timestamp("2026-10-01")]["traffic"] == 10000


def test_clean_baseline_produces_no_flags():
    """Steady traffic with no anomalies → no flags."""
    dates_24 = pd.date_range("2024-01-01", periods=12, freq="MS")
    dates_25 = pd.date_range("2025-01-01", periods=12, freq="MS")
    traffic = [10000] * 24
    ga4 = pd.DataFrame({
        "date": list(dates_24) + list(dates_25),
        "traffic": traffic,
    })
    forecast_dates = list(pd.date_range("2026-01-01", periods=12, freq="MS"))
    lookup = _build_lookup(forecast_dates, ga4)
    flags = detect_baseline_anomalies(ga4, lookup)
    assert flags == [], f"expected no flags on steady traffic, got {flags}"
