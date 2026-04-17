"""Roadmap ingestion — parse uploaded roadmap files and extract forecast assumptions.

Supports two formats:
  Native Pattern xlsx  — the GAZMAN-style task grid produced by the SEO Roadmap page
                         (columns: Task, Focus, Occurrence, Hours)
  Generic CSV/xlsx     — either the same task columns OR a direct parameters table
                         (columns: cadence, effort_level, maintenance_coverage)

The loader extracts three assumptions:
  content_cadence       — posts per month (int)
  effort_level          — "light" | "moderate" | "aggressive"
  maintenance_coverage  — 0.0–1.0 fraction of portfolio actively maintained
"""
from __future__ import annotations

import io
from typing import BinaryIO

import pandas as pd


# ── Column aliases ────────────────────────────────────────────────────────────

_TASK_COL_ALIASES = ["task", "Task", "TASK", "activity", "Activity"]
_FOCUS_COL_ALIASES = ["focus", "Focus", "FOCUS", "area", "Area", "category", "Category"]
_OCC_COL_ALIASES = ["occurrence", "Occurrence", "OCCURRENCE", "frequency", "Frequency"]
_HOURS_COL_ALIASES = ["hours", "Hours", "HOURS", "hrs", "Hrs"]

# Direct parameter columns (generic param table format)
_CADENCE_COL_ALIASES = ["cadence", "Cadence", "content_cadence", "posts_per_month"]
_EFFORT_COL_ALIASES = ["effort_level", "effort", "Effort", "Effort Level"]
_MAINT_COL_ALIASES = ["maintenance_coverage", "maintenance", "Maintenance", "maint_coverage"]

# ── Effort classification thresholds (avg monthly hours) ─────────────────────

_EFFORT_THRESHOLDS = [
    (20.0, "light"),
    (40.0, "moderate"),
    (float("inf"), "aggressive"),
]

# ── Occurrence → monthly equivalent multiplier ───────────────────────────────

_OCC_MONTHLY_FACTOR: dict[str, float] = {
    "monthly": 1.0,
    "bimonthly": 0.5,
    "bi-monthly": 0.5,
    "quarterly": 1 / 3,
    "biannual": 1 / 6,
    "bi-annual": 1 / 6,
    "annual": 1 / 12,
    "oneoff": 1 / 12,
    "one-off": 1 / 12,
    "one off": 1 / 12,
}


def _find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _monthly_equivalent_hours(task_df: pd.DataFrame, months: int = 12) -> float:
    """Compute average monthly hours from a task table.

    Args:
        task_df: DataFrame with occurrence and hours columns.
        months: Horizon used to normalise annual/one-off tasks.

    Returns:
        Float — average scheduled hours per month.
    """
    occ_col = _find_col(task_df, _OCC_COL_ALIASES)
    hrs_col = _find_col(task_df, _HOURS_COL_ALIASES)
    if occ_col is None or hrs_col is None:
        return 0.0

    total_monthly = 0.0
    for _, row in task_df.iterrows():
        occ_key = str(row[occ_col]).strip().lower().replace("-", "").replace(" ", "")
        factor = _OCC_MONTHLY_FACTOR.get(occ_key, 1 / 12)
        try:
            total_monthly += float(row[hrs_col]) * factor
        except (ValueError, TypeError):
            pass
    return total_monthly


def _classify_effort(monthly_hours: float) -> str:
    for threshold, label in _EFFORT_THRESHOLDS:
        if monthly_hours <= threshold:
            return label
    return "aggressive"


def _content_cadence_from_tasks(task_df: pd.DataFrame) -> int:
    """Estimate posts-per-month from content-focused monthly tasks.

    Counts monthly tasks in the "Content" focus area where the task name
    contains "article", "blog", "post", or "content production".
    Falls back to counting all monthly Content tasks if none match.
    """
    focus_col = _find_col(task_df, _FOCUS_COL_ALIASES)
    occ_col = _find_col(task_df, _OCC_COL_ALIASES)
    task_col = _find_col(task_df, _TASK_COL_ALIASES)
    hrs_col = _find_col(task_df, _HOURS_COL_ALIASES)

    if focus_col is None or occ_col is None:
        return 4  # default

    production_keywords = ("article", "blog", "post", "content production", "long-form", "longform")

    content_tasks = task_df[
        task_df[focus_col].str.strip().str.lower() == "content"
    ]
    monthly_content = content_tasks[
        content_tasks[occ_col].str.strip().str.lower().str.replace("-", "").str.replace(" ", "") == "monthly"
    ]

    if task_col is not None:
        production_tasks = monthly_content[
            monthly_content[task_col].str.lower().str.contains("|".join(production_keywords), na=False)
        ]
    else:
        production_tasks = monthly_content

    if len(production_tasks) > 0:
        # If hours available: each 10h ≈ 1 article
        if hrs_col is not None:
            total_hours = production_tasks[hrs_col].sum()
            try:
                return max(1, round(float(total_hours) / 10))
            except (ValueError, TypeError):
                pass
        return len(production_tasks)

    # Fallback: count all monthly content tasks
    if len(monthly_content) > 0:
        return len(monthly_content)

    return 4  # default


def _maintenance_coverage_from_tasks(task_df: pd.DataFrame) -> float:
    """Estimate maintenance coverage from on-page/technical regular tasks.

    Logic:
    - 0.0 if no on-page or technical tasks scheduled monthly/quarterly
    - 0.3–0.7 depending on regularity and breadth of maintenance tasks
    """
    focus_col = _find_col(task_df, _FOCUS_COL_ALIASES)
    occ_col = _find_col(task_df, _OCC_COL_ALIASES)
    if focus_col is None or occ_col is None:
        return 0.0

    maintenance_foci = {"on-page", "technical"}

    def _occ_score(occ: str) -> float:
        key = occ.strip().lower().replace("-", "").replace(" ", "")
        return {"monthly": 1.0, "bimonthly": 0.7, "quarterly": 0.4, "biannual": 0.2}.get(key, 0.1)

    scores: list[float] = []
    for _, row in task_df.iterrows():
        focus = str(row[focus_col]).strip().lower()
        if focus in maintenance_foci:
            scores.append(_occ_score(str(row[occ_col])))

    if not scores:
        return 0.0

    # Average score, capped at 1.0 — more tasks = more coverage, up to a ceiling
    raw = sum(scores) / len(_EFFORT_THRESHOLDS)  # normalise against threshold count
    return round(min(raw, 1.0), 2)


# ── Public API ────────────────────────────────────────────────────────────────


def parse_task_table(df: pd.DataFrame) -> dict:
    """Extract forecast parameters from a task-grid DataFrame.

    Returns dict with keys: content_cadence, effort_level, maintenance_coverage.
    """
    monthly_hours = _monthly_equivalent_hours(df)
    return {
        "content_cadence": _content_cadence_from_tasks(df),
        "effort_level": _classify_effort(monthly_hours),
        "maintenance_coverage": _maintenance_coverage_from_tasks(df),
        "_monthly_hours": monthly_hours,
    }


def parse_param_table(df: pd.DataFrame) -> dict:
    """Extract forecast parameters from a direct parameter table CSV.

    Expects one-row table with optional columns: cadence, effort_level,
    maintenance_coverage (or aliases thereof).
    """
    result: dict = {}

    cadence_col = _find_col(df, _CADENCE_COL_ALIASES)
    if cadence_col is not None and len(df) > 0:
        try:
            result["content_cadence"] = int(df[cadence_col].iloc[0])
        except (ValueError, TypeError):
            pass

    effort_col = _find_col(df, _EFFORT_COL_ALIASES)
    if effort_col is not None and len(df) > 0:
        val = str(df[effort_col].iloc[0]).strip().lower()
        if val in ("light", "moderate", "aggressive"):
            result["effort_level"] = val

    maint_col = _find_col(df, _MAINT_COL_ALIASES)
    if maint_col is not None and len(df) > 0:
        try:
            result["maintenance_coverage"] = float(df[maint_col].iloc[0])
        except (ValueError, TypeError):
            pass

    return result


def load_roadmap(file: BinaryIO | bytes | str) -> dict:
    """Load a roadmap file and return extracted forecast parameters.

    Accepts: file-like object, bytes, or file path string.
    Auto-detects native task-table format vs. direct param table.

    Returns dict with any subset of: content_cadence, effort_level, maintenance_coverage.
    """
    if isinstance(file, (str,)):
        with open(file, "rb") as f:
            raw = f.read()
    elif isinstance(file, bytes):
        raw = file
    else:
        raw = file.read()

    buf = io.BytesIO(raw)

    # Try xlsx first, then csv
    try:
        df = pd.read_excel(buf, engine="openpyxl")
    except Exception:
        buf.seek(0)
        try:
            df = pd.read_csv(buf)
        except Exception as exc:
            raise ValueError(f"Could not parse roadmap file: {exc}") from exc

    if df.empty:
        return {}

    # Detect format: task-table has a "task" or "focus" column
    has_task_cols = (
        _find_col(df, _TASK_COL_ALIASES) is not None
        or _find_col(df, _FOCUS_COL_ALIASES) is not None
    )
    has_param_cols = (
        _find_col(df, _CADENCE_COL_ALIASES) is not None
        or _find_col(df, _EFFORT_COL_ALIASES) is not None
        or _find_col(df, _MAINT_COL_ALIASES) is not None
    )

    if has_param_cols and not has_task_cols:
        return parse_param_table(df)

    if has_task_cols:
        return parse_task_table(df)

    return {}
