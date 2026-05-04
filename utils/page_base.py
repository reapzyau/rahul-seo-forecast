"""Shared Streamlit page scaffolding.

Every page starts with roughly the same 15 lines — header, caption, AI settings,
assumptions init, data-availability checks. This module collapses that to one call.
"""
from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from engine.assumptions import initialise_assumptions
from utils.assumptions_panel import render_assumptions_banner
from utils.data_status import RequirementItem, check_requirements
from utils.session import ASSUMPTIONS
from utils.sidebar import render_ai_settings


def _render_data_banner(requirements: list[str]) -> None:
    """Render a compact data-readiness row and stop if hard requirements are missing."""
    session = dict(st.session_state)
    all_hard_met, any_opt_missing, items = check_requirements(requirements, session)

    def _icon(item: RequirementItem) -> str:
        if item.loaded:
            return "✅"
        return "☐" if not item.required else "❌"

    parts = []
    for item in items:
        icon = _icon(item)
        detail = f" ({item.detail})" if item.detail else ""
        parts.append(f"{icon} **{item.label}**{detail}")

    st.caption("  ·  ".join(parts))

    if not all_hard_met:
        missing_labels = [i.label for i in items if i.required and not i.loaded]
        st.warning(
            f"Missing required data: **{', '.join(missing_labels)}**. "
            "Upload files on the Data pages before running this forecast.",
            icon="🔒",
        )
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            st.page_link("pages/inputs/ga4.py", label="GA4 Upload", icon="📊")
        with col2:
            st.page_link("pages/inputs/semrush.py", label="SEMrush Upload", icon="🔑")
        st.stop()


def setup_page(
    title: str,
    caption: str,
    *,
    requires: Iterable[str] = (),
    data_requirements: list[str] | None = None,
    show_assumptions_banner: bool = True,
) -> dict:
    """Render page header and return the assumptions store.

    Args:
        title: Page header (rendered via st.header).
        caption: Subtitle under the header.
        requires: Session-state keys that must exist (legacy — prefer data_requirements).
                  If any are missing, show an info message and call st.stop().
        data_requirements: Requirement spec strings (see utils/data_status module docs).
                           Renders a compact status row and stops on hard-missing.
        show_assumptions_banner: Whether to render the provenance counts bar.

    Returns:
        The assumptions store dict (for passing to get_assumption, override_assumption).
    """
    st.header(title)
    st.caption(caption)
    render_ai_settings()

    store = st.session_state.setdefault(ASSUMPTIONS, {})
    initialise_assumptions(store)

    if show_assumptions_banner:
        render_assumptions_banner(store)

    if data_requirements:
        _render_data_banner(data_requirements)

    # Legacy hard-key check
    missing = [key for key in requires if key not in st.session_state]
    if missing:
        friendly = ", ".join(f"`{m}`" for m in missing)
        st.info(
            f"This page needs data that isn't loaded yet: {friendly}. "
            "Go to the **Data** page and upload the required files."
        )
        st.stop()

    return store
