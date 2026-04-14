import pandas as pd
import streamlit as st


# Common column name mappings
KEYWORD_COL_ALIASES = {
    "keyword": "keyword", "keywords": "keyword", "query": "keyword",
    "search term": "keyword", "term": "keyword", "target keyword": "keyword",
}
VOLUME_COL_ALIASES = {
    "volume": "volume", "search volume": "volume", "avg. monthly searches": "volume",
    "monthly volume": "volume", "search_volume": "volume", "sv": "volume",
}
KD_COL_ALIASES = {
    "kd": "kd", "keyword difficulty": "kd", "difficulty": "kd",
    "kd %": "kd", "kd%": "kd", "keyword_difficulty": "kd",
}
DATE_COL_ALIASES = {
    "date": "date", "month": "date", "period": "date", "year-month": "date",
}
TRAFFIC_COL_ALIASES = {
    "traffic": "traffic", "sessions": "traffic", "organic traffic": "traffic",
    "visits": "traffic", "clicks": "traffic", "organic sessions": "traffic",
    "organic_traffic": "traffic",
}


def _match_column(df_columns: list[str], aliases: dict[str, str]) -> str | None:
    """Find the first matching column name from aliases."""
    lower_cols = {c.lower().strip(): c for c in df_columns}
    for alias in aliases:
        if alias in lower_cols:
            return lower_cols[alias]
    return None


def load_keywords(file) -> pd.DataFrame | None:
    """Load and validate a keywords CSV.

    Expected columns: keyword, volume, kd (flexible name matching).

    Returns:
        Validated DataFrame with standardised column names, or None on failure.
    """
    try:
        df = pd.read_csv(file)
    except Exception as e:
        st.error(f"Could not read CSV file: {e}")
        return None

    if df.empty:
        st.warning("No valid rows found in your CSV")
        return None

    # Match columns
    kw_col = _match_column(df.columns.tolist(), KEYWORD_COL_ALIASES)
    vol_col = _match_column(df.columns.tolist(), VOLUME_COL_ALIASES)
    kd_col = _match_column(df.columns.tolist(), KD_COL_ALIASES)

    if not all([kw_col, vol_col, kd_col]):
        missing = []
        if not kw_col:
            missing.append("keyword")
        if not vol_col:
            missing.append("volume")
        if not kd_col:
            missing.append("kd")
        st.error(f"Your CSV needs columns: {', '.join(missing)}")
        return None

    # Rename to standard names
    df = df.rename(columns={kw_col: "keyword", vol_col: "volume", kd_col: "kd"})
    df = df[["keyword", "volume", "kd"]].copy()

    # Remove duplicates
    n_before = len(df)
    df = df.drop_duplicates(subset="keyword", keep="first")
    n_dupes = n_before - len(df)
    if n_dupes > 0:
        st.info(f"Removed {n_dupes} duplicate keywords")

    # Coerce types
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["kd"] = pd.to_numeric(df["kd"], errors="coerce")

    # Drop invalid rows
    n_before = len(df)
    df = df.dropna(subset=["keyword", "volume", "kd"])
    df = df[df["volume"] > 0]
    df = df[df["kd"] >= 0]
    n_skipped = n_before - len(df)
    if n_skipped > 0:
        st.info(f"Skipped {n_skipped} rows with invalid data")

    if df.empty:
        st.warning("No valid rows found in your CSV")
        return None

    df["volume"] = df["volume"].astype(int)
    df["kd"] = df["kd"].astype(int)
    df["keyword"] = df["keyword"].astype(str).str.strip()

    return df.reset_index(drop=True)


def load_traffic(file) -> pd.DataFrame | None:
    """Load and validate a historical traffic CSV.

    Expected columns: date + traffic (flexible name matching).

    Returns:
        Validated DataFrame sorted chronologically, or None on failure.
    """
    try:
        df = pd.read_csv(file)
    except Exception as e:
        st.error(f"Could not read CSV file: {e}")
        return None

    if df.empty:
        st.warning("No valid rows found in your CSV")
        return None

    # Match columns
    date_col = _match_column(df.columns.tolist(), DATE_COL_ALIASES)
    traffic_col = _match_column(df.columns.tolist(), TRAFFIC_COL_ALIASES)

    if not all([date_col, traffic_col]):
        missing = []
        if not date_col:
            missing.append("date")
        if not traffic_col:
            missing.append("traffic")
        st.error(f"Your CSV needs columns: {', '.join(missing)}")
        return None

    # Rename to standard names
    df = df.rename(columns={date_col: "date", traffic_col: "traffic"})
    df = df[["date", "traffic"]].copy()

    # Parse dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["traffic"] = pd.to_numeric(df["traffic"], errors="coerce")

    # Drop invalid
    n_before = len(df)
    df = df.dropna()
    n_skipped = n_before - len(df)
    if n_skipped > 0:
        st.info(f"Skipped {n_skipped} rows with invalid data")

    if df.empty:
        st.warning("No valid rows found in your CSV")
        return None

    df["traffic"] = df["traffic"].astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    if len(df) < 6:
        st.warning("Fewer than 6 months of data. Forecasts may be unreliable.")

    return df
