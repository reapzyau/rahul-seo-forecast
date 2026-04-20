"""Deterministic parser for Pattern-native xlsx roadmap format.

Parses the multi-sheet xlsx produced by Pattern's retainer template without
requiring an AI call. Falls back to legacy scalar wrappers for simpler formats.

Pure Python — no Streamlit imports.
"""
from __future__ import annotations

import io
import re
from typing import Any

import openpyxl

# ── Sheet name constants ──────────────────────────────────────────────────────

PATTERN_NATIVE_SHEETS_REQUIRED = {"Breakdown"}
PATTERN_NATIVE_SHEETS_EXPECTED = {
    "1. Client Detail",
    "2. Consulting",
    "3. Technical",
    "4. Content",
    "5. Links",
}

# ── Normalisation maps ────────────────────────────────────────────────────────

INDUSTRY_NORMALISATION: dict[str, str] = {
    "accessories": "Accessories",
    "apparel": "Apparel",
    "clothing": "Apparel",
    "fashion": "Apparel",
    "beauty": "Beauty",
    "cosmetics": "Beauty",
    "home": "Home",
    "homewares": "Home",
    "b2b saas": "B2B SaaS",
    "saas": "B2B SaaS",
    "automotive": "Automotive",
    "travel": "Travel",
    "food": "Food & Beverage",
    "health": "Health",
    "fitness": "Health",
    "finance": "Finance",
    "fintech": "Finance",
}

# ── Effort classification thresholds (avg monthly hours) ─────────────────────

_EFFORT_HOURS_THRESHOLDS: list[tuple[float, str]] = [
    (8.0, "light"),
    (20.0, "moderate"),
    (float("inf"), "aggressive"),
]

# ── Column aliases for format detection ──────────────────────────────────────

_TASK_COL_ALIASES = {"task", "activity"}
_FOCUS_COL_ALIASES = {"focus", "area", "category"}
_OCC_COL_ALIASES = {"occurrence", "frequency"}
_HOURS_COL_ALIASES = {"hours", "hrs"}
_CADENCE_COL_ALIASES = {"cadence", "content_cadence", "posts_per_month"}
_EFFORT_COL_ALIASES = {"effort_level", "effort"}
_MAINT_COL_ALIASES = {"maintenance_coverage", "maintenance", "maint_coverage"}


# ── Format detection ──────────────────────────────────────────────────────────


def detect_roadmap_format(raw_bytes: bytes, file_extension: str) -> str:
    """Detect which roadmap format the bytes represent.

    Returns one of: "pattern_native", "task_table", "param_table", "unknown".
    """
    ext = file_extension.lower().lstrip(".")

    # Only xlsx can be Pattern-native
    if ext in ("xlsx", "xls"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True, read_only=True)
            sheet_names = set(wb.sheetnames)
            wb.close()
            if PATTERN_NATIVE_SHEETS_REQUIRED.issubset(sheet_names):
                matching_expected = sheet_names & PATTERN_NATIVE_SHEETS_EXPECTED
                if len(matching_expected) >= 3:
                    return "pattern_native"
        except Exception:
            pass

    # Try reading as a flat table (csv or xlsx)
    try:
        import pandas as pd

        buf = io.BytesIO(raw_bytes)
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(buf, engine="openpyxl")
        else:
            try:
                df = pd.read_csv(buf)
            except Exception:
                return "unknown"

        cols_lower = {str(c).strip().lower() for c in df.columns}

        has_task = bool(cols_lower & _TASK_COL_ALIASES)
        has_focus = bool(cols_lower & _FOCUS_COL_ALIASES)
        has_occ = bool(cols_lower & _OCC_COL_ALIASES)
        has_hours = bool(cols_lower & _HOURS_COL_ALIASES)
        has_cadence = bool(cols_lower & _CADENCE_COL_ALIASES)
        has_effort = bool(cols_lower & _EFFORT_COL_ALIASES)
        has_maint = bool(cols_lower & _MAINT_COL_ALIASES)

        # param_table: has cadence or effort_level or maintenance_coverage
        if has_cadence or has_maint or (has_effort and not has_task and not has_focus):
            return "param_table"

        # task_table: has task + focus + occurrence + hours (at least 3 of 4)
        task_score = sum([has_task, has_focus, has_occ, has_hours])
        if task_score >= 3:
            return "task_table"

    except Exception:
        pass

    return "unknown"


# ── Empty per-focus skeleton ──────────────────────────────────────────────────


def _empty_per_focus() -> dict:
    """Return a per_focus dict with all 7 focus areas at zero/moderate defaults."""
    focus_areas = ["content", "technical", "on_page", "off_page", "local", "analytics", "strategy"]
    return {
        area: {
            "effort_level": "moderate",
            "monthly_hours": 0.0,
            "cadence": 0,
            "task_count": 0,
            "tasks": [],
        }
        for area in focus_areas
    }


# ── Client detail parser ──────────────────────────────────────────────────────


def _parse_client_detail(ws) -> dict:
    """Parse the '1. Client Detail' worksheet into a metadata dict."""
    result: dict[str, Any] = {}

    for row in ws.iter_rows(min_row=3, max_row=14, values_only=True):
        if not row or row[0] is None:
            continue
        label = str(row[0]).strip().lower()
        value = row[1] if len(row) > 1 else None

        if "client name" in label and value is not None:
            result["client_name"] = str(value).strip()

        elif "industry" in label and value is not None:
            raw = str(value).strip().lower()
            result["industry"] = INDUSTRY_NORMALISATION.get(raw, str(value).strip())

        elif "retainer" in label and value is not None:
            # Parse number from strings like "AUD 5000" or "$5,000"
            num_str = re.sub(r"[^0-9.]", "", str(value))
            try:
                result["retainer_aud_monthly"] = float(num_str)
            except (ValueError, TypeError):
                result["retainer_aud_monthly"] = str(value).strip()

        elif "project start" in label and value is not None:
            result["project_start_date"] = str(value).strip()

        elif label == "cms" or label.startswith("cms"):
            if value is not None:
                result["cms"] = str(value).strip()

    return result


# ── Breakdown parser ──────────────────────────────────────────────────────────


def _parse_breakdown(ws) -> dict:
    """Parse the 'Breakdown' worksheet to extract monthly hours per service type."""
    result: dict[str, list] = {
        "consulting": [0] * 12,
        "technical": [0] * 12,
        "content": [0] * 12,
        "link": [0] * 12,
    }

    label_map = {
        "consulting hours": "consulting",
        "technical hours": "technical",
        "content hours": "content",
        "link hours": "link",
    }

    for row in ws.iter_rows(values_only=True):
        if not row or len(row) < 7:
            continue
        cell_e = row[4]  # col E (0-indexed index 4)
        if cell_e is None:
            continue

        label_lower = str(cell_e).strip().lower()
        matched_key = None
        for label_fragment, key in label_map.items():
            if label_fragment in label_lower:
                matched_key = key
                break

        if matched_key is None:
            continue

        # Extract cols G:R (0-indexed 6:18)
        monthly_values = []
        for val in row[6:18]:
            if val is not None and val != "":
                try:
                    monthly_values.append(float(val))
                except (ValueError, TypeError):
                    pass

        # Pad or trim to 12
        while len(monthly_values) < 12:
            monthly_values.append(0.0)
        result[matched_key] = monthly_values[:12]

    return result


# ── Effort classification ─────────────────────────────────────────────────────


def _classify_effort_hours(hours: float) -> str:
    """Classify average monthly hours into an effort level label."""
    for threshold, label in _EFFORT_HOURS_THRESHOLDS:
        if hours <= threshold:
            return label
    return "aggressive"


# ── Apply breakdown to bundle ─────────────────────────────────────────────────


def _apply_breakdown_to_bundle(bundle: dict, breakdown: dict) -> None:
    """Map breakdown monthly hours into per_focus entries."""
    per_focus = bundle["per_focus"]

    def _avg_nonzero(values: list) -> float:
        nonzero = [v for v in values if v and v != 0.0]
        return sum(nonzero) / len(nonzero) if nonzero else 0.0

    # Consulting hours → 70% strategy, 30% analytics
    consulting_avg = _avg_nonzero(breakdown.get("consulting", []))
    strategy_hours = consulting_avg * 0.70
    analytics_hours = consulting_avg * 0.30
    per_focus["strategy"]["monthly_hours"] = round(strategy_hours, 2)
    per_focus["strategy"]["effort_level"] = _classify_effort_hours(strategy_hours)
    per_focus["analytics"]["monthly_hours"] = round(analytics_hours, 2)
    per_focus["analytics"]["effort_level"] = _classify_effort_hours(analytics_hours)

    # Technical hours → 70% technical, 30% on_page
    technical_avg = _avg_nonzero(breakdown.get("technical", []))
    tech_hours = technical_avg * 0.70
    on_page_hours = technical_avg * 0.30
    per_focus["technical"]["monthly_hours"] = round(tech_hours, 2)
    per_focus["technical"]["effort_level"] = _classify_effort_hours(tech_hours)
    per_focus["on_page"]["monthly_hours"] = round(on_page_hours, 2)
    per_focus["on_page"]["effort_level"] = _classify_effort_hours(on_page_hours)

    # Content hours → content
    content_avg = _avg_nonzero(breakdown.get("content", []))
    per_focus["content"]["monthly_hours"] = round(content_avg, 2)
    per_focus["content"]["effort_level"] = _classify_effort_hours(content_avg)

    # Link hours → off_page
    link_avg = _avg_nonzero(breakdown.get("link", []))
    per_focus["off_page"]["monthly_hours"] = round(link_avg, 2)
    per_focus["off_page"]["effort_level"] = _classify_effort_hours(link_avg)


# ── Content plan parser ───────────────────────────────────────────────────────


def _parse_content_plan(ws) -> list[dict]:
    """Parse the '4. Content' worksheet into a list of content item dicts.

    Header is at row 7; data starts at row 8.
    Columns (0-indexed): A=0 Month#, B=1 Month Name, C=2 URL, D=3 Title,
    E=4 Focus, F=5 Priority, G=6 Content Type, H=7 Word Count, I=8 SEO Hours
    """
    items = []
    for row in ws.iter_rows(min_row=8, values_only=True):
        if not row:
            continue
        # URL is at col C (index 2) — skip empty rows
        url_val = row[2] if len(row) > 2 else None
        if url_val is None or str(url_val).strip() == "":
            continue

        month = int(row[0]) if row[0] and isinstance(row[0], (int, float)) else None
        month_name = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        url = str(url_val).strip()
        title = str(row[3]).strip() if len(row) > 3 and row[3] else ""
        focus = str(row[4]).strip() if len(row) > 4 and row[4] else ""
        priority = str(row[5]).strip() if len(row) > 5 and row[5] else ""
        content_desc = str(row[6]).strip() if len(row) > 6 and row[6] else ""
        try:
            word_count = int(row[7]) if len(row) > 7 and row[7] is not None else 0
        except (ValueError, TypeError):
            word_count = 0
        try:
            seo_hours = float(row[8]) if len(row) > 8 and row[8] is not None else 0.0
        except (ValueError, TypeError):
            seo_hours = 0.0

        content_desc_lower = content_desc.lower()
        is_new_page = "new page" in content_desc_lower
        is_faq = "faq" in content_desc_lower

        if is_new_page:
            content_type = "new_page"
        elif is_faq:
            content_type = "faq"
        else:
            content_type = "optimisation"

        items.append(
            {
                "month": month,
                "month_name": month_name,
                "url": url,
                "title": title,
                "focus": focus,
                "priority": priority,
                "content_type": content_type,
                "word_count": word_count,
                "seo_hours": seo_hours,
            }
        )
    return items


# ── Task sheet parser ─────────────────────────────────────────────────────────


def _parse_task_sheet(ws) -> list[dict]:
    """Parse a Consulting/Technical/Links worksheet (header row 1, data row 2+).

    Returns a list of dicts with keys: task, focus, occurrence, hours.
    """
    tasks = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        # Skip fully-blank rows
        if all(v is None for v in row):
            continue
        task_val = row[0] if len(row) > 0 else None
        focus_val = row[1] if len(row) > 1 else None
        occ_val = row[2] if len(row) > 2 else None
        hrs_val = row[3] if len(row) > 3 else None
        try:
            hours = float(hrs_val) if hrs_val is not None else 0.0
        except (ValueError, TypeError):
            hours = 0.0
        tasks.append(
            {
                "task": str(task_val).strip() if task_val is not None else "",
                "focus": str(focus_val).strip() if focus_val is not None else "",
                "occurrence": str(occ_val).strip() if occ_val is not None else "",
                "hours": hours,
            }
        )
    return tasks


# ── Timeline finalisation ─────────────────────────────────────────────────────


def _finalise_timeline(bundle: dict) -> None:
    """Compute timeline metadata and store it in bundle['timeline']."""
    content_plan = bundle.get("content_plan", [])
    months_with_content = [
        item["month"]
        for item in content_plan
        if item.get("month") and isinstance(item["month"], (int, float))
    ]
    last_month = int(max(months_with_content)) if months_with_content else 12

    consulting_tasks = bundle.get("_consulting_tasks", [])
    has_strategy_review = any(
        "strategy review" in (t.get("task") or "").lower() for t in consulting_tasks
    )

    strategy_restart_month: int | None = None
    if last_month < 12 and has_strategy_review:
        strategy_restart_month = last_month + 1

    bundle["timeline"] = {
        "months_covered": 12,
        "strategy_restart_month": strategy_restart_month,
        "has_launch_dates": bool(months_with_content),
    }

    # Clean up the private key
    bundle.pop("_consulting_tasks", None)


# ── Global rollup finalisation ────────────────────────────────────────────────


def _finalise_global_rollup(bundle: dict) -> None:
    """Compute a global rollup across all per_focus entries."""
    per_focus = bundle.get("per_focus", {})

    total_monthly_hours = sum(f.get("monthly_hours", 0.0) for f in per_focus.values())

    # Max effort across all focus areas
    effort_order = ["light", "moderate", "aggressive"]
    effort_levels = [f.get("effort_level", "moderate") for f in per_focus.values() if f.get("monthly_hours", 0.0) > 0]
    if effort_levels:
        max_effort = max(effort_levels, key=lambda e: effort_order.index(e) if e in effort_order else 0)
    else:
        max_effort = "moderate"

    # Content cadence: number of content items per month from content_plan
    content_plan = bundle.get("content_plan", [])
    new_pages = [item for item in content_plan if item.get("content_type") == "new_page"]
    # Deduplicate by month to get posts per month average
    months_seen: dict[int, int] = {}
    for item in new_pages:
        m = item.get("month")
        if m:
            months_seen[m] = months_seen.get(m, 0) + 1
    content_cadence = round(sum(months_seen.values()) / len(months_seen)) if months_seen else 0

    # Maintenance coverage: fraction of portfolio covered by technical + on_page
    tech_hours = per_focus.get("technical", {}).get("monthly_hours", 0.0)
    on_page_hours = per_focus.get("on_page", {}).get("monthly_hours", 0.0)
    maintenance_hours = tech_hours + on_page_hours
    maintenance_coverage = round(min(maintenance_hours / max(total_monthly_hours, 1.0), 1.0), 2)

    bundle["global_rollup"] = {
        "total_monthly_hours": round(total_monthly_hours, 2),
        "effort_level": max_effort,
        "maintenance_coverage": maintenance_coverage,
        "content_cadence": content_cadence,
        "positional_effort_level": per_focus.get("on_page", {}).get("effort_level", "moderate"),
    }


# ── Main parser ───────────────────────────────────────────────────────────────


def parse_pattern_native(raw_bytes: bytes) -> dict:
    """Parse a Pattern-native xlsx roadmap into a v2 bundle dict.

    Args:
        raw_bytes: Raw bytes of the uploaded xlsx file.

    Returns:
        A bundle dict matching the v2 schema used by engine/assumptions.py.
    """
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
    sheet_names = wb.sheetnames

    bundle: dict = {
        "schema_version": "2.0",
        "format_detected": "pattern_native",
        "extraction_method": "deterministic",
        "source_summary": {
            "sheets_parsed": [],
            "parsing_confidence": 0.95,
        },
        "client_metadata": {},
        "per_focus": _empty_per_focus(),
        "content_plan": [],
        "timeline": {},
        "global_rollup": {},
        "recommendations": [],
        "gaps": [],
    }

    if "1. Client Detail" in sheet_names:
        bundle["client_metadata"] = _parse_client_detail(wb["1. Client Detail"])
        bundle["source_summary"]["sheets_parsed"].append("1. Client Detail")

    if "Breakdown" in sheet_names:
        breakdown = _parse_breakdown(wb["Breakdown"])
        _apply_breakdown_to_bundle(bundle, breakdown)
        bundle["source_summary"]["sheets_parsed"].append("Breakdown")

    if "4. Content" in sheet_names:
        bundle["content_plan"] = _parse_content_plan(wb["4. Content"])
        bundle["source_summary"]["content_launches_detected"] = len(bundle["content_plan"])
        bundle["source_summary"]["sheets_parsed"].append("4. Content")

    if "2. Consulting" in sheet_names:
        consulting_tasks = _parse_task_sheet(wb["2. Consulting"])
        bundle["_consulting_tasks"] = consulting_tasks
        bundle["source_summary"]["sheets_parsed"].append("2. Consulting")

    if "3. Technical" in sheet_names:
        _parse_task_sheet(wb["3. Technical"])  # parse but don't store separately for now
        bundle["source_summary"]["sheets_parsed"].append("3. Technical")

    if "5. Links" in sheet_names:
        _parse_task_sheet(wb["5. Links"])
        bundle["source_summary"]["sheets_parsed"].append("5. Links")

    _finalise_timeline(bundle)
    _finalise_global_rollup(bundle)
    return bundle


# ── Legacy wrappers ───────────────────────────────────────────────────────────


def wrap_legacy_task_table_as_bundle(legacy_result: dict) -> dict:
    """Wrap a legacy parse_task_table() output dict into a v2 bundle.

    Args:
        legacy_result: Dict with keys: content_cadence, effort_level,
            maintenance_coverage (and optional _monthly_hours).

    Returns:
        A v2 bundle with parsing_confidence = 0.7.
    """
    effort = legacy_result.get("effort_level", "moderate")
    cadence = legacy_result.get("content_cadence", 4)
    maintenance = legacy_result.get("maintenance_coverage", 0.0)
    monthly_hours = legacy_result.get("_monthly_hours", 0.0)

    per_focus = _empty_per_focus()
    # Apply effort to content, on_page, off_page (the focus areas that the
    # task-table loader addresses)
    for area in ("content", "on_page", "off_page"):
        per_focus[area]["effort_level"] = effort

    bundle: dict = {
        "schema_version": "2.0",
        "format_detected": "task_table",
        "extraction_method": "deterministic",
        "source_summary": {
            "sheets_parsed": [],
            "parsing_confidence": 0.7,
        },
        "client_metadata": {},
        "per_focus": per_focus,
        "content_plan": [],
        "timeline": {
            "months_covered": 12,
            "strategy_restart_month": None,
            "has_launch_dates": False,
        },
        "global_rollup": {
            "total_monthly_hours": float(monthly_hours),
            "effort_level": effort,
            "maintenance_coverage": float(maintenance),
            "content_cadence": int(cadence),
            "positional_effort_level": effort,
        },
        "recommendations": [],
        "gaps": [],
    }
    return bundle


def wrap_legacy_param_table_as_bundle(legacy_result: dict) -> dict:
    """Wrap a legacy parse_param_table() output dict into a v2 bundle.

    Args:
        legacy_result: Dict with optional keys: content_cadence, effort_level,
            maintenance_coverage.

    Returns:
        A v2 bundle with parsing_confidence = 0.5.
    """
    effort = legacy_result.get("effort_level", "moderate")
    cadence = legacy_result.get("content_cadence", 4)
    maintenance = legacy_result.get("maintenance_coverage", 0.0)

    per_focus = _empty_per_focus()

    bundle: dict = {
        "schema_version": "2.0",
        "format_detected": "param_table",
        "extraction_method": "deterministic",
        "source_summary": {
            "sheets_parsed": [],
            "parsing_confidence": 0.5,
        },
        "client_metadata": {},
        "per_focus": per_focus,
        "content_plan": [],
        "timeline": {
            "months_covered": 12,
            "strategy_restart_month": None,
            "has_launch_dates": False,
        },
        "global_rollup": {
            "total_monthly_hours": 0.0,
            "effort_level": effort,
            "maintenance_coverage": float(maintenance),
            "content_cadence": int(cadence),
            "positional_effort_level": effort,
        },
        "recommendations": [],
        "gaps": [],
    }
    return bundle
