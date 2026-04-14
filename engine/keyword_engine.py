import numpy as np
import pandas as pd

from engine.constants import (
    CTR_BY_POSITION, CTR_11_14, CTR_15_20,
    DIFFICULTY_TIERS, TIME_TO_RANK,
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
    rng = np.random.RandomState(seed)
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

    return int(rng.randint(low, high + 1))


def get_ctr(position: int) -> float:
    """Return CTR percentage for a given SERP position."""
    if position in CTR_BY_POSITION:
        return CTR_BY_POSITION[position]
    if position <= 14:
        return CTR_11_14
    if position <= 20:
        return CTR_15_20
    return 0.0


def time_to_rank_months(tier: str, da: int, seed: int) -> int:
    """Calculate months to rank, adjusted by DA, with seeded randomness."""
    rng = np.random.RandomState(seed)
    low, high = TIME_TO_RANK[tier]
    base = int(rng.randint(low, high + 1))
    # DA adjustment: higher DA speeds things up slightly
    adjustment = (da - 50) / 100  # ranges roughly -0.5 to +0.5
    adjusted = max(1, round(base - adjustment * 2))
    return adjusted


def efficiency_score(volume: int, kd: int) -> float:
    """Calculate efficiency score: volume / (kd + 1)."""
    return volume / (kd + 1)


def run_keyword_forecast(
    df: pd.DataFrame,
    da: int,
    cadence: int,
    months: int,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full keyword forecast pipeline.

    Returns:
        keyword_df: Per-keyword results with all computed fields.
        monthly_df: Month-by-month traffic projection.
    """
    # Step 1: Calculate efficiency score and sort
    df = df.copy()
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
        rng = np.random.RandomState(kw_seed + 1000)
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
            ctr = get_ctr(pos)
            traffic = round(row["volume"] * ctr / 100)
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

    return df, monthly_df
