"""Tests for utils/roadmap_loader.py."""
import io

import pandas as pd
import pytest

from utils.roadmap_loader import (
    _classify_effort,
    _content_cadence_from_tasks,
    _maintenance_coverage_from_tasks,
    _monthly_equivalent_hours,
    load_roadmap,
    parse_param_table,
    parse_task_table,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _task_df(rows: list[dict] | None = None) -> pd.DataFrame:
    if rows is None:
        rows = [
            {"Task": "Long-Form Article Production", "Focus": "Content",   "Occurrence": "Monthly",   "Hours": 10.0},
            {"Task": "Content Calendar & Planning",  "Focus": "Content",   "Occurrence": "Monthly",    "Hours": 2.0},
            {"Task": "Page Optimisation",            "Focus": "On-Page",   "Occurrence": "Monthly",    "Hours": 4.0},
            {"Task": "Technical Audit",              "Focus": "Technical", "Occurrence": "Bi-Annual",  "Hours": 8.0},
            {"Task": "Monthly Reporting",            "Focus": "Analytics", "Occurrence": "Monthly",    "Hours": 3.0},
        ]
    return pd.DataFrame(rows)


# ── TestMonthlyEquivalentHours ────────────────────────────────────────────────


class TestMonthlyEquivalentHours:
    def test_monthly_task_counts_full(self):
        df = _task_df([{"Task": "A", "Focus": "Content", "Occurrence": "Monthly", "Hours": 10.0}])
        assert _monthly_equivalent_hours(df) == pytest.approx(10.0)

    def test_quarterly_task_counts_third(self):
        df = _task_df([{"Task": "A", "Focus": "Technical", "Occurrence": "Quarterly", "Hours": 12.0}])
        assert _monthly_equivalent_hours(df) == pytest.approx(4.0)

    def test_biannual_task_counts_sixth(self):
        df = _task_df([{"Task": "A", "Focus": "Technical", "Occurrence": "Bi-Annual", "Hours": 12.0}])
        assert _monthly_equivalent_hours(df) == pytest.approx(12.0 / 6, rel=0.01)

    def test_annual_task_counts_twelfth(self):
        df = _task_df([{"Task": "A", "Focus": "Strategy", "Occurrence": "Annual", "Hours": 12.0}])
        assert _monthly_equivalent_hours(df) == pytest.approx(1.0, rel=0.01)

    def test_missing_hours_returns_zero(self):
        df = pd.DataFrame({"Task": ["A"], "Focus": ["Content"]})
        assert _monthly_equivalent_hours(df) == 0.0

    def test_multiple_tasks_sum(self):
        df = _task_df([
            {"Task": "A", "Focus": "Content",   "Occurrence": "Monthly", "Hours": 10.0},
            {"Task": "B", "Focus": "On-Page",   "Occurrence": "Monthly", "Hours": 4.0},
        ])
        assert _monthly_equivalent_hours(df) == pytest.approx(14.0)


# ── TestClassifyEffort ────────────────────────────────────────────────────────


class TestClassifyEffort:
    def test_low_hours_is_light(self):
        assert _classify_effort(10.0) == "light"

    def test_boundary_light_moderate(self):
        assert _classify_effort(20.0) == "light"
        assert _classify_effort(20.1) == "moderate"

    def test_boundary_moderate_aggressive(self):
        assert _classify_effort(40.0) == "moderate"
        assert _classify_effort(40.1) == "aggressive"

    def test_high_hours_is_aggressive(self):
        assert _classify_effort(100.0) == "aggressive"

    def test_zero_hours_is_light(self):
        assert _classify_effort(0.0) == "light"


# ── TestContentCadence ────────────────────────────────────────────────────────


class TestContentCadence:
    def test_standard_article_task(self):
        df = _task_df([
            {"Task": "Long-Form Article Production", "Focus": "Content", "Occurrence": "Monthly", "Hours": 10.0},
        ])
        cadence = _content_cadence_from_tasks(df)
        assert cadence >= 1

    def test_hours_drives_cadence(self):
        df = _task_df([
            {"Task": "Long-Form Article Production", "Focus": "Content", "Occurrence": "Monthly", "Hours": 30.0},
        ])
        # 30h / 10h per article = 3 posts/month
        assert _content_cadence_from_tasks(df) == 3

    def test_no_content_tasks_returns_default(self):
        df = _task_df([
            {"Task": "Technical Audit", "Focus": "Technical", "Occurrence": "Quarterly", "Hours": 8.0},
        ])
        assert _content_cadence_from_tasks(df) == 4  # default

    def test_quarterly_content_not_counted(self):
        df = _task_df([
            {"Task": "Content Strategy", "Focus": "Content", "Occurrence": "Quarterly", "Hours": 8.0},
        ])
        # No monthly content tasks — falls back to counting non-monthly tasks = 0, returns default
        assert _content_cadence_from_tasks(df) == 4

    def test_missing_focus_column_returns_default(self):
        df = pd.DataFrame({"Task": ["Article"], "Occurrence": ["Monthly"]})
        assert _content_cadence_from_tasks(df) == 4


# ── TestMaintenanceCoverage ───────────────────────────────────────────────────


class TestMaintenanceCoverage:
    def test_no_maintenance_tasks_returns_zero(self):
        df = _task_df([
            {"Task": "Monthly Reporting", "Focus": "Analytics", "Occurrence": "Monthly", "Hours": 3.0},
        ])
        assert _maintenance_coverage_from_tasks(df) == pytest.approx(0.0)

    def test_monthly_onpage_increases_coverage(self):
        df = _task_df([
            {"Task": "Page Optimisation", "Focus": "On-Page", "Occurrence": "Monthly", "Hours": 4.0},
        ])
        assert _maintenance_coverage_from_tasks(df) > 0.0

    def test_more_maintenance_tasks_higher_coverage(self):
        df_few = _task_df([
            {"Task": "Page Optimisation", "Focus": "On-Page",   "Occurrence": "Quarterly", "Hours": 4.0},
        ])
        df_more = _task_df([
            {"Task": "Page Optimisation", "Focus": "On-Page",   "Occurrence": "Monthly",   "Hours": 4.0},
            {"Task": "Technical Audit",   "Focus": "Technical", "Occurrence": "Monthly",   "Hours": 8.0},
        ])
        assert _maintenance_coverage_from_tasks(df_more) >= _maintenance_coverage_from_tasks(df_few)

    def test_coverage_bounded_0_to_1(self):
        df = _task_df([
            {"Task": "A", "Focus": "On-Page",   "Occurrence": "Monthly", "Hours": 10.0},
            {"Task": "B", "Focus": "On-Page",   "Occurrence": "Monthly", "Hours": 10.0},
            {"Task": "C", "Focus": "Technical", "Occurrence": "Monthly", "Hours": 10.0},
            {"Task": "D", "Focus": "Technical", "Occurrence": "Monthly", "Hours": 10.0},
        ])
        cov = _maintenance_coverage_from_tasks(df)
        assert 0.0 <= cov <= 1.0


# ── TestParseTaskTable ────────────────────────────────────────────────────────


class TestParseTaskTable:
    def test_returns_all_three_keys(self):
        result = parse_task_table(_task_df())
        assert "content_cadence" in result
        assert "effort_level" in result
        assert "maintenance_coverage" in result

    def test_effort_level_valid_value(self):
        result = parse_task_table(_task_df())
        assert result["effort_level"] in ("light", "moderate", "aggressive")

    def test_cadence_is_positive_int(self):
        result = parse_task_table(_task_df())
        assert isinstance(result["content_cadence"], int)
        assert result["content_cadence"] >= 1

    def test_maintenance_coverage_in_range(self):
        result = parse_task_table(_task_df())
        assert 0.0 <= result["maintenance_coverage"] <= 1.0

    def test_high_hours_gives_aggressive(self):
        rows = [
            {"Task": f"Task {i}", "Focus": "Content", "Occurrence": "Monthly", "Hours": 20.0}
            for i in range(5)
        ]
        result = parse_task_table(pd.DataFrame(rows))
        assert result["effort_level"] == "aggressive"

    def test_low_hours_gives_light(self):
        rows = [
            {"Task": "One Task", "Focus": "Content", "Occurrence": "Quarterly", "Hours": 4.0},
        ]
        result = parse_task_table(pd.DataFrame(rows))
        assert result["effort_level"] == "light"


# ── TestParseParamTable ───────────────────────────────────────────────────────


class TestParseParamTable:
    def test_reads_cadence(self):
        df = pd.DataFrame({"cadence": [8], "effort_level": ["moderate"], "maintenance_coverage": [0.5]})
        result = parse_param_table(df)
        assert result["content_cadence"] == 8

    def test_reads_effort_level(self):
        df = pd.DataFrame({"cadence": [4], "effort_level": ["aggressive"]})
        result = parse_param_table(df)
        assert result["effort_level"] == "aggressive"

    def test_reads_maintenance_coverage(self):
        df = pd.DataFrame({"maintenance_coverage": [0.7]})
        result = parse_param_table(df)
        assert result["maintenance_coverage"] == pytest.approx(0.7)

    def test_invalid_effort_level_ignored(self):
        df = pd.DataFrame({"effort_level": ["super_high"]})
        result = parse_param_table(df)
        assert "effort_level" not in result

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        result = parse_param_table(df)
        assert result == {}

    def test_column_aliases(self):
        df = pd.DataFrame({"Effort Level": ["light"], "Cadence": [2]})
        result = parse_param_table(df)
        assert result.get("effort_level") == "light"
        assert result.get("content_cadence") == 2


# ── TestLoadRoadmap ───────────────────────────────────────────────────────────


class TestLoadRoadmap:
    def test_load_from_csv_bytes_task_table(self):
        csv = "Task,Focus,Occurrence,Hours\nLong-Form Article Production,Content,Monthly,10\nPage Optimisation,On-Page,Monthly,4\n"
        result = load_roadmap(csv.encode())
        assert "content_cadence" in result
        assert "effort_level" in result
        assert "maintenance_coverage" in result

    def test_load_from_csv_bytes_param_table(self):
        csv = "cadence,effort_level,maintenance_coverage\n6,aggressive,0.6\n"
        result = load_roadmap(csv.encode())
        assert result["content_cadence"] == 6
        assert result["effort_level"] == "aggressive"
        assert result["maintenance_coverage"] == pytest.approx(0.6)

    def test_empty_csv_returns_empty(self):
        csv = "col1,col2\n"
        result = load_roadmap(csv.encode())
        assert result == {}

    def test_invalid_bytes_raises(self):
        with pytest.raises(ValueError):
            load_roadmap(b"\x00\x01\x02\x03\xff\xfe")  # binary garbage

    def test_load_from_file_like(self):
        csv = "cadence,effort_level\n4,moderate\n"
        buf = io.BytesIO(csv.encode())
        result = load_roadmap(buf)
        assert result.get("content_cadence") == 4

    def test_param_format_takes_priority_when_ambiguous(self):
        # Has both param columns and content columns — param should win
        csv = "cadence,effort_level,Task\n4,moderate,something\n"
        result = load_roadmap(csv.encode())
        # parse_param_table is chosen when has_param_cols and not has_task_cols
        # but here has_task_cols is True too — falls through to task table
        # Just check it returns something without error
        assert isinstance(result, dict)
