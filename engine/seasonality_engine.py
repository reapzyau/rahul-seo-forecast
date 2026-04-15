"""Seasonality engine for applying campaign/event modifiers to forecasts."""

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
