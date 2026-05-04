"""Unit tests for utils/data_status.py — pure Python, no Streamlit."""
from __future__ import annotations

import pytest

from utils.data_status import RequirementItem, check_requirements, page_status_emoji, parse_spec

# ---------------------------------------------------------------------------
# parse_spec
# ---------------------------------------------------------------------------

class TestParseSpec:
    def test_single_hard(self):
        assert parse_spec("ga4") == (["ga4"], False)

    def test_single_optional(self):
        assert parse_spec("roadmap:optional") == (["roadmap"], True)

    def test_pipe_hard(self):
        assert parse_spec("kw_df|roadmap_content_plan") == (["kw_df", "roadmap_content_plan"], False)

    def test_pipe_optional(self):
        names, optional = parse_spec("pos_result|nc_result:optional")
        assert names == ["pos_result", "nc_result"]
        assert optional is True

    def test_no_colon_is_not_optional(self):
        _, optional = parse_spec("hist_results")
        assert optional is False


# ---------------------------------------------------------------------------
# check_requirements
# ---------------------------------------------------------------------------

class TestCheckRequirements:
    """Empty requirements list — trivially satisfied."""

    def test_empty_requirements(self):
        ok, opt_missing, items = check_requirements([], {})
        assert ok is True
        assert opt_missing is False
        assert items == []


class TestAllHardMet:
    def test_all_present(self):
        session = {"ga4_df": "data", "kw_existing": "data"}
        ok, opt_missing, items = check_requirements(["ga4", "kw_existing"], session)
        assert ok is True
        assert opt_missing is False
        assert all(i.loaded for i in items)
        assert all(i.required for i in items)

    def test_detail_string_ga4(self):
        import pandas as pd
        session = {"ga4_df": pd.DataFrame({"month": range(24)})}
        _, _, items = check_requirements(["ga4"], session)
        assert items[0].detail == "24 months"

    def test_detail_string_kw_df(self):
        import pandas as pd
        session = {"kw_df": pd.DataFrame({"kw": range(1018)})}
        _, _, items = check_requirements(["kw_df"], session)
        assert items[0].detail == "1,018 keywords"


class TestHardMissing:
    def test_hard_missing_returns_false(self):
        ok, _, items = check_requirements(["ga4"], {})
        assert ok is False
        assert items[0].loaded is False
        assert items[0].required is True

    def test_one_hard_missing_makes_all_false(self):
        session = {"ga4_df": "data"}
        ok, _, _ = check_requirements(["ga4", "kw_existing"], session)
        assert ok is False


class TestOptionalMissing:
    def test_optional_missing_does_not_fail_hard(self):
        ok, opt_missing, items = check_requirements(["roadmap:optional"], {})
        assert ok is True
        assert opt_missing is True
        assert items[0].required is False
        assert items[0].loaded is False

    def test_optional_present_clears_flag(self):
        session = {"roadmap_bundle": "data"}
        ok, opt_missing, _ = check_requirements(["roadmap:optional"], session)
        assert ok is True
        assert opt_missing is False


class TestPipeAnyOneSuffices:
    def test_first_key_present(self):
        session = {"kw_df": "data"}
        ok, _, items = check_requirements(["kw_df|roadmap_content_plan"], session)
        assert ok is True
        assert items[0].loaded is True

    def test_second_key_present(self):
        session = {"roadmap_content_plan": []}
        ok, _, items = check_requirements(["kw_df|roadmap_content_plan"], session)
        assert ok is True
        assert items[0].loaded is True

    def test_neither_present(self):
        ok, _, items = check_requirements(["kw_df|roadmap_content_plan"], {})
        assert ok is False
        assert items[0].loaded is False

    def test_pipe_optional_any_one_suffices(self):
        session = {"nc_result": "data"}
        ok, opt_missing, items = check_requirements(["pos_result|nc_result:optional"], session)
        assert ok is True
        assert opt_missing is False
        assert items[0].loaded is True


# ---------------------------------------------------------------------------
# page_status_emoji
# ---------------------------------------------------------------------------

class TestPageStatusEmoji:
    def test_all_present(self):
        session = {"ga4_df": 1, "kw_existing": 1, "pos_result": 1}
        result = page_status_emoji(["ga4_df", "kw_existing"], ["pos_result"], session)
        assert result == " ✓"

    def test_soft_missing(self):
        session = {"ga4_df": 1, "kw_existing": 1}
        result = page_status_emoji(["ga4_df", "kw_existing"], ["pos_result"], session)
        assert result == " ⚠"

    def test_hard_missing(self):
        session = {}
        result = page_status_emoji(["ga4_df"], ["pos_result"], session)
        assert result == " 🔒"

    def test_no_soft_keys(self):
        session = {"ga4_df": 1}
        result = page_status_emoji(["ga4_df"], [], session)
        assert result == " ✓"

    def test_empty_all(self):
        result = page_status_emoji([], [], {})
        assert result == " ✓"
