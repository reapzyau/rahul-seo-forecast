# SEO Forecasting Methodology

This document describes the models and assumptions used by each forecasting mode.

---

## Mode 1: Keyword-Based Forecast

The keyword forecast projects traffic from a list of target keywords based on your domain authority, keyword difficulty, and content production cadence.

### Step 1: Classify Keyword Difficulty

Each keyword is assigned a difficulty tier based on its KD score:

| KD Range | Tier |
|----------|------|
| 0–20 | Easy |
| 21–40 | Moderate |
| 41–60 | Hard |
| 61–80 | Very Hard |
| 81–100 | Extreme |

### Step 2: Calculate Efficiency Score

Keywords are prioritised by **efficiency score**, which balances search volume against difficulty:

```
efficiency_score = volume / (kd + 1)
```

Higher efficiency keywords (high volume, low difficulty) are published first.

### Step 3: Ranking Probability

The probability of ranking for a keyword depends on the gap between your Domain Authority (DA) and the keyword's difficulty (KD):

```
probability = clamp((DA - KD + 50) / 100, 0.05, 0.95)
```

- If DA >> KD, probability approaches 0.95
- If DA << KD, probability approaches 0.05
- A seeded random number determines whether each keyword actually ranks

### Step 4: Expected Position

For keywords that pass the ranking check, position is determined by the DA-KD gap:

| DA-KD Gap | Position Range |
|-----------|---------------|
| +30 or more | 1–3 |
| +15 to +29 | 2–5 |
| 0 to +14 | 3–8 |
| -15 to -1 | 5–12 |
| -30 to -16 | 8–16 |
| Below -30 | 12–20 |

A seeded random number picks the exact position within each range.

### Step 5: Click-Through Rate (CTR)

CTR is based on SERP position using industry-average data:

| Position | CTR (%) |
|----------|---------|
| 1 | 22.0 |
| 2 | 13.0 |
| 3 | 9.0 |
| 4 | 6.5 |
| 5 | 4.5 |
| 6 | 3.2 |
| 7 | 2.5 |
| 8 | 2.0 |
| 9 | 1.6 |
| 10 | 1.3 |
| 11–14 | 0.8 |
| 15–20 | 0.3 |

### Step 6: Maturation S-Curve

Instead of a step function or linear ramp, traffic builds via a logistic (sigmoid) S-curve from the publish month:

```
progress(t) = 1 / (1 + exp(-k × (t - t_mid)))
```

`t` is the elapsed months since publication, `t_mid` is the month at which 50% of steady-state traffic is reached, and `k` controls how steeply the curve rises. Both the new-content and positional engines use this same curve shape — new-content uses `t_mid` per difficulty tier; positional uses the Monte Carlo time-to-move sample as the stochastic `t_mid`.

| Tier | t_mid (months) | k (steepness) |
|------|---------------|---------------|
| Easy | 2.5 | 1.8 |
| Moderate | 5.0 | 1.2 |
| Hard | 8.0 | 0.9 |
| Very Hard | 11.0 | 0.7 |
| Extreme | 13.0 | 0.5 |

Higher DA provides a small reduction to time-to-rank (via the stochastic TTR draw); the S-curve shape itself is tier-fixed.

The curve delivers roughly 10% of steady-state traffic by the first quarter of the ramp, ~50% at the midpoint, and ~80% by three-quarters — matching how organic traffic actually builds on a newly published or optimised page.

### Step 7: Traffic Estimation

For each keyword that passes the ranking check:

```
estimated_monthly_traffic = volume * (CTR / 100)
```

Traffic begins in the month the keyword ranks (publish month + time to rank).

### Step 8: Monthly Projection

The month-by-month projection sums all keywords whose traffic has started by that month. Keywords are published according to the cadence (e.g., 4 per month) in efficiency-score order.

---

## Mode 2: Historical Trend Forecast

The historical forecast uses your past traffic data to project future trends.

### v4 Data-Length Gating (run_historical_forecast_v4)

The v4 engine automatically selects the best model based on available data length:

| Data Length | Primary Model | Notes |
|------------|--------------|-------|
| ≥24 months | Prophet | Seasonal + holiday-aware; AU holidays applied |
| 12–23 months | Holt's Exponential Smoothing | Prophet attempted but flagged low-confidence |
| <12 months | Linear Regression | Seasonality cannot be detected; warns user |

The v4 function returns `result.attrs["chosen_method"]` and `result.attrs["method_reason"]` so the UI can display which model was chosen and why.

### Prophet & AU Holidays

Facebook Prophet is used as the primary model when ≥24 months of data are available. Configuration:

- `yearly_seasonality=True` — captures annual seasonal patterns
- `weekly_seasonality=False` — monthly data doesn't have weekly cycles
- `changepoint_prior_scale=0.05` — controls trend flexibility; exposed as a sidebar slider (0.001–0.5)
- Australian retail holidays are injected as a Prophet holiday DataFrame (see `engine/seasonality_engine.AU_HOLIDAYS`)

**AU Holidays included (2023–2028):**
- EOFY (June 30, window: -14 to +1)
- Click Frenzy May (3rd Tuesday of May, ±3 days)
- Click Frenzy November (2nd Tuesday of November, ±3 days)
- Black Friday (4th Friday of November, -2 to +3 days)
- Cyber Monday (Monday after Black Friday, ±1 day)
- Christmas (Dec 25, -10 to +2 days)
- Boxing Day Sales (Dec 26, 0 to +7 days)
- Back to School (Jan 28, ±7 days)

Prophet is an optional dependency. If not installed, the engine falls back to Holt's or linear gracefully.

### Linear Regression (legacy/fallback)

Fits a straight line to historical data using `numpy.polyfit` degree 1.

- **Confidence bands** are calculated as ± X% of the projected value (configurable, default 15%).
- Best for data with a clear upward or downward trend.

### Exponential Smoothing

Holt's linear trend method (double exponential smoothing) weights recent data more heavily:

```
smoothed[t] = alpha * actual[t] + (1 - alpha) * smoothed[t-1]
```

- **Alpha** (0.1–0.9) controls how much weight is given to recent data.
- Higher alpha = more reactive to recent changes.

### Simple Moving Average (SMA)

Averages the last N months (configurable window, default 3). For forecasting, each predicted value is fed back into the window.

### Growth Rates

The tool calculates:
- **Month-over-Month (MoM)**: `(current - previous) / previous * 100`
- **Year-over-Year (YoY)**: `(current - 12_months_ago) / 12_months_ago * 100`

---

## Mode 3: Combined Forecast

The combined forecast merges the historical baseline with keyword-based incremental traffic.

### Process

1. **Baseline**: Linear regression forecast from historical data (representing "what happens if we do nothing").
2. **Incremental**: Monthly traffic from the keyword engine (representing "what new content adds").
3. **Combined**: `baseline + incremental` for each future month.
4. **Uplift**: `(incremental / baseline) * 100` as a percentage.

This framing helps build a business case: the gap between baseline and combined represents the ROI of content investment.

---

## Revenue Projection

Revenue projection is available in all three modes and uses a simple conversion model:

```
leads = traffic * (conversion_rate / 100)
revenue = leads * average_order_value
```

- **Conversion Rate (CVR)**: Percentage of visitors who convert (default 2.5%).
- **Average Order Value (AOV)**: Revenue per conversion (default $100).
- Supports multiple currencies (USD, EUR, GBP, AUD, CAD).

---

## Search Intent Classification

Keywords are automatically classified by search intent using pattern matching:

| Intent | Signals | Example |
|--------|---------|---------|
| Informational | Question words (how, what, why), guide, tutorial, tips, definition | "how to improve site speed" |
| Transactional | buy, purchase, price, pricing, cost, discount, download, subscribe | "buy SEO tool subscription" |
| Commercial | best, top, review, comparison, alternative, tool, software, vs | "best SEO tools 2025" |
| Navigational | login, sign in, sign up, official, website | "google search console login" |

Keywords that match no pattern default to **commercial** (a safe assumption for SEO keyword lists).

### AI Traffic Adjustment

AI Overviews (Google's AI-generated answers) are increasingly answering informational queries directly in the SERP, reducing organic click-through rates for those keywords. The tool offers two ways to account for this:

1. **Exclude informational keywords** — removes them from the forecast entirely, modelling a strategy that avoids AI-vulnerable keywords.
2. **CTR penalty** — reduces CTR for informational keywords by a configurable percentage (e.g. 40% penalty means their CTR is multiplied by 0.6). This models partial traffic loss to AI Overviews.

### CTR Model Versions

Two CTR models are available:

| Model | Position 1 CTR | Position 5 CTR | Position 10 CTR | Positions 11-14 | Positions 15-20 |
|-------|---------------|---------------|----------------|-----------------|-----------------|
| Standard | 22.0% | 4.5% | 1.3% | 0.8% | 0.3% |
| AI-Adjusted | 16.0% | 3.5% | 1.0% | 0.5% | 0.2% |

The **AI-Adjusted** model reduces CTR by approximately 25-30% across all positions, reflecting the aggregate impact of AI Overviews, featured snippets, and other SERP features that reduce organic clicks.

### Forecast Scenarios

Three scenario multipliers adjust overall traffic estimates:

| Scenario | Multiplier | Use When |
|----------|-----------|----------|
| Conservative | 0.7x | Competitive niche, new domain, uncertain rankings |
| Moderate | 1.0x | Typical conditions (recommended default) |
| Aggressive | 1.3x | Strong domain, low competition, proven content track record |

---

## Mode 4: Positional Forecast

The positional forecast projects traffic uplift from moving keywords you **already rank for** up the SERP. Unlike new content forecasting, it uses real current positions from SEMrush.

### Step 1: Current position to target position

For each keyword, the engine looks at its current position and chooses a target position based on effort level and keyword difficulty tier. "Moderate" effort at a moderate KD might move a keyword from position 14 to position 8.

### Step 2: CTR lookup at target position

Uses the same CTR tables as the new content forecast (Standard or AI-Adjusted), looking up the CTR at the target position.

### Step 3: Traffic uplift calculation

```
baseline_traffic = volume * CTR_at_current_position / 100
new_traffic = volume * CTR_at_target_position / 100
uplift = new_traffic - baseline_traffic
```

Uplifts are summed across all keywords and distributed across months based on time-to-move (small moves for easy keywords start delivering in months 1-2; big moves on hard keywords ramp over 6-12 months).

### GA4 anchoring

When a GA4 baseline is provided, the engine rescales SEMrush's traffic estimates so the month-1 baseline equals real GA4 sessions. Without anchoring, SEMrush's traffic estimate is typically 20-40% higher than what GA4 actually reports.

### Data-Driven Movement

When SEMrush exports include a `previous_position` column, the positional engine learns per-tier movement stats from your actual history instead of using the static tier defaults:

```
movement = previous_position - position  (positive = improvement)
```

**Outlier filter:** movements greater than ±30 positions are discarded as likely SEMrush data glitches (e.g. a keyword jumping from position 80 to position 1 in one crawl).

**Minimum sample threshold:** a tier must have at least 10 valid samples before its learned mean replaces the default gain. Tiers with fewer than 10 samples fall back to `_BASE_GAIN_BY_TIER`. This prevents noisy statistics from a handful of keywords distorting the forecast.

The Positional Forecast page shows an info banner indicating whether learned stats or defaults are active, and reports the total sample count across all tiers.

---

## Mode 5: AI Overview Risk

Uses SEMrush's Position Type column. Keywords flagged as "AI overview" are considered AIO-affected; their current traffic is multiplied by the CTR penalty (default 40%) to estimate projected loss.

The analysis segments risk by keyword intent — informational keywords typically carry the highest AIO exposure because AIO summaries compete most directly with informational content.

Recommendations are generated based on exposure percentage:
- < 3%: low exposure, maintain with quarterly review
- 3-10%: moderate, audit informational content for quick-answer optimisation
- \> 10%: high, consider deprioritising informational content in favour of transactional/commercial keywords

---

## Learned Seasonality

When GA4 data is uploaded with ≥12 months of traffic history, the tool learns seasonality indices automatically:

```
monthly_index[m] = avg_traffic_for_month_m / overall_avg_traffic
traffic_mod[m] = monthly_index[m] - 1.0
```

**Blend logic:**
- ≥24 months → fully learned (blend weight 1.0)
- 12–23 months → 50/50 blend with AU retail defaults
- <12 months → AU retail defaults only

The blended seasonality is stored in `st.session_state["seasonality"]` and passed to positional, new content, and historical engines at run time. The Data Upload page shows a comparison chart of learned vs. default modifiers.

---

## Brand Classification

Keywords can be classified as branded or non-branded on the Data Upload page. Brand terms are detected via:
1. **AI detection** — the AI analyses the domain name + top 100 keywords by volume and returns suspected brand terms
2. **Manual entry** — the analyst can add/remove terms in the text area

Matching uses case-insensitive word-boundary regex — "cable" will match "cable melbourne" but NOT "excable".

Branded keywords are tagged with `is_branded = True` in `st.session_state["kw_df"]`. By default (`exclude_brand_from_forecasts = True`), they are excluded from positional forecasts because branded keywords already rank at position 1 and applying uplift math to them distorts results.

---

## Phased Maturation S-Curve

v4 replaces the v3 linear ramp and step function with a logistic S-curve:

```
progress(t) = 1 / (1 + exp(-k × (t - t_mid)))
```

Parameters per difficulty tier:

| Tier | t_mid (months) | k (steepness) |
|------|---------------|---------------|
| Easy | 2.5 | 1.8 |
| Moderate | 5.0 | 1.2 |
| Hard | 8.0 | 0.9 |
| Very Hard | 11.0 | 0.7 |
| Extreme | 13.0 | 0.5 |

The S-curve hits roughly 10% progress by quarter-1, 40% by half, and 80% by three-quarters of the ramp period. Applied to both positional and new content engines.

---

## Mode 6: Keyword Decay

Pages that rank today don't keep ranking tomorrow without maintenance. The decay engine models traffic loss on unmaintained pages using position-bucketed annual rates:

| Position Bucket | Annual Decay Rate |
|----------------|-------------------|
| Top 3 | 8% |
| Top 10 | 12% |
| 11–20 | 18% |
| 21–50 | 25% |
| 51+ | 35% |

Monthly retention is calculated as `(1 - annual_rate)^(1/12)`. The **maintenance coverage** parameter (0–1) reduces effective decay: at 0.7 coverage, only 30% of the decay applies.

The "honest baseline" is the linear projection minus cumulative decay — this is what happens if you stop all SEO work.

---

## Mode 7: Monte Carlo Confidence Bands

Instead of a single-line forecast, the positional engine runs 500 Monte Carlo trials per keyword:

1. **Improvement probability** — logistic function on (effort score − normalised KD). Not every keyword improves.
2. **Target position** — triangular distribution centred on the deterministic target ±3 positions.
3. **Time-to-move** — triangular distribution around tier defaults.

Each trial produces a full monthly traffic projection. The P10/P50/P90 percentiles across trials give:
- **P10** (conservative) — 90% chance of beating this
- **P50** (median) — the most likely outcome
- **P90** (optimistic) — only 10% chance of reaching this

When a single number is needed (e.g. Forecast Grid Export), P50 is used by default.

---

## Mode 8: Portfolio Attention Curve

SEO teams can't meaningfully work on all keywords at once. The attention curve models realistic effort distribution:

| Portfolio Slice | Effort Weight | Label |
|----------------|---------------|-------|
| Top 5% | 1.00 | Focus |
| Next 15% | 0.60 | Secondary |
| Next 30% | 0.25 | Long Tail |
| Bottom 50% | 0.05 | Background |

Keywords are ranked by opportunity score (`volume / (kd + 1)`). The effort weight multiplies the improvement probability in the Monte Carlo — background keywords are unlikely to improve without dedicated effort.

This brings the aggregate uplift from v2's ~75% down to a realistic 30–50% range on typical portfolios.

---

## Mode 9: AIO Impact — Per-Stream CTR Penalty (v4)

In v4, AI Overview impact is applied per-stream as a CTR penalty at the keyword level, rather than as a separate post-hoc deduction from Combined.

**How it works:**
- When running Positional or New Content forecasts, pass `aio_intent_penalties` to the engine
- The penalty is applied at the CTR computation step for each keyword based on its intent
- Result: the forecast traffic is already net of AIO impact; no separate deduction needed

Default intent penalties (same values as v3):

| Intent | CTR Penalty |
|--------|-------------|
| Informational | 45% |
| Commercial | 15% |
| Transactional | 5% |
| Navigational | 0% |

**The AI Overview Risk page (page 7)** is now a diagnostic view only. It shows exposure analysis and projected erosion for visibility — the actual traffic impact is already baked into Positional and New Content forecasts. "Projected Monthly Loss" is no longer shown as a KPI on that page.

The spreading AIO erosion model (`project_aio_erosion` in `engine/aio_risk_engine.py`) remains available for the diagnostic view but is not used in Combined math.

---

## Mode 10: Forecast Variance & Calibration

Every Combined Forecast can be downloaded as a JSON snapshot. Months later, upload it alongside fresh GA4 data to see how the forecast performed.

The variance analysis shows:
- Per-month P50 forecast vs. actual traffic
- Whether actuals fell within the P10–P90 band
- Mean variance %, max overshoot/undershoot

This is the tool's calibration loop. Without it, forecasts are guesses nobody ever grades. With accumulated snapshots, parameters can be tuned to improve accuracy over time.

---

## Assumptions Management

All forecast parameters are tracked in a centralised assumptions store (`engine/assumptions.py`). Each assumption has a **provenance** that tells you how its value was determined:

| Provenance | Colour | Meaning |
|------------|--------|---------|
| defaulted | grey | Using the built-in default — no data has been provided yet |
| detected | blue | Automatically inferred from your uploaded data (GA4, roadmap) |
| overridden | green | You have explicitly set this value via the Assumptions panel |

### Key assumptions

| Key | Default | Detection Source |
|-----|---------|-----------------|
| `blended_cr_pct` | 2.5% | GA4 transactions ÷ sessions |
| `aov` | $100 | GA4 average order value |
| `currency` | USD | — (user sets) |
| `effort_level` | moderate | Roadmap import |
| `content_cadence` | 4 posts/mo | Roadmap import (content hours ÷ 10) |
| `maintenance_coverage` | 0.0 | Roadmap import (on-page/technical task regularity) |
| `aio_monthly_growth` | 2.5% | — |
| `aio_ctr_penalty_informational` | 45% | — |
| `decay_rate_top3` | 8%/yr | — |
| `decay_rate_top10` | 12%/yr | — |
| `brand_terms` | [] | AI detection or user entry |
| `exclude_brand_from_forecasts` | True | — |
| `seasonality_source` | "defaulted" | Auto-detected from GA4 data length |
| `seasonality_blend_weight` | 0.0 | Auto-detected from GA4 data length |

### Roadmap ingestion

Upload a roadmap CSV or XLSX on the **Data Upload → Roadmap** tab. Accepted formats:

1. **Task table** (columns: Task, Focus, Occurrence, Hours) — the native GAZMAN xlsx produced by the SEO Roadmap page
2. **Param table** (columns: cadence, effort_level, maintenance_coverage) — a simple one-row override file

The loader extracts content cadence (from content production hours), effort level (from total monthly hours), and maintenance coverage (from regularity of on-page/technical tasks).

---

## Assumptions and Limitations

1. **CTR data is based on industry averages** — actual CTR varies by industry, SERP features, and brand recognition.
2. **Ranking probability is simplified** — real ranking depends on content quality, backlinks, technical SEO, and hundreds of other factors.
3. **Traffic estimates assume stable search volume** — seasonal variations and trend shifts are not modelled in keyword mode.
4. **Historical forecasts assume trends continue** — they cannot predict algorithm updates, market changes, or competitor actions.
5. **Revenue projections assume constant CVR and AOV** — in practice these vary by traffic source, season, and funnel optimisation.
6. **The tool does not account for keyword cannibalisation** — targeting similar keywords may not produce additive traffic.

Use these forecasts as directional guidance for planning, not as exact predictions.
