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
    "date": "date", "month": "date", "period": "date",
    "year-month": "date", "year month": "date", "year_month": "date",
    "month year": "date", "month_year": "date", "yearmonth": "date",
    "report date": "date", "report_date": "date",
    "ga month": "date", "ga_month": "date",
    "year month (month of year)": "date",
}
TRAFFIC_COL_ALIASES = {
    "traffic": "traffic", "sessions": "traffic",
    "organic traffic": "traffic", "organic_traffic": "traffic",
    "visits": "traffic", "users": "traffic", "pageviews": "traffic",
    "clicks": "traffic", "organic sessions": "traffic",
    "organic_sessions": "traffic", "total sessions": "traffic",
    "total_sessions": "traffic", "web sessions": "traffic",
    "entrances": "traffic",
}
REVENUE_COL_ALIASES = {
    "revenue": "revenue", "organic revenue": "revenue",
    "organic_revenue": "revenue", "total revenue": "revenue",
    "total_revenue": "revenue", "purchase revenue": "revenue",
    "average purchase revenue": "revenue",
    "gross revenue": "revenue", "net revenue": "revenue",
}
TRANSACTIONS_COL_ALIASES = {
    "transactions": "transactions", "organic transactions": "transactions",
    "organic_transactions": "transactions", "orders": "transactions",
    "conversions": "transactions", "purchases": "transactions",
    "total transactions": "transactions", "total_transactions": "transactions",
}
AOV_COL_ALIASES = {
    "aov": "aov", "average order value": "aov", "avg order value": "aov",
    "avg_order_value": "aov", "avg. order value": "aov",
    "average purchase revenue": "aov", "avg purchase value": "aov",
}
CR_COL_ALIASES = {
    "cr": "cr", "cr%": "cr", "cr %": "cr", "conversion rate": "cr",
    "organic cr": "cr", "organic cr %": "cr", "organic cr%": "cr",
    "conversion_rate": "cr", "cvr": "cr", "ecommerce conversion rate": "cr",
}


def _match_column(df_columns: list[str], aliases: dict[str, str]) -> str | None:
    """Find the first matching column name from aliases."""
    lower_cols = {c.lower().strip(): c for c in df_columns}
    for alias in aliases:
        if alias in lower_cols:
            return lower_cols[alias]
    return None


_TRAFFIC_SHEET_NAMES = {
    "sessions", "traffic", "visits", "organic traffic", "organic sessions",
    "organic", "clicks", "gsc", "ga", "analytics",
}

_SHEET_METRIC_MAP = {
    "sessions": "traffic", "traffic": "traffic", "visits": "traffic",
    "clicks": "traffic",
    "revenue": "revenue",
    "transactions": "transactions", "orders": "transactions",
    "conversions": "transactions",
    "average order value": "aov", "aov": "aov",
}


def _pick_excel_sheet(xl: "pd.ExcelFile") -> tuple[pd.DataFrame, str]:
    """Return (df, sheet_name) for the most traffic-relevant sheet.

    Priority: sheet name match → column name match → first sheet.
    """
    sheets = xl.sheet_names
    traffic_col_keys = set(TRAFFIC_COL_ALIASES.keys())

    for sheet in sheets:
        if sheet.lower().strip() in _TRAFFIC_SHEET_NAMES:
            return xl.parse(sheet), sheet

    for sheet in sheets:
        df = xl.parse(sheet)
        lower_cols = {c.lower().strip() for c in df.columns}
        if lower_cols & traffic_col_keys:
            return df, sheet

    return xl.parse(sheets[0]), sheets[0]


def _aggregate_sheet(df: pd.DataFrame, date_col: str, metric_col: str) -> pd.DataFrame:
    """Aggregate a sheet by date, summing the metric across rows (e.g. channel groups)."""
    agg = df[[date_col, metric_col]].copy()
    agg[metric_col] = pd.to_numeric(agg[metric_col], errors="coerce")
    agg = agg.dropna(subset=[metric_col])
    return agg.groupby(date_col, as_index=False)[metric_col].sum()


def _merge_traffic_sheets(xl: "pd.ExcelFile") -> pd.DataFrame | None:
    """Read all metric sheets from a multi-sheet workbook and merge by date.

    Each sheet should have a date column and one numeric metric column.
    Sheets are mapped to standard column names (traffic, revenue, transactions, aov)
    via _SHEET_METRIC_MAP. Rows are aggregated (summed) per date first.
    """
    merged = None
    sheets_used = []

    for sheet_name in xl.sheet_names:
        sheet_lower = sheet_name.lower().strip()
        target_col = None
        for alias, standard in _SHEET_METRIC_MAP.items():
            if alias in sheet_lower:
                target_col = standard
                break
        if target_col is None:
            continue

        df = xl.parse(sheet_name)
        if df.empty:
            continue

        date_col = _match_column(df.columns.tolist(), DATE_COL_ALIASES)
        if not date_col:
            continue

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            for col in df.columns:
                if col == date_col:
                    continue
                coerced = pd.to_numeric(df[col], errors="coerce")
                if coerced.notna().sum() > len(df) * 0.3:
                    df[col] = coerced
                    numeric_cols = [col]
                    break
        if not numeric_cols:
            continue

        metric_col = numeric_cols[-1]
        agg_df = _aggregate_sheet(df, date_col, metric_col)
        agg_df = agg_df.rename(columns={date_col: "date", metric_col: target_col})

        if merged is None:
            merged = agg_df
        elif target_col not in merged.columns:
            merged = merged.merge(agg_df, on="date", how="outer")

        sheets_used.append(f"{sheet_name} → {target_col}")

    if merged is not None and "traffic" in merged.columns:
        st.info(f"Merged **{len(sheets_used)} sheets**: {', '.join(sheets_used)}")
        return merged
    return None


def _read_file(file) -> pd.DataFrame | None:
    """Read a CSV, TSV, or Excel file, return DataFrame or None.

    For multi-sheet Excel files, selects the most traffic-relevant sheet.
    """
    try:
        if isinstance(file, str):
            if file.endswith((".xlsx", ".xls")):
                xl = pd.ExcelFile(file)
                df, _ = _pick_excel_sheet(xl)
                return df
            if file.endswith(".tsv"):
                return pd.read_csv(file, sep="\t")
            return pd.read_csv(file, sep=None, engine="python")

        name = getattr(file, "name", "").lower()
        if name.endswith((".xlsx", ".xls")):
            xl = pd.ExcelFile(file)
            df, chosen_sheet = _pick_excel_sheet(xl)
            if len(xl.sheet_names) > 1:
                st.info(
                    f"Multi-sheet workbook — reading **{chosen_sheet}** sheet "
                    f"(available: {', '.join(xl.sheet_names)}). "
                    "Rename your traffic sheet to 'Sessions' or 'Traffic' to ensure correct selection."
                )
            return df
        if name.endswith(".tsv"):
            return pd.read_csv(file, sep="\t")
        return pd.read_csv(file, sep=None, engine="python")
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
    """Validate and clean a traffic DataFrame (used after multi-sheet merge, AI transform, or normal load)."""
    if "date" not in df.columns or "traffic" not in df.columns:
        st.error("Transformed data is missing required columns: date, traffic")
        return None

    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df["traffic"] = pd.to_numeric(df["traffic"], errors="coerce")

    # Aggregate duplicate dates (e.g. from channel-group rows)
    numeric_cols = [c for c in df.columns if c != "date"]
    dupes = df["date"].dropna().duplicated(keep=False).any()
    if dupes:
        agg = {c: "mean" if c in ("aov", "cr") else "sum" for c in numeric_cols if c in df.columns}
        df = df.groupby("date", as_index=False).agg(agg)

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

    For multi-sheet Excel workbooks, merges all metric sheets (Sessions,
    Revenue, Transactions, AOV) by date before validation. Falls back to
    single-sheet reading + AI transform for unrecognised formats.

    Returns:
        Validated DataFrame sorted chronologically, or None on failure.
    """
    # Multi-sheet Excel: merge all metric sheets natively
    name = getattr(file, "name", "").lower() if not isinstance(file, str) else file.lower()
    if name.endswith((".xlsx", ".xls")):
        xl = pd.ExcelFile(file)
        if len(xl.sheet_names) > 1:
            merged = _merge_traffic_sheets(xl)
            if merged is not None:
                return _validate_traffic_df(merged)
        # Reset file pointer for fallback path
        if hasattr(file, "seek"):
            file.seek(0)

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
