"""Seasonality engine for applying campaign/event modifiers to forecasts.

v4 additions:
- learn_seasonality_from_ga4: compute monthly indices from real GA4 data
- blend_learned_and_default_seasonality: weighted blend of learned vs. AU defaults
- AU_HOLIDAYS: pandas DataFrame for Australian retail holidays (2023-2028)

v5 additions (upgrade guide Sections 1+2):
- derive_seasonality_from_baseline: convert YoY baseline lookup → per-month multipliers
"""

import numpy as np
import pandas as pd

# Default retail seasonality patterns (monthly index 1-12)
DEFAULT_SEASONALITY = {
    1: {"label": "January (Post-Holiday Clearance)", "traffic_mod": -0.05, "cr_mod": 0.10, "aov_mod": -0.10},
    2: {"label": "February (New Season)", "traffic_mod": -0.08, "cr_mod": 0.0, "aov_mod": 0.0},
    3: {"label": "March (Autumn Launch)", "traffic_mod": 0.0, "cr_mod": 0.0, "aov_mod": 0.02},
    4: {"label": "April (Mid-Season)", "traffic_mod": -0.03, "cr_mod": -0.02, "aov_mod": 0.0},
    5: {"label": "May (Winter Preview)", "traffic_mod": 0.05, "cr_mod": 0.02, "aov_mod": 0.03},
    6: {"label": "June (EOFY Sales)", "traffic_mod": 0.15, "cr_mod": 0.08, "aov_mod": -0.05},
    7: {"label": "July (New FY / Winter Sale)", "traffic_mod": 0.10, "cr_mod": 0.05, "aov_mod": -0.08},
    8: {"label": "August (Father's Day Build-up)", "traffic_mod": 0.12, "cr_mod": 0.06, "aov_mod": 0.05},
    9: {"label": "September (Father's Day + Spring)", "traffic_mod": 0.18, "cr_mod": 0.10, "aov_mod": 0.03},
    10: {"label": "October (Spring Campaign)", "traffic_mod": 0.05, "cr_mod": 0.03, "aov_mod": 0.02},
    11: {"label": "November (Black Friday / Frenzy)", "traffic_mod": 0.25, "cr_mod": 0.15, "aov_mod": -0.05},
    12: {"label": "December (Christmas + Summer)", "traffic_mod": 0.20, "cr_mod": 0.12, "aov_mod": 0.08},
}


def apply_seasonality(
    monthly_df: pd.DataFrame,
    seasonality: dict | None = None,
    campaigns: list[dict] | None = None,
    traffic_col: str = "traffic",
) -> pd.DataFrame:
    """Apply seasonal modifiers and campaign events to a monthly forecast.

    Args:
        monthly_df: DataFrame with 'month' (1-indexed) or 'date' column and a traffic column.
        seasonality: Dict of month_number -> {traffic_mod, cr_mod, aov_mod} as decimal %.
                     Defaults to DEFAULT_SEASONALITY.
        campaigns: Optional list of campaign dicts:
                   [{name, month, traffic_boost, cr_boost, aov_boost}]
        traffic_col: Name of the traffic column to modify.

    Returns:
        DataFrame with seasonally adjusted values and modifier columns.
    """
    df = monthly_df.copy()
    season = seasonality or DEFAULT_SEASONALITY

    # Determine month number
    if "date" in df.columns:
        df["_month_num"] = pd.to_datetime(df["date"]).dt.month
    elif "month" in df.columns:
        df["_month_num"] = ((df["month"] - 1) % 12) + 1
    else:
        df["_month_num"] = range(1, len(df) + 1)
        df["_month_num"] = ((df["_month_num"] - 1) % 12) + 1

    # Apply seasonal modifiers
    traffic_mods = []
    cr_mods = []
    aov_mods = []
    season_labels = []

    for _, row in df.iterrows():
        m = int(row["_month_num"])
        s = season.get(m, {"traffic_mod": 0, "cr_mod": 0, "aov_mod": 0, "label": ""})
        traffic_mods.append(s.get("traffic_mod", 0))
        cr_mods.append(s.get("cr_mod", 0))
        aov_mods.append(s.get("aov_mod", 0))
        season_labels.append(s.get("label", f"Month {m}"))

    df["season_label"] = season_labels
    df["traffic_modifier"] = traffic_mods
    df["cr_modifier"] = cr_mods
    df["aov_modifier"] = aov_mods

    # Apply campaign boosts on top
    if campaigns:
        for campaign in campaigns:
            c_month = campaign.get("month")
            if c_month is not None:
                mask = df["_month_num"] == c_month
                df.loc[mask, "traffic_modifier"] += campaign.get("traffic_boost", 0)
                df.loc[mask, "cr_modifier"] += campaign.get("cr_boost", 0)
                df.loc[mask, "aov_modifier"] += campaign.get("aov_boost", 0)
                # Append campaign name to label
                df.loc[mask, "season_label"] = df.loc[mask, "season_label"] + f" + {campaign['name']}"

    # Apply modifiers to traffic
    df[f"{traffic_col}_base"] = df[traffic_col]
    df[traffic_col] = (df[traffic_col] * (1 + df["traffic_modifier"])).round(0).astype(int)

    df = df.drop(columns=["_month_num"])
    return df


_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Public holiday rule definitions — used by build_au_holidays_df()
AU_HOLIDAY_RULES = [
    {"holiday": "EOFY",               "rule": "june_30",           "lower_window": -14, "upper_window": 1},
    {"holiday": "Click Frenzy May",   "rule": "third_tuesday_may", "lower_window": -3,  "upper_window": 3},
    {"holiday": "Click Frenzy Nov",   "rule": "second_tuesday_nov","lower_window": -3,  "upper_window": 3},
    {"holiday": "Black Friday",       "rule": "fourth_friday_nov", "lower_window": -2,  "upper_window": 3},
    {"holiday": "Cyber Monday",       "rule": "monday_after_bf",   "lower_window": -1,  "upper_window": 1},
    {"holiday": "Christmas",          "rule": "dec_25",            "lower_window": -10, "upper_window": 2},
    {"holiday": "Boxing Day Sales",   "rule": "dec_26",            "lower_window": 0,   "upper_window": 7},
    {"holiday": "Back to School",     "rule": "jan_28",            "lower_window": -7,  "upper_window": 7},
]


def _resolve_holiday_date(rule: str, year: int) -> pd.Timestamp:
    """Return the exact date for a holiday rule in the given year."""
    if rule == "june_30":
        return pd.Timestamp(year, 6, 30)
    if rule == "dec_25":
        return pd.Timestamp(year, 12, 25)
    if rule == "dec_26":
        return pd.Timestamp(year, 12, 26)
    if rule == "jan_28":
        return pd.Timestamp(year, 1, 28)
    if rule == "third_tuesday_may":
        first = pd.Timestamp(year, 5, 1)
        days_to_tue = (1 - first.weekday()) % 7
        return first + pd.Timedelta(days=days_to_tue + 14)
    if rule == "second_tuesday_nov":
        first = pd.Timestamp(year, 11, 1)
        days_to_tue = (1 - first.weekday()) % 7
        return first + pd.Timedelta(days=days_to_tue + 7)
    if rule == "fourth_friday_nov":
        first = pd.Timestamp(year, 11, 1)
        days_to_fri = (4 - first.weekday()) % 7
        return first + pd.Timedelta(days=days_to_fri + 21)
    if rule == "monday_after_bf":
        # Cyber Monday = Monday after Black Friday
        bf = _resolve_holiday_date("fourth_friday_nov", year)
        return bf + pd.Timedelta(days=3)
    raise ValueError(f"Unknown holiday rule: {rule!r}")


def build_au_holidays_df(start_year: int = 2023, end_year: int = 2028) -> pd.DataFrame:
    """Expand AU_HOLIDAY_RULES into a Prophet-format holiday DataFrame.

    Columns: holiday, ds, lower_window, upper_window

    Args:
        start_year: First year to generate dates for (inclusive).
        end_year: Last year to generate dates for (inclusive).
    """
    rows = []
    for year in range(start_year, end_year + 1):
        for rule_def in AU_HOLIDAY_RULES:
            ds = _resolve_holiday_date(rule_def["rule"], year)
            rows.append({
                "holiday": rule_def["holiday"],
                "ds": ds,
                "lower_window": rule_def["lower_window"],
                "upper_window": rule_def["upper_window"],
            })
    return pd.DataFrame(rows)


# Pre-built constant for the default range — avoids rebuilding on every import
AU_HOLIDAYS = build_au_holidays_df(2023, 2028)


def learn_seasonality_from_ga4(ga4_df: pd.DataFrame) -> dict | None:
    """Derive monthly seasonality indices from real GA4 traffic data.

    Requires ≥12 months of data. Returns a dict in DEFAULT_SEASONALITY schema
    (keys 1-12, values with traffic_mod, cr_mod, aov_mod, label).

    Returns None when data is insufficient.
    """
    if "date" not in ga4_df.columns or "traffic" not in ga4_df.columns:
        return None
    df = ga4_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month_num"] = df["date"].dt.month

    if len(df) < 12:
        return None

    overall_avg = df["traffic"].mean()
    if overall_avg == 0:
        return None

    learned: dict = {}
    for m in range(1, 13):
        month_rows = df[df["month_num"] == m]
        if month_rows.empty:
            # Fall back to default for missing months
            default = DEFAULT_SEASONALITY.get(m, {"traffic_mod": 0, "cr_mod": 0, "aov_mod": 0, "label": f"Month {m}"})
            learned[m] = dict(default)
            continue

        traffic_idx = month_rows["traffic"].mean() / overall_avg
        traffic_mod = round(traffic_idx - 1.0, 4)

        cr_mod = 0.0
        aov_mod = 0.0
        if "cr" in ga4_df.columns:
            cr_avg = df["cr"].mean()
            if cr_avg > 0:
                cr_idx = month_rows["cr"].mean() / cr_avg
                cr_mod = round(cr_idx - 1.0, 4)
        if "aov" in ga4_df.columns:
            aov_avg = df["aov"].mean()
            if aov_avg > 0:
                aov_idx = month_rows["aov"].mean() / aov_avg
                aov_mod = round(aov_idx - 1.0, 4)

        month_name = _MONTH_NAMES[m] if m <= 12 else f"Month {m}"
        learned[m] = {
            "label": f"{month_name} (learned)",
            "traffic_mod": traffic_mod,
            "cr_mod": cr_mod,
            "aov_mod": aov_mod,
        }

    return learned


def blend_learned_and_default_seasonality(
    learned: dict,
    default: dict,
    blend_weight: float,
) -> dict:
    """Blend learned seasonality indices with the AU retail defaults.

    Args:
        learned: Output of learn_seasonality_from_ga4.
        default: DEFAULT_SEASONALITY (or any same-schema dict).
        blend_weight: 0.0 = fully default; 1.0 = fully learned.

    Returns:
        Blended seasonality dict in the same schema.
    """
    blended: dict = {}
    pct_learned = int(round(blend_weight * 100))
    pct_default = 100 - pct_learned
    for m in range(1, 13):
        learned_m = learned.get(m, {})
        d = default.get(m, {"traffic_mod": 0, "cr_mod": 0, "aov_mod": 0, "label": f"Month {m}"})
        month_name = _MONTH_NAMES[m] if m <= 12 else f"Month {m}"
        if blend_weight >= 1.0:
            label = f"{month_name} (learned)"
        elif blend_weight <= 0.0:
            label = d.get("label", f"Month {m}")
        else:
            label = f"{month_name} ({pct_learned}% learned / {pct_default}% default)"
        blended[m] = {
            "label": label,
            "traffic_mod": round(
                blend_weight * learned_m.get("traffic_mod", 0) + (1 - blend_weight) * d.get("traffic_mod", 0), 4
            ),
            "cr_mod": round(
                blend_weight * learned_m.get("cr_mod", 0) + (1 - blend_weight) * d.get("cr_mod", 0), 4
            ),
            "aov_mod": round(
                blend_weight * learned_m.get("aov_mod", 0) + (1 - blend_weight) * d.get("aov_mod", 0), 4
            ),
        }
    return blended


def seasonality_for_portfolio(ga4_df: pd.DataFrame) -> tuple[dict, dict]:
    """Derive the best seasonality dict for a given GA4 dataset.

    Selection logic:
        ≥24 months → fully learned   (blend_weight=1.0)
        12–23 months → 50/50 blend   (blend_weight=0.5)
        <12 months → AU retail defaults with a warning in meta

    Returns:
        (seasonality_dict, meta) where meta = {
            "source": "learned" | "blended" | "default",
            "blend_weight": float,
            "months_available": int,
        }
    """
    n_months = len(ga4_df) if ga4_df is not None else 0
    meta: dict = {"months_available": n_months}

    if n_months >= 24:
        learned = learn_seasonality_from_ga4(ga4_df)
        if learned is not None:
            blended = blend_learned_and_default_seasonality(learned, DEFAULT_SEASONALITY, 1.0)
            meta.update({"source": "learned", "blend_weight": 1.0})
            return blended, meta

    if n_months >= 12:
        learned = learn_seasonality_from_ga4(ga4_df)
        if learned is not None:
            blended = blend_learned_and_default_seasonality(learned, DEFAULT_SEASONALITY, 0.5)
            meta.update({"source": "blended", "blend_weight": 0.5})
            return blended, meta

    meta.update({
        "source": "default",
        "blend_weight": 0.0,
        "warning": f"Only {n_months} months available — using AU retail defaults (need ≥12 to learn)",
    })
    return dict(DEFAULT_SEASONALITY), meta


INDUSTRY_SEASONALITY_PRIORS: dict[str, dict[int, float]] = {
    # Additive traffic_mod adjustments per month (on top of base seasonality).
    # These are authored defaults, not data-derived — treat as priors, not facts.
    "Accessories": {11: 0.05, 12: 0.08, 1: -0.03, 6: 0.03, 9: 0.04},
    "Apparel": {11: 0.06, 12: 0.06, 1: -0.05, 3: 0.03, 9: 0.04},
    "Beauty": {11: 0.04, 12: 0.05, 2: 0.03, 5: 0.03, 8: 0.02},
    "Home": {11: 0.03, 12: 0.07, 1: 0.02, 3: 0.04, 6: 0.02},
    "B2B SaaS": {1: 0.05, 2: 0.04, 9: 0.04, 10: 0.03, 11: -0.03, 12: -0.07},
    "Automotive": {3: 0.05, 4: 0.04, 9: 0.05, 10: 0.04, 12: -0.03},
    "Travel": {1: 0.06, 6: 0.08, 7: 0.10, 12: 0.05, 9: 0.05},
    "Food & Beverage": {11: 0.04, 12: 0.06, 4: 0.03, 5: 0.02, 8: 0.03},
    "Health": {1: 0.06, 2: 0.04, 9: 0.03, 5: 0.02, 11: 0.02},
    "Finance": {6: 0.08, 7: 0.04, 8: 0.06, 1: 0.03, 2: 0.02},
    "Other": {},
}


def apply_industry_bias(
    seasonality: dict,
    industry: str,
    bias_weight: float = 1.0,
) -> dict:
    """Apply industry-specific traffic_mod adjustments on top of base seasonality.

    Args:
        seasonality: Base seasonality dict (month_num → {traffic_mod, ...}).
        industry: Industry name from INDUSTRY_SEASONALITY_PRIORS keys.
        bias_weight: 0.0 = no bias, 1.0 = full bias. Blends the adjustment.

    Returns:
        New seasonality dict with industry adjustments blended in.
    """
    priors = INDUSTRY_SEASONALITY_PRIORS.get(industry, {})
    if not priors or bias_weight <= 0.0:
        return seasonality

    result = {}
    for month, entry in seasonality.items():
        adj = priors.get(month, 0.0) * bias_weight
        result[month] = dict(entry, traffic_mod=round(entry.get("traffic_mod", 0.0) + adj, 4))
    return result


def deseasonalise_series(
    dates: pd.Series,
    values: pd.Series,
    seasonality: dict,
) -> pd.Series:
    """Divide each value by (1 + traffic_mod) for its calendar month.

    Missing months treated as neutral (multiplier = 1.0).
    Use before fitting a trend so seasonal peaks don't bias the slope.
    """
    multipliers = [
        1.0 + seasonality.get(int(pd.Timestamp(d).month), {}).get("traffic_mod", 0.0)
        for d in dates
    ]
    return pd.Series(
        [v / m if m != 0 else v for v, m in zip(values, multipliers, strict=False)],
        index=values.index,
    )


def reseasonalise_values(
    dates: pd.Series,
    values: pd.Series,
    seasonality: dict,
) -> pd.Series:
    """Multiply each value by (1 + traffic_mod) for its calendar month.

    Inverse of deseasonalise_series. Missing months treated as neutral.
    """
    multipliers = [
        1.0 + seasonality.get(int(pd.Timestamp(d).month), {}).get("traffic_mod", 0.0)
        for d in dates
    ]
    return pd.Series(
        [v * m for v, m in zip(values, multipliers, strict=False)],
        index=values.index,
    )


def build_campaign_list(campaign_text: str) -> list[dict]:
    """Parse campaign definitions from user text input.

    Expected format (one per line):
        Campaign Name | month | traffic_boost | cr_boost | aov_boost

    Example:
        GAZFRENZY | 11 | 0.20 | 0.10 | -0.05
        Father's Day | 9 | 0.15 | 0.08 | 0.03

    Returns:
        List of campaign dicts.
    """
    campaigns = []
    for line in campaign_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2:
            try:
                campaign = {
                    "name": parts[0],
                    "month": int(parts[1]),
                    "traffic_boost": float(parts[2]) if len(parts) > 2 else 0.0,
                    "cr_boost": float(parts[3]) if len(parts) > 3 else 0.0,
                    "aov_boost": float(parts[4]) if len(parts) > 4 else 0.0,
                }
                campaigns.append(campaign)
            except (ValueError, IndexError):
                continue
    return campaigns


# ──────────────────────────────────────────────────────────────────────────────
# Section 2: Derive seasonality implicitly from YoY baseline
# ──────────────────────────────────────────────────────────────────────────────


def derive_seasonality_from_baseline(baseline_lookup: dict) -> dict:
    """Convert a YoY baseline lookup into per-calendar-month multiplier dict.

    When yoy_baseline mode is active the baseline values already encode seasonal
    shape — this function makes that shape explicit for downstream engines
    (positional, new-content) that need to apply matching multiplicative
    seasonality to their uplift streams.

    The multipliers are deviations from the annual mean: positive means above
    average (seasonal peak), negative means below average (seasonal trough).
    The 12 values sum approximately to zero.

    Args:
        baseline_lookup: Output of historical_engine.yoy_baseline() — dict keyed
            by pd.Timestamp, each value containing at minimum {"traffic": int}.

    Returns:
        Dict keyed by calendar month number (1-12), each value:
            {"traffic_mod": float, "cr_mod": float, "aov_mod": float, "label": str}
        matching the DEFAULT_SEASONALITY schema.
    """
    if not baseline_lookup:
        return dict(DEFAULT_SEASONALITY)

    items = sorted(baseline_lookup.items())
    traffic_vals = np.array([v["traffic"] for _, v in items])

    mean_traffic = traffic_vals.mean()
    if mean_traffic == 0:
        return dict(DEFAULT_SEASONALITY)

    result: dict = {}
    for (d, _v), t in zip(items, traffic_vals, strict=False):
        month = d.month
        traffic_mod = float(t / mean_traffic - 1.0)
        month_name = _MONTH_NAMES[month] if month <= 12 else f"Month {month}"
        result[month] = {
            "label": f"{month_name} (derived from YoY baseline)",
            "traffic_mod": round(traffic_mod, 4),
            "cr_mod": 0.0,
            "aov_mod": 0.0,
        }

    # Fill any missing months with DEFAULT_SEASONALITY
    for m in range(1, 13):
        if m not in result:
            result[m] = dict(DEFAULT_SEASONALITY.get(m, {"label": f"Month {m}", "traffic_mod": 0.0, "cr_mod": 0.0, "aov_mod": 0.0}))

    return result
