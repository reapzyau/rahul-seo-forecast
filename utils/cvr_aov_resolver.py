"""Centralised resolver for CVR and AOV — single source of truth for page sidebars.

Priority chain (highest wins):
  1. User override in assumptions store          → source="overridden"
  2. GA4 organic channel breakdown               → source="detected"
     (st.session_state["cr_organic"] / ["aov_organic"])
  3. blended_cr_pct / aov from assumptions store → source as stored in store

Each resolver returns a ``(value, source_literal, human_label)`` tuple so pages
can render a caption explaining where the number came from.
"""
from __future__ import annotations

import streamlit as st

from engine.assumptions import get_assumption, get_provenance


def resolve_cvr(store: dict, ga4_df=None) -> tuple[float, str, str]:
    """Return ``(cvr_as_pct, source_literal, human_label)``."""
    prov = get_provenance(store, "blended_cr_pct")
    if prov.get("provenance") == "overridden":
        val = float(get_assumption(store, "blended_cr_pct"))
        return val, "overridden", "assumptions panel override"

    cr_organic = st.session_state.get("cr_organic")
    if cr_organic:
        return float(cr_organic) * 100, "detected", "GA4 organic channel breakdown"

    val = float(get_assumption(store, "blended_cr_pct"))
    prov_type = prov.get("provenance", "defaulted")
    label = "detected from data" if prov_type == "detected" else "built-in default (1.5%)"
    return val, prov_type, label


def resolve_aov(store: dict, ga4_df=None) -> tuple[float, str, str]:
    """Return ``(aov, source_literal, human_label)``."""
    prov = get_provenance(store, "aov")
    if prov.get("provenance") == "overridden":
        val = float(get_assumption(store, "aov"))
        return val, "overridden", "assumptions panel override"

    aov_organic = st.session_state.get("aov_organic")
    if aov_organic:
        return float(aov_organic), "detected", "GA4 organic channel breakdown"

    val = float(get_assumption(store, "aov"))
    prov_type = prov.get("provenance", "defaulted")
    label = "detected from data" if prov_type == "detected" else "built-in default ($100)"
    return val, prov_type, label
