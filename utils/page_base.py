"""Shared Streamlit page scaffolding.

Every page starts with roughly the same 15 lines — header, caption, AI settings,
assumptions init, data-availability checks. This module collapses that to one call.
"""
from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from engine.assumptions import initialise_assumptions
from utils.assumptions_panel import render_assumptions_banner
from utils.session import ASSUMPTIONS
from utils.sidebar import render_ai_settings


def setup_page(
    title: str,
    caption: str,
    *,
    requires: Iterable[str] = (),
    show_assumptions_banner: bool = True,
) -> dict:
    """Render page header and return the assumptions store.

    Args:
        title: Page header (rendered via st.header).
        caption: Subtitle under the header.
        requires: Session-state keys that must exist. If any are missing,
                  show an info message and call st.stop().
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

    missing = [key for key in requires if key not in st.session_state]
    if missing:
        friendly = ", ".join(f"`{m}`" for m in missing)
        st.info(
            f"This page needs data that isn't loaded yet: {friendly}. "
            "Go to the **Data** page and upload the required files."
        )
        st.stop()

    return store
