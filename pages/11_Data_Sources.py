import pathlib

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Data Sources",
    page_icon="📁",
    layout="wide",
)

st.title("📁 Data Sources")
st.caption(
    "Sample files used by the forecasting engine — preview, inspect, and download each one."
)

_ASSETS = pathlib.Path("assets")

_FILES = [
    {
        "path": _ASSETS / "sample-ga4-organic.xlsx",
        "label": "GA4 Organic Export",
        "description": (
            "Monthly organic sessions, revenue, transactions, and AOV by channel. "
            "Feeds the **Historical Forecast** baseline and **Combined Forecast**."
        ),
    },
    {
        "path": _ASSETS / "sample-semrush-export.xlsx",
        "label": "SEMrush Organic Positions",
        "description": (
            "Keyword-level ranking data: position, previous position, search volume, "
            "keyword difficulty, traffic estimate, and SERP features. "
            "Feeds the **Positional Forecast** and **Strategy** scenarios."
        ),
    },
    {
        "path": _ASSETS / "sample-keywords.csv",
        "label": "Target Keywords (gap analysis)",
        "description": (
            "Net-new keyword list with volume and difficulty columns. "
            "Feeds the **New Content Forecast** for pages not yet published."
        ),
    },
    {
        "path": _ASSETS / "sample-traffic.csv",
        "label": "Traffic History (legacy)",
        "description": (
            "Date/traffic time-series for the legacy historical mode. "
            "Used by **Historical Forecast** when a full GA4 export is unavailable."
        ),
    },
]


def _load(path: pathlib.Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


for info in _FILES:
    path: pathlib.Path = info["path"]
    with st.expander(f"**{info['label']}** — `{path.name}`", expanded=False):
        st.caption(info["description"])
        try:
            df = _load(path)
            col1, col2 = st.columns(2)
            col1.metric("Rows", f"{len(df):,}")
            col2.metric("Memory", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")
            st.dataframe(df, use_container_width=True)
            st.download_button(
                label=f"⬇ Download {path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/octet-stream",
                key=str(path),
            )
        except Exception as exc:
            st.error(f"Could not load `{path.name}`: {exc}")
