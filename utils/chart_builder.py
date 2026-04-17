import plotly.graph_objects as go
import pandas as pd

from engine.constants import TIER_COLORS

_LAYOUT_DEFAULTS = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="sans-serif", color="#0F172A"),
    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
    hovermode="x unified",
    margin=dict(l=60, r=20, t=40, b=60),
    xaxis=dict(showgrid=True, gridcolor="#F1F5F9", gridwidth=1),
    yaxis=dict(showgrid=True, gridcolor="#F1F5F9", gridwidth=1),
)


def _apply_layout(fig: go.Figure, title: str, xaxis_title: str, yaxis_title: str) -> go.Figure:
    fig.update_layout(
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        **_LAYOUT_DEFAULTS,
    )
    return fig


def traffic_projection_chart(monthly_df: pd.DataFrame, title: str = "Monthly Traffic Projection") -> go.Figure:
    """Line chart with area fill for monthly traffic."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly_df["month"],
        y=monthly_df["traffic"],
        mode="lines",
        name="Projected Traffic",
        line=dict(color="#2563EB", width=3),
        fill="tozeroy",
        fillcolor="rgba(37, 99, 235, 0.1)",
        hovertemplate="Month %{x}<br>Traffic: %{y:,.0f}<extra></extra>",
    ))

    # Add vertical line at month where all keywords are covered
    if "traffic" in monthly_df.columns:
        max_traffic = monthly_df["traffic"].max()
        max_month = monthly_df.loc[monthly_df["traffic"].idxmax(), "month"]
        if max_traffic > 0:
            # Find month where traffic first reaches its maximum
            full_coverage = monthly_df[monthly_df["traffic"] == max_traffic]["month"].iloc[0]
            fig.add_vline(
                x=full_coverage, line_dash="dash", line_color="#94A3B8",
                annotation_text="Full ramp-up", annotation_position="top right",
            )

    return _apply_layout(fig, title, "Month", "Estimated Monthly Visits")


def keyword_schedule_chart(keyword_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart coloured by difficulty tier."""
    df = keyword_df[keyword_df["will_rank"]].copy()
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No keywords expected to rank", showarrow=False, font=dict(size=16))
        return fig

    df = df.sort_values("estimated_monthly_traffic", ascending=True).tail(30)

    fig = go.Figure()
    for tier, color in TIER_COLORS.items():
        tier_df = df[df["tier"] == tier]
        if not tier_df.empty:
            fig.add_trace(go.Bar(
                y=tier_df["keyword"],
                x=tier_df["estimated_monthly_traffic"],
                name=tier,
                orientation="h",
                marker_color=color,
                hovertemplate="%{y}<br>Traffic: %{x:,.0f}<extra></extra>",
            ))

    fig.update_layout(
        barmode="stack",
        height=max(400, len(df) * 25),
        **_LAYOUT_DEFAULTS,
    )
    fig.update_layout(
        title="Keywords by Estimated Traffic",
        xaxis_title="Estimated Monthly Traffic",
        yaxis_title="",
    )
    return fig


def historical_comparison_chart(
    historical_df: pd.DataFrame,
    methods: list[str],
) -> go.Figure:
    """Multi-line chart with confidence band for historical forecast methods."""
    fig = go.Figure()

    # Actual data
    actual_mask = historical_df["actual"].notna()
    fig.add_trace(go.Scatter(
        x=historical_df.loc[actual_mask, "date"],
        y=historical_df.loc[actual_mask, "actual"],
        mode="lines+markers",
        name="Actual",
        line=dict(color="#0F172A", width=3),
        hovertemplate="%{x|%b %Y}<br>Traffic: %{y:,.0f}<extra></extra>",
    ))

    forecast_mask = historical_df["is_forecast"]
    colors = {"linear": "#2563EB", "exponential_smoothing": "#8B5CF6", "sma": "#F97316"}
    labels = {"linear": "Linear Regression", "exponential_smoothing": "Exponential Smoothing", "sma": "Simple Moving Average"}

    for col, color in colors.items():
        if col in historical_df.columns:
            # Forecast portion (dashed)
            fig.add_trace(go.Scatter(
                x=historical_df.loc[forecast_mask, "date"],
                y=historical_df.loc[forecast_mask, col],
                mode="lines",
                name=labels[col],
                line=dict(color=color, width=2, dash="dash"),
                hovertemplate="%{x|%b %Y}<br>" + labels[col] + ": %{y:,.0f}<extra></extra>",
            ))

    # Confidence band for linear
    if "linear_upper" in historical_df.columns:
        fig.add_trace(go.Scatter(
            x=historical_df.loc[forecast_mask, "date"],
            y=historical_df.loc[forecast_mask, "linear_upper"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=historical_df.loc[forecast_mask, "date"],
            y=historical_df.loc[forecast_mask, "linear_lower"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(37, 99, 235, 0.1)",
            name="Confidence Band",
            hoverinfo="skip",
        ))

    return _apply_layout(fig, "Historical Traffic Forecast", "Date", "Monthly Traffic")


def combined_forecast_chart(combined_df: pd.DataFrame) -> go.Figure:
    """Baseline vs combined with shaded uplift area."""
    fig = go.Figure()

    # Actual historical data
    actual_mask = combined_df["actual"].notna()
    fig.add_trace(go.Scatter(
        x=combined_df.loc[actual_mask, "date"],
        y=combined_df.loc[actual_mask, "actual"],
        mode="lines+markers",
        name="Historical Actual",
        line=dict(color="#0F172A", width=3),
        hovertemplate="%{x|%b %Y}<br>Actual: %{y:,.0f}<extra></extra>",
    ))

    forecast_mask = combined_df["is_forecast"]

    # Baseline projection
    fig.add_trace(go.Scatter(
        x=combined_df.loc[forecast_mask, "date"],
        y=combined_df.loc[forecast_mask, "baseline"],
        mode="lines",
        name="Baseline (no new content)",
        line=dict(color="#94A3B8", width=2, dash="dash"),
        hovertemplate="%{x|%b %Y}<br>Baseline: %{y:,.0f}<extra></extra>",
    ))

    # Combined projection
    fig.add_trace(go.Scatter(
        x=combined_df.loc[forecast_mask, "date"],
        y=combined_df.loc[forecast_mask, "combined"],
        mode="lines",
        name="Combined (with new content)",
        line=dict(color="#2563EB", width=3),
        hovertemplate="%{x|%b %Y}<br>Combined: %{y:,.0f}<extra></extra>",
    ))

    # Shaded uplift area between baseline and combined
    fig.add_trace(go.Scatter(
        x=combined_df.loc[forecast_mask, "date"],
        y=combined_df.loc[forecast_mask, "combined"],
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=combined_df.loc[forecast_mask, "date"],
        y=combined_df.loc[forecast_mask, "baseline"],
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(37, 99, 235, 0.15)",
        name="Incremental Uplift",
        hoverinfo="skip",
    ))

    return _apply_layout(fig, "Combined Traffic Forecast", "Date", "Monthly Traffic")


def scenario_comparison_chart(scenarios_dict: dict[int, pd.DataFrame]) -> go.Figure:
    """Multi-line overlay comparing different cadence scenarios."""
    fig = go.Figure()
    colors = ["#2563EB", "#8B5CF6", "#F97316", "#22C55E", "#EF4444", "#EAB308"]

    for i, (cadence, df) in enumerate(sorted(scenarios_dict.items())):
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=df["month"],
            y=df["traffic"],
            mode="lines",
            name=f"{cadence} posts/month",
            line=dict(color=color, width=2),
            hovertemplate=f"{cadence}/mo — Month %{{x}}<br>Traffic: %{{y:,.0f}}<extra></extra>",
        ))

    return _apply_layout(fig, "Scenario Comparison: Content Cadence", "Month", "Estimated Monthly Visits")


def combined_scenario_chart(scenarios_dict: dict[int, pd.DataFrame]) -> go.Figure:
    """Multi-line overlay comparing combined traffic at different cadences."""
    fig = go.Figure()
    colors = ["#2563EB", "#8B5CF6", "#F97316", "#22C55E", "#EF4444", "#EAB308"]

    for i, (cadence, df) in enumerate(sorted(scenarios_dict.items())):
        color = colors[i % len(colors)]
        forecast = df[df["is_forecast"]]
        fig.add_trace(go.Scatter(
            x=forecast["date"],
            y=forecast["combined"],
            mode="lines",
            name=f"{cadence} posts/month",
            line=dict(color=color, width=2),
            hovertemplate=f"{cadence}/mo — %{{x|%b %Y}}<br>Combined: %{{y:,.0f}}<extra></extra>",
        ))

    return _apply_layout(fig, "Scenario Comparison: Combined Traffic by Cadence", "Date", "Monthly Traffic")


def revenue_projection_chart(monthly_df: pd.DataFrame, currency_symbol: str = "$") -> go.Figure:
    """Line chart for monthly revenue projection."""
    fig = go.Figure()

    x_col = "month" if "month" in monthly_df.columns else "date"

    fig.add_trace(go.Scatter(
        x=monthly_df[x_col],
        y=monthly_df["revenue"],
        mode="lines",
        name="Projected Revenue",
        line=dict(color="#22C55E", width=3),
        fill="tozeroy",
        fillcolor="rgba(34, 197, 94, 0.1)",
        hovertemplate=(
            f"{'Month %{x}' if x_col == 'month' else '%{x|%b %Y}'}<br>"
            f"Revenue: {currency_symbol}%{{y:,.2f}}<extra></extra>"
        ),
    ))

    return _apply_layout(fig, "Monthly Revenue Projection", x_col.title(), f"Revenue ({currency_symbol})")


def positional_uplift_chart(monthly_df: pd.DataFrame) -> go.Figure:
    """Baseline vs. uplifted traffic for positional forecast."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly_df["month"], y=monthly_df["baseline"],
        mode="lines", name="Baseline",
        line=dict(color="#94A3B8", dash="dash", width=2),
        fill="tozeroy", fillcolor="rgba(148,163,184,0.1)",
    ))
    fig.add_trace(go.Scatter(
        x=monthly_df["month"], y=monthly_df["traffic"],
        mode="lines+markers", name="With positional uplift",
        line=dict(color="#2563EB", width=3),
        fill="tonexty", fillcolor="rgba(37,99,235,0.15)",
    ))
    return _apply_layout(fig, "Positional Uplift Over Time", "Month", "Monthly Organic Sessions")


def combined_three_stream_chart(combined_df: pd.DataFrame) -> go.Figure:
    """Historical actuals + stacked baseline / positional / new-content forecast."""
    fig = go.Figure()

    actual_mask = combined_df["actual"].notna()
    fig.add_trace(go.Scatter(
        x=combined_df.loc[actual_mask, "date"],
        y=combined_df.loc[actual_mask, "actual"],
        mode="lines+markers", name="Historical actual",
        line=dict(color="#0F172A", width=3),
    ))

    fmask = combined_df["is_forecast"]
    fig.add_trace(go.Scatter(
        x=combined_df.loc[fmask, "date"], y=combined_df.loc[fmask, "baseline"],
        mode="lines", name="Baseline",
        line=dict(color="#94A3B8", dash="dash", width=2),
        stackgroup="stream", fillcolor="rgba(148,163,184,0.3)",
    ))
    fig.add_trace(go.Scatter(
        x=combined_df.loc[fmask, "date"], y=combined_df.loc[fmask, "positional_uplift"],
        mode="lines", name="Positional uplift",
        line=dict(color="#2563EB", width=2),
        stackgroup="stream", fillcolor="rgba(37,99,235,0.4)",
    ))
    fig.add_trace(go.Scatter(
        x=combined_df.loc[fmask, "date"], y=combined_df.loc[fmask, "new_content_uplift"],
        mode="lines", name="New content",
        line=dict(color="#22C55E", width=2),
        stackgroup="stream", fillcolor="rgba(34,197,94,0.4)",
    ))
    return _apply_layout(fig, "Combined Traffic Forecast", "Date", "Monthly Organic Sessions")


def aio_risk_chart(intent_breakdown: pd.DataFrame, ctr_penalty: float) -> go.Figure:
    """Grouped bar: traffic at risk vs projected loss by intent."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Traffic at risk",
        x=intent_breakdown["intent"], y=intent_breakdown["traffic"],
        marker_color="#EF4444",
    ))
    fig.add_trace(go.Bar(
        name=f"Projected loss ({ctr_penalty:.0f}%)",
        x=intent_breakdown["intent"], y=intent_breakdown["traffic_loss"],
        marker_color="#991B1B",
    ))
    fig.update_layout(barmode="group")
    return _apply_layout(fig, "AIO Impact by Keyword Intent", "Intent", "Sessions / month")
