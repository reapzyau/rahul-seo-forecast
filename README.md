# SEO Traffic & Revenue Forecasting Engine

A Streamlit web application for SEO traffic and revenue forecasting. Supports native Pattern GA4 + SEMrush inputs, positional uplift modelling, AI Overview risk assessment, and multi-channel-plan-format outputs.

## Quick Start

1. Go to **Data Upload** and either upload your GA4 organic export + SEMrush organic positions export, or tick "Use sample (Cable)" on both tabs
2. Go to **Strategy** — review the portfolio diagnosis, accept or tweak the three scenario presets, and click Run All Forecasts. This is the fastest path from upload to client-ready deliverable.
3. Download the **3-Scenario Forecast Grid XLSX** from the Strategy page or the Deliverables page — four sheets (Conservative / Moderate / Aggressive / Comparison) ready for the client deck.
4. (Optional) Go to **Positional Forecast** for single-scenario deep-dive, or **Historical Forecast** for a do-nothing baseline, or **New Content Forecast** for gap-analysis-driven projections.
5. Go to **Combined Forecast** to see baseline + positional + new content layered for any single scenario.
6. Go to **Deliverables** for full export options including variance grading and methodology.

## Forecasting Modes

| Mode | Input | What it projects |
|------|-------|------------------|
| Strategy | GA4 + SEMrush + (optional) Roadmap | Portfolio diagnosis + 3 coherent scenarios |
| Positional Forecast | SEMrush + GA4 | Uplift from moving keywords up the SERP |
| New Content Forecast | Keyword list (gap analysis) | Traffic from publishing new content |
| Historical Forecast | GA4 organic data | "Do nothing" baseline trajectory |
| Combined Forecast | All three streams layered | Full projection with baseline + uplifts |
| AI Overview Risk | SEMrush | Traffic at risk from AIO with action recommendations |
| Seasonality | Any forecast | Monthly modifiers + campaign events |
| SEO Roadmap | Task list | Month-by-month hours allocation + xlsx export |
| Forecast Grid Export | Any forecast | Multi-channel plan SEO row xlsx |
| Keyword Pipeline | New Content forecast | SERP page distribution over time |
| Content Roadmap | New Content forecast | AI-generated content plan |

## Input Formats

### GA4 Organic Export (xlsx)

Multi-sheet Excel from GA4 with sheets: Sessions, Revenue, Transactions, AOV. Each sheet has columns for Financial Year, Year month, Session default channel group, and the metric.

### SEMrush Organic Positions Export (csv/xlsx)

17-column export: Keyword, Position, Previous position, Search Volume, Keyword Difficulty, CPC, URL, Traffic, Traffic (%), Traffic Cost, Competition, Number of Results, Trends, Timestamp, SERP Features by Keyword, Keyword Intents, Position Type.

### Legacy formats

Keywords CSV (`keyword, volume, kd`) and traffic CSV (`date, traffic`) are still supported on the New Content and Historical Forecast pages.

## Local Development

```bash
pip install -r requirements.txt
streamlit run app.py
```

Prophet support (optional — enables v4 Historical Forecast with ≥24 months of data, falls back to Holt's exponential smoothing otherwise):

```bash
pip install -r requirements-prophet.txt
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Deployment

This app is designed for Streamlit Community Cloud:

1. Push to GitHub
2. Connect at [share.streamlit.io](https://share.streamlit.io)
3. Set main file path to `app.py`
4. No secrets or API keys needed

## Methodology

See the [Methodology](methodology.md) page for full documentation on the forecasting models, assumptions, and limitations.

## License

MIT
