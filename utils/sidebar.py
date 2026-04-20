import os

import streamlit as st

from engine.ai_engine import get_default_model, get_model_options
from utils.session import BIFROST_API_KEY, BIFROST_MODEL, SESSION_COST_AUD


def init_api_key_from_secrets() -> None:
    """Pre-populate bifrost_api_key session state from secrets or env var if not already set."""
    if st.session_state.get(BIFROST_API_KEY):
        return
    try:
        if "BIFROST_API_KEY" in st.secrets and st.secrets["BIFROST_API_KEY"]:
            st.session_state[BIFROST_API_KEY] = st.secrets["BIFROST_API_KEY"]
            return
    except Exception:
        pass
    env_key = os.environ.get("BIFROST_API_KEY")
    if env_key:
        st.session_state[BIFROST_API_KEY] = env_key


def render_ai_settings() -> None:
    """Render AI Settings expander in the sidebar, auto-loading key from secrets."""
    init_api_key_from_secrets()

    models = get_model_options()
    model_ids = [m["id"] for m in models]
    model_labels = [m["label"] for m in models]
    default_model = get_default_model()
    default_idx = model_ids.index(default_model) if default_model in model_ids else 0

    with st.sidebar.expander("AI Settings (Bi Frost)", expanded=False):
        st.text_input(
            "Bi Frost API Key",
            type="password",
            key=BIFROST_API_KEY,
            help="Enter your Bi Frost virtual key (sk-bf-...) to enable AI-powered features.",
            placeholder="sk-bf-...",
        )
        if st.session_state.get(BIFROST_API_KEY):
            st.caption("✓ API key active")
        else:
            st.caption("No key set — AI features will be disabled.")

        selected_label = st.selectbox(
            "AI Model",
            model_labels,
            index=default_idx,
            key="_bifrost_model_label",
            help="Model for AI features. GPT-4o Mini is a good default.",
        )
        label_idx = model_labels.index(selected_label)
        st.session_state[BIFROST_MODEL] = model_ids[label_idx]

        cost = st.session_state.get(SESSION_COST_AUD, 0.0)
        if cost > 0:
            st.caption(f"~A${cost:.3f} estimated session AI cost")
