"""Assumptions panel — Streamlit component for viewing and overriding forecast assumptions.

Renders a table of all assumptions with colour-coded provenance badges:
  defaulted   — grey  — using built-in default
  detected    — blue  — inferred from uploaded data
  overridden  — green — explicitly set by the user

Usage in a page:
    from utils.assumptions_panel import render_assumptions_panel, render_assumptions_banner
    store = st.session_state.setdefault("assumptions", {})
    render_assumptions_banner(store)     # compact inline notice at top of page
    render_assumptions_panel(store)      # full table with override widgets
"""
from __future__ import annotations

import streamlit as st

from engine.assumptions import (
    ASSUMPTIONS,
    assumptions_summary,
    clear_override,
    get_assumption,
    get_provenance,
    initialise_assumptions,
    override_assumption,
    run_detection,
)

_PROVENANCE_BADGE = {
    "defaulted": ":gray-badge[defaulted]",
    "detected": ":blue-badge[detected]",
    "overridden": ":green-badge[overridden]",
}

_PROVENANCE_COLOUR = {
    "defaulted": "#94A3B8",
    "detected": "#2563EB",
    "overridden": "#22C55E",
}


def _badge(provenance: str) -> str:
    return _PROVENANCE_BADGE.get(provenance, provenance)


def _get_store() -> dict:
    store = st.session_state.setdefault("assumptions", {})
    initialise_assumptions(store)
    return store


def render_assumptions_banner(store: dict | None = None) -> None:
    """Render a compact one-line status bar showing provenance counts.

    Shows how many assumptions are detected vs defaulted vs overridden.
    Call at the top of each forecast page after the header.
    """
    if store is None:
        store = _get_store()

    summary = assumptions_summary(store)
    counts: dict[str, int] = {"defaulted": 0, "detected": 0, "overridden": 0}
    for row in summary:
        counts[row["provenance"]] = counts.get(row["provenance"], 0) + 1

    parts: list[str] = []
    if counts["detected"]:
        parts.append(f"**{counts['detected']} detected** from data")
    if counts["overridden"]:
        parts.append(f"**{counts['overridden']} overridden** by you")
    if counts["defaulted"]:
        parts.append(f"{counts['defaulted']} using defaults")

    if not parts:
        return

    msg = "Assumptions: " + " · ".join(parts) + "."
    if counts["defaulted"] == len(summary):
        st.info(msg + " Upload GA4 data or a roadmap to auto-detect values.")
    else:
        st.info(msg)


def render_assumptions_panel(store: dict | None = None, *, expandable: bool = True) -> None:
    """Render the full assumptions table with override controls.

    Each row shows: Assumption label | current value | provenance badge | override input.
    """
    if store is None:
        store = _get_store()

    summary = assumptions_summary(store)

    container = st.expander("Forecast Assumptions", expanded=False) if expandable else st
    with container:
        st.caption(
            "Values detected from your data are shown in blue. "
            "Override any assumption below — overrides persist for the session."
        )
        for row in summary:
            _render_assumption_row(store, row)


def _render_assumption_row(store: dict, row: dict) -> None:
    key = row["key"]
    meta = ASSUMPTIONS[key]
    provenance = row["provenance"]
    current_value = row["value"]
    badge = _badge(provenance)

    col_label, col_val, col_badge, col_action = st.columns([3, 2, 2, 3])

    with col_label:
        st.markdown(f"**{row['label']}**")
        if row.get("source") and provenance != "defaulted":
            st.caption(f"Source: {row['source']}")

    with col_val:
        unit = f" {meta.unit}" if meta.unit else ""
        st.markdown(f"`{current_value}{unit}`")

    with col_badge:
        st.markdown(badge)

    with col_action:
        _render_override_widget(store, key, meta, provenance, current_value)


def _render_override_widget(store: dict, key: str, meta, provenance: str, current_value) -> None:
    widget_key = f"assumption_override_{key}"
    clear_key = f"assumption_clear_{key}"

    if provenance == "overridden":
        if st.button("Clear override", key=clear_key, use_container_width=True):
            clear_override(store, key)
            st.rerun()
        return

    # Show appropriate input widget for the value type
    default_val = current_value if current_value is not None else meta.default

    if key == "effort_level":
        options = ["light", "moderate", "aggressive"]
        idx = options.index(str(default_val)) if str(default_val) in options else 1
        new_val = st.selectbox("Override", options, index=idx, key=widget_key, label_visibility="collapsed")
    elif key == "currency":
        from engine.revenue_engine import CURRENCY_SYMBOLS
        options = list(CURRENCY_SYMBOLS.keys())
        idx = options.index(str(default_val)) if str(default_val) in options else 0
        new_val = st.selectbox("Override", options, index=idx, key=widget_key, label_visibility="collapsed")
    elif isinstance(default_val, float):
        step = 0.01 if meta.max_val is not None and meta.max_val <= 1.0 else 0.1
        new_val = st.number_input(
            "Override",
            min_value=float(meta.min_val) if meta.min_val is not None else 0.0,
            max_value=float(meta.max_val) if meta.max_val is not None else 1e9,
            value=float(default_val),
            step=step,
            key=widget_key,
            label_visibility="collapsed",
        )
    elif isinstance(default_val, int):
        new_val = st.number_input(
            "Override",
            min_value=int(meta.min_val) if meta.min_val is not None else 0,
            max_value=int(meta.max_val) if meta.max_val is not None else 1000,
            value=int(default_val),
            step=1,
            key=widget_key,
            label_visibility="collapsed",
        )
    else:
        new_val = st.text_input("Override", value=str(default_val), key=widget_key, label_visibility="collapsed")

    if st.button("Apply", key=f"apply_{key}", use_container_width=True):
        if new_val != default_val:
            override_assumption(store, key, new_val, source="manual override")
            st.rerun()
