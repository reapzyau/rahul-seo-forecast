"""Tests for engine/v5/da_estimator.py"""

import numpy as np
import pandas as pd

from engine.v5.da_estimator import compare_da_estimate_to_supplied, estimate_da_from_rankings


def _make_synthetic_rankings(n_top10: int, kd_at_p90: int, n_outside: int = 50) -> pd.DataFrame:
    """Synthesise a SEMrush-shape DataFrame with controlled KD distribution in top-10."""
    rng = np.random.default_rng(42)
    top_kds = rng.integers(low=5, high=kd_at_p90 + 5, size=n_top10).clip(0, 100)
    top_rows = pd.DataFrame({
        "keyword": [f"kw_top_{i}" for i in range(n_top10)],
        "position": rng.integers(1, 11, size=n_top10),
        "kd": top_kds,
    })
    rest_rows = pd.DataFrame({
        "keyword": [f"kw_rest_{i}" for i in range(n_outside)],
        "position": rng.integers(20, 100, size=n_outside),
        "kd": rng.integers(1, 100, size=n_outside),
    })
    return pd.concat([top_rows, rest_rows], ignore_index=True)


def test_da_matches_p90_of_top10_kds():
    df = _make_synthetic_rankings(n_top10=200, kd_at_p90=30)
    da, rationale = estimate_da_from_rankings(df)
    assert da is not None
    assert 25 <= da <= 35, f"expected DA near 30, got {da}"
    assert "90th percentile" in rationale


def test_returns_none_when_sample_too_small():
    df = _make_synthetic_rankings(n_top10=10, kd_at_p90=30)
    da, rationale = estimate_da_from_rankings(df)
    assert da is None
    assert "insufficient" in rationale.lower()


def test_brand_classifier_excludes_branded_from_estimate():
    df = _make_synthetic_rankings(n_top10=100, kd_at_p90=30)
    branded = pd.DataFrame({
        "keyword": [f"my_brand_{i}" for i in range(50)],
        "position": [1] * 50,
        "kd": [5] * 50,
    })
    df_with_brand = pd.concat([df, branded], ignore_index=True)
    da_filtered, _ = estimate_da_from_rankings(
        df_with_brand,
        brand_classifier=lambda kw: "my_brand" in str(kw),
    )
    da_unfiltered, _ = estimate_da_from_rankings(df_with_brand)
    assert da_filtered is not None
    assert da_unfiltered is not None
    assert da_filtered > da_unfiltered


def test_compare_da_within_tolerance():
    msg = compare_da_estimate_to_supplied(estimated=42, supplied=45, tolerance=10)
    assert "agrees" in msg


def test_compare_da_diverges():
    msg = compare_da_estimate_to_supplied(estimated=29, supplied=45, tolerance=10)
    assert "differs" in msg
    assert "review" in msg.lower()


def test_handles_missing_columns():
    df = pd.DataFrame({"keyword": ["a"], "position": [1]})
    da, rationale = estimate_da_from_rankings(df)
    assert da is None
    assert "missing" in rationale.lower()
