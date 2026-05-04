"""Metric card components — consistent KPI row layout for all forecast pages.

Every forecast page (3–6) shows a row of 4 KPI cards immediately after the
forecast runs. Before this module existed each page invented its own column
counts, label names, and caption patterns.

Usage
-----
For pages 4 (Positional) and 6 (Combined) — standard baseline/end/uplift/% pattern:

    from utils.metric_cards import render_forecast_kpis
    render_forecast_kpis(
        baseline_traffic=12_000,
        forecast_end_traffic=15_000,
        total_uplift=3_000,
        uplift_pct=25.0,
        uplift_p10=1_800,
        uplift_p90=4_500,
    )

For pages 3 (Historical) and 5 (New Content) — custom label sets:

    from utils.metric_cards import KPICard, render_kpi_row
    render_kpi_row([
        KPICard("Current Traffic", "12,000"),
        KPICard("Projected End", "14,500"),
        KPICard("Avg MoM Growth", "2.1%"),
        KPICard("Latest YoY", "+18.3%"),
    ])
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass
class KPICard:
    """Data for a single metric card cell."""
    label: str
    value: str
    delta: str | None = None
    delta_color: str = "normal"   # "normal" | "inverse" | "off"
    caption: str | None = None    # rendered beneath the metric with st.caption
    help: str | None = None


def render_kpi_row(cards: list[KPICard]) -> None:
    """Render up to 4 KPICards in equal-width columns.

    All pages call this for their primary metric row. The 4-column equal-width
    layout is the shared standard; card content is caller-defined.
    """
    n = min(len(cards), 4)
    cols = st.columns(n)
    for col, card in zip(cols, cards[:n], strict=False):
        col.metric(
            label=card.label,
            value=card.value,
            delta=card.delta,
            delta_color=card.delta_color,
            help=card.help,
        )
        if card.caption:
            col.caption(card.caption)


def render_forecast_kpis(
    *,
    baseline_traffic: int,
    forecast_end_traffic: int,
    total_uplift: int,
    uplift_pct: float,
    uplift_p10: int | None = None,
    uplift_p90: int | None = None,
    confidence_note: str | None = None,
    baseline_label: str = "Baseline Traffic",
    forecast_label: str = "Projected End (P50)",
    uplift_label: str = "Total Uplift (P50)",
    pct_label: str = "Uplift %",
) -> None:
    """Standard 4-card layout: Baseline / Forecast End / Uplift / Uplift %.

    Used by pages 4 (Positional) and 6 (Combined) which share the
    baseline-vs-forecast frame. Pages 3 and 5 have different semantics
    and use render_kpi_row() with their own KPICard lists.

    Args:
        baseline_traffic: Starting traffic (month 1 baseline).
        forecast_end_traffic: Traffic at the end of the forecast horizon (P50).
        total_uplift: Absolute incremental sessions over the horizon (P50).
        uplift_pct: Percentage uplift relative to baseline.
        uplift_p10: P10 uplift bound for caption (optional).
        uplift_p90: P90 uplift bound for caption (optional).
        confidence_note: Short string shown beneath the forecast_end card.
        baseline_label: Override the "Baseline Traffic" label.
        forecast_label: Override the "Projected End (P50)" label.
        uplift_label: Override the "Total Uplift (P50)" label.
        pct_label: Override the "Uplift %" label.
    """
    uplift_caption: str | None = None
    if uplift_p10 is not None and uplift_p90 is not None:
        uplift_caption = f"P10 – P90: {uplift_p10:,.0f} – {uplift_p90:,.0f}"

    cards = [
        KPICard(
            label=baseline_label,
            value=f"{baseline_traffic:,}",
        ),
        KPICard(
            label=forecast_label,
            value=f"{forecast_end_traffic:,}",
            caption=confidence_note,
        ),
        KPICard(
            label=uplift_label,
            value=f"{total_uplift:,}",
            caption=uplift_caption,
        ),
        KPICard(
            label=pct_label,
            value=f"{uplift_pct:+.1f}%",
            delta=f"{uplift_pct:+.1f}%",
            delta_color="normal",
        ),
    ]
    render_kpi_row(cards)
