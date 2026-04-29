"""Tests for engine/v5/ga4_extractor.py"""

import pandas as pd
import pytest

from engine.v5.ga4_extractor import (
    ORGANIC_BROAD_CHANNELS,
    ORGANIC_CHANNELS,
    _fix_fy_dates,
    extract_organic_metrics,
    summarize_for_methodology,
)


def _make_synthetic_ga4(tmp_path, with_channel=True, with_fy_bug=False):
    """Build a synthetic GA4-shaped XLSX with channel breakdown."""
    dates = pd.date_range("2025-04-01", periods=12, freq="MS")
    if with_fy_bug:
        dates = [pd.Timestamp(year=2026, month=d.month, day=25) for d in dates]

    if with_channel:
        sessions = pd.concat([
            pd.DataFrame({
                "Year month": dates,
                "Session default channel group": "Organic Search",
                "Sessions": [1000] * 12,
            }),
            pd.DataFrame({
                "Year month": dates,
                "Session default channel group": "Direct",
                "Sessions": [500] * 12,
            }),
        ], ignore_index=True)
        transactions = pd.concat([
            pd.DataFrame({
                "Year month": dates,
                "Session default channel group": "Organic Search",
                "Transactions": [10] * 12,
            }),
            pd.DataFrame({
                "Year month": dates,
                "Session default channel group": "Direct",
                "Transactions": [20] * 12,
            }),
        ], ignore_index=True)
        revenue = pd.concat([
            pd.DataFrame({
                "Year month": dates,
                "Session default channel group": "Organic Search",
                "Total revenue": [3000] * 12,
            }),
            pd.DataFrame({
                "Year month": dates,
                "Session default channel group": "Direct",
                "Total revenue": [4000] * 12,
            }),
        ], ignore_index=True)
    else:
        sessions = pd.DataFrame({
            "Year month": dates,
            "Sessions": [1500] * 12,
        })
        transactions = pd.DataFrame({
            "Year month": dates,
            "Transactions": [30] * 12,
        })
        revenue = pd.DataFrame({
            "Year month": dates,
            "Total revenue": [7000] * 12,
        })

    path = tmp_path / "ga4_test.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        sessions.to_excel(writer, sheet_name="Sessions", index=False)
        transactions.to_excel(writer, sheet_name="Transactions", index=False)
        revenue.to_excel(writer, sheet_name="Revenue", index=False)
    return str(path)


def test_extract_organic_metrics_with_channel_breakdown(tmp_path):
    path = _make_synthetic_ga4(tmp_path, with_channel=True)
    metrics = extract_organic_metrics(path)
    # Organic: 1000 ses/mo × 12, 10 txns/mo × 12 → CR = 1%
    assert metrics.get("cr_organic") is not None
    assert abs(metrics["cr_organic"] - 0.01) < 0.001
    # AOV organic: $3000 / 10 = $300
    assert abs(metrics["aov_organic"] - 300.0) < 1.0
    # Blended: 1500 ses/mo, 30 txns/mo → CR = 2%
    assert abs(metrics["cr_blended"] - 0.02) < 0.001
    # cr_ratio = 0.01/0.02 = 0.5 < 1
    assert metrics["cr_ratio"] < 1.0


def test_extract_organic_metrics_handles_missing_channel(tmp_path):
    path = _make_synthetic_ga4(tmp_path, with_channel=False)
    metrics = extract_organic_metrics(path)
    # Without "Session default channel group", organic filter finds nothing
    assert metrics.get("warnings"), "expected warnings about missing channel"


def test_fy_day_bug_detection_and_correction():
    df = pd.DataFrame({
        "Year month": [pd.Timestamp("2026-04-25"), pd.Timestamp("2026-05-25")]
    })
    fixed = _fix_fy_dates(df, "Year month")
    # All dates should be normalised to month-starts
    assert all(d.day == 1 for d in fixed["Year month"])


def test_summarize_for_methodology_handles_failure():
    msg = summarize_for_methodology({"warnings": ["test failure"]})
    assert "failed" in msg.lower()


def test_summarize_for_methodology_returns_human_readable(tmp_path):
    path = _make_synthetic_ga4(tmp_path, with_channel=True)
    metrics = extract_organic_metrics(path)
    msg = summarize_for_methodology(metrics)
    assert "Organic Search CR" in msg
    assert "AOV" in msg


def test_organic_broad_channels_includes_shopping_video():
    assert "Organic Shopping" in ORGANIC_BROAD_CHANNELS
    assert "Organic Video" in ORGANIC_BROAD_CHANNELS
    assert ORGANIC_CHANNELS == {"Organic Search"}


def test_cr_by_month_has_required_columns(tmp_path):
    path = _make_synthetic_ga4(tmp_path, with_channel=True)
    metrics = extract_organic_metrics(path)
    assert "cr_by_month" in metrics
    cbm = metrics["cr_by_month"]
    assert "cr_organic" in cbm.columns
    assert "cr_blended" in cbm.columns
    assert len(cbm) == 12
