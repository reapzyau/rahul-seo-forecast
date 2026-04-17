import streamlit as st
import pandas as pd

from engine.ai_engine import get_bifrost_client, generate_content_roadmap, cluster_keywords
from utils.export import to_csv
from utils.sidebar import render_ai_settings

st.header("Content Roadmap")
st.caption("AI-powered content planning and prioritization using your keyword forecast data.")

render_ai_settings()

# ── Check prerequisites ──────────────────────────────────────────────────────
client = get_bifrost_client(st.session_state.get("bifrost_api_key"))
ai_model = st.session_state.get("bifrost_model", "openai/gpt-4o-mini")

if client is None:
    st.warning(
        "This page requires a Bi Frost API key. "
        "Set it in the sidebar under **AI Settings (Bi Frost)** on the home page."
    )
    st.stop()

# ── Upload existing roadmap (optional) ───────────────────────────────────────
st.subheader("Existing Roadmap (Optional)")
st.caption("Upload your current content roadmap to provide context for AI recommendations.")
roadmap_file = st.file_uploader("Upload roadmap file", type=["csv", "tsv", "xlsx", "xls"], key="roadmap_upload")

existing_roadmap_csv = None
if roadmap_file is not None:
    try:
        existing_roadmap = pd.read_csv(roadmap_file)
        existing_roadmap_csv = existing_roadmap.to_csv(index=False)
        st.success(f"Loaded {len(existing_roadmap)} rows from existing roadmap — AI will avoid duplicating these topics")
        st.dataframe(existing_roadmap.head(10), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not read roadmap CSV: {e}")

# ── Get keyword forecast data ────────────────────────────────────────────────
st.divider()
st.subheader("Generate Content Roadmap")

kw_results = st.session_state.get("kw_results")
if kw_results is None:
    st.info(
        "Run a **Keyword Forecast** first to generate data for the roadmap. "
        "Go to the Keyword Forecast page, upload keywords, and click Generate Forecast."
    )
    st.stop()

keyword_df = kw_results["keyword_df"]
st.success(f"Using keyword forecast data: {len(keyword_df)} keywords")

# ── Configuration ────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    roadmap_months = st.slider("Roadmap Duration (months)", 3, 24, 12, key="roadmap_months")
with col2:
    st.metric("Keywords Available", len(keyword_df))
    st.metric("Keywords Ranking", int(keyword_df["will_rank"].sum()))

# ── Generate ─────────────────────────────────────────────────────────────────
if st.button("Generate AI Content Roadmap", type="primary", key="roadmap_generate"):
    with st.spinner("AI is analyzing your keywords and building a content roadmap..."):
        try:
            roadmap = generate_content_roadmap(client, keyword_df, roadmap_months, ai_model, existing_roadmap_csv)
            st.session_state["content_roadmap"] = roadmap
        except Exception as e:
            st.error(f"Roadmap generation failed: {e}")

# ── Display ──────────────────────────────────────────────────────────────────
if "content_roadmap" in st.session_state:
    roadmap = st.session_state["content_roadmap"]

    st.divider()
    st.subheader("Content Roadmap")

    # Build flat table for export
    flat_rows = []
    for month_plan in roadmap:
        month_num = month_plan.get("month", "?")
        pieces = month_plan.get("content_pieces", [])

        with st.expander(f"**Month {month_num}** — {len(pieces)} content pieces", expanded=month_num <= 3):
            for piece in pieces:
                priority = piece.get("priority", "medium")
                icon = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(priority, "\u26aa")

                st.markdown(
                    f"{icon} **{piece.get('title', 'Untitled')}** "
                    f"(~{piece.get('estimated_traffic', 0):,} visits/mo, priority: {priority})"
                )
                kws = piece.get("target_keywords", [])
                if kws:
                    st.caption(f"Target keywords: {', '.join(kws)}")
                notes = piece.get("notes")
                if notes:
                    st.caption(f"Note: {notes}")

                flat_rows.append({
                    "Month": month_num,
                    "Title": piece.get("title", ""),
                    "Target Keywords": ", ".join(kws),
                    "Estimated Traffic": piece.get("estimated_traffic", 0),
                    "Priority": priority,
                    "Notes": notes or "",
                })

    # Export
    if flat_rows:
        st.divider()
        roadmap_df = pd.DataFrame(flat_rows)
        st.download_button(
            "Download Roadmap CSV",
            to_csv(roadmap_df),
            "content-roadmap.csv",
            "text/csv",
            key="roadmap_export",
        )
