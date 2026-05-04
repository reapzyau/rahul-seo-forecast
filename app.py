import streamlit as st

st.set_page_config(
    page_title="SEO Traffic Forecast",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inputs = [
    st.Page("pages/inputs/ga4.py", title="GA4 Organic", icon="📊"),
    st.Page("pages/inputs/semrush.py", title="SEMrush Keywords", icon="🔑"),
    st.Page("pages/inputs/roadmap.py", title="Roadmap", icon="🗺️", url_path="roadmap-upload"),
]
forecasts = [
    st.Page("pages/forecasts/strategy.py", title="Strategy", icon="🎯", default=True),
    st.Page("pages/forecasts/historical.py", title="Historical", icon="📈"),
    st.Page("pages/forecasts/positional.py", title="Positional", icon="📍"),
    st.Page("pages/forecasts/new_content.py", title="New Content", icon="✏️"),
    st.Page("pages/forecasts/combined.py", title="Combined", icon="🔗"),
]
outputs = [
    st.Page("pages/outputs/diagnostics.py", title="Diagnostics", icon="🔍"),
    st.Page("pages/outputs/roadmap.py", title="Content Roadmap", icon="📅", url_path="content-roadmap"),
    st.Page("pages/outputs/deliverables.py", title="Deliverables", icon="📥"),
]

pg = st.navigation({
    "Inputs": inputs,
    "Forecasts": forecasts,
    "Outputs": outputs,
})
pg.run()
