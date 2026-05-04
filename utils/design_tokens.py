"""Design tokens — single source of truth for colours, spacing, and chart styling.

Import these instead of hard-coding hex values in chart functions or pages.
The primary colour matches .streamlit/config.toml primaryColor so buttons and
charts use the same brand blue.
"""
from __future__ import annotations

# ── Colour palette ────────────────────────────────────────────────────────────

# Primary: matches .streamlit/config.toml primaryColor = "#009BFF"
PRIMARY       = "#009BFF"
PRIMARY_DARK  = "#007ACC"

# Neutrals
SLATE_900     = "#0F172A"   # body text, "actual" data lines
SLATE_400     = "#94A3B8"   # secondary lines, baseline / do-nothing
SLATE_100     = "#F1F5F9"   # chart gridlines

# Semantic colours
SUCCESS       = "#22C55E"
WARNING_COLOR = "#F59E0B"
DANGER        = "#EF4444"
DANGER_ALT    = "#F97316"   # orange — paired with DANGER for colourblind safety
PURPLE        = "#8B5CF6"
ORANGE        = "#F97316"

# Intent colours (keyword intent classification)
INTENT_INFORMATIONAL  = "#3B82F6"
INTENT_COMMERCIAL     = "#10B981"
INTENT_TRANSACTIONAL  = "#F59E0B"
INTENT_NAVIGATIONAL   = "#8B5CF6"

# Scenario colours
SCENARIO_CONSERVATIVE = "#94A3B8"
SCENARIO_MODERATE     = "#009BFF"
SCENARIO_AGGRESSIVE   = "#10B981"

# Chart palette (for multi-line scenario / cadence comparisons)
CHART_PALETTE = [PRIMARY, PURPLE, ORANGE, SUCCESS, DANGER, WARNING_COLOR]

# ── Fill opacities (semantic) ─────────────────────────────────────────────────
FILL_SUBTLE = 0.10   # confidence bands, light area fills
FILL_MEDIUM = 0.25   # secondary area fills
FILL_STRONG = 0.40   # primary stacked area fills

# ── Typography ────────────────────────────────────────────────────────────────
FONT_FAMILY          = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_SIZE_ANNOTATION = 14   # chart annotation text

# ── Line weights (semantic hierarchy) ────────────────────────────────────────
LINE_THICK  = 3   # primary / actual data
LINE_NORMAL = 2   # forecast lines, secondary
LINE_THIN   = 1   # invisible fill-bounding traces

# ── Chart layout ──────────────────────────────────────────────────────────────
# Bottom margin accommodates the horizontal legend at y=-0.25
CHART_MARGIN = dict(l=60, r=20, t=45, b=70)

# Keyword bar chart dynamic height
BAR_HEIGHT_PER_ROW = 25   # px per keyword row
BAR_HEIGHT_MIN     = 400
BAR_HEIGHT_MAX     = 1200


def rgba(hex_color: str, alpha: float) -> str:
    """Convert a hex colour + alpha to an rgba() string for Plotly fills."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
