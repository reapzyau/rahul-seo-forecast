"""Tests for engine/scenario_engine.py."""
import pandas as pd
import pytest

from engine.scenario_engine import (
    build_scenario_presets,
    run_three_scenarios,
    summarise_scenarios,
)
from tests.fixtures import make_ga4_df, make_semrush_kw_df


class TestBuildPresets:
    def test_no_roadmap_returns_generic_presets(self):
        presets = build_scenario_presets()
        assert set(presets.keys()) == {"Conservative", "Moderate", "Aggressive"}
        for p in presets.values():
            assert p["source"] == "generic-preset"

    def test_moderate_generic_uses_moderate_effort(self):
        presets = build_scenario_presets()
        assert presets["Moderate"]["effort_level"] == "moderate"
        assert presets["Moderate"]["content_cadence"] == 4
        assert presets["Moderate"]["total_monthly_hours"] == 25

    def test_conservative_has_least_hours(self):
        presets = build_scenario_presets()
        hours = [presets[s]["total_monthly_hours"] for s in ("Conservative", "Moderate", "Aggressive")]
        assert hours[0] < hours[1] < hours[2]

    def test_roadmap_drives_moderate(self):
        bundle = {
            "global_rollup": {
                "effort_level": "aggressive",
                "content_cadence": 6,
                "maintenance_coverage": 0.75,
                "total_monthly_hours": 35.0,
            },
            "client_metadata": {"retainer_aud_monthly": 7500.0},
        }
        presets = build_scenario_presets(roadmap_bundle=bundle)
        assert presets["Moderate"]["source"] == "roadmap-detected"
        assert presets["Moderate"]["total_monthly_hours"] == 35.0
        assert presets["Moderate"]["retainer_aud_monthly"] == 7500.0

    def test_roadmap_conservative_is_60_pct_of_moderate(self):
        bundle = {
            "global_rollup": {
                "effort_level": "moderate",
                "content_cadence": 4,
                "maintenance_coverage": 0.6,
                "total_monthly_hours": 20.0,
            },
            "client_metadata": {"retainer_aud_monthly": 5000.0},
        }
        presets = build_scenario_presets(roadmap_bundle=bundle)
        assert presets["Conservative"]["total_monthly_hours"] == pytest.approx(12.0)
        assert presets["Conservative"]["retainer_aud_monthly"] == pytest.approx(3000.0)

    def test_roadmap_aggressive_is_160_pct_of_moderate(self):
        bundle = {
            "global_rollup": {
                "effort_level": "moderate",
                "content_cadence": 4,
                "maintenance_coverage": 0.6,
                "total_monthly_hours": 20.0,
            },
            "client_metadata": {"retainer_aud_monthly": 5000.0},
        }
        presets = build_scenario_presets(roadmap_bundle=bundle)
        assert presets["Aggressive"]["total_monthly_hours"] == pytest.approx(32.0)
        assert presets["Aggressive"]["retainer_aud_monthly"] == pytest.approx(8000.0)

    def test_position_range_always_5_to_20_when_roadmap(self):
        bundle = {
            "global_rollup": {
                "effort_level": "moderate",
                "content_cadence": 4,
                "maintenance_coverage": 0.6,
                "total_monthly_hours": 20.0,
            },
            "client_metadata": {},
        }
        presets = build_scenario_presets(roadmap_bundle=bundle)
        for s in presets:
            assert presets[s]["position_range"] == (5, 20)


class TestRunThreeScenarios:
    @pytest.fixture
    def inputs(self):
        ga4_df = make_ga4_df(months=18, starting_traffic=15_000, trend=200)
        kw_existing = make_semrush_kw_df(
            n=50,
            positions=[5, 8, 12, 15, 18] * 10,
            kds=[30] * 50,
        )
        kw_existing["is_branded"] = False
        return ga4_df, kw_existing, kw_existing.copy()

    def test_returns_three_scenarios(self, inputs):
        ga4, kw_existing, kw_df = inputs
        presets = build_scenario_presets()
        results = run_three_scenarios(
            ga4_df=ga4, kw_df=kw_df, kw_existing=kw_existing,
            presets=presets, months=6, seed=42,
        )
        assert set(results.keys()) == {"Conservative", "Moderate", "Aggressive"}

    def test_aggressive_produces_larger_uplift_than_conservative(self, inputs):
        ga4, kw_existing, kw_df = inputs
        presets = build_scenario_presets()
        results = run_three_scenarios(
            ga4_df=ga4, kw_df=kw_df, kw_existing=kw_existing,
            presets=presets, months=12, seed=42,
        )
        cons_uplift = results["Conservative"]["combined_df"]["positional_uplift_p50"].sum()
        aggr_uplift = results["Aggressive"]["combined_df"]["positional_uplift_p50"].sum()
        assert aggr_uplift > cons_uplift

    def test_each_scenario_has_expected_keys(self, inputs):
        ga4, kw_existing, kw_df = inputs
        presets = build_scenario_presets()
        results = run_three_scenarios(
            ga4_df=ga4, kw_df=kw_df, kw_existing=kw_existing,
            presets=presets, months=6, seed=42,
        )
        for scenario in results.values():
            if "error" in scenario:
                continue
            assert "preset" in scenario
            assert "positional_monthly" in scenario
            assert "decay_df" in scenario
            assert "combined_df" in scenario

    def test_one_scenario_failure_does_not_break_others(self, inputs, monkeypatch):
        """If positional forecast crashes for one scenario, others still return."""
        from engine import scenario_engine

        original = scenario_engine.run_positional_forecast_mc
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:  # break Moderate specifically
                raise RuntimeError("simulated failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(scenario_engine, "run_positional_forecast_mc", flaky)

        ga4, kw_existing, kw_df = inputs
        presets = build_scenario_presets()
        results = run_three_scenarios(
            ga4_df=ga4, kw_df=kw_df, kw_existing=kw_existing,
            presets=presets, months=6, seed=42,
        )
        assert "error" in results["Moderate"]
        assert "error" not in results["Conservative"]
        assert "error" not in results["Aggressive"]


class TestSummarise:
    def test_returns_three_rows(self):
        ga4 = make_ga4_df(months=12, starting_traffic=10000)
        kw = make_semrush_kw_df(n=20, positions=[8] * 20)
        kw["is_branded"] = False
        presets = build_scenario_presets()
        results = run_three_scenarios(
            ga4_df=ga4, kw_df=kw, kw_existing=kw,
            presets=presets, months=6, seed=42,
        )
        summary = summarise_scenarios(results, months=6)
        assert len(summary) == 3
        assert set(summary["Scenario"]) == {"Conservative", "Moderate", "Aggressive"}

    def test_summary_columns_present(self):
        ga4 = make_ga4_df(months=12, starting_traffic=10000)
        kw = make_semrush_kw_df(n=20, positions=[8] * 20)
        kw["is_branded"] = False
        presets = build_scenario_presets()
        results = run_three_scenarios(
            ga4_df=ga4, kw_df=kw, kw_existing=kw,
            presets=presets, months=6, seed=42,
        )
        summary = summarise_scenarios(results, months=6)
        expected = {"Scenario", "Effort", "Cadence", "Maintenance",
                    "Monthly Hours", "Retainer"}
        assert expected.issubset(set(summary.columns))
