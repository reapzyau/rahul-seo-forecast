"""Centralised assumptions store for the SEO forecasting engine.

All forecast parameters that can be detected from data or overridden by the
user live here. Downstream engines read from the store instead of hardcoding
defaults — making the assumptions visible, auditable, and changeable in one
place.

Provenance tracking:
  "defaulted"  — using the built-in default, no data or user input yet
  "detected"   — value was inferred from uploaded data (GA4, roadmap, etc.)
  "overridden" — user has explicitly set this value via the assumptions panel

Usage (in a Streamlit page):
    from engine.assumptions import initialise_assumptions, get_assumption, run_detection
    store = st.session_state.setdefault("assumptions", {})
    initialise_assumptions(store)
    run_detection(store, ga4_df=ga4_df)
    cvr = get_assumption(store, "blended_cr_pct")

Usage (in tests):
    store = {}
    initialise_assumptions(store)
    assert get_assumption(store, "blended_cr_pct") == 2.5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Provenance = Literal["defaulted", "detected", "overridden"]

_VAL = "value"
_PROV = "provenance"
_SRC = "source"


@dataclass
class Assumption:
    """Metadata definition for a single forecast assumption."""
    key: str
    label: str
    default: Any
    unit: str = ""
    min_val: float | None = None
    max_val: float | None = None


ASSUMPTIONS: dict[str, Assumption] = {
    "blended_cr_pct": Assumption(
        key="blended_cr_pct",
        label="Blended Conversion Rate",
        default=2.5,
        unit="%",
        min_val=0.0,
        max_val=100.0,
    ),
    "aov": Assumption(
        key="aov",
        label="Average Order Value",
        default=100.0,
        unit="$",
        min_val=0.0,
        max_val=None,
    ),
    "currency": Assumption(
        key="currency",
        label="Currency",
        default="USD",
        unit="",
    ),
    # ── Backward-compat rollup keys (computed from per-focus keys) ────────────
    "effort_level": Assumption(
        key="effort_level",
        label="Effort Level",
        default="moderate",
        unit="",
    ),
    "content_cadence": Assumption(
        key="content_cadence",
        label="Content Cadence",
        default=4,
        unit="posts/month",
        min_val=1,
        max_val=100,
    ),
    "maintenance_coverage": Assumption(
        key="maintenance_coverage",
        label="Maintenance Coverage",
        default=0.0,
        unit="",
        min_val=0.0,
        max_val=1.0,
    ),
    "aio_monthly_growth": Assumption(
        key="aio_monthly_growth",
        label="AIO Monthly Growth Rate",
        default=0.025,
        unit="",
        min_val=0.0,
        max_val=1.0,
    ),
    "aio_ctr_penalty_informational": Assumption(
        key="aio_ctr_penalty_informational",
        label="AIO CTR Penalty (Informational)",
        default=0.45,
        unit="",
        min_val=0.0,
        max_val=1.0,
    ),
    "decay_rate_top3": Assumption(
        key="decay_rate_top3",
        label="Annual Decay Rate (Top 3)",
        default=0.08,
        unit="",
        min_val=0.0,
        max_val=1.0,
    ),
    "decay_rate_top10": Assumption(
        key="decay_rate_top10",
        label="Annual Decay Rate (Top 10)",
        default=0.12,
        unit="",
        min_val=0.0,
        max_val=1.0,
    ),
    "brand_terms": Assumption(
        key="brand_terms",
        label="Brand Terms",
        default=[],
        unit="",
    ),
    "exclude_brand_from_forecasts": Assumption(
        key="exclude_brand_from_forecasts",
        label="Exclude Brand from Forecasts",
        default=True,
        unit="",
    ),
    "seasonality_source": Assumption(
        key="seasonality_source",
        label="Seasonality Source",
        default="defaulted",
        unit="",
    ),
    "seasonality_blend_weight": Assumption(
        key="seasonality_blend_weight",
        label="Seasonality Blend Weight",
        default=0.0,
        unit="",
        min_val=0.0,
        max_val=1.0,
    ),
    # ── Per-focus effort levels ───────────────────────────────────────────────
    "content_effort_level": Assumption(
        key="content_effort_level",
        label="Content Effort Level",
        default="moderate",
        unit="",
    ),
    "technical_effort_level": Assumption(
        key="technical_effort_level",
        label="Technical Effort Level",
        default="moderate",
        unit="",
    ),
    "on_page_effort_level": Assumption(
        key="on_page_effort_level",
        label="On-Page Effort Level",
        default="moderate",
        unit="",
    ),
    "off_page_effort_level": Assumption(
        key="off_page_effort_level",
        label="Off-Page Effort Level",
        default="moderate",
        unit="",
    ),
    "local_effort_level": Assumption(
        key="local_effort_level",
        label="Local Effort Level",
        default="moderate",
        unit="",
    ),
    "analytics_effort_level": Assumption(
        key="analytics_effort_level",
        label="Analytics Effort Level",
        default="moderate",
        unit="",
    ),
    "strategy_effort_level": Assumption(
        key="strategy_effort_level",
        label="Strategy Effort Level",
        default="moderate",
        unit="",
    ),
    # ── Per-focus monthly hours ───────────────────────────────────────────────
    "content_monthly_hours": Assumption(
        key="content_monthly_hours",
        label="Content Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "technical_monthly_hours": Assumption(
        key="technical_monthly_hours",
        label="Technical Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "on_page_monthly_hours": Assumption(
        key="on_page_monthly_hours",
        label="On-Page Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "off_page_monthly_hours": Assumption(
        key="off_page_monthly_hours",
        label="Off-Page Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "local_monthly_hours": Assumption(
        key="local_monthly_hours",
        label="Local Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "analytics_monthly_hours": Assumption(
        key="analytics_monthly_hours",
        label="Analytics Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "strategy_monthly_hours": Assumption(
        key="strategy_monthly_hours",
        label="Strategy Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    # ── Portfolio-level derived ───────────────────────────────────────────────
    "total_monthly_hours": Assumption(
        key="total_monthly_hours",
        label="Total Monthly Hours",
        default=0.0,
        unit="hrs/month",
        min_val=0.0,
        max_val=None,
    ),
    "positional_effort_level": Assumption(
        key="positional_effort_level",
        label="Positional Effort Level",
        default="moderate",
        unit="",
    ),
    "timeline_months_covered": Assumption(
        key="timeline_months_covered",
        label="Strategy Timeline (Months)",
        default=12,
        unit="months",
        min_val=1,
        max_val=60,
    ),
    "strategy_restart_month": Assumption(
        key="strategy_restart_month",
        label="Strategy Restart Month",
        default=None,
        unit="",
    ),
    # ── Client metadata ───────────────────────────────────────────────────────
    "industry": Assumption(
        key="industry",
        label="Industry",
        default="Unknown",
        unit="",
    ),
    "retainer_aud_monthly": Assumption(
        key="retainer_aud_monthly",
        label="Monthly Retainer (AUD)",
        default=0.0,
        unit="AUD/month",
        min_val=0.0,
        max_val=None,
    ),
    "client_name": Assumption(
        key="client_name",
        label="Client Name",
        default="",
        unit="",
    ),
}


# ── Core store API ────────────────────────────────────────────────────────────


def initialise_assumptions(store: dict, force: bool = False) -> None:
    """Populate store with defaults. No-op if already initialised (unless force=True)."""
    if not force and store.get("_initialised"):
        return
    for key, assumption in ASSUMPTIONS.items():
        if force or key not in store:
            store[key] = {
                _VAL: assumption.default,
                _PROV: "defaulted",
                _SRC: "built-in default",
            }
    store["_initialised"] = True


def get_assumption(store: dict, key: str) -> Any:
    """Return the current value for an assumption key."""
    if key not in ASSUMPTIONS:
        raise KeyError(f"Unknown assumption: {key!r}")
    entry = store.get(key)
    if entry is None:
        return ASSUMPTIONS[key].default
    return entry.get(_VAL, ASSUMPTIONS[key].default)


def get_provenance(store: dict, key: str) -> dict:
    """Return full provenance record for an assumption."""
    if key not in ASSUMPTIONS:
        raise KeyError(f"Unknown assumption: {key!r}")
    entry = store.get(key, {})
    meta = ASSUMPTIONS[key]
    return {
        "key": key,
        "label": meta.label,
        "value": entry.get(_VAL, meta.default),
        "provenance": entry.get(_PROV, "defaulted"),
        "source": entry.get(_SRC, "built-in default"),
        "unit": meta.unit,
    }


def override_assumption(
    store: dict,
    key: str,
    value: Any,
    source: str = "user override",
) -> None:
    """Explicitly set an assumption value, marking it as overridden."""
    if key not in ASSUMPTIONS:
        raise KeyError(f"Unknown assumption: {key!r}")
    store[key] = {_VAL: value, _PROV: "overridden", _SRC: source}


def clear_override(store: dict, key: str) -> None:
    """Revert an overridden assumption to its built-in default.

    Detected values are not restored — a fresh run_detection() call is needed.
    """
    if key not in ASSUMPTIONS:
        raise KeyError(f"Unknown assumption: {key!r}")
    if store.get(key, {}).get(_PROV) != "overridden":
        return
    store[key] = {
        _VAL: ASSUMPTIONS[key].default,
        _PROV: "defaulted",
        _SRC: "built-in default",
    }


def assumptions_summary(store: dict) -> list[dict]:
    """Return provenance records for all assumptions in registry order."""
    return [get_provenance(store, key) for key in ASSUMPTIONS]


# ── Rollup helpers ────────────────────────────────────────────────────────────


def recompute_rollups(store: dict) -> None:
    """Recompute the 3 backward-compat rollups from per-focus keys.

    Call at the end of _detect_from_roadmap after roadmap processing.
    Rollups are written as "detected" unless the user has already overridden them.
    """
    # effort_level = max of content, on_page, off_page effort levels
    _EFFORT_ORDER = {"light": 0, "moderate": 1, "aggressive": 2}
    effort_keys = ("content_effort_level", "on_page_effort_level", "off_page_effort_level")
    efforts = [get_assumption(store, k) for k in effort_keys]
    max_effort = max(efforts, key=lambda e: _EFFORT_ORDER.get(e, 1))
    _set_detected(store, "effort_level", max_effort, "rollup from per-focus effort levels")

    # maintenance_coverage = clamp((on_page_hours + technical_hours) / 20, 0, 1)
    on_page_hrs = float(get_assumption(store, "on_page_monthly_hours") or 0.0)
    technical_hrs = float(get_assumption(store, "technical_monthly_hours") or 0.0)
    maintenance = round(min((on_page_hrs + technical_hrs) / 20.0, 1.0), 3)
    _set_detected(store, "maintenance_coverage", maintenance, "rollup from on_page + technical hours")

    # content_cadence = max(1, round(content_monthly_hours / 10))
    content_hrs = float(get_assumption(store, "content_monthly_hours") or 0.0)
    cadence = max(1, round(content_hrs / 10.0))
    _set_detected(store, "content_cadence", cadence, "rollup from content monthly hours")

    # positional_effort_level = max of on_page, off_page
    pos_efforts = [get_assumption(store, "on_page_effort_level"), get_assumption(store, "off_page_effort_level")]
    pos_effort = max(pos_efforts, key=lambda e: _EFFORT_ORDER.get(e, 1))
    _set_detected(store, "positional_effort_level", pos_effort, "rollup from on_page + off_page effort")

    # total_monthly_hours = sum of all per-focus hours
    focus_hours_keys = (
        "content_monthly_hours", "technical_monthly_hours", "on_page_monthly_hours",
        "off_page_monthly_hours", "local_monthly_hours", "analytics_monthly_hours",
        "strategy_monthly_hours",
    )
    total_hours = sum(float(get_assumption(store, k) or 0.0) for k in focus_hours_keys)
    _set_detected(store, "total_monthly_hours", round(total_hours, 2), "rollup from per-focus hours")


# ── Detection layer ───────────────────────────────────────────────────────────


def run_detection(
    store: dict,
    ga4_df=None,
    kw_df=None,
    roadmap_data: dict | None = None,
) -> list[str]:
    """Detect assumption values from available data. Returns list of updated keys.

    Only updates assumptions that are "defaulted" or "detected" — never
    overwrites "overridden" values set by the user.
    """
    detected: list[str] = []

    if ga4_df is not None:
        detected.extend(_detect_from_ga4(store, ga4_df))

    if kw_df is not None:
        detected.extend(_detect_from_keywords(store, kw_df))

    if roadmap_data is not None:
        detected.extend(_detect_from_roadmap(store, roadmap_data))

    return detected


def _set_detected(store: dict, key: str, value: Any, source: str) -> None:
    """Update store with a detected value unless the user has overridden it."""
    if store.get(key, {}).get(_PROV) == "overridden":
        return
    store[key] = {_VAL: value, _PROV: "detected", _SRC: source}


def _detect_from_ga4(store: dict, ga4_df) -> list[str]:
    detected: list[str] = []

    traffic_col = "traffic" if "traffic" in ga4_df.columns else None
    txn_col = "transactions" if "transactions" in ga4_df.columns else None
    aov_col = "aov" if "aov" in ga4_df.columns else None

    if traffic_col and txn_col:
        total_traffic = float(ga4_df[traffic_col].sum())
        if total_traffic > 0:
            total_txn = float(ga4_df[txn_col].sum())
            cr_pct = round(total_txn / total_traffic * 100, 2)
            _set_detected(store, "blended_cr_pct", cr_pct, "GA4 sessions + transactions")
            detected.append("blended_cr_pct")

    if aov_col:
        valid = ga4_df[aov_col].dropna()
        if len(valid) > 0:
            aov = round(float(valid.mean()), 2)
            _set_detected(store, "aov", aov, "GA4 average order value")
            detected.append("aov")

    return detected


def _detect_from_keywords(store: dict, kw_df) -> list[str]:
    return []


def _detect_from_roadmap(store: dict, roadmap_data: dict) -> list[str]:
    detected: list[str] = []

    # Handle v2 bundle format (schema_version starts with "2.")
    if roadmap_data.get("schema_version", "").startswith("2."):
        detected.extend(_detect_from_bundle_v2(store, roadmap_data))
        recompute_rollups(store)
        return detected

    # Legacy v1 format (3-scalar dict from utils/roadmap_loader.py)
    mapping = {
        "effort_level": "roadmap import",
        "content_cadence": "roadmap import",
        "maintenance_coverage": "roadmap import",
    }
    for key, source in mapping.items():
        if key in roadmap_data and roadmap_data[key] is not None:
            _set_detected(store, key, roadmap_data[key], source)
            detected.append(key)
    return detected


def _detect_from_bundle_v2(store: dict, bundle: dict) -> list[str]:
    """Extract assumption values from a v2 roadmap bundle."""
    detected: list[str] = []

    # Client metadata
    meta = bundle.get("client_metadata", {})
    for key in ("client_name", "industry", "retainer_aud_monthly"):
        val = meta.get(key)
        if val is not None and val != "" and val != 0.0:
            _set_detected(store, key, val, "roadmap extraction")
            detected.append(key)

    # Per-focus effort levels and monthly hours
    per_focus = bundle.get("per_focus", {})
    focus_map = {
        "content": "content",
        "technical": "technical",
        "on_page": "on_page",
        "off_page": "off_page",
        "local": "local",
        "analytics": "analytics",
        "strategy": "strategy",
    }
    for focus_key, assumption_prefix in focus_map.items():
        focus_data = per_focus.get(focus_key, {})
        effort = focus_data.get("effort_level")
        if effort in ("light", "moderate", "aggressive"):
            key = f"{assumption_prefix}_effort_level"
            _set_detected(store, key, effort, "roadmap extraction")
            detected.append(key)
        hours = focus_data.get("monthly_hours")
        if isinstance(hours, (int, float)):
            key = f"{assumption_prefix}_monthly_hours"
            _set_detected(store, key, float(hours), "roadmap extraction")
            detected.append(key)

    # Timeline
    timeline = bundle.get("timeline", {})
    months = timeline.get("months_covered")
    if months is not None:
        _set_detected(store, "timeline_months_covered", int(months), "roadmap extraction")
        detected.append("timeline_months_covered")
    restart = timeline.get("strategy_restart_month")
    _set_detected(store, "strategy_restart_month", restart, "roadmap extraction")
    detected.append("strategy_restart_month")

    return detected
