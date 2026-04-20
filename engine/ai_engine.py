import json
import logging
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd

from engine.transform_spec import apply_transform
from utils.bifrost import call as _bfcall
from utils.bifrost import call_with_fallback as _bfcall_with_fallback
from utils.bifrost import get_client as _bfget_client

_logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def get_bifrost_client(api_key: str | None = None) -> object | None:
    """Return Bi Frost client. Thin wrapper kept for backward compatibility."""
    return _bfget_client(api_key)


# ── Config helpers ───────────────────────────────────────────────────────────


def _load_models_config() -> dict:
    with open(_CONFIG_DIR / "models.json") as f:
        return json.load(f)


def get_model_options() -> list[dict]:
    """Return the list of available models from config/models.json."""
    return _load_models_config()["models"]


def get_default_model() -> str:
    return _load_models_config()["default"]


def get_fallback_chain() -> list[str]:
    return _load_models_config()["fallback_chain"]


def get_model_for_feature(feature: str, user_override: str | None = None) -> str:
    """Resolve which model to use for a given AI feature.

    Resolution order:
      1. user_override (from sidebar picker) — wins if not None
      2. features.{feature} in config/models.json — feature-specific default
      3. default in config/models.json — global default
    """
    if user_override:
        return user_override
    cfg = _load_models_config()
    return cfg.get("features", {}).get(feature, cfg["default"])


# ── Prompt loader ────────────────────────────────────────────────────────────


def _load_prompt(name: str) -> tuple[str, Template]:
    """Load a prompt file split by --- into (system_instructions, user_template).

    User templates use $variable substitution (string.Template).
    """
    text = (_PROMPT_DIR / f"{name}.txt").read_text()
    parts = text.split("---", 1)
    system = parts[0].strip()
    user = Template(parts[1].strip()) if len(parts) > 1 else Template("")
    return system, user


# ── LLM helpers ──────────────────────────────────────────────────────────────


def _parse_llm_json(text: str):
    """Strip markdown fences and parse JSON from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


def _call_bifrost(
    client: "object",
    model: str,
    instructions: str,
    user_input: str,
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> str:
    """Thin wrapper around utils.bifrost.call for backward compatibility."""
    return _bfcall(client, model, instructions, user_input, temperature, max_tokens)


def generate_with_fallback(
    client: "object",
    model: str,
    instructions: str,
    user_input: str,
    **kwargs,
) -> tuple[str, str]:
    """Call Bi Frost with automatic fallback through the model chain.

    Returns:
        (response_text, model_used) tuple.
    """
    return _bfcall_with_fallback(client, model, instructions, user_input, **kwargs)


# ── AI features ──────────────────────────────────────────────────────────────


def cluster_keywords(
    client: "object",
    keywords: list[str],
    model: str | None = None,
) -> tuple[dict, str]:
    """Group keywords into topical clusters using AI.

    Returns:
        (clusters_dict, model_used) tuple.
    """
    resolved = get_model_for_feature("cluster_keywords", user_override=model)
    system, user_tmpl = _load_prompt("cluster_keywords")
    kw_list = "\n".join(f"- {kw}" for kw in keywords[:200])
    user_input = user_tmpl.substitute(kw_list=kw_list)

    text, used_model = generate_with_fallback(
        client, resolved, system, user_input, temperature=0.3,
    )
    return _parse_llm_json(text), used_model


def check_cannibalization(
    client: "object",
    keywords: list[str],
    existing_urls: list[str],
    model: str | None = None,
) -> tuple[list[dict], str]:
    """Check if proposed keywords conflict with existing URLs.

    Returns:
        (results_list, model_used) tuple.
    """
    resolved = get_model_for_feature("check_cannibalization", user_override=model)
    system, user_tmpl = _load_prompt("check_cannibalization")
    kw_list = "\n".join(f"- {kw}" for kw in keywords[:100])
    url_list = "\n".join(f"- {url}" for url in existing_urls[:100])
    user_input = user_tmpl.substitute(kw_list=kw_list, url_list=url_list)

    text, used_model = generate_with_fallback(
        client, resolved, system, user_input, temperature=0.2,
    )
    return _parse_llm_json(text), used_model


def generate_content_roadmap(
    client: "object",
    keyword_df: pd.DataFrame,
    months: int,
    model: str | None = None,
    existing_roadmap_csv: str | None = None,
) -> tuple[list[dict], str]:
    """Generate an AI-powered content roadmap from keyword forecast data.

    Returns:
        (roadmap_list, model_used) tuple.
    """
    cols = ["keyword", "volume", "kd", "tier", "intent", "efficiency_score",
            "estimated_monthly_traffic", "publish_month"]
    available = [c for c in cols if c in keyword_df.columns]
    summary_df = keyword_df[available].head(50)
    data_str = summary_df.to_csv(index=False)

    existing_ctx = ""
    if existing_roadmap_csv:
        existing_ctx = (
            "\n\nExisting roadmap for context (avoid duplicating these topics):\n"
            + existing_roadmap_csv[:3000]
        )

    resolved = get_model_for_feature("content_roadmap", user_override=model)
    system, user_tmpl = _load_prompt("content_roadmap")
    user_input = user_tmpl.substitute(
        data_str=data_str, existing_ctx=existing_ctx, months=months,
    )

    text, used_model = generate_with_fallback(
        client, resolved, system, user_input, temperature=0.4,
    )
    return _parse_llm_json(text), used_model


def detect_brand_terms(
    client: "object",
    domain: str,
    keywords: list[str],
    model: str | None = None,
) -> tuple[dict, str]:
    """Detect branded keywords from domain name + keyword list using AI.

    Args:
        client: Bi Frost OpenAI-compatible client.
        domain: The website domain (e.g. "example.com").
        keywords: Top keywords by volume (up to 100 used).
        model: Model ID from config/models.json.

    Returns:
        (result_dict, model_used) where result_dict has keys:
            brand_terms: list[str]
            confidence: float
            reasoning: str
    """
    resolved = get_model_for_feature("brand_detection", user_override=model)
    system, user_tmpl = _load_prompt("detect_brand")
    kw_sample = "\n".join(f"- {kw}" for kw in keywords[:100])
    user_input = user_tmpl.substitute(domain=domain, keyword_sample=kw_sample)
    text, used_model = generate_with_fallback(
        client, resolved, system, user_input, temperature=0.2,
    )
    return _parse_llm_json(text), used_model


# ── AI Data Transformation ──────────────────────────────────────────────────


TRAFFIC_TARGET_FORMAT = """
Required columns (exact names):
- date: datetime (YYYY-MM-DD format, first of each month)
- traffic: integer (total organic sessions per month)

Optional columns:
- revenue: float (total organic revenue per month)
- transactions: integer (total organic transactions per month)
- aov: float (average order value per month)
- cr: float (conversion rate as percentage, e.g. 2.5)

Rules:
- Aggregate all organic channels (Organic Search, Organic Shopping, Organic Video, etc.) into a single row per month
- If data has financial year columns (e.g. FY24, FY25), convert "Year month" like "Jan 2024" to date 2024-01-01
- Sum sessions/traffic per month across all organic channel types
- ONLY include revenue, transactions, aov, cr in result if those values actually exist in the source data
- Never reference a column that does not exist in the source DataFrame
- Calculate aov = revenue / transactions and cr = (transactions / traffic) * 100 where possible
- Sort by date ascending
- One row per month
"""

KEYWORDS_TARGET_FORMAT = """
Required columns (exact names):
- keyword: string (the search term)
- volume: integer (monthly search volume, must be > 0)
- kd: integer (keyword difficulty 0-100)

Rules:
- Remove any rows where volume is 0 or missing
- Remove duplicate keywords (keep first occurrence)
- If difficulty is a percentage string like "45%", convert to integer 45
"""


def transform_data(
    client: "object",
    df: pd.DataFrame,
    target_format: str,
    model: str | None = None,
) -> tuple[str, str]:
    """Use AI to generate Python code that transforms uploaded data.

    Returns:
        (code_string, model_used) tuple.
    """
    sample = df.head(15).to_csv(index=False)
    col_info = f"Columns: {list(df.columns)}\nShape: {df.shape}\nDtypes:\n{df.dtypes.to_string()}"

    resolved = get_model_for_feature("transform_data", user_override=model)
    system, user_tmpl = _load_prompt("transform_data")
    user_input = user_tmpl.substitute(
        col_info=col_info, sample=sample, target_format=target_format,
    )

    text, used_model = generate_with_fallback(
        client, resolved, system, user_input, temperature=0.1, max_tokens=2000,
    )
    return _strip_code_fences(text), used_model


_BLOCKED_CODE_PATTERNS = [
    "import os", "import sys", "import subprocess", "import socket",
    "import shutil", "import pathlib", "import tempfile", "import glob",
    "__import__", "__builtins__", "open(", "eval(", "exec(",
    "os.system", "os.popen", "os.environ", "subprocess.", "shutil.",
    "globals()", "locals()", "compile(",
]

_SAFE_BUILTINS = {
    "len": len, "range": range, "int": int, "float": float, "str": str,
    "list": list, "dict": dict, "tuple": tuple, "bool": bool,
    "zip": zip, "enumerate": enumerate, "sorted": sorted,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "isinstance": isinstance, "print": print, "None": None,
    "True": True, "False": False,
}


def apply_transform_spec(df: pd.DataFrame, raw_text: str) -> pd.DataFrame:
    """Parse a JSON transform spec from LLM output and apply it safely.

    If the text is not valid JSON (e.g. LLM returned Python code instead),
    falls back to execute_transform for backward compatibility during
    the transition period.

    Returns the transformed DataFrame.
    """
    text = raw_text.strip()
    try:
        spec = json.loads(text)
        if not isinstance(spec, dict):
            raise ValueError("Spec is not a JSON object")
        _logger.info("Applying JSON transform spec (version %s)", spec.get("version", "?"))
        return apply_transform(df, spec)
    except (json.JSONDecodeError, ValueError):
        _logger.warning(
            "LLM returned non-JSON output; falling back to exec()-based transform. "
            "Update the model or prompt if this happens repeatedly."
        )
        return execute_transform(df, text)


def execute_transform(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Execute AI-generated transform code with restricted builtins.

    Kept as fallback for the transition period while models adapt to
    the JSON spec prompt. See engine/transform_spec.py for the preferred path.
    """
    for pattern in _BLOCKED_CODE_PATTERNS:
        if pattern in code:
            raise ValueError(f"Generated code contains disallowed pattern: {pattern!r}")

    namespace = {"df": df.copy(), "pd": pd, "np": np, "__builtins__": _SAFE_BUILTINS}
    exec(code, namespace)  # noqa: S102
    result = namespace.get("result")
    if result is None:
        raise ValueError("Transform code did not produce a 'result' variable")
    if not isinstance(result, pd.DataFrame):
        raise ValueError(f"Expected DataFrame, got {type(result).__name__}")
    return result
