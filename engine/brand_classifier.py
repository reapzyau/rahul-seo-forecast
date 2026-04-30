"""Brand keyword classifier — v4-compatible shim backed by v5 engine.

The v4 flat-parameter API (build_brand_classifier, classify_keywords_with_two_stage,
brand_match_preview) is preserved for backward compatibility with existing callers
and tests. All logic is now delegated to engine.v5.brand_classifier.

New code should import BrandConfig / build_classifier directly:
    from engine.brand_classifier import BrandConfig, build_classifier
or from the v5 module:
    from engine.v5.brand_classifier import BrandConfig, build_classifier
"""

from __future__ import annotations

import pandas as pd

# v5 public API — re-exported for new callers
from engine.v5.brand_classifier import (
    BrandConfig,
    build_classifier,
    detect_collisions,
    suggest_branded_candidates,
)


def build_brand_classifier(
    substring_terms: list[str],
    word_boundary_terms: list[str] | None = None,
    excluded_followers: list[str] | None = None,
):
    """Return a callable(keyword: str) -> bool. v4-compatible wrapper around v5.

    Args:
        substring_terms: Terms matched anywhere in the keyword (case-insensitive).
        word_boundary_terms: Terms matched only as whole words. Optional.
        excluded_followers: Tokens adjacent to a word_boundary_term that cancel
            the brand match (e.g. "knit" for the brand "cable"). Optional.

    Returns:
        Callable[[str], bool] — True when the keyword is branded.
    """
    config = BrandConfig(
        substring_terms=list(substring_terms or []),
        word_boundary_terms=list(word_boundary_terms or []),
        excluded_followers=list(excluded_followers or []),
    )
    return build_classifier(config)


def classify_keywords_with_two_stage(
    kw_df: pd.DataFrame,
    substring_terms: list[str],
    word_boundary_terms: list[str] | None = None,
    excluded_followers: list[str] | None = None,
) -> pd.DataFrame:
    """Apply brand classification and add an 'is_branded' column.

    v4-compatible wrapper. Prefer building a BrandConfig and using
    build_classifier() directly in new code.
    """
    df = kw_df.copy()
    if "keyword" not in df.columns:
        df["is_branded"] = False
        return df
    classifier = build_brand_classifier(
        substring_terms=substring_terms,
        word_boundary_terms=word_boundary_terms,
        excluded_followers=excluded_followers,
    )
    df["is_branded"] = df["keyword"].map(classifier)
    return df


def brand_match_preview(
    kw_df: pd.DataFrame,
    substring_terms: list[str],
    word_boundary_terms: list[str] | None = None,
    excluded_followers: list[str] | None = None,
    top_n: int = 50,
) -> pd.DataFrame:
    """Return the top-N branded keywords sorted by volume descending.

    v4-compatible wrapper for the brand preview expander in the UI.
    """
    df = classify_keywords_with_two_stage(
        kw_df,
        substring_terms=substring_terms,
        word_boundary_terms=word_boundary_terms,
        excluded_followers=excluded_followers,
    )
    branded = df[df["is_branded"]].copy()
    if "volume" in branded.columns:
        branded = branded.sort_values("volume", ascending=False)
    return branded.head(top_n).reset_index(drop=True)


__all__ = [
    # v5 API
    "BrandConfig",
    "build_classifier",
    "suggest_branded_candidates",
    "detect_collisions",
    # v4-compatible wrappers
    "build_brand_classifier",
    "classify_keywords_with_two_stage",
    "brand_match_preview",
]
