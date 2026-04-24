"""SEO Channel Forecast grid builder (GAZMAN-style).

Generates a single-sheet xlsx "SEO Channel Forecast" with:
  - Rows 1-11: header/preamble block (title, last updated, fee rows)
  - Row 12: column sub-header strip (Forecast | Actuals | % Change per month)
  - Rows 13-19: 7-metric scaffold (BUDGET, REVENUE, ROAS, TRANSACTIONS, AOV, TRAFFIC, CVR)

Data population (B1b), % Change / trailing columns (B1c), and supporting sheets
(Stream Breakdown, Assumptions) are added in subsequent sessions.

Pure Python + openpyxl.  No Streamlit imports.
"""

from __future__ import annotations

import calendar
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_BOLD_FONT = Font(bold=True, size=11)
_NUMBER_FMT = "#,##0"
_CURRENCY_FMT = "$#,##0.00"
_PERCENT_FMT = "0.00%"
_PCT_CHANGE_FMT = "0%"

# ---------------------------------------------------------------------------
# GAZMAN column layout constants and helpers
# ---------------------------------------------------------------------------

_DATA_START = 3  # Col C — A=CHANNEL label, B=metric label, C+ = monthly data


def _fc(i: int) -> int:
    """Forecast column for month i (0-indexed)."""
    return _DATA_START + i * 3


def _ac(i: int) -> int:
    """Actuals column for month i."""
    return _DATA_START + i * 3 + 1


def _pc(i: int) -> int:
    """% Change column for month i."""
    return _DATA_START + i * 3 + 2


def _col_annual(m: int) -> int:
    return _DATA_START + m * 3


def _col_ytd(m: int) -> int:
    return _col_annual(m) + 1


def _col_ass(m: int) -> int:
    return _col_annual(m) + 2


def _col_prior(m: int) -> int:
    return _col_annual(m) + 3


def _col_yoy(m: int) -> int:
    return _col_annual(m) + 4


# ---------------------------------------------------------------------------
# Public column-range helper (reused by data-population sessions)
# ---------------------------------------------------------------------------


def _month_column_ranges(start_month: int, months: int) -> list[tuple[str, int, int, int]]:
    """Return [(month_name, forecast_col, actuals_col, pct_change_col), ...].

    1-based column indices.  First month's forecast col is 3 (A=channel, B=metric).
    """
    result = []
    for i in range(months):
        month_name = calendar.month_abbr[(start_month - 1 + i) % 12 + 1]
        result.append((month_name, _fc(i), _ac(i), _pc(i)))
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _auto_width(ws) -> None:
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:  # noqa: BLE001
                pass
        ws.column_dimensions[col_letter].width = max(max_len + 3, 10)


def _hcell(ws, row: int, col: int, value: str) -> None:
    """Write a styled header cell."""
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = _HEADER_FONT
    cell.fill = _HEADER_FILL
    cell.alignment = Alignment(horizontal="center")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_seo_forecast_grid(
    monthly_traffic: list[float],
    monthly_transactions: list[float],
    monthly_revenue: list[float],
    monthly_cvr: list[float],
    monthly_aov: list[float],
    monthly_budget: list[float],
    actuals_traffic: list[float] | None = None,
    actuals_transactions: list[float] | None = None,
    actuals_revenue: list[float] | None = None,
    actuals_cvr: list[float] | None = None,
    actuals_aov: list[float] | None = None,
    actuals_budget: list[float] | None = None,
    prior_year_traffic: float | None = None,
    prior_year_transactions: float | None = None,
    prior_year_revenue: float | None = None,
    prior_year_cvr: float | None = None,
    prior_year_aov: float | None = None,
    prior_year_budget: float | None = None,
    months: int = 12,
    client_name: str = "",
    fy_label: str = "FY26",
    start_month: int = 1,
    last_updated: str | None = None,
    currency_notes: str = "",
    assumptions_text: str = "",
) -> io.BytesIO:
    """Build a GAZMAN-style SEO Channel Forecast xlsx.

    Returns a BytesIO buffer containing a single-sheet workbook.
    Data cells (per-month values, ROAS, % Change, trailing totals) are
    populated in sessions B1b and B1c.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "SEO Channel Forecast"

    col_ranges = _month_column_ranges(start_month, months)
    ann_col = _col_annual(months)

    # Derive FY year for trailing column headers (FY26 -> 2026)
    try:
        fy_num = int(fy_label.replace("FY", "").strip())
        fy_year = 2000 + fy_num if fy_num < 100 else fy_num
        prior_year_label = fy_year - 1
    except ValueError:
        fy_year, prior_year_label = 2026, 2025

    # Row 2: Title
    title = (
        f"{client_name} | FORECAST | {fy_label}"
        if client_name
        else f"FORECAST | {fy_label}"
    )
    ws.cell(row=2, column=1, value=title).font = Font(bold=True, size=14)

    # Row 4: Last Updated
    if last_updated:
        ws.cell(row=4, column=2, value="Last Updated:")
        ws.cell(row=4, column=3, value=last_updated)

    # Row 5: Currency notes
    if currency_notes:
        ws.cell(row=5, column=2, value=currency_notes)

    # Row 7: Month name headers (each spanning 3 columns via merge)
    ws.cell(row=7, column=1, value="MONTH").font = _BOLD_FONT
    for m_name, fc, _ac_col, _pc_col in col_ranges:
        cell = ws.cell(row=7, column=fc, value=m_name)
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=7, start_column=fc, end_row=7, end_column=fc + 2)

    # "TOTALS" merged header spanning all trailing columns
    cell = ws.cell(row=7, column=ann_col, value="TOTALS")
    cell.font = Font(bold=True, color="FFFFFF", size=11)
    cell.fill = _HEADER_FILL
    cell.alignment = Alignment(horizontal="center")
    ws.merge_cells(
        start_row=7, start_column=ann_col,
        end_row=7, end_column=_col_yoy(months),
    )

    # Row 8: Total Forecasted Management Fee
    ws.cell(row=8, column=1, value="Total Forecasted Management Fee:")
    for i, (_, fc, _, _) in enumerate(col_ranges):
        val = monthly_budget[i] if i < len(monthly_budget) else None
        if val is not None:
            ws.cell(row=8, column=fc, value=val).number_format = _CURRENCY_FMT
    if monthly_budget:
        ws.cell(
            row=8, column=ann_col, value=sum(monthly_budget[:months])
        ).number_format = _CURRENCY_FMT

    # Row 9: Total Actual Management Fee
    ws.cell(row=9, column=1, value="Total Actual Management Fee:")
    if actuals_budget:
        for i, (_, fc, _, _) in enumerate(col_ranges):
            val = actuals_budget[i] if i < len(actuals_budget) else None
            if val is not None:
                ws.cell(row=9, column=fc, value=val).number_format = _CURRENCY_FMT

    # Row 10: Management Fee + Ad Spend (SEO-only = same as forecasted budget)
    ws.cell(row=10, column=1, value="Management Fee + Ad Spend")
    for i, (_, fc, _, _) in enumerate(col_ranges):
        val = monthly_budget[i] if i < len(monthly_budget) else None
        if val is not None:
            ws.cell(row=10, column=fc, value=val).number_format = _CURRENCY_FMT
    if monthly_budget:
        ws.cell(
            row=10, column=ann_col, value=sum(monthly_budget[:months])
        ).number_format = _CURRENCY_FMT

    # Row 12: Column sub-header strip
    _hcell(ws, 12, 1, "CHANNEL")
    for _, fc, ac_col, pc_col in col_ranges:
        _hcell(ws, 12, fc, "Forecast")
        _hcell(ws, 12, ac_col, "Actuals")
        _hcell(ws, 12, pc_col, "% Change")

    _hcell(ws, 12, ann_col, f"{fy_year} Forecast")
    _hcell(ws, 12, _col_ytd(months), f"{fy_year} YTD Actuals")
    _hcell(ws, 12, _col_ass(months), "SEO Assumptions:")
    _hcell(ws, 12, _col_prior(months), f"{prior_year_label} Actuals")
    _hcell(ws, 12, _col_yoy(months), "YoY %")

    # Rows 13-19: 7-metric scaffold (labels only; data populated in B1b)
    _METRIC_LABELS = ["BUDGET", "REVENUE", "ROAS", "TRANSACTIONS", "AOV", "TRAFFIC", "CVR"]
    for r_off, label in enumerate(_METRIC_LABELS):
        row = 13 + r_off
        if r_off == 0:
            ws.cell(row=row, column=1, value="SEO").font = _BOLD_FONT
        ws.cell(row=row, column=2, value=label).font = _BOLD_FONT

    ws.freeze_panes = "B13"
    _auto_width(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
