"""Bi Frost client wrapper — follows the Bi Frost integration skill pattern."""
from __future__ import annotations

import json
import os
from pathlib import Path

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
        try:
            return call(client, attempt, system, user, **kwargs), attempt
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"All models failed. Tried: {attempts}. Last error: {last_error}"
    )
