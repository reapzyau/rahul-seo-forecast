import os
import streamlit as st


def init_api_key_from_secrets() -> None:
    """Pre-populate bifrost_api_key session state from secrets or env var if not already set."""
    if st.session_state.get("bifrost_api_key"):
        return
    # 1. Check Streamlit secrets (Streamlit Cloud dashboard or local secrets.toml)
    try:
        if "BIFROST_API_KEY" in st.secrets and st.secrets["BIFROST_API_KEY"]:
            st.session_state["bifrost_api_key"] = st.secrets["BIFROST_API_KEY"]
            return
    except Exception:
        pass
    # 2. Fall back to environment variable
    env_key = os.environ.get("BIFROST_API_KEY")
    if env_key:
        st.session_state["bifrost_api_key"] = env_key


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
            [
                "openai/gpt-5.4-mini",               # recommended: smart + fast
                "openai/gpt-5.4-nano",               # fastest / cheapest
                "anthropic/claude-haiku-4-5-20251001",  # smart alternative
                "bedrock/us.amazon.nova-micro-v1:0", # fastest / cheapest (Bedrock)
                "openai/gpt-4o-mini",
                "openai/gpt-4o",
            ],
            key="bifrost_model",
            help="Model for AI features. gpt-5.4-mini is a good default. Use nano/nova-micro for speed.",
        )
