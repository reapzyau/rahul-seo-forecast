import numpy as np
import pandas as pd

from engine.constants import (
    CTR_BY_POSITION, CTR_11_14, CTR_15_20,
    DIFFICULTY_TIERS, CTR_MODELS,
)
from engine.new_content_engine import get_ctr, classify_difficulty

# Offset for seeded RNG — avoids collisions with keyword engine seeds (1000-3000)
_TTM_SEED_OFFSET = 4000

_BASE_GAIN_BY_TIER = {
    "Easy": 5,
    "Moderate": 4,
    "Hard": 3,
    "Very Hard": 2,
    "Extreme": 1,
}

_EFFORT_FACTORS = {
    "light": 0.5,
    "moderate": 1.0,
    "aggressive": 1.5,
}

# Months-to-move ranges per tier (distinct from TIME_TO_RANK which is for new content)
_TIME_TO_MOVE = {
    "Easy": (2, 3),
    "Moderate": (3, 5),
    "Hard": (5, 8),
    "Very Hard": (7, 10),
    "Extreme": (10, 14),
}


def estimate_target_position(current_pos: int, kd: int, effort: str) -> int:
    """Estimate where a keyword could realistically move given KD and effort level."""
    tier = classify_difficulty(kd)
    base_gain = _BASE_GAIN_BY_TIER[tier]
    effort_factor = _EFFORT_FACTORS[effort]
    gain = round(base_gain * effort_factor)
    return max(1, current_pos - gain)


def run_positional_forecast(
    df: pd.DataFrame,
    months: int = 12,
    effort: str = "moderate",
    ga4_baseline: float | None = None,
    ctr_model: dict | None = None,
    traffic_multiplier: float = 1.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecast traffic uplift from improving positions of already-ranking keywords.

    Args:
        df: DataFrame with columns: keyword, position, volume, kd,
            current_traffic, primary_intent, has_aio.
        months: Forecast horizon in months.
        effort: One of "light", "moderate", "aggressive".
        ga4_baseline: Optional GA4 total traffic to anchor SEMRush estimates against.
        ctr_model: Optional CTR model dict (from CTR_MODELS).
        traffic_multiplier: Scenario multiplier for target traffic.
        seed: Random seed for reproducibility.

    Returns:
        keyword_df: Per-keyword results sorted by uplift descending.
        monthly_df: Month-by-month traffic projection with baseline, uplift, traffic.
    """
    df = df.copy()

    rows = []
    for i, row in df.iterrows():
        pos = row["position"]
        if not (1 <= pos <= 100):
            continue

        kd = row["kd"]
        volume = row["volume"]
        tier = classify_difficulty(kd)

        target_pos = estimate_target_position(pos, kd, effort)
        current_ctr = get_ctr(pos, ctr_model)
        target_ctr = get_ctr(target_pos, ctr_model)

        baseline_traffic = volume * current_ctr / 100
        target_traffic = volume * target_ctr / 100 * traffic_multiplier
        uplift = max(0.0, target_traffic - baseline_traffic)

        rng = np.random.default_rng(seed + i + _TTM_SEED_OFFSET)
        low, high = _TIME_TO_MOVE[tier]
        time_to_move = int(rng.integers(low, high + 1))

        rows.append({
            "keyword": row["keyword"],
            "position": pos,
            "target_position": target_pos,
            "volume": volume,
            "kd": kd,
            "tier": tier,
            "current_ctr": current_ctr,
            "target_ctr": target_ctr,
            "baseline_traffic": baseline_traffic,
            "target_traffic": target_traffic,
            "uplift": uplift,
            "time_to_move": time_to_move,
            "current_traffic": row.get("current_traffic", 0),
            "primary_intent": row.get("primary_intent", ""),
            "has_aio": row.get("has_aio", False),
        })

    keyword_df = pd.DataFrame(rows)

    if keyword_df.empty:
        monthly_df = pd.DataFrame({"month": [], "baseline": [], "uplift": [], "traffic": []})
        return keyword_df, monthly_df

    # Sort by uplift descending — highest-impact keywords first
    keyword_df = keyword_df.sort_values("uplift", ascending=False).reset_index(drop=True)

    # GA4 anchoring: rescale SEMRush-estimated traffic to match real analytics
    if ga4_baseline is not None:
        total_semrush_baseline = keyword_df["baseline_traffic"].sum()
        if total_semrush_baseline > 0:
            anchor_ratio = ga4_baseline / total_semrush_baseline
            keyword_df["baseline_traffic"] *= anchor_ratio
            keyword_df["target_traffic"] *= anchor_ratio
            keyword_df["uplift"] *= anchor_ratio

    # Build monthly projection
    total_baseline = keyword_df["baseline_traffic"].sum()
    monthly_rows = []
    for m in range(1, months + 1):
        month_uplift = 0.0
        for _, kw in keyword_df.iterrows():
            t = kw["time_to_move"]
            if t <= 0:
                continue
            # Linear ramp: keywords already rank (publish_start=1), so ramp from month 1
            progress = (m - 1) / t
            contribution = kw["uplift"] * min(1.0, max(0.0, progress))
            month_uplift += contribution

        monthly_rows.append({
            "month": m,
            "baseline": total_baseline,
            "uplift": month_uplift,
            "traffic": total_baseline + month_uplift,
        })

    monthly_df = pd.DataFrame(monthly_rows)

    return keyword_df, monthly_df


def quick_wins(keyword_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Extract keywords in positions 4-20 sorted by uplift — the lowest-effort, highest-impact moves."""
    mask = (keyword_df["position"] >= 4) & (keyword_df["position"] <= 20)
    return (
        keyword_df[mask]
        .sort_values("uplift", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
