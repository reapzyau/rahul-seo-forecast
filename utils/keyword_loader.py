"""Load SEMrush organic positions exports (17-column format).

Pure-Python module — no Streamlit imports. Accepts CSV, TSV, or Excel files
and normalises them to a consistent DataFrame schema for the forecasting engine.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# SEMrush column name → standard internal name
# ---------------------------------------------------------------------------
_SEMRUSH_COL_MAP: dict[str, str] = {
    "keyword": "keyword",
    "position": "position",
    "previous_position": "previous_position",
    "previous position": "previous_position",
    "search_volume": "volume",
    "search volume": "volume",
    "keyword_difficulty": "kd",
    "keyword difficulty": "kd",
    "cpc": "cpc",
    "url": "url",
    "traffic": "current_traffic",
    "traffic_(%)": "traffic_pct",
    "traffic (%)": "traffic_pct",
    "traffic_cost": "traffic_cost",
    "traffic cost": "traffic_cost",
    "competition": "competition",
    "number_of_results": "num_results",
    "number of results": "num_results",
    "trends": "trends",
    "timestamp": "timestamp",
    "serp_features_by_keyword": "serp_features",
    "serp features by keyword": "serp_features",
    "keyword_intents": "keyword_intents",
    "keyword intents": "keyword_intents",
    "position_type": "position_type",
    "position type": "position_type",
}

# All standard columns in output order
_STANDARD_COLS = [
    "keyword",
    "position",
    "previous_position",
    "volume",
    "kd",
    "cpc",
    "url",
    "current_traffic",
    "traffic_pct",
    "traffic_cost",
    "competition",
    "num_results",
    "trends",
    "timestamp",
    "serp_features",
    "keyword_intents",
    "position_type",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_snake_case(name: str) -> str:
    """Normalise a column header to lowercase snake_case."""
    s = name.strip().lower()
    # Replace spaces, hyphens, dots with underscores
    s = re.sub(r"[\s\-\.]+", "_", s)
    # Collapse repeated underscores
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def _read_file(file) -> pd.DataFrame | None:
    """Read CSV, TSV, or Excel into a DataFrame.

    *file* may be a path string or a file-like object (e.g. Streamlit
    ``UploadedFile``).  Returns ``None`` on any read error.
    """
    try:
        if isinstance(file, (str, Path)):
            path = str(file)
            if path.endswith((".xlsx", ".xls")):
                return pd.read_excel(path)
            if path.endswith(".tsv"):
                return pd.read_csv(path, sep="\t")
            return pd.read_csv(path, sep=None, engine="python")

        # File-like object — inspect the name attribute for format hints
        name = getattr(file, "name", "").lower()
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(file)
        if name.endswith(".tsv"):
            return pd.read_csv(file, sep="\t")
        return pd.read_csv(file, sep=None, engine="python")
    except Exception:
        return None


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase-snake-case headers, then map to standard names."""
    # First pass: normalise whitespace / casing
    df.columns = [_to_snake_case(c) for c in df.columns]

    # Second pass: rename via the SEMrush map (handles both original and
    # already-snake-cased variants)
    rename = {}
    for col in df.columns:
        # Try the column as-is, then with underscores replaced by spaces
        if col in _SEMRUSH_COL_MAP:
            rename[col] = _SEMRUSH_COL_MAP[col]
        else:
            spaced = col.replace("_", " ")
            if spaced in _SEMRUSH_COL_MAP:
                rename[col] = _SEMRUSH_COL_MAP[spaced]

    df = df.rename(columns=rename)
    return df


def _parse_primary_intent(series: pd.Series) -> pd.Series:
    """Extract the first intent from a delimited string like
    ``'informational, commercial'`` or ``'informational; commercial'``."""
    return (
        series
        .astype(str)
        .str.split(r"[,;]", regex=True)
        .str[0]
        .str.strip()
        .replace({"nan": np.nan, "": np.nan})
    )


def _parse_has_aio(series: pd.Series) -> pd.Series:
    """Return boolean Series — ``True`` when position_type indicates an AI
    Overview (contains 'AI', 'AIO', or 'ai_overview', case-insensitive)."""
    lowered = series.astype(str).str.lower()
    return lowered.str.contains(r"\bai\b|aio|ai_overview", flags=re.IGNORECASE, regex=True).fillna(False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_keyword_portfolio(file) -> pd.DataFrame | None:
    """Load a SEMrush organic positions export and return a cleaned DataFrame.

    Parameters
    ----------
    file : str | Path | file-like
        Path to a CSV / TSV / Excel file, or a file-like object (e.g.
        Streamlit ``UploadedFile``).

    Returns
    -------
    pd.DataFrame | None
        Cleaned DataFrame with standardised column names, derived columns
        (``primary_intent``, ``has_aio``), and zero-volume / duplicate rows
        removed.  Returns ``None`` if the file cannot be parsed or yields
        no valid rows.
    """
    df = _read_file(file)
    if df is None or df.empty:
        return None

    df = _normalise_columns(df)

    # Ensure minimum required column is present
    if "keyword" not in df.columns:
        return None

    # --- Coerce numeric columns -------------------------------------------
    int_cols = ["position", "previous_position", "volume", "kd", "num_results"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    float_cols = ["cpc", "current_traffic", "traffic_pct", "traffic_cost", "competition"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Derived columns --------------------------------------------------
    if "keyword_intents" in df.columns:
        df["primary_intent"] = _parse_primary_intent(df["keyword_intents"])
    else:
        df["primary_intent"] = np.nan

    if "position_type" in df.columns:
        df["has_aio"] = _parse_has_aio(df["position_type"])
    else:
        df["has_aio"] = False

    # --- Clean rows -------------------------------------------------------
    # Remove rows where volume is 0 or missing
    if "volume" in df.columns:
        df = df[df["volume"].notna() & (df["volume"] > 0)]
    else:
        # volume column not found at all — cannot proceed meaningfully
        return None

    if df.empty:
        return None

    # Remove duplicate keywords (keep first occurrence)
    df = df.drop_duplicates(subset="keyword", keep="first")

    # --- Cast integer columns where possible ------------------------------
    for col in int_cols:
        if col in df.columns:
            # Only cast non-null values; nullable Int64 preserves NaN
            df[col] = df[col].astype("Int64")

    # Strip whitespace from keyword
    df["keyword"] = df["keyword"].astype(str).str.strip()

    # Keep standard columns plus derived ones, in a stable order
    keep = [c for c in _STANDARD_COLS if c in df.columns] + ["primary_intent", "has_aio"]
    # Deduplicate list while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in keep:
        if c not in seen and c in df.columns:
            seen.add(c)
            ordered.append(c)
    df = df[ordered]

    return df.reset_index(drop=True)


def split_existing_vs_new(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a keyword portfolio into existing (ranking) and new keywords.

    Parameters
    ----------
    df : pd.DataFrame
        Output of :func:`load_keyword_portfolio`.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        ``(existing_df, new_df)`` where:
        - *existing*: position is not null **and** <= 100 (currently ranking).
        - *new*: position is null **or** > 100 (not currently ranking).
    """
    has_position = df["position"].notna() & (df["position"] <= 100)
    existing_df = df.loc[has_position].reset_index(drop=True)
    new_df = df.loc[~has_position].reset_index(drop=True)
    return existing_df, new_df
