"""Data readiness helpers — pure Python, no Streamlit import.

All public functions accept an explicit ``session`` dict so they can be tested
without a running Streamlit context.  In pages, pass ``dict(st.session_state)``.

Requirement spec format
-----------------------
Each entry in a requirements list is a string of the form::

    "ga4"                           # single hard requirement
    "roadmap:optional"              # single optional
    "kw_df|roadmap_content_plan"    # hard — any ONE of these keys satisfies it
    "pos_result|nc_result:optional" # optional — any one suffices

"""
from __future__ import annotations

from dataclasses import dataclass

from utils.session import (
    COMB_RESULTS,
    GA4_DF,
    HIST_RESULTS,
    KW_DF,
    KW_EXISTING,
    NC_RESULT,
    POS_RESULT,
    ROADMAP_BUNDLE,
    ROADMAP_CONTENT_PLAN,
)

# Maps short name → (session_key, display_label)
_REGISTRY: dict[str, tuple[str, str]] = {
    "ga4":                  (GA4_DF,               "GA4 organic"),
    "kw_df":                (KW_DF,                "SEMrush keywords"),
    "kw_existing":          (KW_EXISTING,          "SEMrush keywords"),
    "roadmap":              (ROADMAP_BUNDLE,        "Roadmap"),
    "roadmap_content_plan": (ROADMAP_CONTENT_PLAN, "Content plan"),
    "pos_result":           (POS_RESULT,            "Positional"),
    "nc_result":            (NC_RESULT,             "New Content"),
    "hist_results":         (HIST_RESULTS,          "Historical"),
    "comb_results":         (COMB_RESULTS,          "Combined"),
}

# Maps short name → callable(value) → human detail string
_DETAIL: dict[str, object] = {
    "ga4":                  lambda v: f"{len(v)} months",
    "kw_df":                lambda v: f"{len(v):,} keywords",
    "kw_existing":          lambda v: f"{len(v):,} ranking",
    "roadmap":              lambda _: "AI extracted",
    "roadmap_content_plan": lambda v: f"{len(v)} pieces",
    "pos_result":           lambda _: "run",
    "nc_result":            lambda _: "run",
    "hist_results":         lambda _: "run",
    "comb_results":         lambda _: "run",
}


@dataclass
class RequirementItem:
    name: str        # pipe-joined spec name, e.g. "kw_df|roadmap_content_plan"
    label: str       # display label, e.g. "SEMrush keywords"
    required: bool   # False = optional
    loaded: bool     # True if at least one key in the spec was found
    detail: str = "" # e.g. "24 months", "1,018 ranking"


def parse_spec(spec: str) -> tuple[list[str], bool]:
    """Parse a requirement spec string into (names, is_optional).

    >>> parse_spec("ga4")
    (['ga4'], False)
    >>> parse_spec("roadmap:optional")
    (['roadmap'], True)
    >>> parse_spec("kw_df|roadmap_content_plan")
    (['kw_df', 'roadmap_content_plan'], False)
    """
    optional = spec.endswith(":optional")
    spec = spec.removesuffix(":optional")
    return spec.split("|"), optional


def _make_item(names: list[str], session: dict, required: bool) -> RequirementItem:
    label = _REGISTRY[names[0]][1] if names[0] in _REGISTRY else names[0]
    loaded_name: str | None = None
    loaded_value = None

    for n in names:
        sk = _REGISTRY[n][0] if n in _REGISTRY else n
        if sk in session:
            loaded_name = n
            loaded_value = session[sk]
            if n in _REGISTRY:
                label = _REGISTRY[n][1]
            break

    detail = ""
    if loaded_name is not None:
        fn = _DETAIL.get(loaded_name)
        if fn is not None:
            try:
                detail = fn(loaded_value)  # type: ignore[operator]
            except Exception:
                pass

    return RequirementItem(
        name="|".join(names),
        label=label,
        required=required,
        loaded=loaded_name is not None,
        detail=detail,
    )


def check_requirements(
    requirements: list[str],
    session: dict,
) -> tuple[bool, bool, list[RequirementItem]]:
    """Check data requirements against a session-state dict.

    Args:
        requirements: List of spec strings (see module docstring).
        session:      Mapping of session-state keys to values.

    Returns:
        ``(all_hard_met, any_optional_missing, items)``
    """
    items: list[RequirementItem] = []
    all_hard_met = True
    any_optional_missing = False

    for spec in requirements:
        names, optional = parse_spec(spec)
        item = _make_item(names, session, required=not optional)
        items.append(item)
        if not item.loaded:
            if not optional:
                all_hard_met = False
            else:
                any_optional_missing = True

    return all_hard_met, any_optional_missing, items


# ---------------------------------------------------------------------------
# Sidebar / app.py helpers
# ---------------------------------------------------------------------------

def page_status_emoji(
    hard_keys: list[str],
    soft_keys: list[str],
    session: dict,
) -> str:
    """Return " ✓", " ⚠", or " 🔒" for a page based on data state.

    Used in app.py to annotate sidebar page titles.
    """
    hard_ok = all(k in session for k in hard_keys)
    soft_ok = all(k in session for k in soft_keys)
    if not hard_ok:
        return " 🔒"
    if not soft_ok:
        return " ⚠"
    return " ✓"
