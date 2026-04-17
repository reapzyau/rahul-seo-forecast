"""Build an xlsx matching the SEO row of the Pattern multi-channel plan
(GAZMAN-style).

The output has monthly columns grouped as Forecast / Actual / % Variance,
with rows for Traffic, Transactions, and Revenue.  The analyst pastes this
into the plan template.

Pure Python + openpyxl.  No Streamlit imports.
"""

from __future__ import annotations

import calendar
import io
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
from openpyxl.utils import get_column_letter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_BOLD_FONT = Font(bold=True, size=11)
_NUMBER_FMT = "#,##0"
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def _month_abbrs(start_month: int, months: int) -> List[str]:
    """Return abbreviated month names starting from *start_month* (1-12)."""
    return [calendar.month_abbr[(start_month - 1 + i) % 12 + 1] for i in range(months)]


def _auto_width(ws) -> None:
    """Set each column width to the max cell length + a small pad."""
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 10)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_seo_forecast_grid(
    monthly_traffic: List[float],
    monthly_transactions: List[float],
    monthly_revenue: List[float],
    months: int = 12,
    client_name: str = "",
    fy_label: str = "FY26",
    start_month: int = 7,
) -> io.BytesIO:
    """Build a GAZMAN-style SEO forecast grid and return an xlsx BytesIO buffer.

    Parameters
    ----------
    monthly_traffic : list
        Forecast traffic values, one per month (length must equal *months*).
    monthly_transactions : list
        Forecast transaction values.
    monthly_revenue : list
        Forecast revenue values.
    months : int
        Number of forecast months (default 12).
    client_name : str
        Client / brand name shown in the header row.
    fy_label : str
        Financial-year label, e.g. "FY26".
    start_month : int
        Calendar month (1-12) in which the financial year starts.
        7 = July (Australian standard).

    Returns
    -------
    io.BytesIO
        In-memory xlsx file ready for ``st.download_button``.
    """

    wb = Workbook()
    ws = wb.active
    ws.title = "SEO Forecast"

    month_names = _month_abbrs(start_month, months)

    # ── Row 1: title ──────────────────────────────────────────────────────
    title_text = f"{client_name} SEO Forecast — {fy_label}" if client_name else f"SEO Forecast — {fy_label}"
    ws.cell(row=1, column=1, value=title_text).font = Font(bold=True, size=14)

    # ── Row 2: blank ──────────────────────────────────────────────────────
    # (left empty)

    # ── Row 3: column headers ─────────────────────────────────────────────
    # Column A = "Metric"
    metric_cell = ws.cell(row=3, column=1, value="Metric")
    metric_cell.font = _HEADER_FONT
    metric_cell.fill = _HEADER_FILL
    metric_cell.border = _THIN_BORDER
    metric_cell.alignment = Alignment(horizontal="center")

    col = 2  # start after "Metric"
    for m_name in month_names:
        for sub in ("Forecast", "Actual", "% Var"):
            header = f"{m_name} {sub}"
            cell = ws.cell(row=3, column=col, value=header)
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.border = _THIN_BORDER
            cell.alignment = Alignment(horizontal="center")
            col += 1

    # ── Rows 4-6: data rows ──────────────────────────────────────────────
    metrics = [
        ("Traffic", monthly_traffic),
        ("Transactions", monthly_transactions),
        ("Revenue", monthly_revenue),
    ]

    for row_offset, (label, values) in enumerate(metrics):
        data_row = 4 + row_offset
        label_cell = ws.cell(row=data_row, column=1, value=label)
        label_cell.font = _BOLD_FONT
        label_cell.border = _THIN_BORDER

        col = 2
        for i in range(months):
            # Forecast column
            fc = ws.cell(row=data_row, column=col, value=values[i])
            fc.number_format = _NUMBER_FMT
            fc.border = _THIN_BORDER
            fc.alignment = Alignment(horizontal="right")
            col += 1

            # Actual column (left empty for manual entry)
            ac = ws.cell(row=data_row, column=col)
            ac.number_format = _NUMBER_FMT
            ac.border = _THIN_BORDER
            col += 1

            # % Var column (left empty for manual entry)
            vc = ws.cell(row=data_row, column=col)
            vc.number_format = "0.0%"
            vc.border = _THIN_BORDER
            col += 1

    # ── Row 7: blank ──────────────────────────────────────────────────────
    # (left empty)

    # ── Row 8: annual totals ──────────────────────────────────────────────
    total_row = 8
    total_label = ws.cell(row=total_row, column=1, value="Annual Total")
    total_label.font = _BOLD_FONT
    total_label.border = _THIN_BORDER

    # Place each metric total in the first "Forecast" column of its
    # respective metric group.  Totals span across the row:
    #   col 2 = first forecast col  -> Traffic total
    #   then skip to the first forecast col of the next metric group,
    #   but the Pattern template puts them sequentially across the row.
    #
    # Layout requested:
    #   "Annual Total" | traffic_sum | (blank) | (blank) |
    #                    txn_sum     | (blank) | (blank) |
    #                    rev_sum     | ...
    # i.e. one total per 3-column block, with blanks in between.
    totals = [
        sum(monthly_traffic),
        sum(monthly_transactions),
        sum(monthly_revenue),
    ]

    col = 2
    for total_val in totals:
        tc = ws.cell(row=total_row, column=col, value=total_val)
        tc.font = _BOLD_FONT
        tc.number_format = _NUMBER_FMT
        tc.border = _THIN_BORDER
        tc.alignment = Alignment(horizontal="right")
        # Skip the "Actual" and "% Var" sub-columns
        col += 3

    # ── Freeze panes: top 3 rows ─────────────────────────────────────────
    ws.freeze_panes = "A4"

    # ── Auto-width columns ────────────────────────────────────────────────
    _auto_width(ws)

    # ── Write to buffer ──────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
