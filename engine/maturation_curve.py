"""Logistic S-curve maturation for new content and positional ramp-up.

Replaces the linear ramp and step functions used in v3 with a smooth S-curve
that hits roughly 10% by quarter-1 of ramp, 40% by half, 80% by three-quarters.
"""

from __future__ import annotations

import numpy as np

# (t_mid, k) per difficulty tier — t_mid = month at which 50% progress is reached
TIER_MATURATION_PARAMS: dict[str, tuple[float, float]] = {
    "Easy": (2.5, 1.8),
    "Moderate": (5.0, 1.2),
    "Hard": (8.0, 0.9),
    "Very Hard": (11.0, 0.7),
    "Extreme": (13.0, 0.5),
}


def logistic_progress(month: float, t_mid: float, k: float) -> float:
    """Return progress in [0, 1] via the logistic (sigmoid) function.

    Args:
        month: Elapsed months since publication / forecast start.
        t_mid: Month at which progress = 0.5 (inflection point).
        k: Steepness of the curve (higher = sharper transition).
    """
    return 1.0 / (1.0 + np.exp(-k * (month - t_mid)))


def tier_maturation_params(tier: str) -> tuple[float, float]:
    """Return (t_mid, k) for the given difficulty tier."""
    return TIER_MATURATION_PARAMS.get(tier, TIER_MATURATION_PARAMS["Moderate"])


def maturation_schedule(tier: str, months: int, publish_month: int) -> np.ndarray:
    """Return an array of progress values [0..1] for each month in the horizon.

    Args:
        tier: Keyword difficulty tier label.
        months: Total forecast horizon length.
        publish_month: 1-indexed month when content is published (traffic before
                       this month is 0).

    Returns:
        Array of shape (months,) with progress values in [0, 1].
    """
    t_mid, k = tier_maturation_params(tier)
    progress = np.zeros(months)
    for m in range(months):
        elapsed = (m + 1) - publish_month
        if elapsed <= 0:
            progress[m] = 0.0
        else:
            progress[m] = logistic_progress(float(elapsed), t_mid, k)
    return progress
