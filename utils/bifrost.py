"""Bi Frost client wrapper — follows the Bi Frost integration skill pattern."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("bifrost")

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]


BIFROST_BASE_URL = "https://bifrost.pattern.com/v1"

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "models.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def _get_fallback_chain() -> list[str]:
    return _load_config()["fallback_chain"]


def get_api_key(user_key: str | None = None) -> str | None:
    """Resolve the Bi Frost key — user input → Streamlit secrets → env var."""
    if user_key:
        return user_key
    try:
        import streamlit as st
        if "BIFROST_API_KEY" in st.secrets and st.secrets["BIFROST_API_KEY"]:
            return st.secrets["BIFROST_API_KEY"]
        if "BIFROST_KEY" in st.secrets and st.secrets["BIFROST_KEY"]:
            return st.secrets["BIFROST_KEY"]
    except Exception:
        pass
    return os.environ.get("BIFROST_API_KEY") or os.environ.get("BIFROST_KEY")


def get_client(api_key: str | None = None) -> OpenAI | None:
    """Return an OpenAI-compatible Bi Frost client, or None if no key available."""
    if OpenAI is None:
        return None
    key = get_api_key(api_key)
    if not key:
        return None
    base_url = BIFROST_BASE_URL
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    return OpenAI(base_url=base_url, api_key=key)


# ── Cost estimation ──────────────────────────────────────────────────────────

# Rough AUD per 1M tokens (input + output averaged) — refresh quarterly.
# These are estimates; actual Bi Frost billing may differ.
MODEL_RATES_AUD_PER_MTOK: dict[str, float] = {
    "anthropic/claude-haiku-4-5": 1.50,
    "anthropic/claude-sonnet-4-6": 6.00,
    "openai/gpt-4.1": 5.00,
    "openai/gpt-5": 15.00,
}

_WARNED_UNKNOWN_MODELS: set[str] = set()


def estimate_cost_aud(model: str, input_chars: int, output_chars: int) -> float:
    """Estimate AUD cost for a single call based on character counts."""
    if model not in MODEL_RATES_AUD_PER_MTOK and model not in _WARNED_UNKNOWN_MODELS:
        logger.warning(json.dumps({
            "event": "unknown_model_rate",
            "model": model,
            "fallback_rate": 5.0,
        }))
        _WARNED_UNKNOWN_MODELS.add(model)
    rate = MODEL_RATES_AUD_PER_MTOK.get(model, 5.0)
    tokens = (input_chars + output_chars) // 4
    return (tokens / 1_000_000) * rate


def _accumulate_cost(model: str, input_chars: int, output_chars: int) -> None:
    """Add estimated call cost to the Streamlit session state accumulator."""
    cost = estimate_cost_aud(model, input_chars, output_chars)
    try:
        import streamlit as st
        current = st.session_state.get("session_cost_aud", 0.0)
        st.session_state["session_cost_aud"] = current + cost
    except Exception:
        pass  # not running inside Streamlit


# ── API calls ─────────────────────────────────────────────────────────────────


def call(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.3,
    max_tokens: int = 4000,
) -> str:
    """Single synchronous call. Prefer call_with_fallback in application code."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content


def call_with_fallback(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    fallback_chain: list[str] | None = None,
    **kwargs,
) -> tuple[str, str]:
    """Try model, then walk fallback_chain on error. Returns (response_text, model_used)."""
    if fallback_chain is None:
        fallback_chain = _get_fallback_chain()
    attempts = [model] + [m for m in fallback_chain if m != model]
    last_error: Exception | None = None
    for attempt in attempts:
        start = time.perf_counter()
        try:
            response_text = call(client, attempt, system, user, **kwargs)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info(json.dumps({
                "event": "bifrost_call",
                "model_requested": model,
                "model_used": attempt,
                "fell_back": attempt != model,
                "elapsed_ms": elapsed_ms,
                "user_tokens_est": len(user) // 4,
                "system_tokens_est": len(system) // 4,
                "response_chars": len(response_text),
                "success": True,
            }))
            _accumulate_cost(attempt, len(system) + len(user), len(response_text))
            return response_text, attempt
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(json.dumps({
                "event": "bifrost_call",
                "model_requested": model,
                "model_attempted": attempt,
                "elapsed_ms": elapsed_ms,
                "error": str(exc)[:200],
                "success": False,
            }))
            last_error = exc
    raise RuntimeError(
        f"All models failed. Tried: {attempts}. Last error: {last_error}"
    )
