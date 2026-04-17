"""AI Overview (AIO) risk analysis engine.

Calculates CTR erosion risk from Google AI Overviews appearing for
SEMrush keyword data, and generates actionable recommendations.
"""

import pandas as pd


def calculate_aio_risk(df: pd.DataFrame, ctr_penalty_pct: float = 40.0) -> dict:
    """Calculate AI Overview risk metrics from keyword data.

    Args:
        df: DataFrame with columns: keyword, has_aio (bool), volume (int),
            current_traffic (float), primary_intent (str).
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
            aio_df.groupby("primary_intent", as_index=False)
            .agg(keywords=("keyword", "count"), traffic=("current_traffic", "sum"))
        )
        intent_agg["traffic_loss"] = intent_agg["traffic"] * penalty_fraction
        intent_agg = intent_agg.rename(columns={"primary_intent": "intent"})
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
