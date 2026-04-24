import pathlib

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="SEO Forecast",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide all Streamlit chrome so the React app fills the viewport edge-to-edge
st.markdown("""
<style>
.block-container { padding: 0 !important; max-width: 100% !important; }
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

_HTML_PATH = pathlib.Path("assets/Forecast System.html")


@st.cache_data
def _load_html(mtime: float) -> str:
    return _HTML_PATH.read_text(encoding="utf-8")


_html = _load_html(_HTML_PATH.stat().st_mtime)

components.html(_html, height=1080, scrolling=True)
