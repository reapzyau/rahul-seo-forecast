"""Regression: methodology doc claims vs code reality.

When someone tweaks a constant (CTR table, decay rates, attention weights)
without updating methodology.md, this test flags it. Extend as needed.
"""
import re
from pathlib import Path

import pytest

_METHODOLOGY = (Path(__file__).parent.parent / "methodology.md").read_text()


def test_ctr_position_1_matches():
    from engine.constants import CTR_BY_POSITION
    # Doc claims position 1 = 22.0%
    assert f"| 1 | {CTR_BY_POSITION[1]:.1f} |" in _METHODOLOGY


def test_top3_decay_rate_matches():
    from engine.decay_engine import DEFAULT_DECAY_RATES
    pct = int(DEFAULT_DECAY_RATES["top3"] * 100)
    # Doc claims "Top 3 | 8%"
    assert re.search(rf"\|\s*Top 3\s*\|\s*{pct}%\s*\|", _METHODOLOGY), (
        f"methodology.md says Top 3 decay but code has {pct}%"
    )


def test_attention_top5_weight_matches():
    from engine.positional_engine import ATTENTION_TIERS
    top_weight = ATTENTION_TIERS[0]["weight"]
    # Doc claims "Top 5% | 1.00 | Focus"
    assert re.search(
        rf"\|\s*Top 5%\s*\|\s*{top_weight:.2f}\s*\|",
        _METHODOLOGY,
    ), f"methodology.md missing Top 5% attention weight {top_weight:.2f}"


def test_intent_cvr_multipliers_match():
    from engine.revenue_engine import INTENT_CVR_MULTIPLIERS
    for intent in INTENT_CVR_MULTIPLIERS:
        assert intent.lower() in _METHODOLOGY.lower(), (
            f"methodology.md missing intent: {intent}"
        )


def test_maturation_curve_params_match():
    from engine.maturation_curve import TIER_MATURATION_PARAMS
    for tier in TIER_MATURATION_PARAMS:
        assert tier in _METHODOLOGY, f"methodology.md missing maturation tier: {tier}"
