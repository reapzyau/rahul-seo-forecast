"""Tests for engine/v5/movement_stats.py"""

import numpy as np
import pandas as pd

from engine.v5.movement_stats import (
    ENGINE_DEFAULTS,
    TIER_ORDER,
    estimate_target_position_v2,
    learn_movement_from_history_v2,
    resolve_movement_stats,
)


def _make_kw_df(tier_gains: dict, n_per_tier: int = 50, seed: int = 42) -> pd.DataFrame:
    """Synthesise a kw_df with controlled movement per tier.
    tier_gains: dict {tier_label: gain_value}
    """
    rng = np.random.default_rng(seed)
    tier_kd = {"Easy": 14, "Moderate": 28, "Hard": 49, "Very Hard": 69, "Extreme": 85}
    rows = []
    for tier, gain in tier_gains.items():
        kd = tier_kd[tier]
        for _ in range(n_per_tier):
            current_pos = rng.integers(5, 30)
            previous_pos = current_pos + gain
            rows.append({
                "previous_position": previous_pos,
                "position": current_pos,
                "kd": kd,
            })
    return pd.DataFrame(rows)


def test_positive_gains_use_learned_in_force_learned_mode():
    df = _make_kw_df({"Easy": 6, "Moderate": 5, "Hard": 4, "Very Hard": 3, "Extreme": 2})
    learned = learn_movement_from_history_v2(df)
    resolved, decisions = resolve_movement_stats(learned, mode="force_learned")
    for tier, expected in [("Easy", 6), ("Moderate", 5), ("Hard", 4), ("Very Hard", 3), ("Extreme", 2)]:
        assert abs(resolved[tier] - expected) < 1.0, f"{tier}: {resolved[tier]} != {expected}"


def test_all_negative_uses_engine_defaults_in_auto():
    df = _make_kw_df({"Easy": -2, "Moderate": -2, "Hard": -2, "Very Hard": -2, "Extreme": -2})
    learned = learn_movement_from_history_v2(df)
    resolved, decisions = resolve_movement_stats(learned, mode="auto")
    for tier in TIER_ORDER:
        assert resolved[tier] == ENGINE_DEFAULTS[tier], \
            f"{tier}: expected default {ENGINE_DEFAULTS[tier]}, got {resolved[tier]}"


def test_mixed_tiers_resolve_independently():
    df = _make_kw_df({
        "Easy": 8, "Moderate": 0, "Hard": -2, "Very Hard": -1, "Extreme": -1,
    })
    learned = learn_movement_from_history_v2(df)
    resolved, decisions = resolve_movement_stats(learned, mode="auto")
    assert resolved["Easy"] >= ENGINE_DEFAULTS["Easy"], "Easy should be at least default"
    assert resolved["Hard"] == ENGINE_DEFAULTS["Hard"]


def test_force_engine_overrides_learned():
    df = _make_kw_df({"Easy": 10, "Moderate": 10, "Hard": 10, "Very Hard": 10, "Extreme": 10})
    learned = learn_movement_from_history_v2(df)
    resolved, decisions = resolve_movement_stats(learned, mode="force_engine")
    for tier in TIER_ORDER:
        assert resolved[tier] == ENGINE_DEFAULTS[tier]


def test_no_learned_data_uses_defaults():
    resolved, decisions = resolve_movement_stats(None, mode="auto")
    for tier in TIER_ORDER:
        assert resolved[tier] == ENGINE_DEFAULTS[tier]


def test_estimate_target_position_v2_respects_effort_factor():
    resolved = ENGINE_DEFAULTS.copy()
    target_light = estimate_target_position_v2(20, kd=10, effort="light", resolved_gains=resolved)
    target_moderate = estimate_target_position_v2(20, kd=10, effort="moderate", resolved_gains=resolved)
    target_aggressive = estimate_target_position_v2(20, kd=10, effort="aggressive", resolved_gains=resolved)
    assert target_light > target_moderate > target_aggressive
    assert target_light == 20 - round(5 * 0.5)
    assert target_moderate == 20 - 5
    assert target_aggressive == 20 - round(5 * 1.5)


def test_undersampled_tier_falls_back_to_default():
    df = _make_kw_df({"Easy": 5}, n_per_tier=5)
    learned = learn_movement_from_history_v2(df)
    assert "Easy" not in learned, "Easy tier should be skipped — below min_sample"
    resolved, _ = resolve_movement_stats(learned, mode="auto")
    assert resolved["Easy"] == ENGINE_DEFAULTS["Easy"]
