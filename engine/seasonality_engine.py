"""Seasonality engine for applying campaign/event modifiers to forecasts.

v4 additions:
- learn_seasonality_from_ga4: compute monthly indices from real GA4 data
- blend_learned_and_default_seasonality: weighted blend of learned vs. AU defaults
- AU_HOLIDAYS: pandas DataFrame for Australian retail holidays (2023-2028)
"""

import pandas as pd
import numpy as np


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


def _build_au_holidays() -> pd.DataFrame:
    """Generate AU retail holiday DataFrame for years 2023-2028 (Prophet format)."""
    rows = []

    def _add(name: str, ds: pd.Timestamp, lower: int, upper: int):
        rows.append({"holiday": name, "ds": ds, "lower_window": lower, "upper_window": upper})

    for year in range(2023, 2029):
        # EOFY
        _add("EOFY", pd.Timestamp(year, 6, 30), -14, 1)

        # Click Frenzy May — third Tuesday of May
        first_may = pd.Timestamp(year, 5, 1)
        # weekday() 1 = Tuesday
        days_to_tue = (1 - first_may.weekday()) % 7
        third_tuesday_may = first_may + pd.Timedelta(days=days_to_tue + 14)
        _add("Click Frenzy May", third_tuesday_may, -3, 3)

        # Click Frenzy November — second Tuesday of November
        first_nov = pd.Timestamp(year, 11, 1)
        days_to_tue = (1 - first_nov.weekday()) % 7
        second_tuesday_nov = first_nov + pd.Timedelta(days=days_to_tue + 7)
        _add("Click Frenzy November", second_tuesday_nov, -3, 3)

        # Black Friday — fourth Friday of November
        first_nov = pd.Timestamp(year, 11, 1)
        days_to_fri = (4 - first_nov.weekday()) % 7
        black_friday = first_nov + pd.Timedelta(days=days_to_fri + 21)
        _add("Black Friday", black_friday, -2, 3)

        # Cyber Monday — Monday after Black Friday
        cyber_monday = black_friday + pd.Timedelta(days=3)
        _add("Cyber Monday", cyber_monday, -1, 1)

        # Christmas
        _add("Christmas", pd.Timestamp(year, 12, 25), -10, 2)

        # Boxing Day Sales
        _add("Boxing Day Sales", pd.Timestamp(year, 12, 26), 0, 7)

        # Back to School (AU — late Jan)
        _add("Back to School", pd.Timestamp(year, 1, 28), -7, 7)

    return pd.DataFrame(rows)


AU_HOLIDAYS = _build_au_holidays()


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

        default_label = DEFAULT_SEASONALITY.get(m, {}).get("label", f"Month {m}")
        learned[m] = {
            "label": default_label,
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
    for m in range(1, 13):
        l = learned.get(m, {})
        d = default.get(m, {"traffic_mod": 0, "cr_mod": 0, "aov_mod": 0, "label": f"Month {m}"})
        blended[m] = {
            "label": d.get("label", f"Month {m}"),
            "traffic_mod": round(
                blend_weight * l.get("traffic_mod", 0) + (1 - blend_weight) * d.get("traffic_mod", 0), 4
            ),
            "cr_mod": round(
                blend_weight * l.get("cr_mod", 0) + (1 - blend_weight) * d.get("cr_mod", 0), 4
            ),
            "aov_mod": round(
                blend_weight * l.get("aov_mod", 0) + (1 - blend_weight) * d.get("aov_mod", 0), 4
            ),
        }
    return blended


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
