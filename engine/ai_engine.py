import json
import os

import pandas as pd

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_bifrost_client(api_key: str | None = None) -> "OpenAI | None":
    """Get Bi Frost OpenAI-compatible client.

    Args:
        api_key: Bi Frost virtual key. Falls back to BIFROST_API_KEY env var.

    Returns:
        OpenAI client configured for Bi Frost, or None if unavailable.
    """
    if OpenAI is None:
        return None
    key = api_key or os.environ.get("BIFROST_API_KEY")
    if not key:
        return None
    return OpenAI(base_url="https://bifrost.pattern.com", api_key=key)


def cluster_keywords(
    client: "OpenAI",
    keywords: list[str],
    model: str = "openai/gpt-4o-mini",
) -> dict:
    """Group keywords into topical clusters using AI.

    Returns:
        Dict with 'clusters' key containing list of cluster objects.
    """
    kw_list = "\n".join(f"- {kw}" for kw in keywords[:200])  # Cap at 200

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO expert. Group the given keywords into topical clusters. "
                    "Each cluster should represent one content piece or page. "
                    "Return valid JSON only, no markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Group these SEO keywords into topical clusters:\n\n{kw_list}\n\n"
                    'Return JSON: {"clusters": [{"name": "cluster name", '
                    '"keywords": ["kw1", "kw2"], "suggested_title": "Article Title"}]}'
                ),
            },
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    text = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


def check_cannibalization(
    client: "OpenAI",
    keywords: list[str],
    existing_urls: list[str],
    model: str = "openai/gpt-4o-mini",
) -> list[dict]:
    """Check if proposed keywords conflict with existing URLs.

    Returns:
        List of dicts with keyword, conflicting_url, risk, recommendation.
    """
    kw_list = "\n".join(f"- {kw}" for kw in keywords[:100])
    url_list = "\n".join(f"- {url}" for url in existing_urls[:100])

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO cannibalization expert. Analyze whether proposed keywords "
                    "would compete with existing URLs. Return valid JSON only, no markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Proposed keywords:\n{kw_list}\n\n"
                    f"Existing URLs:\n{url_list}\n\n"
                    "For each keyword, assess cannibalization risk. Return JSON array:\n"
                    '[{"keyword": "...", "conflicting_url": "..." or null, '
                    '"risk": "high"|"medium"|"low"|"none", '
                    '"recommendation": "brief action item"}]'
                ),
            },
        ],
        temperature=0.2,
        max_tokens=4000,
    )

    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


def generate_content_roadmap(
    client: "OpenAI",
    keyword_df: pd.DataFrame,
    months: int,
    model: str = "openai/gpt-4o-mini",
) -> list[dict]:
    """Generate an AI-powered content roadmap from keyword forecast data.

    Returns:
        List of monthly content plans.
    """
    # Prepare summary data for the LLM
    cols = ["keyword", "volume", "kd", "tier", "intent", "efficiency_score",
            "estimated_monthly_traffic", "publish_month"]
    available = [c for c in cols if c in keyword_df.columns]
    summary_df = keyword_df[available].head(50)
    data_str = summary_df.to_csv(index=False)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO content strategist. Create a prioritized content roadmap "
                    "from keyword forecast data. Consider: publish highest-efficiency keywords first, "
                    "cluster related keywords into single posts, flag informational keywords at risk "
                    "from AI Overviews. Return valid JSON only, no markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Keyword forecast data (top 50 by efficiency):\n\n{data_str}\n\n"
                    f"Create a {months}-month content roadmap. Return JSON:\n"
                    '[{"month": 1, "content_pieces": [{"title": "...", '
                    '"target_keywords": ["kw1", "kw2"], "estimated_traffic": 1000, '
                    '"priority": "high"|"medium"|"low", "notes": "brief note"}]}]'
                ),
            },
        ],
        temperature=0.4,
        max_tokens=4000,
    )

    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)
