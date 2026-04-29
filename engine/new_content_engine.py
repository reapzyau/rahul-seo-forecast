import numpy as np
import pandas as pd

from engine.constants import (
    CTR_11_14,
    CTR_15_20,
    CTR_BY_POSITION,
    DIFFICULTY_TIERS,
    INTENT_PATTERNS,
    TIME_TO_RANK,
)
from engine.maturation_curve import maturation_schedule, tier_maturation_params


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
    seasonality: dict | None = None,
    forecast_start_month: int | None = None,
    aio_intent_penalties: dict | None = None,
    roadmap_content_plan: list[dict] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full new-content keyword forecast pipeline.

    Projects traffic from publishing new content targeting keywords you don't yet rank for.

    AIO CTR penalties are applied per-keyword at the CTR computation step (Step 5).
    Seasonality is applied to the monthly totals as the final step.

    Args:
        df: DataFrame with columns keyword, volume, kd.
        da: Domain authority (1-100).
        cadence: Keywords published per month.
        months: Forecast horizon in months.
        seed: Random seed for reproducibility.
        ctr_model: Optional CTR model dict (from CTR_MODELS).
        traffic_multiplier: Multiplier for traffic estimates (e.g. 0.7 conservative).
        include_informational: If False, drop informational-intent keywords.
        ai_overview_ctr_penalty: Percentage CTR reduction for informational keywords (legacy).
        seasonality: Dict {month_num: {traffic_mod: float}} applied to monthly totals.
        forecast_start_month: Calendar month (1-12) of horizon month 1.
        aio_intent_penalties: Dict {intent: penalty_pct} — supersedes ai_overview_ctr_penalty.
        roadmap_content_plan: List of content plan dicts from parse_pattern_native
            (keys: url, content_type, month, is_new_page). When provided, keywords are
            matched to plan URLs (substring: keyword in url.lower()). Matched keywords
            use the plan's publish month; unmatched fall back to cadence-based assignment.
            Optimisation URLs use t_mid=1.5 amplitude in S-curve; new pages use standard.

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

    # Step 3: Assign publish months — roadmap plan overrides cadence for matched keywords
    if roadmap_content_plan:
        plan_months: list[int] = []
        plan_is_optimisation: list[bool] = []
        has_url_hint = "_content_url" in df.columns
        for _, row in df.iterrows():
            kw_lower = str(row["keyword"]).lower()
            # Prefer direct URL match when _content_url metadata is present
            # (populated by build_keyword_df_from_roadmap). Fall back to the
            # legacy keyword-in-URL substring check for manually uploaded keywords.
            url_hint = str(row.get("_content_url", "")).lower() if has_url_hint else ""
            matched = next(
                (
                    item for item in roadmap_content_plan
                    if (url_hint and str(item.get("url", "")).lower() == url_hint)
                    or kw_lower in str(item.get("url", "")).lower()
                ),
                None,
            )
            if matched and isinstance(matched.get("month"), (int, float)):
                plan_months.append(int(matched["month"]))
                plan_is_optimisation.append(matched.get("content_type") == "optimisation")
            else:
                plan_months.append(df.index.get_loc(_) // cadence + 1)
                plan_is_optimisation.append(False)
        df["publish_month"] = plan_months
        df["_is_optimisation"] = plan_is_optimisation
    else:
        df["publish_month"] = df.index // cadence + 1
        df["_is_optimisation"] = False

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
    # Build effective per-intent penalty dict (new API supersedes legacy)
    _aio_penalties: dict = {}
    if aio_intent_penalties:
        _aio_penalties = {k.lower(): v for k, v in aio_intent_penalties.items()}
    elif ai_overview_ctr_penalty > 0:
        _aio_penalties = {"informational": ai_overview_ctr_penalty}

    for i, row in df.iterrows():
        if row["will_rank"]:
            pos = expected_position(da, row["kd"], seed + i + 2000)
            ctr = get_ctr(pos, ctr_model)
            # Apply AIO CTR penalty based on intent
            penalty_pct = _aio_penalties.get(str(row["intent"]).lower(), 0.0)
            if penalty_pct > 0:
                ctr = ctr * (1 - penalty_pct / 100)
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
    # traffic_midpoint_month = publish_month + t_mid of the S-curve (kept for compat)
    df["traffic_midpoint_month"] = [
        row["publish_month"] + tier_maturation_params(row["tier"])[0]
        if row["will_rank"] and row["time_to_rank"] is not None else None
        for _, row in df.iterrows()
    ]
    # Backward-compat alias
    df["traffic_starts_month"] = [
        row["publish_month"] + (row["time_to_rank"] or 0)
        if row["will_rank"] else None
        for _, row in df.iterrows()
    ]

    # Step 7: S-curve phased maturation projection
    monthly_totals = np.zeros(months)
    for _, row in df.iterrows():
        if not row["will_rank"] or row["estimated_monthly_traffic"] == 0:
            continue
        if row.get("_is_optimisation", False):
            # Optimisation of existing copy: faster ramp (t_mid=1.5), lower amplitude (0.3)
            from engine.maturation_curve import logistic_progress
            pub = int(row["publish_month"])
            sched = np.array([
                0.3 * logistic_progress(max(0, m + 1 - pub), 1.5, 1.8) if m + 1 >= pub else 0.0
                for m in range(months)
            ])
            monthly_totals += row["estimated_monthly_traffic"] * sched
        else:
            schedule = maturation_schedule(row["tier"], months, int(row["publish_month"]))
            monthly_totals += row["estimated_monthly_traffic"] * schedule

    # Apply seasonality to monthly totals
    if seasonality and forecast_start_month is not None:
        season_mults = np.array([
            1.0 + seasonality.get(((forecast_start_month - 1 + m) % 12) + 1, {}).get("traffic_mod", 0.0)
            for m in range(months)
        ])
        monthly_totals = monthly_totals * season_mults

    monthly_df = pd.DataFrame({
        "month": range(1, months + 1),
        "traffic": monthly_totals.round(0).astype(int),
    })

    # Add rank column (1-indexed ordering)
    df.insert(0, "rank", range(1, len(df) + 1))

    # Store metadata for UI display
    df.attrs["n_excluded_informational"] = n_excluded

    return df, monthly_df


# ──────────────────────────────────────────────────────────────────────────────
# Section 5: Deterministic per-post new-content stream
# ──────────────────────────────────────────────────────────────────────────────


def run_new_content_forecast_simple(
    n_posts_total: int,
    months: int = 12,
    posts_per_month: int = 2,
    per_post_longtail_traffic: int = 400,
    rank_probability: float = 0.55,
    maturation_tier: str = "Moderate",
    seasonality: dict | None = None,
    forecast_start_month: int | None = None,
    seed: int = 42,
) -> np.ndarray:
    """Forecast new-content traffic without keyword-level inputs.

    Suitable when the SOW describes a content cadence but no keyword gap analysis
    has been done.  Each published post is assumed to capture per_post_longtail_traffic
    mature monthly sessions with rank_probability probability of doing so meaningfully
    within the forecast horizon. Traffic accumulates via S-curve maturation.

    This function does NOT accept the client's SEMrush keyword export — that data
    describes keywords the client already ranks for, not new-content opportunities.

    Args:
        n_posts_total: Maximum posts published over the forecast horizon.
        months: Forecast horizon in months.
        posts_per_month: Posts published each month (cadence).
        per_post_longtail_traffic: Estimated mature monthly organic sessions per post
            that successfully ranks. Typical long-tail blog post: 200–800.
        rank_probability: Probability each post ranks meaningfully (0.1–0.95).
        maturation_tier: S-curve tier — "Easy", "Moderate", "Hard", etc.
        seasonality: Dict {month_num: {traffic_mod: float}} applied to monthly totals.
        forecast_start_month: Calendar month (1-12) of horizon month 1 (for seasonality).
        seed: Random seed for reproducibility.

    Returns:
        1-D numpy int array of length `months` — monthly traffic from new content.
    """
    from engine.maturation_curve import maturation_schedule

    rng = np.random.default_rng(seed)
    monthly = np.zeros(months, dtype=float)
    posts_done = 0

    for m in range(months):
        n_to_pub = min(posts_per_month, max(0, n_posts_total - posts_done))
        for _ in range(n_to_pub):
            if rng.random() < rank_probability:
                # Publish month is m+1 (1-indexed); maturation_schedule returns a
                # fraction-of-mature-traffic array of length `months`.
                schedule = maturation_schedule(maturation_tier, months, m + 1)
                monthly += per_post_longtail_traffic * schedule
        posts_done += n_to_pub

    if seasonality and forecast_start_month is not None:
        season_mults = np.array([
            1.0 + seasonality.get(
                ((forecast_start_month - 1 + m) % 12) + 1, {}
            ).get("traffic_mod", 0.0)
            for m in range(months)
        ])
        monthly *= season_mults

    return monthly.round(0).astype(int)


