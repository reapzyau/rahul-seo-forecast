import streamlit as st

st.set_page_config(
    page_title="About",
    page_icon="ℹ️",
    layout="wide",
)

st.title("ℹ️ About & Methodology")

st.markdown("""
## What is this?

The **SEO Traffic & Revenue Forecasting Engine** is a data-driven tool built by
**Pattern Digital** for e-commerce and retail SEO teams. It turns GA4 organic exports
and SEMrush keyword rankings into defensible 12-month traffic and revenue projections,
formatted to drop directly into a multi-channel media plan.

## Forecast Streams

| Stream | Input | Method |
|--------|-------|--------|
| Historical baseline | GA4 organic sessions | Holt's exponential smoothing / Prophet |
| Positional uplift | SEMrush rankings | Monte Carlo — 500 trials, P10 / P50 / P90 bands |
| New content | Gap-analysis keyword list | Probabilistic ranking by domain authority vs. KD |
| Combined | All three streams | `baseline + positional + new_content − decay` |

## Key Assumptions

- **CTR curve** — industry-standard SERP click distribution by position
- **GA4 anchoring** — SEMrush traffic estimates (typically 20–40% higher than actuals)
  are rescaled so month-1 matches the real GA4 baseline
- **Movement statistics** — per-tier keyword movement rates learned from portfolio history;
  tiers with < 10 samples fall back to baseline gain rates
- **AIO penalties** — applied per-keyword at the CTR computation step (not post-hoc)
- **Seasonality** — applied per-stream using GA4-learned monthly modifiers

## Output Format

The 3-scenario forecast grid (Conservative / Moderate / Aggressive) matches the SEO row
of the Pattern multi-channel plan: monthly columns grouped as Forecast / Actual / % Var,
with rows for Traffic / Transactions / Revenue.

## Links

- GitHub repository: [github.com/rsen-pattern/SEO-Forecast](https://github.com/rsen-pattern/SEO-Forecast)
- Full methodology: see `methodology.md` in the repository root
""")
