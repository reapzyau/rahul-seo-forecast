import pathlib

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Forecast Dashboard",
    page_icon="🔮",
    layout="wide",
)

# Kill Streamlit chrome so the React app fills the viewport edge-to-edge
st.markdown("""
<style>
.block-container { padding: 0 !important; max-width: 100% !important; }
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
section[data-testid="stSidebar"] > div { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

_HTML_PATH = pathlib.Path("assets/Forecast System.html")

if not _HTML_PATH.exists():
    st.error(
        f"Dashboard file not found at `{_HTML_PATH}`. "
        "Make sure the file is present in the `assets/` directory."
    )
    st.stop()


@st.cache_data
def _load_html(mtime: float) -> str:
    return _HTML_PATH.read_text(encoding="utf-8")


_mtime = _HTML_PATH.stat().st_mtime
_html = _load_html(_mtime)

components.html(_html, height=1100, scrolling=True)
