"""Tests for engine/roadmap_ai_engine.py.

All AI calls are mocked — no network or Bi Frost access required in CI.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from engine.roadmap_ai_engine import (
    ROADMAP_BUNDLE_SCHEMA,
    _cache_key,
    _df_to_markdown,
    _read_roadmap_file,
    estimate_extraction_tokens,
    extract_roadmap_with_ai,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_CANNED_BUNDLE: dict = {
    "schema_version": "1.0",
    "extraction_date": "2026-01-01T00:00:00+00:00",
    "source_summary": {
        "total_tasks_detected": 5,
        "focus_areas_detected": ["content", "technical", "on_page"],
        "timeline_months_covered": 12,
        "parsing_confidence": 0.9,
    },
    "per_focus": {
        "content": {"effort_level": "aggressive", "monthly_hours": 32.0, "cadence": 4, "task_count": 2, "tasks": []},
        "technical": {"effort_level": "light", "monthly_hours": 4.0, "cadence": 0, "task_count": 1, "tasks": []},
        "on_page": {"effort_level": "moderate", "monthly_hours": 12.0, "cadence": 0, "task_count": 1, "tasks": []},
        "off_page": {"effort_level": "light", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "local": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "analytics": {"effort_level": "light", "monthly_hours": 3.0, "cadence": 0, "task_count": 1, "tasks": []},
        "strategy": {"effort_level": "light", "monthly_hours": 2.0, "cadence": 0, "task_count": 0, "tasks": []},
    },
    "timeline": {"months_covered": 12, "phasing_notes": "", "has_launch_dates": False},
    "global_rollup": {
        "total_monthly_hours": 53.0,
        "effort_level": "moderate",
        "maintenance_coverage": 0.8,
        "content_cadence": 4,
        "positional_effort_level": "moderate",
    },
    "recommendations": [{"severity": "warning", "message": "No off-page tasks detected."}],
    "gaps": [{"focus_area": "Off-Page", "note": "No tasks found."}],
}


def _make_fake_client(bundle: dict = _CANNED_BUNDLE):
    """Fake Bi Frost client that returns a canned bundle as JSON text."""

    class _FakeCompletion:
        class _Choice:
            class _Message:
                content = json.dumps(bundle)
            message = _Message()
        choices = [_Choice()]

    class _FakeChat:
        class _Completions:
            def create(self, **kwargs):
                return _FakeCompletion()
        completions = _Completions()

    class _FakeClient:
        chat = _FakeChat()

    return _FakeClient()


def _make_csv_bytes(rows: list[dict] | None = None) -> bytes:
    if rows is None:
        rows = [
            {"Task": "Long-Form Article", "Focus": "Content", "Occurrence": "Monthly", "Hours": 10},
            {"Task": "Technical Audit", "Focus": "Technical", "Occurrence": "Quarterly", "Hours": 8},
        ]
    return pd.DataFrame(rows).to_csv(index=False).encode()


# ── TestDfToMarkdown ──────────────────────────────────────────────────────────


class TestDfToMarkdown:
    def test_short_df_not_truncated(self):
        df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
        md, truncated = _df_to_markdown(df, max_chars=10000)
        assert not truncated
        assert "| A |" in md
        assert "| 1 |" in md

    def test_long_df_is_truncated(self):
        df = pd.DataFrame({"col": ["x" * 200] * 50})
        md, truncated = _df_to_markdown(df, max_chars=500)
        assert truncated
        assert "truncated" in md

    def test_output_has_header_and_sep(self):
        df = pd.DataFrame({"Task": ["A"], "Hours": [10]})
        md, _ = _df_to_markdown(df)
        lines = md.split("\n")
        assert lines[0].startswith("| Task")
        assert "---" in lines[1]

    def test_empty_df_produces_header_only(self):
        df = pd.DataFrame({"A": pd.Series([], dtype=str)})
        md, truncated = _df_to_markdown(df)
        assert "| A |" in md
        assert not truncated


# ── TestReadRoadmapFile ───────────────────────────────────────────────────────


class TestReadRoadmapFile:
    def test_reads_csv_bytes(self):
        raw = _make_csv_bytes()
        df = _read_roadmap_file(raw, "csv")
        assert len(df) == 2
        assert "Task" in df.columns

    def test_empty_raises(self):
        raw = b"col1,col2\n"  # header but no rows → empty DataFrame
        with pytest.raises(ValueError, match="empty"):
            _read_roadmap_file(raw, "csv")

    def test_tsv_extension(self):
        raw = b"A\tB\n1\t2\n3\t4\n"
        df = _read_roadmap_file(raw, "tsv")
        assert list(df.columns) == ["A", "B"]
        assert len(df) == 2


# ── TestCacheKey ──────────────────────────────────────────────────────────────


class TestCacheKey:
    def test_same_inputs_same_key(self):
        b = b"some bytes"
        assert _cache_key(b, "correction", "model-x") == _cache_key(b, "correction", "model-x")

    def test_different_bytes_different_key(self):
        assert _cache_key(b"aaa", None, "m") != _cache_key(b"bbb", None, "m")

    def test_different_nl_different_key(self):
        b = b"bytes"
        assert _cache_key(b, "correction A", "m") != _cache_key(b, "correction B", "m")

    def test_none_nl_treated_as_empty(self):
        b = b"bytes"
        assert _cache_key(b, None, "m") == _cache_key(b, "", "m")

    def test_key_is_16_chars(self):
        assert len(_cache_key(b"x", None, "m")) == 16


# ── TestExtractionCaching ─────────────────────────────────────────────────────


class TestExtractionCaching:
    def test_cached_result_returned_without_ai_call(self):
        raw = _make_csv_bytes()
        key = _cache_key(raw, None, "openai/gpt-4o-mini")
        cache = {key: {"bundle": _CANNED_BUNDLE, "model": "openai/gpt-4o-mini"}}

        class _NeverCallClient:
            class chat:
                class completions:
                    def create(self, **_):
                        raise AssertionError("Should not call AI — cache should be hit")

        bundle, used_model = extract_roadmap_with_ai(
            _NeverCallClient(), raw, "csv", cache=cache
        )
        assert bundle is _CANNED_BUNDLE
        assert used_model == "openai/gpt-4o-mini"

    def test_cache_populated_after_first_call(self):
        raw = _make_csv_bytes()
        cache: dict = {}
        extract_roadmap_with_ai(_make_fake_client(), raw, "csv", cache=cache)
        assert len(cache) == 1

    def test_different_nl_different_cache_entry(self):
        raw = _make_csv_bytes()
        cache: dict = {}
        extract_roadmap_with_ai(_make_fake_client(), raw, "csv", nl_correction="fix A", cache=cache)
        extract_roadmap_with_ai(_make_fake_client(), raw, "csv", nl_correction="fix B", cache=cache)
        assert len(cache) == 2


# ── TestBundleSchema ──────────────────────────────────────────────────────────


class TestBundleSchema:
    def test_bundle_schema_has_required_keys(self):
        for key in ("schema_version", "source_summary", "per_focus", "timeline", "global_rollup"):
            assert key in ROADMAP_BUNDLE_SCHEMA

    def test_bundle_schema_has_all_focus_areas(self):
        foci = set(ROADMAP_BUNDLE_SCHEMA["per_focus"].keys())
        expected = {"content", "technical", "on_page", "off_page", "local", "analytics", "strategy"}
        assert foci == expected

    def test_extraction_returns_bundle_and_model(self):
        raw = _make_csv_bytes()
        bundle, model = extract_roadmap_with_ai(_make_fake_client(), raw, "csv")
        assert isinstance(bundle, dict)
        assert isinstance(model, str)

    def test_extraction_stamps_date(self):
        raw = _make_csv_bytes()
        bundle, _ = extract_roadmap_with_ai(_make_fake_client(), raw, "csv")
        assert "extraction_date" in bundle

    def test_all_focus_areas_in_returned_bundle(self):
        raw = _make_csv_bytes()
        bundle, _ = extract_roadmap_with_ai(_make_fake_client(), raw, "csv")
        for fk in ("content", "technical", "on_page", "off_page", "local", "analytics", "strategy"):
            assert fk in bundle["per_focus"]


# ── TestCorrectionLoop ────────────────────────────────────────────────────────


class TestCorrectionLoop:
    def test_nl_correction_changes_cache_key(self):
        raw = _make_csv_bytes()
        k1 = _cache_key(raw, None, "openai/gpt-4o-mini")
        k2 = _cache_key(raw, "some correction", "openai/gpt-4o-mini")
        assert k1 != k2

    def test_previous_extraction_passed_through(self):
        """Verify the user template receives correction_context when nl_correction is set."""
        captured = {}

        class _CapturingClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        captured["messages"] = kwargs.get("messages", [])

                        class _R:
                            class _C:
                                class _M:
                                    content = json.dumps(_CANNED_BUNDLE)
                                message = _M()
                            choices = [_C()]
                        return _R()

        raw = _make_csv_bytes()
        extract_roadmap_with_ai(
            _CapturingClient(),
            raw,
            "csv",
            nl_correction="Technical audit is quarterly",
            previous_extraction=_CANNED_BUNDLE,
        )
        user_msg = captured["messages"][-1]["content"]
        assert "Technical audit is quarterly" in user_msg
        assert "Previous extraction" in user_msg


# ── TestFlattening ────────────────────────────────────────────────────────────


class TestFlattening:
    """Test that bundle → assumptions store mapping produces ≥15 keys."""

    def test_bundle_flattens_to_assumption_keys(self):
        from engine.assumptions import _detect_from_bundle_v2, initialise_assumptions

        store: dict = {}
        initialise_assumptions(store)
        detected = _detect_from_bundle_v2(store, _CANNED_BUNDLE)
        assert len(detected) >= 15  # 7 effort + 7 hours + 1 timeline

    def test_content_effort_detected(self):
        from engine.assumptions import _detect_from_bundle_v2, get_assumption, initialise_assumptions

        store: dict = {}
        initialise_assumptions(store)
        _detect_from_bundle_v2(store, _CANNED_BUNDLE)
        assert get_assumption(store, "content_effort_level") == "aggressive"

    def test_monthly_hours_detected(self):
        from engine.assumptions import _detect_from_bundle_v2, get_assumption, initialise_assumptions

        store: dict = {}
        initialise_assumptions(store)
        _detect_from_bundle_v2(store, _CANNED_BUNDLE)
        assert get_assumption(store, "content_monthly_hours") == pytest.approx(32.0)

    def test_timeline_detected(self):
        from engine.assumptions import _detect_from_bundle_v2, get_assumption, initialise_assumptions

        store: dict = {}
        initialise_assumptions(store)
        _detect_from_bundle_v2(store, _CANNED_BUNDLE)
        assert get_assumption(store, "timeline_months_covered") == 12


# ── TestEstimateTokens ────────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_returns_positive_int(self):
        tokens = estimate_extraction_tokens("some markdown", "correction", "schema")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_longer_input_more_tokens(self):
        t1 = estimate_extraction_tokens("short")
        t2 = estimate_extraction_tokens("x" * 4000)
        assert t2 > t1


# ── TestEnrichBundleWithAi ────────────────────────────────────────────────────


def _make_enrichment_client(enrichment: dict):
    """Fake client that returns canned enrichment JSON."""
    import json

    class _FakeCompletion:
        class _Choice:
            class _Message:
                content = json.dumps(enrichment)
            message = _Message()
        choices = [_Choice()]

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**_):
                    return _FakeCompletion()

    return _FakeClient()


_CANNED_ENRICHMENT = {
    "recommendations": [
        {"severity": "warning", "focus_area": "off_page", "message": "No link-building tasks detected."}
    ],
    "focus_corrections": [],
    "effort_verification": [
        {"focus": "content", "claimed": "aggressive", "verified": "aggressive", "note": ""}
    ],
}


class TestEnrichBundleWithAi:
    def _base_bundle(self) -> dict:
        import copy
        return copy.deepcopy(_CANNED_BUNDLE)

    def test_enrich_adds_recommendations(self):
        from engine.roadmap_ai_engine import enrich_bundle_with_ai
        client = _make_enrichment_client(_CANNED_ENRICHMENT)
        bundle, used_model = enrich_bundle_with_ai(client, self._base_bundle())
        assert len(bundle["recommendations"]) >= 1
        assert isinstance(used_model, str)

    def test_enrich_does_not_modify_per_focus_hours(self):
        from engine.roadmap_ai_engine import enrich_bundle_with_ai
        client = _make_enrichment_client(_CANNED_ENRICHMENT)
        bundle = self._base_bundle()
        original_hours = bundle["per_focus"]["content"]["monthly_hours"]
        enrich_bundle_with_ai(client, bundle)
        assert bundle["per_focus"]["content"]["monthly_hours"] == original_hours

    def test_enrich_skips_when_client_none(self):
        from engine.roadmap_ai_engine import enrich_bundle_with_ai
        bundle = self._base_bundle()
        bundle["recommendations"] = []
        result, model = enrich_bundle_with_ai(None, bundle)
        assert result["recommendations"] == []  # unchanged
        assert model == "no-client"

    def test_focus_correction_moves_task(self):
        from engine.roadmap_ai_engine import _reclassify_task
        bundle = {
            "per_focus": {
                "strategy": {
                    "monthly_hours": 5.0,
                    "task_count": 1,
                    "tasks": [{"name": "Monthly Report", "hours": 3}],
                },
                "analytics": {
                    "monthly_hours": 2.0,
                    "task_count": 0,
                    "tasks": [],
                },
            }
        }
        _reclassify_task(bundle, "Monthly Report", "strategy", "analytics")
        assert bundle["per_focus"]["strategy"]["task_count"] == 0
        assert bundle["per_focus"]["strategy"]["monthly_hours"] == pytest.approx(2.0)
        assert bundle["per_focus"]["analytics"]["task_count"] == 1
        assert bundle["per_focus"]["analytics"]["monthly_hours"] == pytest.approx(5.0)

    def test_focus_correction_noop_on_missing_task(self):
        from engine.roadmap_ai_engine import _reclassify_task
        bundle = {
            "per_focus": {
                "strategy": {"monthly_hours": 5.0, "task_count": 1, "tasks": [{"name": "Other Task", "hours": 3}]},
                "analytics": {"monthly_hours": 0.0, "task_count": 0, "tasks": []},
            }
        }
        _reclassify_task(bundle, "Non-existent Task", "strategy", "analytics")
        assert bundle["per_focus"]["strategy"]["task_count"] == 1  # unchanged


class TestLoadRoadmapV2WithEnrichment:
    def test_load_roadmap_v2_calls_enrichment_when_client_provided(self):
        from engine.roadmap_ai_engine import load_roadmap_v2
        client = _make_enrichment_client(_CANNED_ENRICHMENT)
        raw = _make_csv_bytes()
        bundle, used_model = load_roadmap_v2(client, raw, "roadmap.csv")
        # task_table format → deterministic parse + enrichment
        assert "recommendations" in bundle
        assert used_model != "deterministic"  # enrichment model was used

    def test_load_roadmap_v2_skips_enrichment_when_client_none(self):
        from engine.roadmap_ai_engine import load_roadmap_v2
        raw = _make_csv_bytes()
        bundle, used_model = load_roadmap_v2(None, raw, "roadmap.csv")
        assert used_model == "deterministic"

    def test_load_roadmap_v2_raises_clearly_on_unknown_without_client(self):
        from engine.roadmap_ai_engine import load_roadmap_v2
        raw = b"col1,col2\nvalue1,value2\n"  # doesn't match any known format
        with pytest.raises(NotImplementedError, match="Unknown roadmap format"):
            load_roadmap_v2(None, raw, "mystery.csv")

    def test_full_ai_extraction_uses_correction_context(self):
        from engine.roadmap_ai_engine import extract_roadmap_full_ai
        captured = {}

        class _CapturingClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        captured["messages"] = kwargs.get("messages", [])

                        class _R:
                            class _C:
                                class _M:
                                    content = json.dumps({
                                        "schema_version": "2.0",
                                        "per_focus": {
                                            k: {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []}
                                            for k in ("content", "technical", "on_page", "off_page", "local", "analytics", "strategy")
                                        },
                                        "source_summary": {}, "client_metadata": {},
                                        "content_plan": [], "timeline": {}, "global_rollup": {},
                                        "recommendations": [], "gaps": [],
                                    })
                                message = _M()
                            choices = [_C()]
                        return _R()

        raw = _make_csv_bytes()
        prev = {"schema_version": "2.0", "per_focus": {}}
        extract_roadmap_full_ai(
            _CapturingClient(), raw, "csv",
            nl_correction="Technical audit is quarterly",
            previous_bundle=prev,
        )
        user_msg = captured["messages"][-1]["content"]
        assert "Technical audit is quarterly" in user_msg
        assert "Previous extraction" in user_msg


class TestStrategySummary:
    def test_summary_uses_bundle_fields(self):
        from engine.roadmap_ai_engine import summarise_strategy_with_ai

        captured = {}

        class _CapturingClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        captured["messages"] = kwargs.get("messages", [])

                        class _R:
                            class _C:
                                class _M:
                                    content = json.dumps({"strategy_summary": "Test summary text."})
                                message = _M()
                            choices = [_C()]
                        return _R()

        bundle = {
            "client_metadata": {"client_name": "Acme Co", "industry": "Accessories"},
            "per_focus": {k: {"monthly_hours": 0.0} for k in ("content", "technical", "on_page", "off_page", "local", "analytics", "strategy")},
            "content_plan": [],
            "timeline": {"months_covered": 12},
            "primary_domain": "acme.com",
            "localisation_domains": [],
        }
        summary, model = summarise_strategy_with_ai(_CapturingClient(), bundle)
        assert summary == "Test summary text."
        user_msg = captured["messages"][-1]["content"]
        assert "Acme Co" in user_msg
        assert "acme.com" in user_msg

    def test_returns_empty_when_client_none(self):
        from engine.roadmap_ai_engine import summarise_strategy_with_ai
        summary, model = summarise_strategy_with_ai(None, {})
        assert summary == ""
        assert model == "no-client"
