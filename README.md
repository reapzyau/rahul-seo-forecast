# SEO Traffic & Revenue Forecasting Engine

A Streamlit web application for SEO traffic and revenue forecasting. Combines keyword-based traffic modelling, historical trend forecasting, and revenue projection into a single interactive tool.

## Quick Start

1. **Upload a CSV** with your keyword data (columns: `keyword`, `volume`, `kd`) or historical traffic data (columns: `date`, `traffic`)
2. **Set your Domain Authority** and other parameters in the sidebar
3. **Click Generate Forecast** to see projections
4. **Export** results as CSV or interactive HTML reports

Or check the **Use sample data** box on any page to explore immediately.

## Forecasting Modes

| Mode | Description | Input Required |
|------|-------------|----------------|
| **Keyword Forecast** | Project traffic from target keywords | Keywords CSV |
| **Historical Forecast** | Extrapolate from past organic data | Traffic CSV |
| **Combined Forecast** | Layer new content onto existing baseline | Both CSVs |
| **Methodology** | How the models work | None |

## Input Formats

### Keywords CSV

```csv
keyword,volume,kd
seo audit tool,14742,62
keyword research tool,12500,71
```

- **keyword**: Target search term
- **volume**: Monthly search volume
- **kd**: Keyword difficulty (0–100)

### Historical Traffic CSV

```csv
date,traffic
2023-07-01,26053
2023-08-01,26929
```

- **date**: Month (any parseable date format)
- **traffic**: Organic traffic for that month

## Local Development

```bash
pip install -r requirements.txt
streamlit run app.py
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
