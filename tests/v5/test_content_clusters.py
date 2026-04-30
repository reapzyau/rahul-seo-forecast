"""Tests for engine/v5/content_clusters.py"""

import numpy as np
import pandas as pd
import pytest

try:
    import sklearn  # noqa: F401
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from engine.v5.content_clusters import (
    INDUSTRY_PER_POST_RANGES,
    fallback_per_post_traffic,
    forecast_cluster_capture,
    forecast_cluster_traffic_over_horizon,
)

if _SKLEARN_AVAILABLE:
    from engine.v5.content_clusters import cluster_content_opportunities

pytestmark = pytest.mark.skipif(
    not _SKLEARN_AVAILABLE,
    reason="scikit-learn not installed — skipping cluster tests",
)


def _make_synthetic_keywords(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Build a synthetic SEMrush-shape DataFrame with two distinct topical clusters."""
    rng = np.random.default_rng(seed)
    cooking_terms = [
        "best pasta recipe", "how to bake bread", "easy soup recipe",
        "vegetable stir fry tips", "dessert ideas", "homemade pizza dough",
    ]
    gardening_terms = [
        "how to grow tomatoes", "best soil for vegetables",
        "garden pest control", "watering schedule plants",
        "raised bed gardening", "composting at home",
    ]
    rows = []
    for i in range(n // 2):
        kw = rng.choice(cooking_terms) + f" tip {i}"
        rows.append({
            "keyword": kw, "position": rng.integers(21, 80),
            "volume": rng.integers(100, 5000), "kd": rng.integers(10, 30),
            "intent": "informational",
        })
    for i in range(n // 2):
        kw = rng.choice(gardening_terms) + f" guide {i}"
        rows.append({
            "keyword": kw, "position": rng.integers(21, 80),
            "volume": rng.integers(100, 5000), "kd": rng.integers(10, 30),
            "intent": "informational",
        })
    return pd.DataFrame(rows)


def test_cluster_content_opportunities_returns_clusters():
    df = _make_synthetic_keywords(200)
    clusters = cluster_content_opportunities(df)
    assert not clusters.empty
    assert "cluster_label" in clusters.columns
    assert "median_keyword_volume" in clusters.columns
    assert clusters["keyword_count"].sum() <= len(df)


def test_cluster_skips_when_no_data():
    df = pd.DataFrame({
        "keyword": ["a", "b"], "position": [50, 50],
        "volume": [100, 100], "kd": [20, 20], "intent": ["informational"] * 2,
    })
    clusters = cluster_content_opportunities(df)
    assert clusters.empty  # below the 20-keyword minimum


def test_cluster_filters_branded():
    df = _make_synthetic_keywords(200)
    branded = pd.DataFrame({
        "keyword": ["my brand kw"] * 100,
        "position": [50] * 100, "volume": [1000] * 100,
        "kd": [20] * 100, "intent": ["informational"] * 100,
    })
    df_with_brand = pd.concat([df, branded], ignore_index=True)
    clusters = cluster_content_opportunities(
        df_with_brand,
        brand_classifier=lambda kw: "my brand" in str(kw),
    )
    assert clusters["keyword_count"].sum() <= 200


def test_capture_respects_floor_and_ceiling():
    cluster_df = pd.DataFrame([{
        "cluster_id": 0, "cluster_label": "test", "keyword_count": 10,
        "total_volume": 100000, "median_keyword_volume": 5000,
        "mean_kd": 10, "mean_position": 50,
    }])
    enriched = forecast_cluster_capture(cluster_df, da=70, capture_ceiling=600)
    assert enriched["capture_per_post"].iloc[0] == 600  # capped at ceiling

    cluster_df_tiny = pd.DataFrame([{
        "cluster_id": 0, "cluster_label": "test", "keyword_count": 5,
        "total_volume": 50, "median_keyword_volume": 5,
        "mean_kd": 80, "mean_position": 70,
    }])
    enriched_tiny = forecast_cluster_capture(cluster_df_tiny, da=20, capture_floor=50)
    assert enriched_tiny["capture_per_post"].iloc[0] == 50  # floored


def test_forecast_returns_monthly_array():
    df = _make_synthetic_keywords(300)
    clusters = cluster_content_opportunities(df)
    if clusters.empty:
        pytest.skip("clustering produced no clusters")
    forecast = forecast_cluster_traffic_over_horizon(
        clusters, da=40, months=12, posts_per_month=2,
    )
    assert "monthly_total" in forecast
    assert len(forecast["monthly_total"]) == 12
    assert forecast["monthly_total"][-1] > forecast["monthly_total"][0]


def test_fallback_per_post_traffic_known_industries():
    lo, hi, rationale = fallback_per_post_traffic("apparel_fashion")
    assert lo == 150 and hi == 400
    assert "apparel" in rationale.lower()

    lo_def, hi_def, _ = fallback_per_post_traffic("nonexistent_industry")
    assert (lo_def, hi_def) == INDUSTRY_PER_POST_RANGES["default"]
