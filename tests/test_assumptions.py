"""Tests for the centralised assumptions store (engine/assumptions.py)."""
import io

import pandas as pd
import pytest

from engine.assumptions import (
    ASSUMPTIONS,
    Assumption,
    assumptions_summary,
    clear_override,
    get_assumption,
    get_provenance,
    initialise_assumptions,
    override_assumption,
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
