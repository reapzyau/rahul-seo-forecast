# UI/UX Audit — SEO Traffic & Revenue Forecasting Engine

**Auditor:** Claude Code (Senior Product Designer + Frontend Engineer + Accessibility Specialist role)  
**Date:** 2026-05-04  
**Stack:** Streamlit 1.32+, Python 3.x, Plotly 5.x, no external CSS framework, no component library

---

## 1. Executive Summary

This is a capable, functionally rich analytical tool that handles a genuinely complex domain with reasonable clarity. The data pipeline, assumptions system, and scenario engine are well-thought-out. However, the UI layer carries significant technical debt: the primary colour in `config.toml` (`#009BFF`) and the primary colour used in every chart (`#2563EB`) are two completely different blues that have never been reconciled, meaning the app has a split visual identity it has never resolved. Beyond that, several pages will crash silently if opened without prerequisite data, the chart library has no design-token contract (30+ raw hex values), and the home page still describes a generic "upload a CSV" workflow that bears no resemblance to the real three-tab data ingestion flow. The single highest-value fix is unifying the colour system; the second is adding `st.stop()` guards to four pages that currently execute into broken state.

---

## 2. Top 10 Issues (Prioritised)

| # | Issue | Severity | Effort | Impact | File(s) |
|---|-------|----------|--------|--------|---------|
| 1 | Split colour identity: theme primary `#009BFF` vs chart primary `#2563EB` — two different blues, everywhere | Critical | S | High | `.streamlit/config.toml:3`, `utils/chart_builder.py:36,106,162,182,261,278,283,285,304,310,312` |
| 2 | Pages 7, 8, 9, 10 lack `st.stop()` after prerequisite warnings — execution falls through into broken code paths | Critical | S | High | `pages/7_Diagnostics.py`, `pages/8_Roadmap.py`, `pages/9_Deliverables.py`, `pages/10_Forecast_Dashboard.py` |
| 3 | `aio_risk_chart()` has no `hovertemplate` on either Bar trace — inconsistent with every other chart | High | S | Med | `utils/chart_builder.py:350-358` |
| 4 | No design-tokens file — ~30 unique hex values scattered across chart functions, no single source of truth | High | M | High | `utils/chart_builder.py` (entire file) |
| 5 | Inconsistent fill-area opacities: 0.1, 0.15, 0.3, 0.4 mixed without semantic rationale | High | S | Med | `utils/chart_builder.py:38,142,202,279,285,307,313,319,334,341` |
| 6 | Revenue opt-in inconsistency: pages 3/4/5 gate it behind a checkbox; page 6 enables it by default with no explanation | High | S | Med | `pages/3_Historical_Forecast.py`, `pages/6_Combined_Forecast.py` |
| 7 | Home page `app.py` still describes a generic CSV-upload workflow that doesn't match the real product flow | High | S | High | `app.py:14-38` |
| 8 | `label_visibility="collapsed"` on all 7+ assumption override widgets — removes every visible label | High | S | Med | `utils/assumptions_panel.py:189,201,214,226,237,246,263,275` |
| 9 | `keyword_schedule_chart` hover template swaps x/y axis order vs every other chart | Medium | S | Low | `utils/chart_builder.py:76` |
| 10 | Page 4 re-computes movement stats twice per run (preview + button press) — 500-trial MC doubles its cost | Medium | S | Med | `pages/4_Positional_Forecast.py` |

---

## 3. Detailed Findings

### A. Visual Design & Hierarchy

**✅ What's working**
- Streamlit theme in `config.toml` is sensible: light base, dark text (`#0F172A`), clean white background.
- `_apply_layout()` in `chart_builder.py` provides a genuine shared baseline — legend position, grid colour, hover mode, margins all come from one dict. This is the right instinct.
- `TIER_COLORS` in `engine/constants.py` is the one example of a centralised colour constant; it's imported correctly in `chart_builder.py:4`.
- Metric cards using `st.columns` + `st.metric` give consistent KPI presentation within individual pages.

**⚠️ What's broken or weak**

**The blue split.** The app has two primary blues that have never been unified:
```
# .streamlit/config.toml:3
primaryColor = "#009BFF"   # Streamlit buttons, widgets, links

# utils/chart_builder.py:36, 162, 182, 261, 278, 283, 285…
line=dict(color="#2563EB", …)   # every chart trace
```
Every button and interactive widget is one blue; every chart line is a noticeably different blue. Users perceive these as two separate brands in one UI.

**30+ unique hex values, no token file.** Counting distinct values in `chart_builder.py` alone: `#0F172A`, `#94A3B8`, `#F1F5F9`, `#2563EB`, `#8B5CF6`, `#F97316`, `#22C55E`, `#EF4444`, `#EAB308`, `#991B1B`, plus the rgba variants of each. None are named constants.

**Inconsistent fill opacities.** The same `#2563EB` blue fills appear at four different alpha values with no semantic logic:
- `rgba(37, 99, 235, 0.1)` — confidence bands (`chart_builder.py:38,142`)
- `rgba(37, 99, 235, 0.15)` — uplift shading (`chart_builder.py:202,285`)
- `rgba(37, 99, 235, 0.4)` — stacked areas (`chart_builder.py:313`)

**Metric card layouts are not standardised.** Each page defines its own column count and metric set:
- Page 3: 4 columns (Months, Latest, Avg, Range)
- Page 4: 4 columns (Baseline, Projected, P50 Uplift, Uplift %)
- Page 5: 4 columns (Total Visits, Peak Traffic, Peak Month, Keywords Ranking)
- Page 6: 4 columns (Baseline End, Combined End, Positional, Uplift %)
- Strategy page: 3 + 3 column split

There is no "Traffic / Revenue / Uplift / Confidence" north star — each page is its own invention.

**💡 Recommendations**

Before/after — colour tokens:
```python
# utils/design_tokens.py  (new file, proposed)
# Palette
PRIMARY      = "#009BFF"   # match config.toml — one source of truth
PRIMARY_DARK = "#0077CC"
SLATE_900    = "#0F172A"
SLATE_400    = "#94A3B8"
SLATE_100    = "#F1F5F9"
SUCCESS      = "#22C55E"
WARNING      = "#F59E0B"
DANGER       = "#EF4444"
DANGER_DARK  = "#991B1B"
PURPLE       = "#8B5CF6"
ORANGE       = "#F97316"

# Fill opacities — semantic names
FILL_SUBTLE  = 0.1   # confidence bands
FILL_MEDIUM  = 0.25  # secondary fill
FILL_STRONG  = 0.4   # stacked areas

def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
```

Then in `chart_builder.py`:
```python
# Before
line=dict(color="#2563EB", width=3)
fillcolor="rgba(37, 99, 235, 0.1)"

# After
from utils.design_tokens import PRIMARY, rgba, FILL_SUBTLE
line=dict(color=PRIMARY, width=3)
fillcolor=rgba(PRIMARY, FILL_SUBTLE)
```

Also update `.streamlit/config.toml` — or update `design_tokens.PRIMARY` to match. Pick one blue and apply it everywhere.

---

### B. Interaction & Microcopy

**✅ What's working**
- "Run All Forecasts" on the Strategy page is a clear, action-oriented primary button.
- Help text (`help=` parameter) is used consistently on most sidebars in pages 3–5.
- Error messages generally identify what went wrong ("Could not parse the uploaded GA4 file. Please check the format.").
- `st.spinner("Running three scenarios…")` labels are descriptive enough.

**⚠️ What's broken or weak**

**Home page describes the wrong product.** `app.py:30-37` reads:
```
1. Upload a CSV with your keyword or traffic data (or use the built-in sample data)
2. Configure settings in the sidebar
3. Click Generate Forecast to see your projections
4. Export results as CSV or an interactive HTML report
```
The actual flow has three tabs (GA4, SEMrush, Roadmap), no sidebar configuration on the upload page, a "Run All Forecasts" button not "Generate Forecast", and the primary export is XLSX not CSV. A new user following these instructions will be lost within 30 seconds.

**Page 5 sidebar header is wrong.** `pages/5_New_Content_Forecast.py` sidebar header reads "Keyword Forecast Settings" — every other page uses "X Forecast Settings" matching the page name. This one is the odd one out.

**"Apply" button repeated 7 times identically** in `utils/assumptions_panel.py:191,202,215,227,238,247,277` with no variation in label — users cannot tell which "Apply" applies to what when they're in the same scrolled view.

**Revenue is not clearly optional on page 6.** Page 6 enables revenue projection by default with a checkbox, but pages 3, 4, 5 gate it behind an expander. Users who didn't enable revenue on page 3 may not realise page 6 is showing revenue numbers derived from different (less accurate) sources.

**Empty states are inconsistent.** Page 7 shows `st.info("Upload SEMrush data…")` but continues rendering tabs and empty charts below it. Pages 3–5 gate cleanly with `st.stop()`. The result on page 7 is a confusing page with partially visible (but empty) charts beneath the info message.

**💡 Recommendations**

Rewrite `app.py:30-37`:
```python
st.markdown("""
### Getting Started

1. **Data Upload (page 1)** — Upload your GA4 export, SEMrush keyword positions, and an optional roadmap.
2. **Strategy (page 2)** — Review the portfolio diagnosis, adjust the three scenario presets, and click **Run All Forecasts**.
3. **Deliverables (page 9)** — Download the three-scenario forecast grid XLSX, ready to paste into your multi-channel plan.

Deep-dive pages (3–8) are available for per-stream analysis and diagnostics.
""")
```

Fix the "Apply" problem — prefix each button label with the field name:
```python
# Before
st.button("Apply", key=f"apply_{key}", use_container_width=True)

# After
label = meta.label if hasattr(meta, 'label') else key.replace('_', ' ').title()
st.button(f"Apply {label}", key=f"apply_{key}", use_container_width=True)
```

---

### C. Accessibility (WCAG 2.2 AA)

**✅ What's working**
- Streamlit's default widget rendering uses semantic HTML under the hood — `<button>`, `<input>`, `<label>` are rendered correctly by the framework.
- Plotly hover tooltips use `<extra></extra>` to suppress default trace name duplication — cleaner screen reader output.
- The `_PROVENANCE_BADGE` system uses Streamlit's badge syntax which includes text, not just colour.

**⚠️ What's broken or weak**

**All override widget labels are hidden.** `utils/assumptions_panel.py:189,201,214,226,237,246,263,275` all use `label_visibility="collapsed"`. This pattern relies entirely on visual column position to communicate what each widget controls. A screen reader user or keyboard-only user navigating the assumptions panel hits 7+ unlabelled inputs with no context.

```python
# utils/assumptions_panel.py:189 — current
new_text = st.text_area(
    "Override (one per line)", value=terms_text, key=widget_key,
    label_visibility="collapsed", height=80,
)

# Fix: keep the label visible or use aria_label equivalent
new_text = st.text_area(
    f"Override {row['label']} (one per line)",
    value=terms_text, key=widget_key,
    height=80,
)
```

**`aio_risk_chart` uses two near-identical reds** — `#EF4444` and `#991B1B` — to distinguish "traffic at risk" from "projected loss". These are indistinguishable under deuteranopia and protanopia. The difference will be invisible to ~8% of male users.

```python
# utils/chart_builder.py:353,358 — current
marker_color="#EF4444"   # traffic at risk
marker_color="#991B1B"   # projected loss

# Fix: use red + orange, or red + hatching
marker_color="#EF4444"
marker_color="#F97316"   # orange — distinguishable for all colour vision types
```

**Colour-only provenance system.** `render_assumptions_banner()` reports "N detected · M overridden · P defaults" but the provenance badges in the detail panel use colour alone (grey/blue/green) with no icon or pattern fallback. The text labels ("defaulted", "detected", "overridden") do appear in the badge text, so this is a medium concern rather than critical.

**Font family is too generic.** `chart_builder.py:9`: `font=dict(family="sans-serif")` — this resolves differently across browsers and operating systems. On Windows this often renders as Arial; on macOS as Helvetica; on Linux as DejaVu Sans. None are bad, but the inconsistency is avoidable.

```python
# Before
font=dict(family="sans-serif", color="#0F172A")

# After
font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif", color="#0F172A")
```

**Plotly charts have no text description for screen readers.** Streamlit does not expose chart `alt` text directly, but `st.plotly_chart` accepts `config` which can include `displayModeBar` settings. Consider adding `st.caption()` with a text summary immediately after every `st.plotly_chart()` call for the two or three most important charts.

**💡 Recommendations**
1. Remove `label_visibility="collapsed"` from all override widgets in `assumptions_panel.py` — or restructure the layout so the column header acts as the label.
2. Replace the two-red AIO chart with red + orange (`#EF4444` / `#F97316`).
3. Add a brief `st.caption()` below the Combined chart on the Strategy page describing the P50 end value.

---

### D. Responsive & Mobile

**⚠️ What's broken or weak**

Streamlit's layout model gives limited responsive control. Most issues here are Streamlit framework constraints, but some are addressable.

**Fixed 4-column metric grids will collapse poorly on narrow screens.** `pages/1_Data_Upload.py:116` uses `st.columns(4)` for KPI cards. On Streamlit's mobile breakpoint (~640px) these compress to tiny widths. There is no fallback to 2-column or 1-column.

**The assumptions panel 4-column layout** (`utils/assumptions_panel.py:153`: `st.columns([3, 2, 2, 3])`) will be unreadable on small screens — 10-character-wide columns.

**The Strategy page 3-column scenario editor** has 7 widgets per column, making the page extremely long and scroll-heavy even on desktop.

**💡 Recommendations**
- For the scenario editor, consider collapsing to `st.expander` per scenario on mobile, or reducing the widget count by moving secondary controls (position range) to an "Advanced" expander.
- For metric cards, 3 columns are safer than 4 for Streamlit's responsive behaviour.

---

### E. Performance & Frontend Hygiene

**✅ What's working**
- All heavy forecast computation is correctly gated behind `st.button` + `st.session_state`. No inline computation on every rerun.
- Roadmap AI extraction has a proper cache (`ROADMAP_AI_CACHE` keyed by `compute_cache_key`).
- Page imports are clean — no redundant libraries.

**⚠️ What's broken or weak**

**Movement stats computed twice on page 4.** The positional forecast page calls `learn_movement_from_history(kw_df)` once for the preview/sidebar display and again inside the button handler. With a 10,000-keyword portfolio this is a non-trivial redundant operation. Store the result in session state after first computation.

**`from collections import Counter` imported inside a code block** at `pages/1_Data_Upload.py:369`:
```python
# Current — runs on every Streamlit rerun inside the with tab_semrush: block
from collections import Counter
detected_domain = Counter(domains).most_common(1)[0][0]

# Fix: move import to top of file
from collections import Counter
```

**`from engine.revenue_engine import CURRENCY_SYMBOLS` imported inside a function** at `utils/assumptions_panel.py:234`. This is a module-level import inside a runtime function — deferred imports like this hide dependency graphs and slow the first call.

**`keyword_schedule_chart` height grows unbounded** at `chart_builder.py:81`:
```python
height=max(400, len(df) * 25)
```
For a 200-keyword portfolio this renders a 5,000px tall chart. Cap it:
```python
height=min(1200, max(400, len(df) * 25))
```

**💡 Recommendations**
```python
# pages/4_Positional_Forecast.py — cache movement stats
if "movement_stats" not in st.session_state:
    st.session_state["movement_stats"] = learn_movement_from_history(kw_df)
movement_stats = st.session_state["movement_stats"]
```

---

### F. Information Architecture & Flow

**✅ What's working**
- The numbered sidebar pages (1–12) give a clear sequential reading. Pages 1→2→9 is the "express" path for clients; it's discoverable.
- The Strategy page correctly positions itself as the orchestrator with a "Run All Forecasts" CTA.
- The `setup_page()` helper enforces consistent header + caption + assumptions banner structure.

**⚠️ What's broken or weak**

**Page 10 (Forecast Dashboard) is a dead end.** It embeds a static HTML file (`assets/Forecast System.html`) with no Streamlit controls, no connection to current session data, no export, and no explanation of its relationship to the live forecasts. There is no error handling — if the file doesn't exist, the page silently renders nothing.

**Pages 11 and 12 are navigation dead ends.** "Data Sources" and "About" are informational pages with no next action. At minimum, each should include a "Go to Data Upload →" link.

**The flow from Strategy → Deliverables is implicit.** After "Run All Forecasts" there is a download button on the Strategy page and a separate, more capable export on the Deliverables page. Nothing tells the user these are related. The Strategy page caption for the download button reads "For deeper customisation… use the Deliverables page" — this is the right instinct but buried at the bottom.

**Deep-dive pages (3–6) duplicate the Strategy flow** without making it clear what incremental value they offer over the Strategy run. The distinction (deep-dive vs. quick scenario) is only explained in one line of caption text on the Strategy page.

**💡 Recommendations**
- Add `st.link_button("Continue to Deliverables →", "9_Deliverables")` at the bottom of the Strategy page after the download button.
- Add `st.info("No current session data — go to Data Upload to get started.", icon="ℹ️")` + `st.stop()` to pages 10 and 11 when prerequisites are missing.
- Consider renaming page 10 "Forecast Dashboard" to something that makes its purpose clear, or remove/replace it with a live summary derived from session state.

---

### G. Code-Level UI Smells

**⚠️ What's broken or weak**

**Magic numbers in chart layout.** `chart_builder.py:12`:
```python
margin=dict(l=60, r=20, t=40, b=60)
```
These are arbitrary. The right margin `r=20` is asymmetric with no justification. The bottom margin `b=60` is large because the legend is at the bottom (`y=-0.2`) but this is not documented. Any future change to legend position will silently break the margin relationship.

**Magic `25` in dynamic chart height.** `chart_builder.py:81`:
```python
height=max(400, len(df) * 25)
```
Why 25 pixels per keyword? No comment, no rationale.

**Annotation font hardcoded.** `chart_builder.py:61`:
```python
fig.add_annotation(text="No keywords expected to rank", showarrow=False, font=dict(size=16))
```
`size=16` chosen arbitrarily; no relation to the typography system.

**Duplicate Apply boilerplate.** `utils/assumptions_panel.py:191,202,215,227,238,247,277` — seven structurally identical blocks:
```python
if st.button("Apply", key=f"apply_{key}", use_container_width=True):
    if new_val != default_val:
        override_assumption(store, key, new_val, source="manual override")
        st.rerun()
```
This should be a helper function. Any change to the override pattern (e.g., adding confirmation, changing the label) must be made 7 times.

**`hovermode="x unified"` in `_LAYOUT_DEFAULTS`** is a good default for time-series line charts but is inappropriate for bar charts (AIO risk, position distribution) where it creates confusing vertical crosshair behaviour. Override `hovermode="closest"` for non-time-series charts.

```python
# utils/chart_builder.py:347 — aio_risk_chart
# After applying _apply_layout, override hovermode
fig = _apply_layout(fig, "AIO Impact by Keyword Intent", "Intent", "Sessions / month")
fig.update_layout(hovermode="closest")   # bar chart — override unified hover
return fig
```

**Inconsistent trace naming capitalisation.** Some traces use title case ("Historical Actual", "Baseline Revenue"), others use sentence case ("With positional uplift", "New content"). Compare `chart_builder.py:104` ("Actual") vs `chart_builder.py:171` ("Baseline (no new content)") vs `chart_builder.py:298` ("Historical actual").

---

### H. Dark Mode / Theming

**⚠️ What's broken or weak**

The app uses Streamlit's light theme exclusively (`base = "light"` in `config.toml`). There is no dark mode. This is fine as a product decision, but it is not stated anywhere as intentional. If a user forces dark mode via their OS, Plotly charts will still render with white backgrounds while Streamlit's UI shifts to dark — the charts will look like embedded light-mode islands in a dark page.

This is a known Streamlit limitation, not a bug in this codebase. The mitigation is to ensure `plot_bgcolor="white"` and `paper_bgcolor="white"` are always set — which `_LAYOUT_DEFAULTS` already does. No action required unless dark mode is planned.

---

### I. Trust, Polish & Delight

**✅ What's working**
- Page icon is set (`page_icon="\U0001f4c8"`) — a chart emoji, appropriate.
- Page title is "SEO Traffic Forecast" — clear.
- The assumptions provenance system (defaulted/detected/overridden) is a genuinely trustworthy feature. Showing users exactly which values were inferred from their data vs. assumed builds confidence in the forecast.
- `st.success()` feedback after brand terms are saved ("Saved. 42 branded / 312 total keywords (13.5%)") is specific and reassuring.
- AI model cost estimate (`~A$0.003 estimated session AI cost`) is a strong trust signal.

**⚠️ What's broken or weak**

**No favicon beyond the emoji.** The emoji page icon is fine for browser tabs but there's no OG image, no meta description, and no site `<title>` beyond the page-level title. These matter if the app is ever shared via link.

**The methodology page lives at the bottom of page 9** in a tab labelled "Methodology". It is not discoverable without already knowing it exists. Given this is a client-facing tool where methodology trust is critical, it deserves more prominent placement.

**P10/P90 confidence bands are not consistently explained.** The positional forecast shows P10/P50/P90 bands. Page 4 explains this in a sidebar `help=` tooltip. Page 6 references "P50 (median scenario)" in a label. The Strategy page uses "P50" without definition. Users who land on the Strategy page first encounter unexplained acronyms.

**The "Seasonality Tuning" section** on the Data Upload page appears below the tab structure as a loose section at the bottom of the page (`pages/1_Data_Upload.py:856`), outside of all three tabs. This makes it structurally disconnected from the GA4 tab where seasonality is detected. It should live inside the GA4 tab.

**💡 Recommendations**
- Move "Seasonality Tuning" inside `tab_ga4` on the Data Upload page, directly after the traffic chart.
- Add a one-sentence definition of P10/P50/P90 to the Strategy page above the scenario comparison chart: `st.caption("Bands show Monte Carlo uncertainty: P10 = pessimistic, P50 = median, P90 = optimistic.")`
- Surface the methodology link in the app.py home page.

---

## 4. Design System Recommendations

The app needs a single-file design token module. This addresses issues 1, 4, and 5 simultaneously.

**Proposed `utils/design_tokens.py`:**

```python
"""Design tokens — single source of truth for colours, typography, spacing, chart layout."""

# ── Colour palette ────────────────────────────────────────────────────────────
# Primary: match .streamlit/config.toml primaryColor
PRIMARY        = "#009BFF"
PRIMARY_DARK   = "#007ACC"
PRIMARY_BG     = "#E6F5FF"   # 10% tint for fill areas

# Neutrals
SLATE_900      = "#0F172A"   # body text, "actual" data lines
SLATE_400      = "#94A3B8"   # secondary lines, baseline/do-nothing
SLATE_100      = "#F1F5F9"   # chart gridlines

# Semantic colours
SUCCESS        = "#22C55E"
SUCCESS_BG     = "#DCFCE7"
WARNING        = "#F59E0B"
DANGER         = "#EF4444"
DANGER_ALT     = "#F97316"   # orange — use instead of dark red for colourblind safety
PURPLE         = "#8B5CF6"

# Intent colours (keyword intent classification)
INTENT_INFORMATIONAL  = "#3B82F6"
INTENT_COMMERCIAL     = "#10B981"
INTENT_TRANSACTIONAL  = "#F59E0B"
INTENT_NAVIGATIONAL   = "#8B5CF6"

# ── Fill opacities (semantic) ────────────────────────────────────────────────
FILL_SUBTLE  = 0.10   # confidence bands, light backgrounds
FILL_MEDIUM  = 0.25   # secondary area fills
FILL_STRONG  = 0.40   # primary stacked area fills

# ── Typography ───────────────────────────────────────────────────────────────
FONT_FAMILY    = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_SIZE_ANNOTATION = 14   # chart annotations (was hardcoded 16)

# ── Chart spacing ─────────────────────────────────────────────────────────────
# Margin note: bottom=70 accommodates horizontal legend at y=-0.25
CHART_MARGIN   = dict(l=60, r=20, t=45, b=70)
BAR_HEIGHT_PER_ROW = 25   # px per keyword in horizontal bar charts
BAR_HEIGHT_MIN     = 400
BAR_HEIGHT_MAX     = 1200

# ── Line weights (semantic hierarchy) ────────────────────────────────────────
LINE_THICK   = 3   # primary / actual data
LINE_NORMAL  = 2   # forecast lines
LINE_THIN    = 1   # invisible fill-bounding lines


def rgba(hex_color: str, alpha: float) -> str:
    """Convert hex + alpha to rgba string for Plotly fill colours."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
```

**Migrate `chart_builder.py` to use tokens.** The entire file is ~40 chart traces; replacing raw hex strings with token names takes roughly one hour and touches every function. The result is a file where color intent is self-documenting:

```python
# Before
line=dict(color="#2563EB", width=3),
fillcolor="rgba(37, 99, 235, 0.1)",

# After
from utils.design_tokens import PRIMARY, LINE_THICK, rgba, FILL_SUBTLE
line=dict(color=PRIMARY, width=LINE_THICK),
fillcolor=rgba(PRIMARY, FILL_SUBTLE),
```

**Update `.streamlit/config.toml`** to match `design_tokens.PRIMARY`:
```toml
[theme]
primaryColor = "#009BFF"   # already matches — keep
```
Or change `design_tokens.PRIMARY` to `"#009BFF"` — but do not have two different values.

---

## 5. Quick Wins

Changes achievable in under one hour each, ordered by impact:

- [ ] **Fix home page copy** (`app.py:14-38`) — rewrite the "Getting Started" section to describe the real flow: Data Upload → Strategy → Deliverables. Current text describes a fictional generic tool.
- [ ] **Add `st.stop()` after prerequisite warnings on pages 7, 8, 9, 10** — four single-line additions that prevent silent crash-through. Search for `st.info(` or `st.warning(` followed by missing-data messages and add `st.stop()` immediately after.
- [ ] **Add hover templates to `aio_risk_chart`** (`chart_builder.py:350-358`) — two `hovertemplate=` parameters, 10 minutes of work, makes the AIO chart consistent with everything else.
- [ ] **Fix `keyword_schedule_chart` hover template** (`chart_builder.py:76`) — change `"%{y}<br>Traffic: %{x:,.0f}"` to `"%{y}<br>Traffic: %{x:,.0f}<extra></extra>"` and verify axes are labelled consistently with other charts.
- [ ] **Cap keyword bar chart height** (`chart_builder.py:81`) — change `max(400, len(df) * 25)` to `min(1200, max(400, len(df) * 25))` to prevent unbounded 5,000px charts.
- [ ] **Move `from collections import Counter` to top of file** (`pages/1_Data_Upload.py:369`) and move `from engine.revenue_engine import CURRENCY_SYMBOLS` out of `_render_override_widget` (`assumptions_panel.py:234`).
- [ ] **Add `hovermode="closest"` override on bar charts** (AIO risk, position distribution) — `_LAYOUT_DEFAULTS` uses `"x unified"` which creates confusing crosshairs on bar charts. One line per bar chart.
- [ ] **Replace `#991B1B` dark red in `aio_risk_chart`** with `#F97316` orange (`chart_builder.py:358`) for colourblind safety.
- [ ] **Move "Seasonality Tuning" section** into the GA4 tab on the Data Upload page (`pages/1_Data_Upload.py:856`) — it is currently structurally disconnected from the tab where seasonality is detected.
- [ ] **Add P10/P50/P90 definition** to Strategy page above the scenario comparison chart — one `st.caption()` line preventing analyst embarrassment when clients ask.

---

## 6. Larger Initiatives

### 6.1 — Introduce `utils/design_tokens.py` and migrate chart colours (Effort: M, ~4 hours)
**Rationale:** The split colour identity (config blue vs chart blue) is the most visually obvious quality issue. Until this is fixed, every chart is a reminder that the UI layer was never finished. The token file proposed in Section 4 provides the scaffold; migrating `chart_builder.py` (the primary consumer, ~360 lines) to import from it completes the work. This is not a visual redesign — just making the existing choices consistent and maintainable.

**Scope:** `utils/design_tokens.py` (new), `utils/chart_builder.py` (full migration), `.streamlit/config.toml` (verify primary colour matches).

### 6.2 — Consolidate the `_render_override_widget` pattern (Effort: S–M, ~2 hours)
**Rationale:** The 7× repeated Apply boilerplate in `utils/assumptions_panel.py` makes every future change to the override UX a 7-file hunt. Extract the pattern to a single `_apply_override_button(store, key, meta, new_val, current_val)` helper. This also enables adding a single improvement (e.g., button label that names the field) uniformly.

**Scope:** `utils/assumptions_panel.py` only.

### 6.3 — Standardise metric card layout across forecast pages (Effort: M, ~3 hours)
**Rationale:** Each forecast page invents its own KPI card set. A `utils/metric_cards.py` module with a `render_forecast_kpis(baseline_end, combined_end_p50, uplift_pct, confidence_note)` function would give every page the same vocabulary. Users moving page-to-page would see consistent signal instead of learning a new dashboard on each page.

**Scope:** `pages/3_Historical_Forecast.py`, `pages/4_Positional_Forecast.py`, `pages/5_New_Content_Forecast.py`, `pages/6_Combined_Forecast.py`, new `utils/metric_cards.py`.

### 6.4 — Rethink or replace page 10 (Forecast Dashboard) (Effort: M, ~3 hours)
**Rationale:** Page 10 embeds a static HTML file that has no connection to live session data. It either needs to become a live summary dashboard built from `st.session_state[SCENARIO_RESULTS]` (a genuinely useful executive view), or it should be removed. As it stands, it's the one page in the app that is guaranteed to show stale data regardless of what the user uploaded.

**Scope:** `pages/10_Forecast_Dashboard.py`, potentially a new `utils/dashboard_builder.py`.

---

## 7. Out of Scope / Open Questions

1. **Page 10 intent.** `assets/Forecast System.html` — is this a client-facing deliverable document, a historical mockup, or a live product? The code at `pages/10_Forecast_Dashboard.py` reads it and renders it in an iframe. If it is a client deliverable, should it be generated dynamically from session state rather than served as a static file?

2. **AU retail seasonality default.** The default seasonality preset is explicitly Australian retail (`seasonality_engine.py`). The product is deployed as a general tool. Is this intentional (Pattern agency is AU-based) or should the default be unlabelled generic? If the former, it should be more prominently disclosed in the UI ("Defaults are calibrated for Australian retail — change Industry in Assumptions to adjust").

3. **`strategy_restart_month` UX.** The assumptions panel offers a "strategy restart month" control with 36 options as a selectbox. This is a forecasting concept that will be opaque to most end-users. Is there intended documentation for this? Should it be gated behind an "Advanced" toggle?

4. **Page 9 Deliverables — variance grading.** The Deliverables page has a "Variance Analysis" tab that allows uploading a previous forecast snapshot for grading. This is a genuinely sophisticated feature but there is no hint of it anywhere in the navigation flow. Is it intended for internal analyst use only? Should it be surfaced more prominently, or intentionally buried?

5. **`pages/12_About.py`** describes the forecast methodology in detail. Is this intended for end-clients or internal analysts? The answer affects how it should be positioned in the navigation (currently last, numbered 12).

6. **Emoji inconsistency in tab labels.** Some tabs use `"\U0001f4ca"` (Unicode escape) and others may use raw emoji characters. Is there a style guide preference, or should all be standardised to raw emoji (`📊`) for readability in source?
