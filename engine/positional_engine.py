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


def run_positional_forecast_mc(
    df: pd.DataFrame,
    months: int = 12,
    effort: str = "moderate",
    n_trials: int = 500,
    ctr_model: dict | None = None,
    traffic_multiplier: float = 1.0,
    ga4_baseline: int | None = None,
    use_attention_curve: bool = True,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monte Carlo positional forecast with P10/P50/P90 bands.

    Returns:
        keyword_df: Per-keyword with uplift_p10/p50/p90.
        monthly_df: Monthly bands — baseline, uplift_p10/p50/p90, traffic_p10/p50/p90.
    """
    df = df.copy()
    df = df[df["position"].between(1, 100)].reset_index(drop=True)
    df["kd"] = df["kd"].fillna(0)
    df["volume"] = df["volume"].fillna(0)

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
        estimate_target_position(int(p), int(k), effort)
        for p, k in zip(positions, kds)
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

    # Monthly traffic across trials: (n_trials, months)
    monthly_trials = np.zeros((n_trials, months))
    for m in range(months):
        month_num = m + 1
        progress = np.clip((month_num - 1) / ttm_samples, 0.0, 1.0)
        monthly_contrib = (uplift_per_kw * progress).sum(axis=1)
        monthly_trials[:, m] = monthly_contrib

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

    return keyword_df, monthly_df
