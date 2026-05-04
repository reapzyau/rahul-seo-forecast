import streamlit as st

from utils.data_status import page_status_emoji
from utils.session import (
    COMB_RESULTS,
    GA4_DF,
    HIST_RESULTS,
    KW_EXISTING,
    NC_RESULT,
    POS_RESULT,
    ROADMAP_BUNDLE,
    ROADMAP_CONTENT_PLAN,
)

st.set_page_config(
    page_title="SEO Traffic Forecast",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

_s = dict(st.session_state)


def _e(hard: list[str], soft: list[str] | None = None) -> str:
    return page_status_emoji(hard, soft or [], _s)


inputs = [
    st.Page("pages/inputs/ga4.py",      title="GA4 Organic",       icon="📊", url_path="ga4"),
    st.Page("pages/inputs/semrush.py",  title="SEMrush Keywords",  icon="🔑", url_path="semrush"),
    st.Page("pages/inputs/roadmap.py",  title="Roadmap",           icon="🗺️", url_path="roadmap-upload"),
]
forecasts = [
    st.Page(
        "pages/forecasts/strategy.py",
        title="Strategy" + _e([GA4_DF, KW_EXISTING], [ROADMAP_BUNDLE]),
        icon="🎯",
        default=True,
        url_path="strategy",
    ),
    st.Page(
        "pages/forecasts/historical.py",
        title="Historical" + _e([GA4_DF]),
        icon="📈",
        url_path="historical",
    ),
    st.Page(
        "pages/forecasts/positional.py",
        title="Positional" + _e([KW_EXISTING], [GA4_DF]),
        icon="📍",
        url_path="positional",
    ),
    st.Page(
        "pages/forecasts/new_content.py",
        title="New Content" + _e([], [ROADMAP_CONTENT_PLAN, KW_EXISTING]),
        icon="✏️",
        url_path="new-content",
    ),
    st.Page(
        "pages/forecasts/combined.py",
        title="Combined" + _e([], [POS_RESULT, NC_RESULT, HIST_RESULTS]),
        icon="🔗",
        url_path="combined",
    ),
]
outputs = [
    st.Page(
        "pages/outputs/diagnostics.py",
        title="Diagnostics" + _e([], [KW_EXISTING, COMB_RESULTS]),
        icon="🔍",
        url_path="diagnostics",
    ),
    st.Page(
        "pages/outputs/roadmap.py",
        title="Content Roadmap" + _e([], [ROADMAP_BUNDLE]),
        icon="📅",
        url_path="content-roadmap",
    ),
    st.Page(
        "pages/outputs/deliverables.py",
        title="Deliverables" + _e([], [COMB_RESULTS]),
        icon="📥",
        url_path="deliverables",
    ),
]

pg = st.navigation({
    "Inputs": inputs,
    "Forecasts": forecasts,
    "Outputs": outputs,
})
pg.run()
