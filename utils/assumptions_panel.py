"""Assumptions panel — Streamlit component for viewing and overriding forecast assumptions.

Renders assumptions grouped by category with colour-coded provenance badges:
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
    initialise_assumptions,
    override_assumption,
)

_PROVENANCE_BADGE = {
    "defaulted": ":gray-badge[defaulted]",
    "detected": ":blue-badge[detected]",
    "overridden": ":green-badge[overridden]",
}

_KNOWN_INDUSTRIES = [
    "Unknown", "Accessories", "Apparel", "Automotive", "B2B SaaS",
    "Beauty", "Finance", "Food & Beverage", "Health", "Home", "Travel", "Other",
]

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
    "Content & Maintenance": [
        "content_cadence", "maintenance_coverage",
    ],
    "Brand": [
        "brand_terms", "exclude_brand_from_forecasts",
    ],
    "Financial Model": [
        "blended_cr_pct", "aov", "currency",
    ],
    "Seasonality": [
        "seasonality_source", "seasonality_blend_weight",
    ],
    "AIO": [
        "aio_monthly_growth", "aio_ctr_penalty_informational",
    ],
    "Decay": [
        "decay_rate_top3", "decay_rate_top10",
    ],
}


def _badge(provenance: str) -> str:
    return _PROVENANCE_BADGE.get(provenance, provenance)


def _get_store() -> dict:
    store = st.session_state.setdefault("assumptions", {})
    initialise_assumptions(store)
    return store


def render_assumptions_banner(store: dict | None = None) -> None:
    """Render a compact one-line status bar showing provenance counts."""
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
    """Render the full assumptions table grouped by category with override controls."""
    if store is None:
        store = _get_store()

    summary_by_key = {row["key"]: row for row in assumptions_summary(store)}
    seen_keys: set[str] = set()

    container = st.expander("Forecast Assumptions", expanded=False) if expandable else st
    with container:
        st.caption(
            "Values detected from your data are shown in blue. "
            "Override any assumption below — overrides persist for the session."
        )

        for group_name, keys in _ASSUMPTION_GROUPS.items():
            group_rows = [summary_by_key[k] for k in keys if k in summary_by_key]
            if not group_rows:
                continue
            st.markdown(f"**{group_name}**")
            for row in group_rows:
                seen_keys.add(row["key"])
                _render_assumption_row(store, row)
            st.divider()

        # Ungrouped assumptions (catch-all)
        ungrouped = [r for k, r in summary_by_key.items() if k not in seen_keys]
        if ungrouped:
            st.markdown("**Other**")
            for row in ungrouped:
                _render_assumption_row(store, row)


def _render_assumption_row(store: dict, row: dict) -> None:
    key = row["key"]
    if key not in ASSUMPTIONS:
        return
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
        display = ", ".join(current_value) if isinstance(current_value, list) else str(current_value)
        st.markdown(f"`{display}{unit}`")

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

    default_val = current_value if current_value is not None else meta.default

    # ── Special-case widgets ──────────────────────────────────────────────────
    if key == "brand_terms":
        terms_text = "\n".join(default_val) if isinstance(default_val, list) else str(default_val or "")
        new_text = st.text_area(
            "Override (one per line)", value=terms_text, key=widget_key,
            label_visibility="collapsed", height=80,
        )
        if st.button("Apply", key=f"apply_{key}", use_container_width=True):
            new_list = [t.strip() for t in new_text.splitlines() if t.strip()]
            if new_list != default_val:
                override_assumption(store, key, new_list, source="manual override")
                st.rerun()
        return

    if key == "industry":
        options = _KNOWN_INDUSTRIES
        idx = options.index(str(default_val)) if str(default_val) in options else 0
        new_val = st.selectbox("Override", options, index=idx, key=widget_key, label_visibility="collapsed")
        if st.button("Apply", key=f"apply_{key}", use_container_width=True):
            if new_val != default_val:
                override_assumption(store, key, new_val, source="manual override")
                st.rerun()
        return

    if key == "strategy_restart_month":
        none_opt = "None (no restart)"
        month_opts = [none_opt] + [str(m) for m in range(1, 37)]
        cur_str = none_opt if default_val is None else str(int(default_val))
        if cur_str not in month_opts:
            cur_str = none_opt
        new_str = st.selectbox("Override", month_opts, index=month_opts.index(cur_str), key=widget_key, label_visibility="collapsed")
        if st.button("Apply", key=f"apply_{key}", use_container_width=True):
            new_val = None if new_str == none_opt else int(new_str)
            if new_val != default_val:
                override_assumption(store, key, new_val, source="manual override")
                st.rerun()
        return

    # ── Effort-level dropdowns ─────────────────────────────────────────────────
    if key in ("effort_level", "positional_effort_level") or key.endswith("_effort_level"):
        options = ["light", "moderate", "aggressive"]
        idx = options.index(str(default_val)) if str(default_val) in options else 1
        new_val = st.selectbox("Override", options, index=idx, key=widget_key, label_visibility="collapsed")
        if st.button("Apply", key=f"apply_{key}", use_container_width=True):
            if new_val != default_val:
                override_assumption(store, key, new_val, source="manual override")
                st.rerun()
        return

    if key == "currency":
        from engine.revenue_engine import CURRENCY_SYMBOLS
        options = list(CURRENCY_SYMBOLS.keys())
        idx = options.index(str(default_val)) if str(default_val) in options else 0
        new_val = st.selectbox("Override", options, index=idx, key=widget_key, label_visibility="collapsed")
        if st.button("Apply", key=f"apply_{key}", use_container_width=True):
            if new_val != default_val:
                override_assumption(store, key, new_val, source="manual override")
                st.rerun()
        return

    # ── Numeric widgets ────────────────────────────────────────────────────────
    if isinstance(default_val, bool):
        new_val = st.checkbox("Enable", value=bool(default_val), key=widget_key, label_visibility="collapsed")
        if st.button("Apply", key=f"apply_{key}", use_container_width=True):
            if new_val != default_val:
                override_assumption(store, key, new_val, source="manual override")
                st.rerun()
        return

    if isinstance(default_val, float):
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
