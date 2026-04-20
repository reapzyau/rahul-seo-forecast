"""Declarative JSON transform spec interpreter.

Replaces exec()-based AI data transformation with a safe, auditable spec
that the LLM fills in and this module executes without eval/exec.

Spec schema (all keys optional except 'version'):
{
  "version": "1",
  "rename": {"old_col": "new_col", ...},
  "filter_rows": [
    {"column": "ch", "op": "contains", "value": "organic", "case_insensitive": true},
    {"column": "volume", "op": "gt", "value": 0}
  ],
  "drop_duplicates": ["keyword"],
  "aggregate": {"groupby": ["date"], "agg": {"traffic": "sum", ...}},
  "derive": [
    {"column": "aov", "op": "/", "left": "revenue", "right": "transactions"},
    {"column": "cr",  "op": "/", "left": "transactions", "right": "traffic", "scale": 100}
  ],
  "type_coerce": [
    {"column": "date", "to": "datetime"},
    {"column": "traffic", "to": "int"},
    {"column": "kd", "to": "int_strip_pct"}
  ],
  "sort_by": ["date"],
  "drop_nulls": ["date", "traffic"]
}

Supported ops in filter_rows: contains, not_contains, eq, neq, gt, gte, lt, lte, notnull, isnull
Supported ops in derive: +, -, *, /  (between two columns or a column and a scalar)
Supported types in type_coerce: datetime, int, float, str, int_strip_pct
"""
from __future__ import annotations

import pandas as pd


def apply_transform(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Execute a declarative transform spec against df. Returns a new DataFrame."""
    result = df.copy()

    result = _apply_rename(result, spec.get("rename", {}))
    result = _apply_filter_rows(result, spec.get("filter_rows", []))
    result = _apply_type_coerce(result, spec.get("type_coerce", []))
    result = _apply_aggregate(result, spec.get("aggregate"))
    result = _apply_derive(result, spec.get("derive", []))
    result = _apply_drop_duplicates(result, spec.get("drop_duplicates", []))

    sort_by = spec.get("sort_by", [])
    if sort_by:
        valid = [c for c in sort_by if c in result.columns]
        if valid:
            result = result.sort_values(valid).reset_index(drop=True)

    drop_nulls = spec.get("drop_nulls", [])
    if drop_nulls:
        cols = [c for c in drop_nulls if c in result.columns]
        if cols:
            result = result.dropna(subset=cols).reset_index(drop=True)

    return result


def _apply_rename(df: pd.DataFrame, rename: dict) -> pd.DataFrame:
    if not rename:
        return df
    valid = {k: v for k, v in rename.items() if k in df.columns}
    return df.rename(columns=valid)


def _apply_filter_rows(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    for f in filters:
        col = f.get("column")
        op = f.get("op", "eq")
        val = f.get("value")
        ci = f.get("case_insensitive", False)

        if col not in df.columns:
            continue

        series = df[col]

        if op == "contains":
            mask = series.astype(str).str.contains(str(val), case=not ci, na=False)
        elif op == "not_contains":
            mask = ~series.astype(str).str.contains(str(val), case=not ci, na=False)
        elif op == "eq":
            mask = series == val
        elif op == "neq":
            mask = series != val
        elif op == "gt":
            mask = pd.to_numeric(series, errors="coerce") > val
        elif op == "gte":
            mask = pd.to_numeric(series, errors="coerce") >= val
        elif op == "lt":
            mask = pd.to_numeric(series, errors="coerce") < val
        elif op == "lte":
            mask = pd.to_numeric(series, errors="coerce") <= val
        elif op == "notnull":
            mask = series.notna()
        elif op == "isnull":
            mask = series.isna()
        else:
            continue

        df = df[mask].reset_index(drop=True)

    return df


def _apply_type_coerce(df: pd.DataFrame, coercions: list[dict]) -> pd.DataFrame:
    for c in coercions:
        col = c.get("column")
        to = c.get("to")
        if col not in df.columns:
            continue
        if to == "datetime":
            df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce")
        elif to == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif to == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
        elif to == "str":
            df[col] = df[col].astype(str)
        elif to == "int_strip_pct":
            df[col] = (
                df[col].astype(str)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _apply_aggregate(df: pd.DataFrame, agg_spec: dict | None) -> pd.DataFrame:
    if not agg_spec:
        return df
    groupby = agg_spec.get("groupby", [])
    agg = agg_spec.get("agg", {})
    if not groupby or not agg:
        return df
    valid_groupby = [c for c in groupby if c in df.columns]
    valid_agg = {c: fn for c, fn in agg.items() if c in df.columns}
    if not valid_groupby or not valid_agg:
        return df
    return df.groupby(valid_groupby, as_index=False).agg(valid_agg)


def _apply_derive(df: pd.DataFrame, derivations: list[dict]) -> pd.DataFrame:
    for d in derivations:
        col = d.get("column")
        op = d.get("op", "/")
        left = d.get("left")
        right = d.get("right")
        scale = d.get("scale", 1)

        if col is None or left is None or right is None:
            continue
        if left not in df.columns:
            continue

        left_series = pd.to_numeric(df[left], errors="coerce")

        # right can be a column name or a scalar
        if isinstance(right, str) and right in df.columns:
            right_val = pd.to_numeric(df[right], errors="coerce")
        else:
            try:
                right_val = float(right)
            except (TypeError, ValueError):
                continue

        if op == "+":
            df[col] = (left_series + right_val) * scale
        elif op == "-":
            df[col] = (left_series - right_val) * scale
        elif op == "*":
            df[col] = (left_series * right_val) * scale
        elif op == "/":
            df[col] = (left_series / right_val.replace(0, float("nan"))
                       if hasattr(right_val, "replace")
                       else left_series / (right_val or float("nan"))) * scale
        # silently skip unknown ops

    return df


def _apply_drop_duplicates(df: pd.DataFrame, subset: list[str]) -> pd.DataFrame:
    if not subset:
        return df
    valid = [c for c in subset if c in df.columns]
    if valid:
        df = df.drop_duplicates(subset=valid).reset_index(drop=True)
    return df
