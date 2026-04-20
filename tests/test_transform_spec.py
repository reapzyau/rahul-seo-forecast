"""Tests for engine/transform_spec.py declarative JSON interpreter."""
import pandas as pd
import pytest

from engine.transform_spec import apply_transform

# ── rename ────────────────────────────────────────────────────────────────────

class TestRename:
    def test_renames_columns(self):
        df = pd.DataFrame({"Sessions": [1, 2], "Month": ["Jan", "Feb"]})
        result = apply_transform(df, {"version": "1", "rename": {"Sessions": "traffic", "Month": "date"}})
        assert "traffic" in result.columns
        assert "date" in result.columns
        assert "Sessions" not in result.columns

    def test_missing_source_column_ignored(self):
        df = pd.DataFrame({"a": [1]})
        result = apply_transform(df, {"version": "1", "rename": {"nonexistent": "b"}})
        assert "a" in result.columns


# ── filter_rows ───────────────────────────────────────────────────────────────

class TestFilterRows:
    def test_contains_filter(self):
        df = pd.DataFrame({"ch": ["Organic Search", "Paid Search", "Organic Shopping"]})
        result = apply_transform(df, {"version": "1", "filter_rows": [
            {"column": "ch", "op": "contains", "value": "organic", "case_insensitive": True}
        ]})
        assert len(result) == 2

    def test_gt_filter(self):
        df = pd.DataFrame({"volume": [0, 100, 500, 0]})
        result = apply_transform(df, {"version": "1", "filter_rows": [
            {"column": "volume", "op": "gt", "value": 0}
        ]})
        assert len(result) == 2
        assert (result["volume"] > 0).all()

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"a": [1, 2]})
        result = apply_transform(df, {"version": "1", "filter_rows": [
            {"column": "missing", "op": "eq", "value": 1}
        ]})
        assert len(result) == 2  # unchanged


# ── type_coerce ───────────────────────────────────────────────────────────────

class TestTypeCoerce:
    def test_datetime_coerce(self):
        df = pd.DataFrame({"date": ["2024-01-01", "2024-02-01"]})
        result = apply_transform(df, {"version": "1", "type_coerce": [
            {"column": "date", "to": "datetime"}
        ]})
        assert pd.api.types.is_datetime64_any_dtype(result["date"])

    def test_int_strip_pct(self):
        df = pd.DataFrame({"kd": ["45%", "70%", "20%"]})
        result = apply_transform(df, {"version": "1", "type_coerce": [
            {"column": "kd", "to": "int_strip_pct"}
        ]})
        assert result["kd"].tolist() == [45.0, 70.0, 20.0]


# ── aggregate ─────────────────────────────────────────────────────────────────

class TestAggregate:
    def test_groupby_sum(self):
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01", "2024-02-01"],
            "traffic": [1000, 500, 2000],
        })
        result = apply_transform(df, {"version": "1", "aggregate": {
            "groupby": ["date"], "agg": {"traffic": "sum"}
        }})
        assert len(result) == 2
        jan = result[result["date"] == "2024-01-01"]["traffic"].iloc[0]
        assert jan == 1500


# ── derive ────────────────────────────────────────────────────────────────────

class TestDerive:
    def test_ratio_division(self):
        df = pd.DataFrame({"revenue": [1000.0], "transactions": [10.0]})
        result = apply_transform(df, {"version": "1", "derive": [
            {"column": "aov", "op": "/", "left": "revenue", "right": "transactions"}
        ]})
        assert result["aov"].iloc[0] == pytest.approx(100.0)

    def test_ratio_with_scale(self):
        df = pd.DataFrame({"transactions": [25.0], "traffic": [1000.0]})
        result = apply_transform(df, {"version": "1", "derive": [
            {"column": "cr", "op": "/", "left": "transactions", "right": "traffic", "scale": 100}
        ]})
        assert result["cr"].iloc[0] == pytest.approx(2.5)

    def test_divide_by_zero_produces_nan(self):
        df = pd.DataFrame({"a": [10.0], "b": [0.0]})
        result = apply_transform(df, {"version": "1", "derive": [
            {"column": "ratio", "op": "/", "left": "a", "right": "b"}
        ]})
        assert pd.isna(result["ratio"].iloc[0])


# ── apply_transform_spec fallback ─────────────────────────────────────────────

class TestApplyTransformSpecFallback:
    def test_valid_json_spec_applied(self):
        from engine.ai_engine import apply_transform_spec
        df = pd.DataFrame({"Sessions": [100, 200], "Month": ["2024-01-01", "2024-02-01"]})
        spec_json = '{"version": "1", "rename": {"Sessions": "traffic", "Month": "date"}}'
        result = apply_transform_spec(df, spec_json)
        assert "traffic" in result.columns

    def test_python_code_fallback(self):
        from engine.ai_engine import apply_transform_spec
        df = pd.DataFrame({"a": [1, 2, 3]})
        code = "result = df.rename(columns={'a': 'traffic'})"
        result = apply_transform_spec(df, code)
        assert "traffic" in result.columns
