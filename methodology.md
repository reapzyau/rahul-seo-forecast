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

### Step 6: Time to Rank

Time to rank depends on the difficulty tier, with DA providing a small adjustment:

| Tier | Base Range (months) |
|------|-------------------|
| Easy | 2–3 |
| Moderate | 4–6 |
| Hard | 7–9 |
| Very Hard | 10–12 |
| Extreme | 12–14 |

Higher DA slightly reduces time to rank; lower DA slightly increases it.

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

### Linear Regression

Fits a straight line to your historical data using least-squares regression (`numpy.polyfit` with degree 1). The slope represents your average monthly traffic change.

- **Confidence bands** are calculated as ± X% of the projected value (configurable, default 15%).
- Best for data with a clear upward or downward trend.

### Exponential Smoothing

Simple exponential smoothing weights recent data more heavily:

```
smoothed[t] = alpha * actual[t] + (1 - alpha) * smoothed[t-1]
```

- **Alpha** (0.1–0.9) controls how much weight is given to recent data.
- Higher alpha = more reactive to recent changes.
- Lower alpha = smoother, more stable trend.
- Extrapolation uses a weighted average of trend differences from the smoothed series.

### Simple Moving Average (SMA)

Averages the last N months (configurable window, default 3). For forecasting, each predicted value is fed back into the window:

```
forecast[t] = mean(values[t-window:t])
```

- Smooths out short-term fluctuations.
- Responsive to recent changes but can lag behind sharp trends.

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

---

## Mode 5: AI Overview Risk

Uses SEMrush's Position Type column. Keywords flagged as "AI overview" are considered AIO-affected; their current traffic is multiplied by the CTR penalty (default 40%) to estimate projected loss.

The analysis segments risk by keyword intent — informational keywords typically carry the highest AIO exposure because AIO summaries compete most directly with informational content.

Recommendations are generated based on exposure percentage:
- < 3%: low exposure, maintain with quarterly review
- 3-10%: moderate, audit informational content for quick-answer optimisation
- \> 10%: high, consider deprioritising informational content in favour of transactional/commercial keywords

---

## Assumptions and Limitations

1. **CTR data is based on industry averages** — actual CTR varies by industry, SERP features, and brand recognition.
2. **Ranking probability is simplified** — real ranking depends on content quality, backlinks, technical SEO, and hundreds of other factors.
3. **Traffic estimates assume stable search volume** — seasonal variations and trend shifts are not modelled in keyword mode.
4. **Historical forecasts assume trends continue** — they cannot predict algorithm updates, market changes, or competitor actions.
5. **Revenue projections assume constant CVR and AOV** — in practice these vary by traffic source, season, and funnel optimisation.
6. **The tool does not account for keyword cannibalisation** — targeting similar keywords may not produce additive traffic.

Use these forecasts as directional guidance for planning, not as exact predictions.
