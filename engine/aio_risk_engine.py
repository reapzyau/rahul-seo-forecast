"""AI Overview (AIO) risk analysis engine.

Calculates CTR erosion risk from Google AI Overviews appearing for
SEMrush keyword data, and generates actionable recommendations.

v3 adds time-varying erosion: AIO coverage spreads ~2-3% of queries
per month, so a forecast-horizon projection shows increasing loss.
"""

import pandas as pd

# ── Time-varying AIO erosion constants ─────────────────────────────────────

DEFAULT_MONTHLY_AIO_GROWTH = 0.025  # 2.5% per month

INTENT_AIO_CTR_PENALTY = {
    "informational": 0.45,
    "commercial": 0.15,
    "transactional": 0.05,
    "navigational": 0.00,
}


def calculate_aio_risk(df: pd.DataFrame, ctr_penalty_pct: float = 40.0) -> dict:
    """Calculate AI Overview risk metrics from keyword data.

    Args:
        df: DataFrame with columns: keyword, has_aio (bool), volume (int),
            current_traffic (float), intent (str).
        ctr_penalty_pct: Estimated CTR loss percentage when an AI Overview
            is present (e.g. 40.0 = 40%).

    Returns:
        Dict with keys:
            - keywords_affected: int
            - total_keywords: int
            - traffic_at_risk: float
            - projected_loss: float
            - intent_breakdown: DataFrame (intent, keywords, traffic, traffic_loss)
            - detail_df: filtered AIO-affected rows with projected_loss column
    """
    total_keywords = len(df)
    penalty_fraction = ctr_penalty_pct / 100.0

    # Filter to AIO-affected keywords
    aio_df = df[df["has_aio"] == True].copy()  # noqa: E712

    keywords_affected = len(aio_df)
    traffic_at_risk = aio_df["current_traffic"].sum() if keywords_affected > 0 else 0.0
    projected_loss = traffic_at_risk * penalty_fraction

    # Per-keyword projected loss
    aio_df["projected_loss"] = aio_df["current_traffic"] * penalty_fraction

    # Intent breakdown
    if keywords_affected > 0:
        intent_agg = (
            aio_df.groupby("intent", as_index=False)
            .agg(keywords=("keyword", "count"), traffic=("current_traffic", "sum"))
        )
        intent_agg["traffic_loss"] = intent_agg["traffic"] * penalty_fraction
        intent_agg = intent_agg.sort_values("traffic_loss", ascending=False).reset_index(drop=True)
    else:
        intent_agg = pd.DataFrame(columns=["intent", "keywords", "traffic", "traffic_loss"])

    return {
        "keywords_affected": keywords_affected,
        "total_keywords": total_keywords,
        "traffic_at_risk": traffic_at_risk,
        "projected_loss": projected_loss,
        "intent_breakdown": intent_agg,
        "detail_df": aio_df.reset_index(drop=True),
    }


def aio_recommendations(risk: dict) -> list[str]:
    """Generate actionable recommendations from an AIO risk assessment.

    Args:
        risk: Dict returned by ``calculate_aio_risk()``.

    Returns:
        List of recommendation strings.
    """
    keywords_affected = risk["keywords_affected"]
    total_keywords = risk.get("total_keywords", 0)

    if keywords_affected == 0:
        return ["Low AIO exposure — no immediate action needed."]

    recommendations: list[str] = []

    # Exposure-level recommendation
    if total_keywords > 0:
        exposure_pct = (keywords_affected / total_keywords) * 100
    else:
        exposure_pct = 0.0

    if exposure_pct < 3:
        recommendations.append(
            "Low AIO exposure. Maintain current strategy with quarterly review."
        )
    elif exposure_pct <= 10:
        recommendations.append(
            "Moderate AIO exposure. Audit informational content for featured snippet optimization."
        )
    else:
        recommendations.append(
            "High AIO exposure. Consider shifting content strategy toward transactional/commercial keywords."
        )

    # Intent-specific recommendations
    intent_breakdown = risk.get("intent_breakdown")
    if intent_breakdown is not None and not intent_breakdown.empty:
        total_loss = risk["projected_loss"]

        # Check informational share
        info_rows = intent_breakdown[
            intent_breakdown["intent"].str.lower().str.contains("informational", na=False)
        ]
        if not info_rows.empty and total_loss > 0:
            info_loss = info_rows["traffic_loss"].sum()
            if info_loss > total_loss * 0.5:
                recommendations.append(
                    "Informational content carries the highest AIO risk. "
                    "Consider converting guides to interactive tools or calculators."
                )

        # Check commercial keywords
        commercial_rows = intent_breakdown[
            intent_breakdown["intent"].str.lower().str.contains("commercial", na=False)
        ]
        if not commercial_rows.empty and commercial_rows["keywords"].sum() > 0:
            recommendations.append(
                "Optimize product/service pages with structured data to maintain visibility in AI results."
            )

    return recommendations


# ── Time-varying AIO erosion ───────────────────────────────────────────────


def project_aio_erosion(
    keyword_df: pd.DataFrame,
    months: int,
    monthly_growth: float = DEFAULT_MONTHLY_AIO_GROWTH,
    intent_penalties: dict | None = None,
) -> pd.DataFrame:
    """Project per-month traffic loss from spreading AIO coverage.

    Two components:
      1. Keywords already flagged with AIO lose CTR from month 1.
      2. Additional keywords become AIO-affected over time at monthly_growth rate.

    Returns:
        DataFrame with month, aio_affected_count, monthly_erosion, cumulative_erosion.
    """
    if keyword_df.empty:
        return pd.DataFrame({
            "month": range(1, months + 1),
            "aio_affected_count": [0] * months,
            "monthly_erosion": [0] * months,
            "cumulative_erosion": [0] * months,
        })

    penalties = intent_penalties or INTENT_AIO_CTR_PENALTY
    df = keyword_df.copy()
    df["penalty"] = df["intent"].map(lambda i: penalties.get(i, 0.10))
    df["current_traffic"] = df.get("current_traffic", pd.Series([0] * len(df))).fillna(0)

    initially_affected = df["has_aio"].astype(bool)
    already_traffic = df.loc[initially_affected, "current_traffic"].values.astype(float)
    already_penalties = df.loc[initially_affected, "penalty"].values
    newcomer_traffic = df.loc[~initially_affected, "current_traffic"].values.astype(float)
    newcomer_penalties = df.loc[~initially_affected, "penalty"].values
    n_initially = int(initially_affected.sum())
    n_newcomers = int((~initially_affected).sum())

    rows = []
    prev_cumulative = 0
    for m in range(1, months + 1):
        p_affected_by_m = 1.0 - (1.0 - monthly_growth) ** m

        already_loss = float((already_traffic * already_penalties).sum())
        newcomer_loss = float((newcomer_traffic * newcomer_penalties).sum()) * p_affected_by_m

        cumulative_erosion = int(already_loss + newcomer_loss)
        monthly_loss = cumulative_erosion - prev_cumulative
        prev_cumulative = cumulative_erosion

        affected_count = n_initially + int(n_newcomers * p_affected_by_m)

        rows.append({
            "month": m,
            "aio_affected_count": affected_count,
            "monthly_erosion": monthly_loss,
            "cumulative_erosion": cumulative_erosion,
        })

    return pd.DataFrame(rows)
