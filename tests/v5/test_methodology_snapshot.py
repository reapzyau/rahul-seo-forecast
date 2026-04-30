"""Tests for v5 extensions to engine/snapshot_engine.py"""

import json
import os
import tempfile

import pandas as pd
import pytest

from engine.snapshot_engine import (
    _serialise_flags,
    _serialise_overrides,
    build_methodology_snapshot,
    write_methodology_snapshot,
)


def _minimal_snapshot(**overrides) -> dict:
    kwargs = dict(
        client_name="Test Client",
        forecast_start="2026-05-01",
        forecast_end="2027-04-01",
        months=12,
        ga4_summary={"rows": 24, "date_range": "2024-01 – 2025-12", "latest_6mo_avg": 10000},
        baseline_mode="yoy_replay",
        baseline_mode_rationale="≥12 months available",
        seasonality_source="learned_blend",
        seasonality_rationale="Derived from GA4 history",
        position_filter=(21, 100),
        positional_kw_count=150,
        movement_stats_decision="auto — p75 confidence-weighted",
        brand_config={"substring_terms": ["acme"], "matched_count": 5, "total_kw_count": 500},
        new_content_source="cluster_from_semrush",
        aio_penalties={"informational": 0.0},
        blended_cr=2.5,
        weighted_aov=120.0,
        tier_outputs=[],
        seed=42,
    )
    kwargs.update(overrides)
    return build_methodology_snapshot(**kwargs)


def test_required_fields_present():
    snap = _minimal_snapshot()
    required_top_level = [
        "snapshot_version", "snapshot_type", "generated_at", "client_name",
        "forecast_horizon", "ga4_input", "baseline", "seasonality",
        "positional_pool", "movement_stats", "brand_classification",
        "new_content", "aio_penalties", "revenue_assumptions",
        "monte_carlo_seed", "tier_outputs", "v5_extensions",
    ]
    for key in required_top_level:
        assert key in snap, f"missing top-level key: {key!r}"

    v5 = snap["v5_extensions"]
    required_v5 = [
        "version", "fixes_applied", "da_derived", "da_rationale",
        "cr_organic", "cr_blended", "aov_organic", "aov_blended",
        "n_branded_keywords", "anomaly_flags", "anomaly_overrides",
        "movement_stats_decisions",
    ]
    for key in required_v5:
        assert key in v5, f"missing v5_extensions key: {key!r}"


def test_json_serializable():
    snap = _minimal_snapshot(
        da_derived=42.5,
        da_rationale="Derived from SEMrush authority score",
        cr_organic=0.031,
        cr_blended=0.025,
        aov_organic=135.0,
        aov_blended=110.0,
        n_branded_keywords=12,
        fixes_applied=["v5_movement_stats", "v5_anomaly_detector"],
        movement_stats_decisions={"top_3": "p75_gain=3.2", "top_10": "engine_default"},
    )
    serialised = json.dumps(snap)
    loaded = json.loads(serialised)
    assert loaded["v5_extensions"]["version"] == "5.0"
    assert loaded["v5_extensions"]["cr_organic"] == pytest.approx(0.031)
    assert loaded["v5_extensions"]["da_derived"] == pytest.approx(42.5)
    assert loaded["v5_extensions"]["fixes_applied"] == ["v5_movement_stats", "v5_anomaly_detector"]


def test_flags_serialize_dates():
    flags = [
        {
            "forecast_month": pd.Timestamp("2026-09-01"),
            "source_month": pd.Timestamp("2025-09-01"),
            "flag_type": "yoy_dip",
            "source_value": 5000,
            "suggested_replacement": 10000,
            "ratio": 0.5,
            "comparison_basis": "yoy",
        }
    ]
    overrides = {pd.Timestamp("2026-09-01"): 10000}

    serialised_flags = _serialise_flags(flags)
    serialised_overrides = _serialise_overrides(overrides)

    assert isinstance(serialised_flags[0]["forecast_month"], str)
    assert "2026-09-01" in serialised_flags[0]["forecast_month"]
    assert isinstance(list(serialised_overrides.keys())[0], str)
    assert "2026-09-01" in list(serialised_overrides.keys())[0]

    snap = _minimal_snapshot(anomaly_flags=flags, anomaly_overrides=overrides)
    json_str = json.dumps(snap)  # must not raise
    loaded = json.loads(json_str)
    assert len(loaded["v5_extensions"]["anomaly_flags"]) == 1
    assert loaded["v5_extensions"]["anomaly_flags"][0]["flag_type"] == "yoy_dip"
    assert loaded["v5_extensions"]["anomaly_overrides"] != {}


def test_file_written():
    snap = _minimal_snapshot(da_derived=35.0)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_methodology_snapshot(snap, client_name="ACME Corp", run_dir=tmpdir)
        assert os.path.exists(path)
        assert "acme_corp" in os.path.basename(path)
        assert "_methodology_" in os.path.basename(path)
        assert path.endswith(".json")
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded["client_name"] == "Test Client"
        assert loaded["v5_extensions"]["da_derived"] == pytest.approx(35.0)
