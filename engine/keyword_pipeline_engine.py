"""Keyword ranking pipeline engine — tracks keyword distribution across SERP pages."""

import numpy as np
import pandas as pd

# SERP page boundaries
PAGE_RANGES = {
    "Page 1": (1, 10),
    "Page 2": (11, 20),
    "Page 3": (21, 30),
    "Pages 4-10": (31, 100),
}


def classify_serp_page(position: int | None) -> str:
    """Classify a keyword position into a SERP page bucket."""
    if position is None or pd.isna(position):
        return "Not Ranking"
    position = int(position)
    for page_name, (low, high) in PAGE_RANGES.items():
        if low <= position <= high:
            return page_name
    return "Not Ranking"


def build_pipeline_snapshot(keyword_df: pd.DataFrame) -> dict[str, int]:
    """Count keywords in each SERP page bucket from keyword forecast data.

    Args:
        keyword_df: DataFrame with 'expected_position' column.

    Returns:
        Dict of page_name -> count.
    """
    counts = {"Page 1": 0, "Page 2": 0, "Page 3": 0, "Pages 4-10": 0, "Not Ranking": 0}
    for _, row in keyword_df.iterrows():
        page = classify_serp_page(row.get("expected_position"))
        counts[page] = counts.get(page, 0) + 1
    return counts


def build_pipeline_over_time(
    keyword_df: pd.DataFrame,
    months: int,
) -> pd.DataFrame:
    """Project keyword ranking distribution over time.

    Models keywords moving from lower pages to higher pages as they rank.
    Uses publish_month and time_to_rank to determine when keywords enter Page 1.

    Args:
        keyword_df: Per-keyword results from keyword forecast.
        months: Forecast horizon.

    Returns:
        DataFrame with month, page_1, page_2, page_3, pages_4_10, not_ranking columns.
    """
    rows = []
    for m in range(1, months + 1):
        page_counts = {"Page 1": 0, "Page 2": 0, "Page 3": 0, "Pages 4-10": 0, "Not Ranking": 0}

        for _, kw in keyword_df.iterrows():
            publish_month = kw.get("publish_month")
            if publish_month is None or m < publish_month:
                continue  # Not yet published

            if not kw.get("will_rank", False):
                page_counts["Not Ranking"] += 1
                continue

            traffic_start = kw.get("traffic_starts_month")
            pos = kw.get("expected_position")

            if traffic_start is not None and m >= traffic_start:
                # Keyword has reached its final position
                page = classify_serp_page(pos)
                page_counts[page] += 1
            elif traffic_start is not None and m >= publish_month:
                # Keyword is published but still climbing
                months_since_publish = m - publish_month
                ttr = kw.get("time_to_rank")
                if ttr and ttr > 0:
                    progress = min(1.0, months_since_publish / ttr)
                else:
                    progress = 0

                if progress < 0.3:
                    page_counts["Pages 4-10"] += 1
                elif progress < 0.6:
                    page_counts["Page 3"] += 1
                elif progress < 0.9:
                    page_counts["Page 2"] += 1
                else:
                    page = classify_serp_page(pos)
                    page_counts[page] += 1
            else:
                page_counts["Pages 4-10"] += 1

        rows.append({
            "month": m,
            "page_1": page_counts["Page 1"],
            "page_2": page_counts["Page 2"],
            "page_3": page_counts["Page 3"],
            "pages_4_10": page_counts["Pages 4-10"],
            "not_ranking": page_counts["Not Ranking"],
            "total_published": sum(page_counts.values()),
        })

    result = pd.DataFrame(rows)

    # Add MoM changes
    for col in ["page_1", "page_2", "page_3"]:
        result[f"{col}_mom_change"] = result[col].diff().fillna(0).astype(int)
        prev = result[col].shift(1)
        result[f"{col}_mom_pct"] = ((result[col] - prev) / prev.replace(0, np.nan) * 100).round(1)

    return result
