"""Native GA4 multi-sheet xlsx loader for Pattern's GA4 export format.

The GA4 export contains sheets: Sessions, Revenue, Transactions, AOV.
Each sheet has a channel grouping column, a date column (typically "Year month"),
and a metric column.

Known bug: the Revenue sheet encodes Financial Year as the day-of-month in the
date column (e.g. day=23 means FY23).  This module detects and corrects that
using Australian financial year convention (FY24 = Jul 2023 - Jun 2024).

This module is pure Python + pandas — no Streamlit imports.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import IO

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sheet name matching
# ---------------------------------------------------------------------------

_SHEET_METRIC = {
    "sessions": "traffic",
    "revenue": "revenue",
    "transactions": "transactions",
    "aov": "aov",
    "average order value": "aov",
}

# ---------------------------------------------------------------------------
# Column aliases for flexible matching
# ---------------------------------------------------------------------------

_DATE_ALIASES = {
    "year month", "year month (month of year)", "month", "date",
    "year-month", "year_month", "month year", "month_year",
    "yearmonth", "period", "ga month", "ga_month", "report date",
}

_CHANNEL_ALIASES = {
    "session default channel group",
    "session default channel grouping",
    "default channel group",
    "default channel grouping",
    "channel group",
    "channel grouping",
    "channel",
}

_ORGANIC_KEYWORDS = {"organic search", "organic", "organic social"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_column(columns: list[str], aliases: set[str]) -> str | None:
    """Return the first column whose lowered/stripped name is in *aliases*."""
    lower_map = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


def _find_metric_column(df: pd.DataFrame, date_col: str, channel_col: str | None) -> str | None:
    """Pick the best numeric metric column (excluding date/channel)."""
    skip = {date_col}
    if channel_col:
        skip.add(channel_col)

    # First pass: already-numeric columns
    for col in df.columns:
        if col in skip:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            return col

    # Second pass: coercible columns with >30% valid values
    for col in df.columns:
        if col in skip:
            continue
        coerced = pd.to_numeric(df[col].astype(str).str.replace(",", "", regex=False), errors="coerce")
        if coerced.notna().sum() > len(df) * 0.3:
            return col

    return None


def _clean_header(df: pd.DataFrame) -> pd.DataFrame:
    """Handle merged/multi-row headers that GA4 exports sometimes produce.

    If the first few rows look like header continuations (mostly NaN or
    contain obvious header text like "Financial Year"), skip them and
    re-read with the first valid row as header.
    """
    # Check if the first column name looks like "Unnamed" — indicates merged header rows
    if not any(str(c).startswith("Unnamed") for c in df.columns):
        return df

    # Try to find the real header row (within the first 5 rows)
    for i in range(min(5, len(df))):
        row = df.iloc[i]
        non_null = row.dropna()
        if len(non_null) >= 2:
            # This row looks like a real header
            new_header = df.iloc[i].astype(str).str.strip()
            out = df.iloc[i + 1:].copy()
            out.columns = new_header.values
            out = out.reset_index(drop=True)
            # Drop columns named 'nan'
            out = out.loc[:, out.columns != "nan"]
            return out

    return df


def _parse_month(series: pd.Series) -> pd.Series:
    """Parse a date-like series into month-start Timestamps.

    Handles formats like 'Jan 2024', '2024-01', '01/2024', etc.
    """
    return pd.to_datetime(series, format="mixed", errors="coerce").dt.to_period("M").dt.to_timestamp()


def _is_fy_day_bug(dates: pd.Series | pd.DatetimeIndex) -> bool:
    """Detect the Revenue sheet FY-date bug.

    The bug manifests as day-of-month values that look like two-digit
    financial year codes (20-30 range) while months/years stay normal.
    If >80% of non-null dates have the same suspicious day value within
    a row's group, flag it.
    """
    # Normalise to Series so .dt accessor works uniformly
    if isinstance(dates, pd.DatetimeIndex):
        dates = dates.to_series()

    if dates.isna().all():
        return False

    days = dates.dt.day
    non_null_days = days.dropna()
    if len(non_null_days) == 0:
        return False

    unique_days = non_null_days.unique()

    # If all dates share just 1-3 unique day values and those days are in
    # the FY range (20-30), it's almost certainly the bug.
    if len(unique_days) <= 4:
        if all(15 <= d <= 35 for d in unique_days):
            return True

    # Also flag if most day values are in a narrow band that doesn't match
    # typical month-start (day=1) data.
    fy_like = non_null_days.apply(lambda d: 15 <= d <= 35)
    if fy_like.mean() > 0.8 and non_null_days.nunique() <= 6:
        return True

    return False


def _fix_fy_dates(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Reconstruct correct dates from FY-encoded day values.

    Australian financial year convention:
      FY24 = Jul 2023 - Jun 2024

    The bug stores FY as the day-of-month. So a date like 2024-03-23
    really means March of FY23, which is March 2023 (since Mar is in
    the Jul-Jun window of FY23: Jul 2022 - Jun 2023).

    Approach: extract the month from the date (reliable), extract the FY
    from the day component, then compute the correct calendar year.
      - Months Jul-Dec: calendar year = FY - 1
      - Months Jan-Jun: calendar year = FY (already in the right year)

    FY value is interpreted as 2000 + day (day=23 -> FY23 -> 2023).
    """
    out = df.copy()
    dates = pd.to_datetime(out[date_col], format="mixed", errors="coerce")

    months = dates.dt.month
    fy_raw = dates.dt.day  # This is actually the FY code

    # Convert FY code to full year: day 23 -> FY23 -> 2023
    fy_year = 2000 + fy_raw

    # Determine calendar year from FY and month
    # Jul-Dec are in the first half of the FY -> calendar year = FY - 1
    # Jan-Jun are in the second half of the FY -> calendar year = FY
    calendar_year = fy_year.copy()
    jul_dec_mask = months >= 7
    calendar_year[jul_dec_mask] = fy_year[jul_dec_mask] - 1

    # Reconstruct dates with day=1
    corrected = pd.to_datetime(
        {
            "year": calendar_year,
            "month": months,
            "day": 1,
        },
        errors="coerce",
    )

    out[date_col] = corrected
    return out


def _read_sheet(
    xl: pd.ExcelFile,
    sheet_name: str,
    target_metric: str,
) -> pd.DataFrame | None:
    """Read one GA4 sheet, filter to organic, return a two-column df (date, metric).

    Returns None if parsing fails or no data is found.
    """
    try:
        raw = xl.parse(sheet_name)
    except Exception:
        logger.warning("Could not parse sheet '%s'", sheet_name)
        return None

    if raw.empty:
        return None

    # Handle potential merged headers
    df = _clean_header(raw)
    if df.empty:
        return None

    # --- Locate columns ---
    date_col = _find_column(df.columns.tolist(), _DATE_ALIASES)
    channel_col = _find_column(df.columns.tolist(), _CHANNEL_ALIASES)

    if date_col is None:
        # Fall back: look for any column with parseable dates
        for col in df.columns:
            sample = df[col].dropna().head(10)
            parsed = pd.to_datetime(sample, format="mixed", errors="coerce")
            if parsed.notna().sum() >= len(sample) * 0.5:
                date_col = col
                break
    if date_col is None:
        logger.warning("No date column found in sheet '%s'", sheet_name)
        return None

    metric_col = _find_metric_column(df, date_col, channel_col)
    if metric_col is None:
        logger.warning("No metric column found in sheet '%s'", sheet_name)
        return None

    # --- Filter to organic channels ---
    if channel_col is not None:
        lower_channel = df[channel_col].astype(str).str.lower().str.strip()
        organic_mask = lower_channel.isin(_ORGANIC_KEYWORDS)
        if organic_mask.any():
            df = df[organic_mask].copy()
        else:
            # If no exact match, try substring match
            organic_mask = lower_channel.str.contains("organic", case=False, na=False)
            if organic_mask.any():
                df = df[organic_mask].copy()
            # If still nothing matched, use all rows (may be pre-filtered)

    if df.empty:
        return None

    # --- Clean metric values ---
    df[metric_col] = (
        df[metric_col]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
    )
    df[metric_col] = pd.to_numeric(df[metric_col], errors="coerce")

    # --- Handle FY-date bug on Revenue sheet ---
    # Parse dates first as raw datetime to inspect day values
    raw_dates = pd.to_datetime(df[date_col], format="mixed", errors="coerce")

    is_revenue = target_metric == "revenue"
    if is_revenue and _is_fy_day_bug(raw_dates):
        logger.warning(
            "Detected FY-date encoding in sheet '%s' — day-of-month values appear to be "
            "financial year codes. Reconstructing calendar dates using AU FY convention "
            "(FY24 = Jul 2023–Jun 2024). If your dates are already correct, this "
            "correction will produce wrong years.",
            sheet_name,
        )
        df[date_col] = raw_dates  # store parsed version for fix
        df = _fix_fy_dates(df, date_col)
        dates = df[date_col]
    else:
        dates = _parse_month(df[date_col])

    result = pd.DataFrame({"date": dates, target_metric: df[metric_col].values})
    result = result.dropna(subset=["date", target_metric])

    if result.empty:
        return None

    # Aggregate by month (sum across rows — e.g. multiple organic sub-channels)
    result["date"] = result["date"].dt.to_period("M").dt.to_timestamp()
    result = result.groupby("date", as_index=False)[target_metric].sum()

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def load_ga4_organic(file: str | IO | BytesIO) -> pd.DataFrame | None:
    """Load a GA4 multi-sheet xlsx export and return a clean monthly DataFrame.

    Parameters
    ----------
    file : str or file-like
        Path to an xlsx file, or a file-like object (e.g. Streamlit UploadedFile).

    Returns
    -------
    pd.DataFrame or None
        Columns: date, traffic, and optionally revenue, transactions, aov, cr.
        Sorted by date ascending, no future dates.  Returns None if parsing fails.
    """
    try:
        xl = pd.ExcelFile(file)
    except Exception:
        logger.error("Could not open file as Excel workbook")
        return None

    # Map sheet names to target metrics
    sheets_to_read: list[tuple[str, str]] = []
    for sheet_name in xl.sheet_names:
        sheet_lower = sheet_name.lower().strip()
        for alias, metric in _SHEET_METRIC.items():
            if alias in sheet_lower:
                sheets_to_read.append((sheet_name, metric))
                break

    if not sheets_to_read:
        logger.warning("No recognised GA4 sheets found (expected: Sessions, Revenue, Transactions, AOV)")
        return None

    # Read and merge all sheets
    merged: pd.DataFrame | None = None
    sheets_loaded: list[str] = []

    for sheet_name, target_metric in sheets_to_read:
        sheet_df = _read_sheet(xl, sheet_name, target_metric)
        if sheet_df is None:
            logger.info("Skipped sheet '%s' — no usable data", sheet_name)
            continue

        if merged is None:
            merged = sheet_df
        else:
            # Only merge if this metric isn't already present
            if target_metric not in merged.columns:
                merged = merged.merge(sheet_df, on="date", how="outer")

        sheets_loaded.append(f"{sheet_name} -> {target_metric}")

    if merged is None:
        logger.warning("No data extracted from any GA4 sheet")
        return None

    # We must have traffic at minimum
    if "traffic" not in merged.columns:
        logger.warning("No Sessions/Traffic sheet found — cannot produce forecast input")
        return None

    # --- Compute derived columns ---

    # Conversion rate: transactions / traffic * 100
    if "transactions" in merged.columns and "traffic" in merged.columns:
        safe_traffic = merged["traffic"].replace(0, pd.NA)
        merged["cr"] = (merged["transactions"] / safe_traffic * 100).round(2)

    # AOV: revenue / transactions (if AOV sheet was missing but we have both)
    if "aov" not in merged.columns and "revenue" in merged.columns and "transactions" in merged.columns:
        safe_txn = merged["transactions"].replace(0, pd.NA)
        merged["aov"] = (merged["revenue"] / safe_txn).round(2)

    # --- Final cleanup ---

    # Coerce types
    merged["traffic"] = pd.to_numeric(merged["traffic"], errors="coerce")
    for col in ("revenue", "transactions", "aov", "cr"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    merged = merged.dropna(subset=["date", "traffic"])

    if merged.empty:
        return None

    merged["traffic"] = merged["traffic"].astype(int)
    if "transactions" in merged.columns:
        merged["transactions"] = merged["transactions"].fillna(0).astype(int)

    # Sort and filter out future dates
    merged = merged.sort_values("date").reset_index(drop=True)
    today = pd.Timestamp.now().normalize()
    merged = merged[merged["date"] <= today].reset_index(drop=True)

    if merged.empty:
        return None

    # Attach metadata
    merged.attrs["ga4_sheets_loaded"] = sheets_loaded
    merged.attrs["ga4_months"] = len(merged)

    logger.info(
        "GA4 loader: %d months from %d sheets (%s)",
        len(merged),
        len(sheets_loaded),
        ", ".join(sheets_loaded),
    )

    return merged
