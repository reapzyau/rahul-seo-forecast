import streamlit as st


def init_api_key_from_secrets() -> None:
    """Pre-populate bifrost_api_key session state from Streamlit secrets if not already set."""
    if st.session_state.get("bifrost_api_key"):
        return
    try:
        if "BIFROST_API_KEY" in st.secrets and st.secrets["BIFROST_API_KEY"]:
            st.session_state["bifrost_api_key"] = st.secrets["BIFROST_API_KEY"]
    except Exception:
        pass


def render_ai_settings() -> None:
    """Render AI Settings expander in the sidebar, auto-loading key from secrets."""
    init_api_key_from_secrets()

    with st.sidebar.expander("AI Settings (Bi Frost)", expanded=False):
        st.text_input(
            "Bi Frost API Key",
            type="password",
            key="bifrost_api_key",
            help="Enter your Bi Frost virtual key (sk-bf-...) to enable AI-powered features.",
            placeholder="sk-bf-..." ,
        )
        if st.session_state.get("bifrost_api_key"):
            st.caption("✓ API key active")
        else:
            st.caption("No key set — AI features will be disabled.")
        st.selectbox(
            "AI Model",
            ["openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-sonnet-4-5-20250929"],
            key="bifrost_model",
            help="Model used for keyword clustering, cannibalization checks, and content roadmap.",
        )
