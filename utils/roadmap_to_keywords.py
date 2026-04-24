"""Convert a roadmap content plan into a keyword DataFrame suitable for the
new content forecast engine.

The roadmap names target keywords per content piece but doesn't include search
volume or KD. This module joins those keywords against the SEMrush portfolio
(by exact-match keyword text, falling back to None) so the forecast engine
gets volume + KD for every keyword that has SEMrush data, and reasonable
defaults for the ones that don't.
"""
from __future__ import annotations

import pandas as pd

# Defaults for keywords not found in SEMrush — conservative so forecasts don't
# over-promise on unknown terms
DEFAULT_VOLUME_FOR_UNKNOWN_KEYWORD = 200
DEFAULT_KD_FOR_UNKNOWN_KEYWORD = 35


def build_keyword_df_from_roadmap(
    content_plan: list[dict],
    semrush_kw_df: pd.DataFrame | None = None,
    default_volume: int = DEFAULT_VOLUME_FOR_UNKNOWN_KEYWORD,
    default_kd: int = DEFAULT_KD_FOR_UNKNOWN_KEYWORD,
) -> pd.DataFrame:
    """Convert roadmap content_plan items into a keyword-level DataFrame.

    Each content_plan item may target multiple keywords. This function explodes
    them so each row is one (keyword, content_url, publish_month) triple, then
    joins against SEMrush data for volume/KD enrichment.

    Args:
        content_plan: List of dicts from roadmap_native_parser.parse_pattern_native()
                      Each dict must have: keywords (list[str]), url, month, content_type.
        semrush_kw_df: Optional KW_DF from session state. Used for volume/KD lookup.
        default_volume: Volume to assume when keyword not in SEMrush.
        default_kd: KD to assume when keyword not in SEMrush.

    Returns:
        DataFrame with columns: keyword, volume, kd, _content_url, _content_type,
        _publish_month, _has_semrush_match. The underscore-prefixed columns are
        metadata for downstream use; the engine reads keyword/volume/kd.
    """
    if not content_plan:
        return pd.DataFrame(columns=["keyword", "volume", "kd"])

    # Build a fast lookup from semrush data: lowered keyword -> (volume, kd)
    semrush_lookup: dict[str, tuple[int, int]] = {}
    if semrush_kw_df is not None and not semrush_kw_df.empty:
        for _, row in semrush_kw_df.iterrows():
            kw = str(row.get("keyword", "")).strip().lower()
            if not kw:
                continue
            try:
                vol = int(row.get("volume", 0))
                kd = int(row.get("kd", 0))
                semrush_lookup[kw] = (vol, kd)
            except (TypeError, ValueError):
                continue

    rows = []
    for item in content_plan:
        keywords = item.get("keywords", []) or []
        if not isinstance(keywords, list):
            continue
        url = item.get("url", "")
        content_type = item.get("content_type", "")
        month = item.get("month")

        for kw in keywords:
            kw_str = str(kw).strip()
            if not kw_str:
                continue
            kw_lower = kw_str.lower()
            if kw_lower in semrush_lookup:
                vol, kd = semrush_lookup[kw_lower]
                has_match = True
            else:
                vol, kd = default_volume, default_kd
                has_match = False
            rows.append({
                "keyword": kw_str,
                "volume": vol,
                "kd": kd,
                "_content_url": url,
                "_content_type": content_type,
                "_publish_month": month,
                "_has_semrush_match": has_match,
            })

    if not rows:
        return pd.DataFrame(columns=["keyword", "volume", "kd"])

    df = pd.DataFrame(rows)

    # Deduplicate keywords (keep first occurrence — same keyword on multiple URLs)
    df = df.drop_duplicates(subset="keyword", keep="first").reset_index(drop=True)

    # Filter out zero-volume rows (engine will reject them anyway)
    df = df[df["volume"] > 0].reset_index(drop=True)

    return df


def summarise_roadmap_extraction(
    content_plan: list[dict],
    keyword_df: pd.DataFrame,
) -> dict:
    """Build a summary of the conversion for UI display.

    Returns:
        Dict with: n_content_pieces, n_keywords_total, n_keywords_with_semrush,
        n_keywords_default, n_unique_urls, content_type_breakdown.
    """
    n_pieces = len(content_plan)
    n_keywords_total = len(keyword_df)
    if "_has_semrush_match" in keyword_df.columns:
        n_with_semrush = int(keyword_df["_has_semrush_match"].sum())
    else:
        n_with_semrush = 0
    n_default = n_keywords_total - n_with_semrush

    n_unique_urls = 0
    if "_content_url" in keyword_df.columns:
        n_unique_urls = keyword_df["_content_url"].nunique()

    content_type_breakdown = {}
    if "_content_type" in keyword_df.columns:
        content_type_breakdown = keyword_df["_content_type"].value_counts().to_dict()

    return {
        "n_content_pieces": n_pieces,
        "n_keywords_total": n_keywords_total,
        "n_keywords_with_semrush": n_with_semrush,
        "n_keywords_default": n_default,
        "n_unique_urls": n_unique_urls,
        "content_type_breakdown": content_type_breakdown,
    }
