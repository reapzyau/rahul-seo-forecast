import numpy as np
import pandas as pd

from engine.constants import (
    CTR_BY_POSITION, CTR_11_14, CTR_15_20,
    DIFFICULTY_TIERS, TIME_TO_RANK, INTENT_PATTERNS,
)


def classify_difficulty(kd: int) -> str:
    """Classify keyword difficulty into a tier label."""
    for threshold, label in DIFFICULTY_TIERS:
        if kd <= threshold:
            return label
    return "Extreme"


def ranking_probability(da: int, kd: int) -> float:
    """Calculate the probability of ranking, clamped 0.05-0.95."""
    raw = (da - kd + 50) / 100
    return float(np.clip(raw, 0.05, 0.95))


def expected_position(da: int, kd: int, seed: int) -> int:
    """Determine expected ranking position using seeded randomness.

    Higher DA relative to KD yields positions closer to 1.
    The gap between DA and KD defines the range of possible positions.
    """
    rng = np.random.default_rng(seed)
    gap = da - kd

    if gap >= 30:
        low, high = 1, 3
    elif gap >= 15:
        low, high = 2, 5
    elif gap >= 0:
        low, high = 3, 8
    elif gap >= -15:
        low, high = 5, 12
    elif gap >= -30:
        low, high = 8, 16
    else:
        low, high = 12, 20

    return int(rng.integers(low, high + 1))


def classify_intent(keyword: str) -> str:
    """Classify keyword search intent based on pattern matching.

    Returns one of: informational, transactional, commercial, navigational.
    Defaults to commercial if no patterns match.
    """
    kw = keyword.lower().strip()

    # Check transactional first (highest commercial value)
    patterns = INTENT_PATTERNS["transactional"]
    for term in patterns["contains"]:
        if term in kw:
            return "transactional"

    # Check navigational
    patterns = INTENT_PATTERNS["navigational"]
    for term in patterns["contains"]:
        if term in kw:
            return "navigational"

    # Check informational (question words + info patterns)
    patterns = INTENT_PATTERNS["informational"]
    for prefix in patterns["starts_with"]:
        if kw.startswith(prefix):
            return "informational"
    for term in patterns["contains"]:
        if term in kw:
            return "informational"

    # Check commercial
    patterns = INTENT_PATTERNS["commercial"]
    for term in patterns["contains"]:
        if term in kw:
            return "commercial"

    # Default to commercial (safe assumption for SEO keyword lists)
    return "commercial"


def get_ctr(position: int, ctr_model: dict | None = None) -> float:
    """Return CTR percentage for a given SERP position.

    Args:
        position: SERP position (1-20+).
        ctr_model: Optional dict with keys 'ctr_by_position', 'ctr_11_14', 'ctr_15_20'.
                   Defaults to the standard CTR model.
    """
    if ctr_model is not None:
        ctr_table = ctr_model["ctr_by_position"]
        ctr_11_14 = ctr_model["ctr_11_14"]
        ctr_15_20 = ctr_model["ctr_15_20"]
    else:
        ctr_table = CTR_BY_POSITION
        ctr_11_14 = CTR_11_14
        ctr_15_20 = CTR_15_20

    if position in ctr_table:
        return ctr_table[position]
    if position <= 14:
        return ctr_11_14
    if position <= 20:
        return ctr_15_20
    return 0.0


def time_to_rank_months(tier: str, da: int, seed: int) -> int:
    """Calculate months to rank, adjusted by DA, with seeded randomness."""
    rng = np.random.default_rng(seed)
    low, high = TIME_TO_RANK[tier]
    base = int(rng.integers(low, high + 1))
    # DA adjustment: higher DA speeds things up slightly
    adjustment = (da - 50) / 100  # ranges roughly -0.5 to +0.5
    adjusted = max(1, round(base - adjustment * 2))
    return adjusted


def efficiency_score(volume: int, kd: int) -> float:
    """Calculate efficiency score: volume / (kd + 1)."""
    return volume / (kd + 1)


def run_new_content_forecast(
    df: pd.DataFrame,
    da: int,
    cadence: int,
    months: int,
    seed: int = 42,
    ctr_model: dict | None = None,
    traffic_multiplier: float = 1.0,
    include_informational: bool = True,
    ai_overview_ctr_penalty: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full new-content keyword forecast pipeline.

    Projects traffic from publishing new content targeting keywords you don't yet rank for.

    Args:
        df: DataFrame with columns keyword, volume, kd.
        da: Domain authority (1-100).
        cadence: Keywords published per month.
        months: Forecast horizon in months.
        seed: Random seed for reproducibility.
        ctr_model: Optional CTR model dict (from CTR_MODELS).
        traffic_multiplier: Multiplier for traffic estimates (e.g. 0.7 conservative).
        include_informational: If False, drop informational-intent keywords.
        ai_overview_ctr_penalty: Percentage CTR reduction for informational keywords (0-100).

    Returns:
        keyword_df: Per-keyword results with all computed fields.
        monthly_df: Month-by-month traffic projection.
    """
    # Step 0: Classify intent (always computed for visibility)
    df = df.copy()
    df["intent"] = df["keyword"].apply(classify_intent)

    # Step 0b: Optionally exclude informational keywords
    n_excluded = 0
    if not include_informational:
        n_excluded = (df["intent"] == "informational").sum()
        df = df[df["intent"] != "informational"].reset_index(drop=True)

    # Step 1: Calculate efficiency score and sort
    df["efficiency_score"] = df.apply(
        lambda r: efficiency_score(r["volume"], r["kd"]), axis=1
    )
    df = df.sort_values("efficiency_score", ascending=False).reset_index(drop=True)

    # Step 2: Classify difficulty
    df["tier"] = df["kd"].apply(classify_difficulty)

    # Step 3: Assign publish months based on cadence
    df["publish_month"] = df.index // cadence + 1

    # Step 4: Roll ranking probability dice (seeded per keyword)
    probabilities = []
    ranks = []
    for i, row in df.iterrows():
        kw_seed = seed + i
        prob = ranking_probability(da, row["kd"])
        probabilities.append(prob)
        rng = np.random.default_rng(kw_seed + 1000)
        roll = rng.random()
        ranks.append(roll <= prob)

    df["rank_probability"] = probabilities
    df["will_rank"] = ranks

    # Step 5: Assign positions for keywords that pass
    positions = []
    ctrs = []
    estimated_traffic = []
    for i, row in df.iterrows():
        if row["will_rank"]:
            pos = expected_position(da, row["kd"], seed + i + 2000)
            ctr = get_ctr(pos, ctr_model)
            # Apply AI Overview CTR penalty to informational keywords
            if ai_overview_ctr_penalty > 0 and row["intent"] == "informational":
                ctr = ctr * (1 - ai_overview_ctr_penalty / 100)
            traffic = round(row["volume"] * ctr / 100 * traffic_multiplier)
        else:
            pos = None
            ctr = 0.0
            traffic = 0
        positions.append(pos)
        ctrs.append(ctr)
        estimated_traffic.append(traffic)

    df["expected_position"] = positions
    df["ctr"] = ctrs
    df["estimated_monthly_traffic"] = estimated_traffic

    # Step 6: Calculate time to rank
    ttr_values = []
    traffic_starts = []
    for i, row in df.iterrows():
        if row["will_rank"]:
            ttr = time_to_rank_months(row["tier"], da, seed + i + 3000)
            ttr_values.append(ttr)
            traffic_starts.append(row["publish_month"] + ttr)
        else:
            ttr_values.append(None)
            traffic_starts.append(None)

    df["time_to_rank"] = ttr_values
    df["traffic_starts_month"] = traffic_starts

    # Step 7: Build month-by-month projection
    monthly_traffic = []
    for m in range(1, months + 1):
        total = 0
        for _, row in df.iterrows():
            if row["will_rank"] and row["traffic_starts_month"] is not None:
                if m >= row["traffic_starts_month"]:
                    total += row["estimated_monthly_traffic"]
        monthly_traffic.append({"month": m, "traffic": total})

    monthly_df = pd.DataFrame(monthly_traffic)

    # Add rank column (1-indexed ordering)
    df.insert(0, "rank", range(1, len(df) + 1))

    # Store metadata for UI display
    df.attrs["n_excluded_informational"] = n_excluded

    return df, monthly_df
