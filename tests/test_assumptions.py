"""Tests for the centralised assumptions store (engine/assumptions.py)."""
import io

import pandas as pd
import pytest

from engine.assumptions import (
    ASSUMPTIONS,
    Assumption,
    _detect_from_roadmap_bundle,
    assumptions_summary,
    clear_override,
    get_assumption,
    get_provenance,
    initialise_assumptions,
    override_assumption,
    recompute_rollups,
    run_detection,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def fresh_store() -> dict:
    store: dict = {}
    initialise_assumptions(store)
    return store


# ── TestInitialisation ────────────────────────────────────────────────────────


class TestInitialisation:
    def test_all_keys_present_after_init(self):
        store = fresh_store()
        for key in ASSUMPTIONS:
            assert key in store

    def test_default_values_match_registry(self):
        store = fresh_store()
        for key, assumption in ASSUMPTIONS.items():
            assert get_assumption(store, key) == assumption.default

    def test_all_provenance_defaulted(self):
        store = fresh_store()
        for key in ASSUMPTIONS:
            assert get_provenance(store, key)["provenance"] == "defaulted"

    def test_noop_on_second_call(self):
        store = fresh_store()
        override_assumption(store, "aov", 999.0)
        initialise_assumptions(store)  # should NOT reset the override
        assert get_assumption(store, "aov") == 999.0

    def test_force_resets_all(self):
        store = fresh_store()
        override_assumption(store, "aov", 999.0)
        initialise_assumptions(store, force=True)
        assert get_assumption(store, "aov") == ASSUMPTIONS["aov"].default

    def test_initialised_flag_set(self):
        store: dict = {}
        initialise_assumptions(store)
        assert store["_initialised"] is True

    def test_assumption_dataclass_fields(self):
        a = ASSUMPTIONS["blended_cr_pct"]
        assert isinstance(a, Assumption)
        assert a.unit == "%"
        assert a.min_val == 0.0
        assert a.max_val == 100.0

    def test_unknown_key_raises(self):
        store = fresh_store()
        with pytest.raises(KeyError):
            get_assumption(store, "nonexistent_key")


# ── TestDetection ─────────────────────────────────────────────────────────────


class TestDetection:
    def _ga4_df(self, traffic=10000, transactions=250, aov=150.0) -> pd.DataFrame:
        return pd.DataFrame({
            "date": ["2025-01-01", "2025-02-01"],
            "traffic": [traffic // 2, traffic // 2],
            "transactions": [transactions // 2, transactions // 2],
            "aov": [aov, aov],
        })

    def test_cr_detected_from_ga4(self):
        store = fresh_store()
        ga4 = self._ga4_df(traffic=10000, transactions=250)
        run_detection(store, ga4_df=ga4)
        # 250 / 10000 * 100 = 2.5
        assert get_assumption(store, "blended_cr_pct") == pytest.approx(2.5, rel=0.01)

    def test_cr_provenance_becomes_detected(self):
        store = fresh_store()
        run_detection(store, ga4_df=self._ga4_df())
        assert get_provenance(store, "blended_cr_pct")["provenance"] == "detected"

    def test_aov_detected_from_ga4(self):
        store = fresh_store()
        run_detection(store, ga4_df=self._ga4_df(aov=200.0))
        assert get_assumption(store, "aov") == pytest.approx(200.0, rel=0.01)

    def test_aov_provenance_becomes_detected(self):
        store = fresh_store()
        run_detection(store, ga4_df=self._ga4_df())
        assert get_provenance(store, "aov")["provenance"] == "detected"

    def test_returns_list_of_detected_keys(self):
        store = fresh_store()
        keys = run_detection(store, ga4_df=self._ga4_df())
        assert "blended_cr_pct" in keys
        assert "aov" in keys

    def test_zero_traffic_skips_cr_detection(self):
        store = fresh_store()
        ga4 = pd.DataFrame({"traffic": [0], "transactions": [0], "aov": [100.0]})
        run_detection(store, ga4_df=ga4)
        assert get_provenance(store, "blended_cr_pct")["provenance"] == "defaulted"

    def test_roadmap_effort_detected(self):
        store = fresh_store()
        run_detection(store, roadmap_data={"effort_level": "aggressive"})
        assert get_assumption(store, "effort_level") == "aggressive"
        assert get_provenance(store, "effort_level")["provenance"] == "detected"

    def test_roadmap_cadence_detected(self):
        store = fresh_store()
        run_detection(store, roadmap_data={"content_cadence": 8})
        assert get_assumption(store, "content_cadence") == 8

    def test_roadmap_maintenance_detected(self):
        store = fresh_store()
        run_detection(store, roadmap_data={"maintenance_coverage": 0.7})
        assert get_assumption(store, "maintenance_coverage") == pytest.approx(0.7)

    def test_detection_does_not_overwrite_override(self):
        store = fresh_store()
        override_assumption(store, "aov", 999.0)
        run_detection(store, ga4_df=self._ga4_df(aov=200.0))
        # Override must survive detection
        assert get_assumption(store, "aov") == 999.0
        assert get_provenance(store, "aov")["provenance"] == "overridden"

    def test_detection_overwrites_previous_detected(self):
        store = fresh_store()
        run_detection(store, ga4_df=self._ga4_df(aov=100.0))
        run_detection(store, ga4_df=self._ga4_df(aov=200.0))
        assert get_assumption(store, "aov") == pytest.approx(200.0, rel=0.01)

    def test_ga4_without_aov_column(self):
        store = fresh_store()
        ga4 = pd.DataFrame({"traffic": [5000], "transactions": [100]})
        run_detection(store, ga4_df=ga4)
        # AOV should stay at default since no aov column
        assert get_provenance(store, "aov")["provenance"] == "defaulted"


# ── TestOverride ──────────────────────────────────────────────────────────────


class TestOverride:
    def test_override_changes_value(self):
        store = fresh_store()
        override_assumption(store, "blended_cr_pct", 5.0)
        assert get_assumption(store, "blended_cr_pct") == 5.0

    def test_override_sets_provenance(self):
        store = fresh_store()
        override_assumption(store, "blended_cr_pct", 5.0)
        assert get_provenance(store, "blended_cr_pct")["provenance"] == "overridden"

    def test_override_custom_source(self):
        store = fresh_store()
        override_assumption(store, "currency", "AUD", source="client config")
        assert get_provenance(store, "currency")["source"] == "client config"

    def test_clear_override_restores_default(self):
        store = fresh_store()
        override_assumption(store, "content_cadence", 12)
        clear_override(store, "content_cadence")
        assert get_assumption(store, "content_cadence") == ASSUMPTIONS["content_cadence"].default
        assert get_provenance(store, "content_cadence")["provenance"] == "defaulted"

    def test_clear_override_noop_when_not_overridden(self):
        store = fresh_store()
        clear_override(store, "effort_level")  # Should not raise
        assert get_provenance(store, "effort_level")["provenance"] == "defaulted"

    def test_clear_override_noop_when_detected(self):
        store = fresh_store()
        run_detection(store, roadmap_data={"effort_level": "light"})
        clear_override(store, "effort_level")
        # Detected value must be preserved (clear_override only acts on overridden)
        assert get_provenance(store, "effort_level")["provenance"] == "detected"

    def test_unknown_key_raises_on_override(self):
        store = fresh_store()
        with pytest.raises(KeyError):
            override_assumption(store, "does_not_exist", 42)

    def test_unknown_key_raises_on_clear(self):
        store = fresh_store()
        with pytest.raises(KeyError):
            clear_override(store, "does_not_exist")

    def test_multiple_overrides_independent(self):
        store = fresh_store()
        override_assumption(store, "aov", 200.0)
        override_assumption(store, "blended_cr_pct", 3.0)
        assert get_assumption(store, "aov") == 200.0
        assert get_assumption(store, "blended_cr_pct") == 3.0

    def test_override_then_re_override(self):
        store = fresh_store()
        override_assumption(store, "aov", 200.0)
        override_assumption(store, "aov", 300.0)
        assert get_assumption(store, "aov") == 300.0


# ── TestSummary ───────────────────────────────────────────────────────────────


class TestSummary:
    def test_summary_length_matches_registry(self):
        store = fresh_store()
        summary = assumptions_summary(store)
        assert len(summary) == len(ASSUMPTIONS)

    def test_summary_contains_all_keys(self):
        store = fresh_store()
        summary = assumptions_summary(store)
        summary_keys = {row["key"] for row in summary}
        assert summary_keys == set(ASSUMPTIONS.keys())

    def test_summary_includes_provenance(self):
        store = fresh_store()
        summary = assumptions_summary(store)
        for row in summary:
            assert "provenance" in row
            assert row["provenance"] in ("defaulted", "detected", "overridden")

    def test_summary_reflects_override(self):
        store = fresh_store()
        override_assumption(store, "aov", 500.0)
        summary = assumptions_summary(store)
        aov_row = next(r for r in summary if r["key"] == "aov")
        assert aov_row["value"] == 500.0
        assert aov_row["provenance"] == "overridden"

    def test_get_provenance_includes_label(self):
        store = fresh_store()
        prov = get_provenance(store, "blended_cr_pct")
        assert prov["label"] == "Blended Conversion Rate"

    def test_get_provenance_includes_unit(self):
        store = fresh_store()
        prov = get_provenance(store, "blended_cr_pct")
        assert prov["unit"] == "%"

    def test_summary_order_matches_registry(self):
        store = fresh_store()
        summary = assumptions_summary(store)
        assert [r["key"] for r in summary] == list(ASSUMPTIONS.keys())

    def test_uninitialised_store_returns_defaults(self):
        store: dict = {}
        # get_assumption on uninitialised store falls back to ASSUMPTIONS default
        assert get_assumption(store, "blended_cr_pct") == ASSUMPTIONS["blended_cr_pct"].default


# ── TestRoadmapBundleDetection ────────────────────────────────────────────────


_SAMPLE_BUNDLE: dict = {
    "per_focus": {
        "content": {"effort_level": "aggressive", "monthly_hours": 30.0, "cadence": 3, "task_count": 2, "tasks": []},
        "technical": {"effort_level": "light", "monthly_hours": 4.0, "cadence": 0, "task_count": 1, "tasks": []},
        "on_page": {"effort_level": "moderate", "monthly_hours": 10.0, "cadence": 0, "task_count": 1, "tasks": []},
        "off_page": {"effort_level": "light", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "local": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "analytics": {"effort_level": "light", "monthly_hours": 3.0, "cadence": 0, "task_count": 1, "tasks": []},
        "strategy": {"effort_level": "light", "monthly_hours": 2.0, "cadence": 0, "task_count": 0, "tasks": []},
    },
    "timeline": {"months_covered": 12, "phasing_notes": "", "has_launch_dates": False},
    "global_rollup": {
        "total_monthly_hours": 49.0,
        "effort_level": "moderate",
        "maintenance_coverage": 0.7,
        "content_cadence": 3,
        "positional_effort_level": "moderate",
    },
    "recommendations": [],
    "gaps": [],
}


def _fresh():
    s: dict = {}
    initialise_assumptions(s)
    return s


class TestRoadmapBundleDetection:
    def test_detects_content_effort(self):
        store = _fresh()
        _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        assert get_assumption(store, "content_effort_level") == "aggressive"

    def test_detects_monthly_hours(self):
        store = _fresh()
        _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        assert get_assumption(store, "content_monthly_hours") == pytest.approx(30.0)

    def test_detects_timeline(self):
        store = _fresh()
        _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        assert get_assumption(store, "timeline_months_covered") == 12

    def test_all_seven_focus_effort_detected(self):
        store = _fresh()
        detected = _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        effort_keys = [k for k in detected if k.endswith("_effort_level")]
        assert len(effort_keys) == 7

    def test_all_seven_focus_hours_detected(self):
        store = _fresh()
        detected = _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        hour_keys = [k for k in detected if k.endswith("_monthly_hours")]
        assert len(hour_keys) == 7

    def test_provenance_is_detected(self):
        store = _fresh()
        _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        prov = get_provenance(store, "content_effort_level")
        assert prov["provenance"] == "detected"

    def test_run_detection_with_bundle_populates_keys(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        assert get_assumption(store, "on_page_effort_level") == "moderate"

    def test_bundle_does_not_overwrite_override(self):
        store = _fresh()
        override_assumption(store, "content_effort_level", "light")
        _detect_from_roadmap_bundle(store, _SAMPLE_BUNDLE)
        assert get_assumption(store, "content_effort_level") == "light"


class TestRecomputeRollups:
    def test_effort_level_is_max_of_three_foci(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # content=aggressive, on_page=moderate, off_page=light → max = aggressive
        assert get_assumption(store, "effort_level") == "aggressive"

    def test_positional_effort_is_max_of_on_page_off_page(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # on_page=moderate, off_page=light → max = moderate
        assert get_assumption(store, "positional_effort_level") == "moderate"

    def test_content_cadence_computed_from_hours(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # 30 hours / 10 = 3
        assert get_assumption(store, "content_cadence") == 3

    def test_maintenance_coverage_from_on_page_technical(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # (10 + 4) / 20 = 0.7
        assert get_assumption(store, "maintenance_coverage") == pytest.approx(0.7)

    def test_total_monthly_hours_is_sum(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # 30 + 4 + 10 + 0 + 0 + 3 + 2 = 49
        assert get_assumption(store, "total_monthly_hours") == pytest.approx(49.0)

    def test_rollups_not_run_when_all_defaulted(self):
        """recompute_rollups must no-op when no per-focus keys have been detected."""
        store = _fresh()
        recompute_rollups(store)
        # effort_level should remain "moderate" (its default), not be re-detected
        assert get_provenance(store, "effort_level")["provenance"] == "defaulted"

    def test_override_survives_recompute(self):
        store = _fresh()
        override_assumption(store, "effort_level", "light")
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # Override must not be overwritten by recompute
        assert get_assumption(store, "effort_level") == "light"

    def test_legacy_roadmap_format_still_works(self):
        store = _fresh()
        legacy = {"effort_level": "aggressive", "content_cadence": 6, "maintenance_coverage": 0.5}
        run_detection(store, roadmap_data=legacy)
        assert get_assumption(store, "effort_level") == "aggressive"
        assert get_assumption(store, "content_cadence") == 6


# ── Prompt 6 spec-named tests ─────────────────────────────────────────────────

_PER_FOCUS_EFFORT_KEYS = [
    "content_effort_level", "technical_effort_level", "on_page_effort_level",
    "off_page_effort_level", "local_effort_level", "analytics_effort_level",
    "strategy_effort_level",
]
_PER_FOCUS_HOURS_KEYS = [
    "content_monthly_hours", "technical_monthly_hours", "on_page_monthly_hours",
    "off_page_monthly_hours", "local_monthly_hours", "analytics_monthly_hours",
    "strategy_monthly_hours",
]


class TestPerFocusAndRollupSpec:
    def test_new_per_focus_keys_registered(self):
        for key in _PER_FOCUS_EFFORT_KEYS + _PER_FOCUS_HOURS_KEYS:
            assert key in ASSUMPTIONS, f"{key} not in ASSUMPTIONS"

    def test_defaults_for_new_keys(self):
        store = fresh_store()
        for key in _PER_FOCUS_EFFORT_KEYS:
            assert get_assumption(store, key) == "moderate"
        for key in _PER_FOCUS_HOURS_KEYS:
            assert get_assumption(store, key) == pytest.approx(0.0)

    def test_recompute_rollups_effort_level_is_max(self):
        store = _fresh()
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # content=aggressive, on_page=moderate, off_page=light → max = aggressive
        assert get_assumption(store, "effort_level") == "aggressive"

    def test_recompute_rollups_maintenance_clamped(self):
        store = _fresh()
        # Set very high hours to verify clamping at 1.0
        bundle = {
            "per_focus": {
                "on_page": {"effort_level": "aggressive", "monthly_hours": 100.0},
                "technical": {"effort_level": "moderate", "monthly_hours": 100.0},
            }
        }
        run_detection(store, roadmap_data=bundle)
        assert get_assumption(store, "maintenance_coverage") == pytest.approx(1.0)

    def test_recompute_rollups_cadence_min_1(self):
        store = _fresh()
        bundle = {"per_focus": {"content": {"effort_level": "light", "monthly_hours": 0.0}}}
        run_detection(store, roadmap_data=bundle)
        assert get_assumption(store, "content_cadence") >= 1

    def test_recompute_rollups_preserves_user_overrides_on_per_focus_keys(self):
        store = _fresh()
        override_assumption(store, "content_effort_level", "light")
        run_detection(store, roadmap_data=_SAMPLE_BUNDLE)
        # Per-focus override must survive roadmap detection
        assert get_assumption(store, "content_effort_level") == "light"

    def test_brand_terms_key_accepts_list_value(self):
        store = fresh_store()
        terms = ["nike", "adidas", "puma"]
        override_assumption(store, "brand_terms", terms)
        assert get_assumption(store, "brand_terms") == terms


def test_recompute_rollups_defined_exactly_once():
    """Guard against the duplicate-definition bug resurfacing."""
    import inspect

    import engine.assumptions as mod
    source = inspect.getsource(mod)
    assert source.count("\ndef recompute_rollups(") == 1, (
        "recompute_rollups is defined more than once in engine/assumptions.py"
    )
