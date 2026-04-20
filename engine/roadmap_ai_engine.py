"""AI-powered roadmap extraction engine.

Converts an uploaded xlsx/csv roadmap file into a structured per-focus-area bundle
using a Bi Frost LLM call. The bundle maps cleanly to the per-focus assumption keys
in engine/assumptions.py via _detect_from_roadmap_bundle().

Pure Python — no Streamlit imports. Session-state caching is handled by the caller
(page passes `cache=st.session_state.setdefault("roadmap_ai_cache", {})`).
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone

import pandas as pd

from engine.ai_engine import _load_prompt, _parse_llm_json, generate_with_fallback

# ── Schema constant ───────────────────────────────────────────────────────────

ROADMAP_BUNDLE_SCHEMA: dict = {
    "schema_version": "1.0",
    "extraction_date": "<ISO timestamp>",
    "source_summary": {
        "total_tasks_detected": 0,
        "focus_areas_detected": [],
        "timeline_months_covered": 12,
        "parsing_confidence": 0.9,
    },
    "per_focus": {
        "content": {
            "effort_level": "moderate",
            "monthly_hours": 0.0,
            "cadence": 0,
            "task_count": 0,
            "tasks": [
                {"name": "<task name>", "hours": 0, "occurrence": "<Monthly|Quarterly|…>", "contribution": "<primary|supporting>"},
            ],
        },
        "technical": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "on_page": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "off_page": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "local": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "analytics": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
        "strategy": {"effort_level": "moderate", "monthly_hours": 0.0, "cadence": 0, "task_count": 0, "tasks": []},
    },
    "timeline": {
        "months_covered": 12,
        "phasing_notes": "",
        "has_launch_dates": False,
    },
    "global_rollup": {
        "total_monthly_hours": 0.0,
        "effort_level": "moderate",
        "maintenance_coverage": 0.0,
        "content_cadence": 0,
        "positional_effort_level": "moderate",
    },
    "recommendations": [
        {"severity": "info", "message": "<recommendation text>"},
    ],
    "gaps": [
        {"focus_area": "<focus area>", "note": "<gap note>"},
    ],
}


# ── Internal helpers ──────────────────────────────────────────────────────────


def _cache_key(raw_bytes: bytes, nl_correction: str | None, model: str) -> str:
    h = hashlib.sha256()
    h.update(raw_bytes)
    h.update((nl_correction or "").encode())
    h.update(model.encode())
    return h.hexdigest()[:16]


def _read_roadmap_file(raw_bytes: bytes, file_extension: str) -> pd.DataFrame:
    """Parse roadmap file bytes into a DataFrame."""
    buf = io.BytesIO(raw_bytes)
    ext = file_extension.lower().lstrip(".")

    if ext in ("xlsx", "xls"):
        try:
            df = pd.read_excel(buf, engine="openpyxl")
        except Exception as exc:
            raise ValueError(f"Cannot read Excel file: {exc}") from exc
    elif ext == "tsv":
        try:
            df = pd.read_csv(buf, sep="\t")
        except Exception as exc:
            raise ValueError(f"Cannot read TSV file: {exc}") from exc
    else:
        # csv or unknown — try Excel then CSV
        try:
            df = pd.read_excel(buf, engine="openpyxl")
        except Exception:
            buf.seek(0)
            try:
                df = pd.read_csv(buf)
            except Exception as exc:
                raise ValueError(f"Cannot parse roadmap file: {exc}") from exc

    if df.empty:
        raise ValueError("Roadmap file is empty or could not be read")
    return df


def _df_to_markdown(df: pd.DataFrame, max_chars: int = 4000) -> tuple[str, bool]:
    """Convert DataFrame to a compact markdown table, truncated to max_chars."""
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows_md = [
        "| " + " | ".join(str(v) for v in row.values) + " |"
        for _, row in df.iterrows()
    ]
    full = "\n".join([header, sep] + rows_md)
    if len(full) <= max_chars:
        return full, False
    return full[:max_chars] + "\n... [truncated]", True


# ── Public API ────────────────────────────────────────────────────────────────


def extract_roadmap_with_ai(
    client,
    raw_roadmap_bytes: bytes,
    file_extension: str,
    nl_correction: str | None = None,
    previous_extraction: dict | None = None,
    model: str = "openai/gpt-4o-mini",
    cache: dict | None = None,
) -> tuple[dict, str]:
    """Extract structured roadmap bundle from a raw xlsx/csv file using AI.

    Args:
        client: Bi Frost OpenAI-compatible client.
        raw_roadmap_bytes: The uploaded file contents.
        file_extension: "xlsx" | "xls" | "csv" | "tsv".
        nl_correction: User's natural-language correction text, if any.
        previous_extraction: Prior extraction dict for re-run context.
        model: Bi Frost model ID.
        cache: Dict for caching results (pass session_state["roadmap_ai_cache"]).
            Identical inputs return the cached result without an AI call.

    Returns:
        (bundle, used_model) where bundle matches ROADMAP_BUNDLE_SCHEMA.
    """
    key = _cache_key(raw_roadmap_bytes, nl_correction, model)
    if cache is not None and key in cache:
        return cache[key]["bundle"], cache[key]["model"]

    df = _read_roadmap_file(raw_roadmap_bytes, file_extension)
    roadmap_md, truncated = _df_to_markdown(df, max_chars=4000)

    system, user_tmpl = _load_prompt("extract_roadmap")
    schema_str = json.dumps(ROADMAP_BUNDLE_SCHEMA, indent=2)

    if nl_correction and previous_extraction:
        correction_ctx = (
            f'User correction to previous extraction:\n"{nl_correction}"\n\n'
            f"Previous extraction (apply the correction above to this):\n"
            f"{json.dumps(previous_extraction, indent=2)}"
        )
    elif nl_correction:
        correction_ctx = f'User correction:\n"{nl_correction}"'
    else:
        correction_ctx = ""

    user_input = user_tmpl.substitute(
        roadmap_markdown=roadmap_md,
        correction_context=correction_ctx,
        schema=schema_str,
    )

    text, used_model = generate_with_fallback(
        client, model, system, user_input, temperature=0.1, max_tokens=3000,
    )
    bundle = _parse_llm_json(text)

    # Stamp extraction date
    bundle["extraction_date"] = datetime.now(timezone.utc).isoformat()

    # Downgrade confidence when input was truncated
    if truncated and "source_summary" in bundle:
        conf = bundle["source_summary"].get("parsing_confidence", 0.9)
        bundle["source_summary"]["parsing_confidence"] = min(float(conf), 0.75)

    if cache is not None:
        cache[key] = {"bundle": bundle, "model": used_model}

    return bundle, used_model


def estimate_extraction_tokens(
    roadmap_md: str,
    correction_ctx: str = "",
    schema_str: str = "",
) -> int:
    """Rough token estimate for a roadmap extraction call (4 chars ≈ 1 token)."""
    chars = len(roadmap_md) + len(correction_ctx) + len(schema_str) + 1500  # system prompt overhead
    return chars // 4
