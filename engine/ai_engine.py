import json
import os

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_bifrost_client(api_key: str | None = None) -> "OpenAI | None":
    """Get Bi Frost OpenAI-compatible client.

    Args:
        api_key: Bi Frost virtual key. Falls back to Streamlit secrets,
                 then BIFROST_API_KEY env var.

    Returns:
        OpenAI client configured for Bi Frost, or None if unavailable.
    """
    if OpenAI is None:
        return None
    key = api_key if api_key else None
    if not key:
        try:
            import streamlit as st
            if "BIFROST_API_KEY" in st.secrets:
                key = st.secrets["BIFROST_API_KEY"] or None
        except Exception:
            pass
    if not key:
        key = os.environ.get("BIFROST_API_KEY")
    if not key:
        return None
    return OpenAI(base_url="https://bifrost.pattern.com/openai", api_key=key)


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


def _call_bifrost(client: "OpenAI", model: str, instructions: str, user_input: str,
                  temperature: float = 0.3, max_tokens: int = 4000) -> str:
    """Call Bi Frost using the Responses API and return the output text."""
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=user_input,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    return response.output_text


def cluster_keywords(
    client: "OpenAI",
    keywords: list[str],
    model: str = "openai/gpt-5.4-mini",
) -> dict:
    """Group keywords into topical clusters using AI."""
    kw_list = "\n".join(f"- {kw}" for kw in keywords[:200])

    text = _call_bifrost(
        client, model,
        instructions=(
            "You are an SEO expert. Group the given keywords into topical clusters. "
            "Each cluster should represent one content piece or page. "
            "Return valid JSON only, no markdown fences."
        ),
        user_input=(
            f"Group these SEO keywords into topical clusters:\n\n{kw_list}\n\n"
            'Return JSON: {"clusters": [{"name": "cluster name", '
            '"keywords": ["kw1", "kw2"], "suggested_title": "Article Title"}]}'
        ),
        temperature=0.3,
    )

    return _parse_llm_json(text)


def check_cannibalization(
    client: "OpenAI",
    keywords: list[str],
    existing_urls: list[str],
    model: str = "openai/gpt-5.4-mini",
) -> list[dict]:
    """Check if proposed keywords conflict with existing URLs."""
    kw_list = "\n".join(f"- {kw}" for kw in keywords[:100])
    url_list = "\n".join(f"- {url}" for url in existing_urls[:100])

    text = _call_bifrost(
        client, model,
        instructions=(
            "You are an SEO cannibalization expert. Analyze whether proposed keywords "
            "would compete with existing URLs. Return valid JSON only, no markdown fences."
        ),
        user_input=(
            f"Proposed keywords:\n{kw_list}\n\n"
            f"Existing URLs:\n{url_list}\n\n"
            "For each keyword, assess cannibalization risk. Return JSON array:\n"
            '[{"keyword": "...", "conflicting_url": "..." or null, '
            '"risk": "high"|"medium"|"low"|"none", '
            '"recommendation": "brief action item"}]'
        ),
        temperature=0.2,
    )

    return _parse_llm_json(text)


def generate_content_roadmap(
    client: "OpenAI",
    keyword_df: pd.DataFrame,
    months: int,
    model: str = "openai/gpt-5.4-mini",
) -> list[dict]:
    """Generate an AI-powered content roadmap from keyword forecast data."""
    cols = ["keyword", "volume", "kd", "tier", "intent", "efficiency_score",
            "estimated_monthly_traffic", "publish_month"]
    available = [c for c in cols if c in keyword_df.columns]
    summary_df = keyword_df[available].head(50)
    data_str = summary_df.to_csv(index=False)

    text = _call_bifrost(
        client, model,
        instructions=(
            "You are an SEO content strategist. Create a prioritized content roadmap "
            "from keyword forecast data. Consider: publish highest-efficiency keywords first, "
            "cluster related keywords into single posts, flag informational keywords at risk "
            "from AI Overviews. Return valid JSON only, no markdown fences."
        ),
        user_input=(
            f"Keyword forecast data (top 50 by efficiency):\n\n{data_str}\n\n"
            f"Create a {months}-month content roadmap. Return JSON:\n"
            '[{"month": 1, "content_pieces": [{"title": "...", '
            '"target_keywords": ["kw1", "kw2"], "estimated_traffic": 1000, '
            '"priority": "high"|"medium"|"low", "notes": "brief note"}]}]'
        ),
        temperature=0.4,
    )

    return _parse_llm_json(text)


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
- If revenue and transactions exist on separate sheets or columns, include them
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
    client: "OpenAI",
    df: pd.DataFrame,
    target_format: str,
    model: str = "openai/gpt-5.4-mini",
) -> str:
    """Use AI to generate Python code that transforms uploaded data into the target format.

    Args:
        client: Bi Frost OpenAI client.
        df: The uploaded DataFrame.
        target_format: Description of the target format.
        model: Model to use.

    Returns:
        Python code string that transforms variable 'df' into the target format.
    """
    sample = df.head(15).to_csv(index=False)
    col_info = f"Columns: {list(df.columns)}\nShape: {df.shape}\nDtypes:\n{df.dtypes.to_string()}"

    code = _call_bifrost(
        client, model,
        instructions=(
            "You are a data engineering expert. Given a sample of uploaded data, "
            "write Python/pandas code to transform it into the required format. "
            "The code should operate on a variable called 'df' (a pandas DataFrame) "
            "and produce a variable called 'result' (the transformed DataFrame). "
            "Return ONLY the Python code, no explanations, no markdown fences. "
            "Import only pandas (already available as pd). numpy is available as np. "
            "Handle edge cases like missing values gracefully."
        ),
        user_input=(
            f"## Source data\n{col_info}\n\nSample rows:\n{sample}\n\n"
            f"## Target format\n{target_format}\n\n"
            "Write Python code to transform 'df' into 'result'."
        ),
        temperature=0.1,
        max_tokens=2000,
    )

    return _strip_code_fences(code)


def execute_transform(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Safely execute AI-generated transform code.

    Args:
        df: Source DataFrame.
        code: Python code that transforms 'df' into 'result'.

    Returns:
        Transformed DataFrame.

    Raises:
        Exception: If code execution fails.
    """
    namespace = {"df": df.copy(), "pd": pd, "np": np}
    exec(code, namespace)
    result = namespace.get("result")
    if result is None:
        raise ValueError("Transform code did not produce a 'result' variable")
    if not isinstance(result, pd.DataFrame):
        raise ValueError(f"Expected DataFrame, got {type(result).__name__}")
    return result
