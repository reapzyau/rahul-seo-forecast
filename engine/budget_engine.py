"""SEO budget and task roadmap engine."""

import pandas as pd


# Default SEO task templates with hours per month
DEFAULT_SEO_TASKS = [
    {
        "category": "Technical SEO",
        "task": "Bi-Annual Technical Audit",
        "hours_per_month": 4.0,
        "frequency": "Bi-Annual",
        "description": "Comprehensive site audit covering crawlability, indexation, Core Web Vitals, and schema markup.",
    },
    {
        "category": "Content Production",
        "task": "Long-Form Article Production",
        "hours_per_month": 10.0,
        "frequency": "2x per month",
        "description": "Research, write, and optimise 2 long-form articles (1500+ words) per month targeting priority keywords.",
    },
    {
        "category": "Content Production",
        "task": "Content Calendar & Planning",
        "hours_per_month": 2.0,
        "frequency": "Monthly",
        "description": "Monthly content calendar aligned with keyword forecast and campaign calendar.",
    },
    {
        "category": "On-Page SEO",
        "task": "Page Optimisation & Updates",
        "hours_per_month": 4.0,
        "frequency": "Ongoing",
        "description": "Title tags, meta descriptions, internal linking, and content refreshes on existing pages.",
    },
    {
        "category": "Local SEO",
        "task": "Google Business Profile Optimisation",
        "hours_per_month": 2.0,
        "frequency": "Monthly",
        "description": "GMB posts, review management, Q&A updates, and local citation building.",
    },
    {
        "category": "Link Building",
        "task": "Outreach & Link Acquisition",
        "hours_per_month": 8.0,
        "frequency": "Ongoing",
        "description": "Digital PR, guest posting, and strategic link building to priority pages.",
    },
    {
        "category": "Reporting",
        "task": "Monthly Reporting & Analysis",
        "hours_per_month": 3.0,
        "frequency": "Monthly",
        "description": "Performance reporting, keyword tracking, and strategic recommendations.",
    },
    {
        "category": "Strategy",
        "task": "Quarterly Strategy Review",
        "hours_per_month": 2.75,
        "frequency": "Quarterly",
        "description": "In-depth strategy review, forecast recalibration, and roadmap adjustments.",
    },
]


def build_budget_roadmap(
    tasks: list[dict] | None = None,
    hourly_rate: float = 200.0,
    months: int = 12,
) -> tuple[pd.DataFrame, dict]:
    """Build a monthly SEO budget roadmap.

    Args:
        tasks: List of task dicts with category, task, hours_per_month, frequency, description.
               Defaults to DEFAULT_SEO_TASKS.
        hourly_rate: Cost per hour.
        months: Number of months to project.

    Returns:
        Tuple of (task_df, summary_dict).
        task_df: Per-task breakdown with costs.
        summary_dict: Aggregated budget stats.
    """
    task_list = tasks or DEFAULT_SEO_TASKS

    rows = []
    for t in task_list:
        hours = t.get("hours_per_month", 0)
        monthly_cost = hours * hourly_rate
        rows.append({
            "Category": t.get("category", ""),
            "Task": t.get("task", ""),
            "Hours/Month": hours,
            "Monthly Cost": monthly_cost,
            "Frequency": t.get("frequency", ""),
            "Description": t.get("description", ""),
        })

    task_df = pd.DataFrame(rows)

    total_hours = task_df["Hours/Month"].sum()
    total_monthly = task_df["Monthly Cost"].sum()

    summary = {
        "total_hours_per_month": total_hours,
        "total_monthly_cost": total_monthly,
        "total_annual_cost": total_monthly * 12,
        "total_project_cost": total_monthly * months,
        "hourly_rate": hourly_rate,
        "months": months,
        "task_count": len(task_list),
    }

    return task_df, summary


def build_monthly_budget_timeline(
    tasks: list[dict] | None = None,
    hourly_rate: float = 200.0,
    months: int = 12,
) -> pd.DataFrame:
    """Build a month-by-month budget allocation timeline.

    Args:
        tasks: List of task dicts.
        hourly_rate: Cost per hour.
        months: Number of months.

    Returns:
        DataFrame with month rows and category columns showing monthly spend.
    """
    task_list = tasks or DEFAULT_SEO_TASKS

    # Aggregate hours by category
    category_hours = {}
    for t in task_list:
        cat = t.get("category", "Other")
        hours = t.get("hours_per_month", 0)
        category_hours[cat] = category_hours.get(cat, 0) + hours

    rows = []
    for m in range(1, months + 1):
        row = {"Month": m}
        total = 0
        for cat, hours in category_hours.items():
            cost = hours * hourly_rate
            row[cat] = cost
            total += cost
        row["Total"] = total
        rows.append(row)

    return pd.DataFrame(rows)
