"""Build an xlsx matching the SEO row of the Pattern multi-channel plan
(GAZMAN-style).

The output has monthly columns grouped as Forecast / Actual / % Variance,
with rows for Traffic, Transactions, CVR %, AOV, and Revenue.

Three sheets are produced when the optional data is supplied:
  Sheet 1 "SEO Forecast" — the primary GAZMAN row (always present)
  Sheet 2 "Stream Breakdown" — layered math (when stream data provided)
  Sheet 3 "Assumptions" — provenance trail (when assumptions_summary provided)

Pure Python + openpyxl.  No Streamlit imports.
"""

from __future__ import annotations

import calendar
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_HEADER_FILL = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_BOLD_FONT = Font(bold=True, size=11)
_GROUP_FILL = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
_GROUP_FONT = Font(bold=True, size=10, color="1E3A5F")
_NUMBER_FMT = "#,##0"
_CURRENCY_FMT = "$#,##0.00"
_PERCENT_FMT = "0.00%"
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Mirrors utils/assumptions_panel._ASSUMPTION_GROUPS (no Streamlit dependency here)
_ASSUMPTION_GROUPS: dict[str, list[str]] = {
    "Client Info": [
        "client_name", "industry", "retainer_aud_monthly",
        "timeline_months_covered", "strategy_restart_month",
    ],
    "Per-Focus Effort": [
        "content_effort_level", "technical_effort_level", "on_page_effort_level",
        "off_page_effort_level", "local_effort_level", "analytics_effort_level",
        "strategy_effort_level", "positional_effort_level", "effort_level",
    ],
    "Per-Focus Hours": [
        "content_monthly_hours", "technical_monthly_hours", "on_page_monthly_hours",
        "off_page_monthly_hours", "local_monthly_hours", "analytics_monthly_hours",
        "strategy_monthly_hours", "total_monthly_hours",
    ],
    "Content & Maintenance": ["content_cadence", "maintenance_coverage"],
    "Brand": ["brand_terms", "exclude_brand_from_forecasts"],
    "Financial Model": ["blended_cr_pct", "aov", "currency"],
    "Seasonality": ["seasonality_source", "seasonality_blend_weight"],
    "AIO": ["aio_monthly_growth", "aio_ctr_penalty_informational"],
    "Decay": ["decay_rate_top3", "decay_rate_top10"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_abbrs(start_month: int, months: int) -> list[str]:
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


def _header_cell(ws, row: int, col: int, value: str) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = _HEADER_FONT
    cell.fill = _HEADER_FILL
    cell.border = _THIN_BORDER
    cell.alignment = Alignment(horizontal="center")


def _data_cell(ws, row: int, col: int, value, fmt: str) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.number_format = fmt
    cell.border = _THIN_BORDER
    cell.alignment = Alignment(horizontal="right")


def _label_cell(ws, row: int, value: str) -> None:
    cell = ws.cell(row=row, column=1, value=value)
    cell.font = _BOLD_FONT
    cell.border = _THIN_BORDER


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _build_forecast_sheet(
    ws,
    title_text: str,
    month_names: list[str],
    months: int,
    data_rows: list[tuple],
) -> None:
    """Write the primary forecast sheet.

    data_rows items: (label, values, fmt, include_in_annual_total)
    CVR values must already be divided by 100 before passing (for 0.00% format).
    """
    # Row 1: title
    ws.cell(row=1, column=1, value=title_text).font = Font(bold=True, size=14)

    # Row 3: column headers
    _header_cell(ws, 3, 1, "Metric")
    col = 2
    for m_name in month_names:
        for sub in ("Forecast", "Actual", "% Var"):
            _header_cell(ws, 3, col, f"{m_name} {sub}")
            col += 1

    # Data rows starting at row 4
    current_row = 4
    total_labels: list[str] = []
    total_values: list[float] = []

    for label, values, fmt, include_total in data_rows:
        _label_cell(ws, current_row, label)
        col = 2
        for i in range(months):
            val = values[i] if i < len(values) else None
            _data_cell(ws, current_row, col, val, fmt)
            col += 1
            # Actual column — blank for manual entry
            ws.cell(row=current_row, column=col).border = _THIN_BORDER
            col += 1
            # % Var column — blank for manual entry
            ws.cell(row=current_row, column=col).number_format = "0.0%"
            ws.cell(row=current_row, column=col).border = _THIN_BORDER
            col += 1
        if include_total:
            total_labels.append(label)
            total_values.append(sum(v for v in values[:months] if v is not None))
        current_row += 1

    # Blank separator row
    current_row += 1

    # Annual Total row
    total_row = current_row
    _label_cell(ws, total_row, "Annual Total")
    col = 2
    for _label, total_val in zip(total_labels, total_values, strict=False):
        cell = ws.cell(row=total_row, column=col, value=total_val)
        cell.font = _BOLD_FONT
        # Use integer format for totals (not CVR/AOV)
        cell.number_format = _NUMBER_FMT
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="right")
        col += 3  # skip Actual and % Var positions

    ws.freeze_panes = "A4"
    _auto_width(ws)


def _build_stream_sheet(
    ws,
    month_names: list[str],
    months: int,
    monthly_baseline: list[float] | None,
    monthly_positional_uplift: list[float] | None,
    monthly_new_content_uplift: list[float] | None,
    monthly_decay: list[float] | None,
    monthly_traffic: list[float],
) -> None:
    """Write the Stream Breakdown sheet."""
    ws.title = "Stream Breakdown"

    ws.cell(row=1, column=1, value="Stream Breakdown — Layered Traffic Math").font = Font(
        bold=True, size=14
    )

    # Month column headers
    _header_cell(ws, 3, 1, "Stream")
    for i, m_name in enumerate(month_names):
        _header_cell(ws, 3, 2 + i, m_name)

    streams = [
        ("Baseline", monthly_baseline),
        ("Positional Uplift", monthly_positional_uplift),
        ("New Content Uplift", monthly_new_content_uplift),
        ("Decay (−)", [-(v) for v in monthly_decay] if monthly_decay else None),
    ]

    row = 4
    for label, values in streams:
        if values is not None:
            _label_cell(ws, row, label)
            for i in range(months):
                val = values[i] if i < len(values) else None
                _data_cell(ws, row, 2 + i, val, _NUMBER_FMT)
            row += 1

    # Combined sum-check row
    _label_cell(ws, row, "Combined (check)")
    ws.cell(row=row, column=1).font = Font(bold=True, size=11, color="166534")
    for i in range(months):
        val = monthly_traffic[i] if i < len(monthly_traffic) else None
        cell = ws.cell(row=row, column=2 + i, value=val)
        cell.number_format = _NUMBER_FMT
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="right")
        cell.font = Font(bold=True, color="166534")

    # Notes section
    note_row = row + 2
    ws.cell(row=note_row, column=1, value="How it works:").font = _BOLD_FONT
    ws.cell(row=note_row + 1, column=1,
        value="Traffic = Baseline + Positional Uplift + New Content Uplift − Decay")
    ws.cell(row=note_row + 2, column=1,
        value="AIO impact is baked into Positional and New Content streams via per-stream CTR penalty.")
    ws.cell(row=note_row + 3, column=1,
        value="Decay = traffic lost from unmaintained pages decaying in the SERP over time.")

    ws.freeze_panes = "A4"
    _auto_width(ws)


def _build_assumptions_sheet(ws, assumption_rows: list[dict]) -> None:
    """Write the Assumptions provenance sheet."""
    ws.title = "Assumptions"

    ws.cell(row=1, column=1, value="Forecast Assumptions & Provenance").font = Font(
        bold=True, size=14
    )

    # Column headers
    for col, header in enumerate(("Assumption", "Value", "Source"), start=1):
        _header_cell(ws, 3, col, header)

    # Build lookup: key → row dict
    by_key = {row["key"]: row for row in assumption_rows}

    # Keys that appear in a group (rendered with group header)
    grouped_keys: set[str] = set()
    for keys in _ASSUMPTION_GROUPS.values():
        grouped_keys.update(keys)

    current_row = 4

    def _write_assumption_row(r: int, entry: dict) -> None:
        label = entry.get("label", entry["key"])
        value = entry.get("value", "")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        source = entry.get("source", entry.get("provenance", ""))
        for col, val in enumerate((label, str(value), source), start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.border = _THIN_BORDER

    for group_name, keys in _ASSUMPTION_GROUPS.items():
        # Group header row
        for col in range(1, 4):
            cell = ws.cell(row=current_row, column=col)
            cell.fill = _GROUP_FILL
            cell.font = _GROUP_FONT
            cell.border = _THIN_BORDER
        ws.cell(row=current_row, column=1, value=group_name)
        current_row += 1

        for key in keys:
            if key in by_key:
                _write_assumption_row(current_row, by_key[key])
                current_row += 1

    # Ungrouped assumptions
    ungrouped = [r for r in assumption_rows if r["key"] not in grouped_keys]
    if ungrouped:
        for col in range(1, 4):
            cell = ws.cell(row=current_row, column=col)
            cell.fill = _GROUP_FILL
            cell.font = _GROUP_FONT
            cell.border = _THIN_BORDER
        ws.cell(row=current_row, column=1, value="Other")
        current_row += 1
        for entry in ungrouped:
            _write_assumption_row(current_row, entry)
            current_row += 1

    # Footer legend
    footer_row = current_row + 1
    ws.cell(row=footer_row, column=1,
        value="Source legend: defaulted = built-in default  |  detected = inferred from your data  |  overridden = explicitly set by analyst"
    ).font = Font(italic=True, size=9, color="666666")

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_seo_forecast_grid(
    monthly_traffic: list[float],
    monthly_transactions: list[float],
    monthly_revenue: list[float],
    monthly_cvr: list[float] | None = None,
    monthly_aov: list[float] | None = None,
    months: int = 12,
    client_name: str = "",
    fy_label: str = "FY26",
    start_month: int = 7,
    # Band data (optional)
    traffic_p10: list[float] | None = None,
    traffic_p90: list[float] | None = None,
    revenue_p10: list[float] | None = None,
    revenue_p90: list[float] | None = None,
    # Stream breakdown (optional)
    monthly_baseline: list[float] | None = None,
    monthly_positional_uplift: list[float] | None = None,
    monthly_new_content_uplift: list[float] | None = None,
    monthly_decay: list[float] | None = None,
    # Assumption provenance (optional)
    assumptions_summary: list[dict] | None = None,
) -> io.BytesIO:
    """Build a GAZMAN-style SEO forecast grid and return an xlsx BytesIO buffer.

    Produces up to three sheets:
      "SEO Forecast" — always present; Traffic/Transactions/CVR/AOV/Revenue rows
      "Stream Breakdown" — layered traffic math (when stream args provided)
      "Assumptions" — provenance trail (when assumptions_summary provided)

    Existing callers that pass only the first three positional args continue to
    receive a single-sheet, three-row workbook identical to the previous format.

    CVR values must be passed as percentages (e.g., 2.5 for 2.5%).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "SEO Forecast"

    month_names = _month_abbrs(start_month, months)
    title_text = (
        f"{client_name} SEO Forecast — {fy_label}" if client_name
        else f"SEO Forecast — {fy_label}"
    )

    # Build ordered list of data rows for the Forecast sheet
    # (label, values, format, include_in_annual_total)
    data_rows: list[tuple] = []

    data_rows.append(("Traffic", monthly_traffic, _NUMBER_FMT, True))
    if traffic_p10 is not None:
        data_rows.append(("Traffic P10", traffic_p10, _NUMBER_FMT, False))
    if traffic_p90 is not None:
        data_rows.append(("Traffic P90", traffic_p90, _NUMBER_FMT, False))

    data_rows.append(("Transactions", monthly_transactions, _NUMBER_FMT, True))

    if monthly_cvr is not None:
        # Excel's 0.00% format expects the decimal form (0.025 → "2.50%")
        cvr_decimal = [v / 100.0 for v in monthly_cvr]
        data_rows.append(("CVR %", cvr_decimal, _PERCENT_FMT, False))

    if monthly_aov is not None:
        data_rows.append(("AOV", monthly_aov, _CURRENCY_FMT, False))

    data_rows.append(("Revenue", monthly_revenue, _CURRENCY_FMT, True))

    if revenue_p10 is not None:
        data_rows.append(("Revenue P10", revenue_p10, _CURRENCY_FMT, False))
    if revenue_p90 is not None:
        data_rows.append(("Revenue P90", revenue_p90, _CURRENCY_FMT, False))

    _build_forecast_sheet(ws, title_text, month_names, months, data_rows)

    # Sheet 2: Stream Breakdown (only when stream data provided)
    has_streams = any(x is not None for x in [
        monthly_baseline, monthly_positional_uplift,
        monthly_new_content_uplift, monthly_decay,
    ])
    if has_streams:
        ws2 = wb.create_sheet("Stream Breakdown")
        _build_stream_sheet(
            ws2, month_names, months,
            monthly_baseline, monthly_positional_uplift,
            monthly_new_content_uplift, monthly_decay,
            monthly_traffic,
        )

    # Sheet 3: Assumptions (only when summary provided)
    if assumptions_summary:
        ws3 = wb.create_sheet("Assumptions")
        _build_assumptions_sheet(ws3, assumptions_summary)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
