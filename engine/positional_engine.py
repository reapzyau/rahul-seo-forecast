import numpy as np
import pandas as pd

from engine.maturation_curve import TIER_MATURATION_PARAMS
from engine.new_content_engine import classify_difficulty, get_ctr

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


def learn_movement_from_history(kw_df: "pd.DataFrame") -> dict:
    """Learn per-tier position gain stats from SEMrush previous_position data.

    Args:
        kw_df: DataFrame with 'previous_position', 'position', and 'kd' columns.

    Returns:
        Dict of {tier: {"mean_gain": float, "std_gain": float, "sample_size": int}}.
        Only tiers with ≥10 samples are included.
    """
    if "previous_position" not in kw_df.columns or "position" not in kw_df.columns:
        return {}

    df = kw_df.dropna(subset=["previous_position", "position"]).copy()
    df["movement"] = df["previous_position"].astype(float) - df["position"].astype(float)
    # Filter outliers (>30 positions likely SEMrush glitches)
    df = df[df["movement"].abs() <= 30]

    stats: dict = {}
    for tier in ["Easy", "Moderate", "Hard", "Very Hard", "Extreme"]:
        tier_mask = df["kd"].apply(classify_difficulty) == tier
        gains = df.loc[tier_mask, "movement"]
        if len(gains) >= 10:
            stats[tier] = {
                "mean_gain": float(gains.mean()),
                "std_gain": float(gains.std()),
                "sample_size": int(len(gains)),
            }
    return stats


def learn_movement_from_history_v2(kw_df: "pd.DataFrame") -> dict:
    """Learn per-tier position gain stats using percentile-based metrics (Refinement B).

    Extends learn_movement_from_history() with p75_gain and p90_gain columns,
    which are more robust than mean for skewed gain distributions (where a few
    big movers inflate the average while the median barely shifts).

    Args:
        kw_df: DataFrame with 'previous_position', 'position', and 'kd' columns.

    Returns:
        Dict of {tier: {"mean_gain", "p75_gain", "p90_gain", "std_gain", "sample_size"}}.
        Only tiers with ≥10 samples are included.
    """
    if "previous_position" not in kw_df.columns or "position" not in kw_df.columns:
        return {}

    df = kw_df.dropna(subset=["previous_position", "position"]).copy()
    df["movement"] = df["previous_position"].astype(float) - df["position"].astype(float)
    df = df[df["movement"].abs() <= 30]

    stats: dict = {}
    for tier in ["Easy", "Moderate", "Hard", "Very Hard", "Extreme"]:
        tier_mask = df["kd"].apply(classify_difficulty) == tier
        gains = df.loc[tier_mask, "movement"]
        if len(gains) >= 10:
            stats[tier] = {
                "mean_gain": float(gains.mean()),
                "p75_gain": float(np.percentile(gains, 75)),
                "p90_gain": float(np.percentile(gains, 90)),
                "std_gain": float(gains.std()),
                "sample_size": int(len(gains)),
            }
    return stats


def estimate_target_position(
    current_pos: int,
    kd: int,
    effort: str,
    historical_movement_stats: dict | None = None,
    min_learned_gain: float = 2.0,
) -> int:
    """Estimate where a keyword could realistically move given KD and effort level.

    When historical_movement_stats has ≥10 samples for a tier, learned gain is used
    instead of the default tier table — unless learned gain is below `min_learned_gain`.

    Low or negative learned gain (e.g. stable or declining site history) is treated
    as a signal of low *past effort*, not a ceiling on what effort can achieve. When
    learned_gain < min_learned_gain the function blends toward the tier default:
      - Fewer samples (lower confidence) → more weight on default
      - Higher samples → blended with a 40%-of-default floor so the forecast
        always shows some potential even when history is reliably flat

    Negative mean gain (keywords lost positions on average) is clamped to 0
    before blending to prevent projecting backwards movement.
    """
    tier = classify_difficulty(kd)
    effort_factor = _EFFORT_FACTORS[effort]
    default_gain = _BASE_GAIN_BY_TIER[tier]

    if (
        historical_movement_stats
        and tier in historical_movement_stats
        and historical_movement_stats[tier]["sample_size"] >= 10
    ):
        learned_gain = historical_movement_stats[tier]["mean_gain"]
        if learned_gain < min_learned_gain:
            # Blend toward defaults. Clamp to 0 to avoid backwards projection.
            n = historical_movement_stats[tier]["sample_size"]
            confidence = min(1.0, n / 50.0)
            clamped = max(0.0, learned_gain)
            blended = clamped * confidence + default_gain * (1.0 - confidence)
            # Floor at 40% of the tier default so high-confidence-zero history
            # still shows achievable upside (effort can shift even stagnant sites).
            base_gain = max(blended, default_gain * 0.4)
        else:
            base_gain = learned_gain
    else:
        base_gain = default_gain

    gain = round(base_gain * effort_factor)
    return max(1, current_pos - gain)


def run_positional_forecast(
    df: pd.DataFrame,
    months: int = 12,
    effort: str = "moderate",
    ga4_baseline: float | None = None,
    ctr_model: dict | None = None,
    traffic_multiplier: float = 1.0,
    historical_movement_stats: dict | None = None,
    position_range: tuple[int, int] | None = None,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backward-compatible wrapper around run_positional_forecast_mc.

    Returns monthly_df with 'uplift' and 'traffic' columns (P50 values)
    for callers that don't need full bands.
    """
    return run_positional_forecast_mc(
        df,
        months=months,
        effort=effort,
        n_trials=500,
        ctr_model=ctr_model,
        traffic_multiplier=traffic_multiplier,
        ga4_baseline=ga4_baseline,
        use_attention_curve=True,
        position_range=position_range,
        historical_movement_stats=historical_movement_stats,
        seed=seed,
    )


def quick_wins(keyword_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Extract keywords in positions 4-20 sorted by uplift — the lowest-effort, highest-impact moves."""
    mask = (keyword_df["position"] >= 4) & (keyword_df["position"] <= 20)
    return (
        keyword_df[mask]
        .sort_values("uplift", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


# ──────────────────────────────────────────────────────────────────────
# Portfolio attention curve — models the reality that SEO teams can't
# meaningfully work on all keywords at once.
# ──────────────────────────────────────────────────────────────────────

ATTENTION_TIERS = [
    {"share": 0.05, "weight": 1.00, "label": "focus"},
    {"share": 0.15, "weight": 0.60, "label": "secondary"},
    {"share": 0.30, "weight": 0.25, "label": "long_tail"},
    {"share": 1.00, "weight": 0.05, "label": "background"},
]


def attention_weight(rank_pct: float) -> float:
    """Given a keyword's rank percentile (0 = top, 1 = bottom), return the
    effective-effort weight."""
    cumulative = 0.0
    for tier in ATTENTION_TIERS:
        cumulative += tier["share"]
        if rank_pct <= cumulative:
            return tier["weight"]
    return ATTENTION_TIERS[-1]["weight"]


def apply_attention_curve(
    keyword_df: pd.DataFrame,
    opportunity_col: str = "opportunity_score",
) -> pd.DataFrame:
    """Rank keywords by opportunity and assign attention weights."""
    df = keyword_df.copy()
    if opportunity_col not in df.columns:
        df[opportunity_col] = df["volume"] / (df["kd"] + 1)
    df = df.sort_values(opportunity_col, ascending=False).reset_index(drop=True)
    df["rank_pct"] = (df.index + 1) / len(df)
    df["attention_weight"] = df["rank_pct"].apply(attention_weight)
    return df


# ──────────────────────────────────────────────────────────────────────
# Monte Carlo forecasting — P10/P50/P90 bands
# ──────────────────────────────────────────────────────────────────────

_EFFORT_SCORES = {"light": -0.5, "moderate": 0.0, "aggressive": 0.5}


def _improvement_probability(effort_score: float, kd: int) -> float:
    """Logistic function on (effort - normalised KD)."""
    kd_normalised = kd / 100.0 * 2.0 - 1.0
    x = effort_score - kd_normalised
    return 1.0 / (1.0 + np.exp(-x * 2.0))


def _resolve_movement_stats(
    learned: dict | None,
    mode: bool | str,
) -> tuple[dict | None, str]:
    """Decide whether to use learned movement stats based on mode.

    Args:
        learned: Output of learn_movement_from_history() — dict by tier.
        mode: True | False | "auto"
            True  — always use learned stats.
            False — always use engine tier-defaults.
            "auto" — use learned only when mean_gain is positive across all tiers;
                     fall back to engine defaults otherwise (e.g. when the portfolio
                     has been declining — the forecast is conditional on a retainer
                     reversing that decline, so defaulting to engine gains is correct).

    Returns:
        (stats_to_use, decision_reason): tuple of dict-or-None and str.
    """
    if mode is False:
        return None, "explicit override → using engine tier-defaults"
    if mode is True:
        return learned, "explicit use of learned movement stats"
    # "auto" mode
    if not learned:
        return None, "no learned stats available → engine defaults"
    # Prefer p75_gain when available (Refinement B: percentile-based decision)
    # p75 is a more robust signal for skewed distributions than mean
    if all("p75_gain" in v for v in learned.values()):
        p75_gains = [v["p75_gain"] for v in learned.values()]
        if all(g > 0 for g in p75_gains):
            return learned, (
                f"learned stats positive at P75 across all tiers "
                f"(range: {min(p75_gains):.2f}–{max(p75_gains):.2f}) → using learned"
            )
        return None, (
            f"learned P75 gains show decline "
            f"(range: {min(p75_gains):.2f}–{max(p75_gains):.2f}) → "
            f"using engine defaults assuming retainer reverses decline"
        )
    # Legacy fallback: mean_gain decision
    mean_gains = [v["mean_gain"] for v in learned.values()]
    if all(g > 0 for g in mean_gains):
        return learned, (
            f"learned stats positive across all tiers "
            f"(range: {min(mean_gains):.2f}–{max(mean_gains):.2f}) → using learned"
        )
    return None, (
        f"learned stats show decline (mean_gain range: "
        f"{min(mean_gains):.2f} to {max(mean_gains):.2f}) → "
        f"using engine defaults assuming retainer reverses decline"
    )


def run_positional_forecast_mc(
    df: pd.DataFrame,
    months: int = 12,
    effort: str = "moderate",
    n_trials: int = 500,
    ctr_model: dict | None = None,
    traffic_multiplier: float = 1.0,
    ga4_baseline: int | None = None,
    use_attention_curve: bool = True,
    position_range: tuple[int, int] | None = None,
    historical_movement_stats: dict | None = None,
    use_learned_movement_stats: bool | str = "auto",
    seasonality: dict | None = None,
    forecast_start_month: int | None = None,
    aio_intent_penalties: dict | None = None,
    seed: int = 42,
    position_filter: tuple[int, int] | None = (4, 30),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monte Carlo positional forecast with P10/P50/P90 bands.

    Seasonality is applied per-month to the uplift trials array before percentile
    computation, so bands reflect seasonal variation.
    AIO CTR penalties are applied per-keyword at the target-CTR step based on intent.

    Args:
        use_learned_movement_stats: True | False | "auto" (default "auto").
            In "auto" mode, learned stats are only used when all tiers show
            positive mean_gain; otherwise engine tier-defaults are used. This
            prevents declining portfolios from producing zero-uplift forecasts
            when a paid retainer is meant to reverse the decline.
        position_filter: (lo, hi) tuple — only keywords in this position range are
            included in the positional pool. Default (4, 30) excludes P1-3 (small
            uplift ceiling) and P31-100 (near-zero CTR improvement). Pass None to
            include the full ranking portfolio (backward-compatible).
        position_range: Override for position_filter (main-branch compat).
            When set, takes precedence over position_filter. Prefer position_filter
            for new callers; use position_range=None to keep the (4, 30) default.
        seasonality: Dict {month_num: {traffic_mod: float}} — applied to uplift.
        forecast_start_month: Calendar month (1-12) of horizon month 1 (for seasonality).
        aio_intent_penalties: Dict {intent: penalty_pct} e.g. {"informational": 45.0}.

    Returns:
        keyword_df: Per-keyword with uplift_p10/p50/p90.
        monthly_df: Monthly bands — baseline, uplift_p10/p50/p90, traffic_p10/p50/p90.
            monthly_df.attrs["movement_stats_reason"] records the auto-decision reason.
    """
    df = df.copy()
    df = df[df["position"].between(1, 100)].reset_index(drop=True)

    # Section 3: positional pool filter.
    # position_range (main-branch param) overrides when explicitly set;
    # otherwise position_filter default (4, 30) applies.
    _active_filter = position_range if position_range is not None else position_filter
    if _active_filter is not None:
        lo, hi = _active_filter
        df = df[df["position"].between(lo, hi)].reset_index(drop=True)

    df["kd"] = df["kd"].fillna(0)
    df["volume"] = df["volume"].fillna(0)

    # Section 4: resolve movement stats (after fill so df.empty is accurate)
    stats_to_use, movement_reason = _resolve_movement_stats(
        historical_movement_stats, use_learned_movement_stats
    )

    if df.empty:
        empty_monthly = pd.DataFrame({
            "month": range(1, months + 1),
            "baseline": [0] * months,
            "uplift_p10": [0] * months,
            "uplift_p50": [0] * months,
            "uplift_p90": [0] * months,
            "traffic_p10": [0] * months,
            "traffic_p50": [0] * months,
            "traffic_p90": [0] * months,
        })
        empty_monthly.attrs["movement_stats_reason"] = movement_reason
        empty_monthly.attrs["position_filter"] = _active_filter
        empty_monthly.attrs["keyword_count"] = 0
        return pd.DataFrame(), empty_monthly

    rng = np.random.default_rng(seed)
    n_kw = len(df)
    effort_score = _EFFORT_SCORES[effort]

    # Pre-compute per-keyword deterministic targets and properties
    positions = df["position"].values.astype(int)
    volumes = df["volume"].values.astype(float)
    kds = df["kd"].values.astype(int)
    tiers = np.array([classify_difficulty(int(k)) for k in kds])

    det_targets = np.array([
        estimate_target_position(int(p), int(k), effort, stats_to_use)
        for p, k in zip(positions, kds, strict=False)
    ])

    # CTR lookup table for positions 1-100
    ctr_table = np.array([get_ctr(p, ctr_model) for p in range(1, 101)])
    current_ctrs = ctr_table[positions - 1]
    baseline_per_kw = volumes * current_ctrs / 100.0

    # Time-to-move ranges per keyword
    ttm_lows = np.array([_TIME_TO_MOVE[t][0] for t in tiers], dtype=float)
    ttm_highs = np.array([_TIME_TO_MOVE[t][1] for t in tiers], dtype=float)

    # Improvement probabilities
    improve_probs = np.array([
        _improvement_probability(effort_score, int(k)) for k in kds
    ])

    # Attention curve
    if use_attention_curve:
        opp_scores = volumes / (kds + 1)
        sorted_idx = np.argsort(-opp_scores)
        rank_pcts = np.empty(n_kw)
        rank_pcts[sorted_idx] = (np.arange(n_kw) + 1) / n_kw
        attn_weights = np.array([attention_weight(r) for r in rank_pcts])
        effective_probs = improve_probs * attn_weights
    else:
        effective_probs = improve_probs
        attn_weights = np.ones(n_kw)

    # GA4 anchoring
    total_semrush_baseline = baseline_per_kw.sum()
    anchor_ratio = 1.0
    if ga4_baseline is not None and total_semrush_baseline > 0:
        anchor_ratio = ga4_baseline / total_semrush_baseline
    baseline_per_kw_anchored = baseline_per_kw * anchor_ratio
    total_baseline = baseline_per_kw_anchored.sum()

    # ── Monte Carlo trials ──────────────────────────────────────────
    # Shape: (n_trials, n_kw)
    will_improve = rng.random((n_trials, n_kw)) < effective_probs[np.newaxis, :]

    # Target positions: triangular centred on deterministic target ±3
    target_low = np.maximum(1.0, det_targets - 3.0)
    target_high = np.minimum(100.0, det_targets + 3.0)
    target_mode = np.clip(det_targets.astype(float), target_low, target_high)
    target_samples = rng.triangular(
        target_low[np.newaxis, :],
        target_mode[np.newaxis, :],
        target_high[np.newaxis, :],
        size=(n_trials, n_kw),
    )
    target_samples = np.clip(np.round(target_samples), 1, 100).astype(int)

    # CTR at sampled targets
    target_ctrs = ctr_table[target_samples - 1]  # (n_trials, n_kw)

    # Apply AIO CTR penalties per-keyword at the target-CTR step
    if aio_intent_penalties:
        if "intent" in df.columns:
            intents = df["intent"].values
            aio_penalty_per_kw = np.array([
                aio_intent_penalties.get(str(intent).lower(), 0.0) / 100.0
                for intent in intents
            ])
            # Apply: target_ctrs *= (1 - penalty)
            target_ctrs = target_ctrs * (1.0 - aio_penalty_per_kw[np.newaxis, :])

    target_traffic = volumes[np.newaxis, :] * target_ctrs / 100.0 * traffic_multiplier * anchor_ratio
    uplift_per_kw = np.maximum(0.0, target_traffic - baseline_per_kw_anchored[np.newaxis, :])
    uplift_per_kw *= will_improve  # zero out non-improving keywords

    # Time-to-move samples: triangular
    ttm_modes = (ttm_lows + ttm_highs) / 2.0
    ttm_samples = rng.triangular(
        ttm_lows[np.newaxis, :],
        ttm_modes[np.newaxis, :],
        ttm_highs[np.newaxis, :] + 1.0,
        size=(n_trials, n_kw),
    )
    ttm_samples = np.maximum(1.0, ttm_samples)

    # Build per-tier S-curve t_mid/k arrays (shape: n_kw)
    tier_t_mids = np.array([TIER_MATURATION_PARAMS[t][0] for t in tiers], dtype=float)
    tier_ks = np.array([TIER_MATURATION_PARAMS[t][1] for t in tiers], dtype=float)

    # Monthly traffic across trials: (n_trials, months)
    monthly_trials = np.zeros((n_trials, months))
    for m in range(months):
        month_num = float(m + 1)
        # S-curve progress per keyword (shape: n_kw), using tier params
        # Each trial scales by whether the keyword improves (will_improve) via uplift_per_kw
        s_progress = 1.0 / (1.0 + np.exp(-tier_ks * (month_num - tier_t_mids)))
        # s_progress shape: (n_kw,); broadcast over trials: (n_trials, n_kw)
        monthly_contrib = (uplift_per_kw * s_progress[np.newaxis, :]).sum(axis=1)
        monthly_trials[:, m] = monthly_contrib

    # Apply seasonality to uplift trials (before percentile computation so bands reflect it)
    if seasonality and forecast_start_month is not None:
        season_mults = np.array([
            1.0 + seasonality.get(((forecast_start_month - 1 + m) % 12) + 1, {}).get("traffic_mod", 0.0)
            for m in range(months)
        ])
        monthly_trials *= season_mults[np.newaxis, :]

    # Per-keyword uplift summary (at full ramp = month == max(ttm))
    kw_uplift_at_ramp = uplift_per_kw.copy()
    kw_uplift_p10 = np.percentile(kw_uplift_at_ramp, 10, axis=0)
    kw_uplift_p50 = np.percentile(kw_uplift_at_ramp, 50, axis=0)
    kw_uplift_p90 = np.percentile(kw_uplift_at_ramp, 90, axis=0)

    keyword_df = df.copy()
    keyword_df["target_position"] = det_targets
    keyword_df["tier"] = tiers
    keyword_df["current_ctr"] = current_ctrs
    keyword_df["baseline_traffic"] = baseline_per_kw_anchored
    keyword_df["uplift"] = kw_uplift_p50
    keyword_df["uplift_p10"] = kw_uplift_p10
    keyword_df["uplift_p50"] = kw_uplift_p50
    keyword_df["uplift_p90"] = kw_uplift_p90
    keyword_df["attention_weight"] = attn_weights
    keyword_df = keyword_df.sort_values("uplift", ascending=False).reset_index(drop=True)

    # Monthly bands
    monthly_df = pd.DataFrame({
        "month": range(1, months + 1),
        "baseline": total_baseline,
        "uplift_p10": np.percentile(monthly_trials, 10, axis=0).astype(int),
        "uplift_p50": np.percentile(monthly_trials, 50, axis=0).astype(int),
        "uplift_p90": np.percentile(monthly_trials, 90, axis=0).astype(int),
    })
    monthly_df["traffic_p10"] = (monthly_df["baseline"] + monthly_df["uplift_p10"]).astype(int)
    monthly_df["traffic_p50"] = (monthly_df["baseline"] + monthly_df["uplift_p50"]).astype(int)
    monthly_df["traffic_p90"] = (monthly_df["baseline"] + monthly_df["uplift_p90"]).astype(int)

    # Backward-compat aliases
    monthly_df["uplift"] = monthly_df["uplift_p50"]
    monthly_df["traffic"] = monthly_df["traffic_p50"]

    # Audit trail: movement stats decision reason
    monthly_df.attrs["movement_stats_reason"] = movement_reason
    monthly_df.attrs["position_filter"] = _active_filter
    monthly_df.attrs["keyword_count"] = len(df)

    return keyword_df, monthly_df


# ──────────────────────────────────────────────────────────────────────
# Refinement C: Auto-derive Domain Authority from SEMrush rankings
# ──────────────────────────────────────────────────────────────────────

# KD → DA mapping derived from Moz/Ahrefs correlation studies.
# A site ranking in top-10 for keywords at a given KD ceiling
# implies an effective DA at least as high as the mapped value.
_KD_TO_DA = [
    (10,  20),
    (20,  25),
    (30,  32),
    (40,  40),
    (50,  47),
    (60,  55),
    (70,  63),
    (80,  72),
    (90,  82),
    (100, 92),
]


def estimate_da_from_rankings(
    semrush_df: "pd.DataFrame",
    brand_classifier: "callable | None" = None,
    top_n: int = 10,
    kd_percentile: float = 90.0,
) -> dict:
    """Auto-derive effective Domain Authority from the site's existing rankings.

    Takes the top-N non-branded keywords by position, finds their KD at the
    specified percentile, then maps that KD ceiling to an estimated DA range
    using a KD→DA lookup derived from Moz/Ahrefs correlation studies.

    This gives a defensible DA estimate without requiring external API access,
    useful for seeding the new-content rank-probability model.

    Args:
        semrush_df: SEMrush keyword DataFrame with 'position', 'kd', and
            optionally 'keyword' and 'is_branded' columns.
        brand_classifier: Optional callable(keyword: str) → bool. When
            provided, keywords returning True are excluded. Falls back to
            the 'is_branded' column if present, or includes all keywords.
        top_n: How many top-ranked keywords to use for the estimate (default 10).
        kd_percentile: Which KD percentile of the top-N pool to use as the
            difficulty ceiling (default 90th — robustly excludes outliers).

    Returns:
        Dict with keys:
            "estimated_da": int — point estimate of DA.
            "da_range": (int, int) — conservative to optimistic bounds (±10).
            "kd_ceiling": float — KD percentile value used.
            "sample_keywords": int — number of non-branded top-N keywords found.
            "rationale": str — human-readable explanation.
    """
    df = semrush_df.copy()
    df = df[df["position"].between(1, 100)].copy()

    # Exclude branded keywords
    if brand_classifier is not None and "keyword" in df.columns:
        df = df[~df["keyword"].apply(brand_classifier)].copy()
    elif "is_branded" in df.columns:
        df = df[~df["is_branded"].astype(bool)].copy()

    if df.empty or "kd" not in df.columns:
        return {
            "estimated_da": 30,
            "da_range": (20, 40),
            "kd_ceiling": 0.0,
            "sample_keywords": 0,
            "rationale": "No non-branded ranking keywords found — defaulting to DA 30.",
        }

    top = df.nsmallest(top_n, "position")
    kd_ceil = float(np.percentile(top["kd"].fillna(0).values, kd_percentile))

    # Map KD ceiling → estimated DA via lookup table
    estimated_da = _KD_TO_DA[0][1]
    for kd_thresh, da_val in _KD_TO_DA:
        if kd_ceil >= kd_thresh:
            estimated_da = da_val

    da_lo = max(1, estimated_da - 10)
    da_hi = min(100, estimated_da + 10)

    return {
        "estimated_da": estimated_da,
        "da_range": (da_lo, da_hi),
        "kd_ceiling": round(kd_ceil, 1),
        "sample_keywords": len(top),
        "rationale": (
            f"Top-{len(top)} non-branded keywords have P{int(kd_percentile)} KD = {kd_ceil:.0f}. "
            f"Estimated DA ≈ {estimated_da} (range {da_lo}–{da_hi})."
        ),
    }
