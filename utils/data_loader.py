import pandas as pd
import streamlit as st

from engine.ai_engine import (
    get_bifrost_client,
    transform_data,
    execute_transform,
    TRAFFIC_TARGET_FORMAT,
    KEYWORDS_TARGET_FORMAT,
)


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
REVENUE_COL_ALIASES = {
    "revenue": "revenue", "organic revenue": "revenue", "organic_revenue": "revenue",
    "total revenue": "revenue",
}
TRANSACTIONS_COL_ALIASES = {
    "transactions": "transactions", "organic transactions": "transactions",
    "organic_transactions": "transactions", "orders": "transactions",
    "conversions": "transactions",
}
AOV_COL_ALIASES = {
    "aov": "aov", "average order value": "aov", "avg order value": "aov",
    "avg_order_value": "aov",
}
CR_COL_ALIASES = {
    "cr": "cr", "cr%": "cr", "cr %": "cr", "conversion rate": "cr",
    "organic cr": "cr", "organic cr %": "cr", "organic cr%": "cr",
    "conversion_rate": "cr", "cvr": "cr",
}


def _match_column(df_columns: list[str], aliases: dict[str, str]) -> str | None:
    """Find the first matching column name from aliases."""
    lower_cols = {c.lower().strip(): c for c in df_columns}
    for alias in aliases:
        if alias in lower_cols:
            return lower_cols[alias]
    return None


def _read_file(file) -> pd.DataFrame | None:
    """Read a CSV, TSV, or Excel file, return DataFrame or None."""
    try:
        if isinstance(file, str):
            if file.endswith((".xlsx", ".xls")):
                return pd.read_excel(file)
            if file.endswith(".tsv"):
                return pd.read_csv(file, sep="\t")
            df = pd.read_csv(file, sep=None, engine="python")
            return df
        # Uploaded file object
        name = getattr(file, "name", "").lower()
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(file)
        if name.endswith(".tsv"):
            return pd.read_csv(file, sep="\t")
        # Auto-detect separator (handles CSV and TSV)
        df = pd.read_csv(file, sep=None, engine="python")
        return df
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return None


def load_keywords(file) -> pd.DataFrame | None:
    """Load and validate a keywords CSV.

    Expected columns: keyword, volume, kd (flexible name matching).

    Returns:
        Validated DataFrame with standardised column names, or None on failure.
    """
    df = _read_file(file)
    if df is None or df.empty:
        st.warning("No valid rows found in your file")
        return None

    # Match columns
    kw_col = _match_column(df.columns.tolist(), KEYWORD_COL_ALIASES)
    vol_col = _match_column(df.columns.tolist(), VOLUME_COL_ALIASES)
    kd_col = _match_column(df.columns.tolist(), KD_COL_ALIASES)

    if not all([kw_col, vol_col, kd_col]):
        # Try AI transform before giving up
        ai_result = _try_ai_transform(df, KEYWORDS_TARGET_FORMAT, "keywords")
        if ai_result is not None and "keyword" in ai_result.columns:
            return ai_result.reset_index(drop=True)
        missing = []
        if not kw_col:
            missing.append("keyword")
        if not vol_col:
            missing.append("volume")
        if not kd_col:
            missing.append("kd")
        st.error(f"Your file needs columns: {', '.join(missing)}")
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
        st.warning("No valid rows found in your file")
        return None

    df["volume"] = df["volume"].astype(int)
    df["kd"] = df["kd"].astype(int)
    df["keyword"] = df["keyword"].astype(str).str.strip()

    return df.reset_index(drop=True)


def _try_ai_transform(raw_df: pd.DataFrame, target_format: str, data_type: str) -> pd.DataFrame | None:
    """Attempt to transform data using AI when standard column matching fails.

    Args:
        raw_df: The raw uploaded DataFrame.
        target_format: Description of the target format.
        data_type: "traffic" or "keywords" for user messaging.

    Returns:
        Transformed DataFrame, or None if AI is unavailable or transform fails.
    """
    client = get_bifrost_client(st.session_state.get("bifrost_api_key"))
    if client is None:
        return None

    model = st.session_state.get("bifrost_model", "openai/gpt-4o-mini")

    st.info(f"Data format doesn't match expected columns. Using AI to transform your {data_type} data...")

    try:
        with st.spinner("AI is analyzing your data format..."):
            code, used_model = transform_data(client, raw_df, target_format, model)

        if used_model != model:
            st.info(f"Fell back to {used_model} — selected model was unavailable")
        with st.expander("AI-generated transform code", expanded=False):
            st.code(code, language="python")

        result = execute_transform(raw_df, code)
        st.success(f"AI successfully transformed your data ({len(result)} rows)")
        return result

    except Exception as e:
        st.error(f"AI transform failed: {e}")
        st.caption("Try reformatting your data to match the template, or adjust your Bi Frost API key.")
        return None


def _validate_traffic_df(df: pd.DataFrame) -> pd.DataFrame | None:
    """Validate and clean a traffic DataFrame (used after AI transform or normal load)."""
    if "date" not in df.columns or "traffic" not in df.columns:
        st.error("Transformed data is missing required columns: date, traffic")
        return None

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["traffic"] = pd.to_numeric(df["traffic"], errors="coerce")

    for col in ["revenue", "transactions", "aov", "cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    n_before = len(df)
    df = df.dropna(subset=["date", "traffic"])
    n_skipped = n_before - len(df)
    if n_skipped > 0:
        st.info(f"Skipped {n_skipped} rows with invalid data")

    if df.empty:
        st.warning("No valid rows after transformation")
        return None

    df["traffic"] = df["traffic"].astype(int)
    if "transactions" in df.columns:
        df["transactions"] = df["transactions"].fillna(0).astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    optional = [c for c in ["revenue", "transactions", "aov", "cr"] if c in df.columns]
    if optional:
        st.info(f"Detected additional columns: {', '.join(optional)}")

    if len(df) < 6:
        st.warning("Fewer than 6 months of data. Forecasts may be unreliable.")

    return df


def load_traffic(file) -> pd.DataFrame | None:
    """Load and validate a historical traffic CSV/Excel.

    Required columns: date, traffic (flexible name matching).
    Optional columns: revenue, transactions, aov, cr (auto-detected).

    Returns:
        Validated DataFrame sorted chronologically, or None on failure.
    """
    df = _read_file(file)
    if df is None or df.empty:
        st.warning("No valid rows found in your file")
        return None

    # Match required columns
    date_col = _match_column(df.columns.tolist(), DATE_COL_ALIASES)
    traffic_col = _match_column(df.columns.tolist(), TRAFFIC_COL_ALIASES)

    if not all([date_col, traffic_col]):
        # Try AI transform before giving up
        ai_result = _try_ai_transform(df, TRAFFIC_TARGET_FORMAT, "traffic")
        if ai_result is not None:
            return _validate_traffic_df(ai_result)
        missing = []
        if not date_col:
            missing.append("date")
        if not traffic_col:
            missing.append("traffic")
        st.error(f"Your file needs columns: {', '.join(missing)}")
        return None

    # Match optional columns
    rev_col = _match_column(df.columns.tolist(), REVENUE_COL_ALIASES)
    trans_col = _match_column(df.columns.tolist(), TRANSACTIONS_COL_ALIASES)
    aov_col = _match_column(df.columns.tolist(), AOV_COL_ALIASES)
    cr_col = _match_column(df.columns.tolist(), CR_COL_ALIASES)

    # Build rename map and select columns
    rename_map = {date_col: "date", traffic_col: "traffic"}
    keep_cols = ["date", "traffic"]

    if rev_col:
        rename_map[rev_col] = "revenue"
        keep_cols.append("revenue")
    if trans_col:
        rename_map[trans_col] = "transactions"
        keep_cols.append("transactions")
    if aov_col:
        rename_map[aov_col] = "aov"
        keep_cols.append("aov")
    if cr_col:
        rename_map[cr_col] = "cr"
        keep_cols.append("cr")

    df = df.rename(columns=rename_map)
    df = df[keep_cols].copy()

    # Parse dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["traffic"] = pd.to_numeric(df["traffic"], errors="coerce")

    # Coerce optional numeric columns
    for col in ["revenue", "transactions", "aov", "cr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows with invalid required data
    n_before = len(df)
    df = df.dropna(subset=["date", "traffic"])
    n_skipped = n_before - len(df)
    if n_skipped > 0:
        st.info(f"Skipped {n_skipped} rows with invalid data")

    if df.empty:
        st.warning("No valid rows found in your file")
        return None

    df["traffic"] = df["traffic"].astype(int)
    if "transactions" in df.columns:
        df["transactions"] = df["transactions"].fillna(0).astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    # Report detected columns
    optional = [c for c in ["revenue", "transactions", "aov", "cr"] if c in df.columns]
    if optional:
        st.info(f"Detected additional columns: {', '.join(optional)}")

    if len(df) < 6:
        st.warning("Fewer than 6 months of data. Forecasts may be unreliable.")

    return df
