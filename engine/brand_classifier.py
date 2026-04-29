"""Two-stage brand keyword classifier.

Stage 1 — substring match: terms that always indicate branded intent
    (e.g. "cable melbourne", "csblr").

Stage 2 — whole-word match with exclusions: brand names that are also
    common words (e.g. "cable" the brand vs "cable knit" the category).

Usage
-----
    is_brand = build_brand_classifier(
        substring_terms=["cable melbourne", "cable clothing", "csblr"],
        word_boundary_terms=["cable"],
        excluded_followers=["knit", "tie", "car", "management"],
    )
    df["is_branded"] = df["keyword"].map(is_brand)
"""

from __future__ import annotations

import re

import pandas as pd


def build_brand_classifier(
    substring_terms: list[str],
    word_boundary_terms: list[str] | None = None,
    excluded_followers: list[str] | None = None,
):
    """Return a callable that classifies a keyword string as branded or not.

    Args:
        substring_terms: Terms matched anywhere in the keyword (case-insensitive).
            Safe set — e.g. full brand name, abbreviations, domain.
        word_boundary_terms: Terms matched only as whole words. For brand names
            that are also common words (e.g. the brand "Cable"). Optional.
        excluded_followers: When a word_boundary_term appears adjacent to one of
            these words the keyword is NOT treated as branded. Prevents category
            terms like "cable knit" from being classified as the brand "Cable".
            Matching is symmetric (before or after). Optional.

    Returns:
        Callable[[str], bool] — True if the keyword is branded.

    Examples:
        >>> is_brand = build_brand_classifier(
        ...     substring_terms=["patagonia"],
        ... )
        >>> is_brand("patagonia fleece jacket")
        True
        >>> is_brand("jacket")
        False

        >>> is_brand = build_brand_classifier(
        ...     substring_terms=["cable melbourne", "csblr"],
        ...     word_boundary_terms=["cable"],
        ...     excluded_followers=["knit", "tie", "car", "bay"],
        ... )
        >>> is_brand("csblr dress")
        True
        >>> is_brand("cable clothing")
        True
        >>> is_brand("cable knit sweater")
        False
        >>> is_brand("cable")
        True
    """
    word_boundary_terms = word_boundary_terms or []
    excluded_followers = excluded_followers or []

    sub_pat: re.Pattern | None = None
    if substring_terms:
        sub_pat = re.compile(
            "|".join(re.escape(t) for t in substring_terms if t.strip()),
            re.IGNORECASE,
        )

    # Build per-term exclusion patterns for word-boundary terms
    wb_patterns: list[tuple[re.Pattern, list[re.Pattern]]] = []
    for term in word_boundary_terms:
        term_pat = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        excl_pats = [
            re.compile(
                rf"\b{re.escape(term)}\s+{re.escape(f)}\b|"
                rf"\b{re.escape(f)}\s+{re.escape(term)}\b",
                re.IGNORECASE,
            )
            for f in excluded_followers
            if f.strip()
        ]
        wb_patterns.append((term_pat, excl_pats))

    def is_branded(keyword: str) -> bool:
        s = str(keyword).lower().strip()
        # Stage 1: substring match (always branded)
        if sub_pat and sub_pat.search(s):
            return True
        # Stage 2: whole-word match with exclusion check
        for term_pat, excl_pats in wb_patterns:
            if term_pat.search(s):
                if any(ep.search(s) for ep in excl_pats):
                    return False
                return True
        return False

    return is_branded


def classify_keywords_with_two_stage(
    kw_df: pd.DataFrame,
    substring_terms: list[str],
    word_boundary_terms: list[str] | None = None,
    excluded_followers: list[str] | None = None,
) -> pd.DataFrame:
    """Apply two-stage brand classification to a keyword DataFrame.

    Adds an 'is_branded' boolean column. Replaces classify_keywords_as_branded
    in engine/brand_engine.py when advanced classification is needed.

    Args:
        kw_df: DataFrame with a 'keyword' column.
        substring_terms: Always-branded substring terms.
        word_boundary_terms: Whole-word branded terms (optional).
        excluded_followers: Category words that override whole-word match (optional).

    Returns:
        Copy of kw_df with 'is_branded' column added or replaced.
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

    Useful for a UI debug expander so analysts can verify classification.

    Args:
        kw_df: DataFrame with 'keyword' and 'volume' columns.
        substring_terms: Substring brand terms.
        word_boundary_terms: Whole-word brand terms (optional).
        excluded_followers: Exclusion words (optional).
        top_n: Maximum rows to return.

    Returns:
        DataFrame of matched (branded) keywords, volume-sorted.
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
