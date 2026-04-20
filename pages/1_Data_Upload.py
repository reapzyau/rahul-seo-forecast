import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.ga4_loader import load_ga4_organic
from utils.keyword_loader import load_keyword_portfolio, split_existing_vs_new
from utils.roadmap_loader import load_roadmap
from utils.chart_builder import _apply_layout
from utils.sidebar import render_ai_settings
from utils.assumptions_panel import render_assumptions_panel, render_assumptions_banner
from engine.assumptions import initialise_assumptions, run_detection, override_assumption, get_assumption
from engine.seasonality_engine import (
    learn_seasonality_from_ga4, blend_learned_and_default_seasonality, DEFAULT_SEASONALITY,
)
from engine.brand_engine import classify_keywords_as_branded

st.header("Data Upload")
st.caption("Upload GA4 organic traffic, SEMrush keyword exports, and an optional roadmap file. Data flows to all downstream pages.")

render_ai_settings()

# ── Assumptions store ────────────────────────────────────────────────────────
store = st.session_state.setdefault("assumptions", {})
initialise_assumptions(store)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_ga4, tab_semrush, tab_roadmap = st.tabs([
    "📊 GA4 Organic Traffic",
    "🔑 SEMrush Keywords",
    "🗺️ Roadmap",
])

# ── GA4 Tab ──────────────────────────────────────────────────────────────────
with tab_ga4:
    uploaded_ga4 = st.file_uploader(
        "Upload GA4 organic export",
        type=["xlsx", "xls"],
        key="ga4_upload",
    )
    use_ga4_sample = st.checkbox("Use sample data (Cable Melbourne)", key="ga4_sample")

    ga4_df = None
    if uploaded_ga4 is not None:
        ga4_df = load_ga4_organic(uploaded_ga4)
    elif use_ga4_sample:
        sample_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "sample-ga4-organic.xlsx"
        )
        ga4_df = load_ga4_organic(sample_path)

    if ga4_df is not None:
        st.session_state["ga4_df"] = ga4_df
        run_detection(store, ga4_df=ga4_df)

        # ── Seasonality Detection ─────────────────────────────────────
        n_months = len(ga4_df)
        learned = learn_seasonality_from_ga4(ga4_df)
        if learned is not None:
            if n_months >= 24:
                blend_weight = 1.0
                source = "learned"
            elif n_months >= 12:
                blend_weight = 0.5
                source = "blended"
            else:
                blend_weight = 0.0
                source = "defaulted"

            blended = blend_learned_and_default_seasonality(learned, DEFAULT_SEASONALITY, blend_weight)
            st.session_state["seasonality"] = blended
            st.session_state["learned_seasonality"] = learned
            override_assumption(store, "seasonality_source", source, f"GA4 data ({n_months} months)")
            override_assumption(store, "seasonality_blend_weight", blend_weight, f"GA4 data ({n_months} months)")

        date_min = ga4_df["date"].min()
        date_max = ga4_df["date"].max()
        st.success(
            f"{len(ga4_df)} months loaded ({date_min.strftime('%b %Y')} – {date_max.strftime('%b %Y')})"
        )

        # KPI cards
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Months", f"{len(ga4_df)}")
        c2.metric("Latest Traffic", f"{ga4_df['traffic'].iloc[-1]:,}")
        c3.metric("Avg Traffic", f"{ga4_df['traffic'].mean():,.0f}")
        c4.metric("Date Range", f"{date_min.strftime('%b %Y')} – {date_max.strftime('%b %Y')}")

        # Revenue / transactions KPIs if present
        has_revenue = "revenue" in ga4_df.columns
        has_transactions = "transactions" in ga4_df.columns
        if has_revenue or has_transactions:
            extra_cols = st.columns(4)
            col_idx = 0
            if has_revenue:
                extra_cols[col_idx].metric(
                    "Total Revenue", f"${ga4_df['revenue'].sum():,.2f}"
                )
                col_idx += 1
                extra_cols[col_idx].metric(
                    "Avg Monthly Revenue", f"${ga4_df['revenue'].mean():,.2f}"
                )
                col_idx += 1
            if has_transactions:
                extra_cols[col_idx].metric(
                    "Total Transactions", f"{ga4_df['transactions'].sum():,}"
                )
                col_idx += 1

        # Traffic line chart
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=ga4_df["date"],
                y=ga4_df["traffic"],
                mode="lines+markers",
                name="Organic Traffic",
                line=dict(color="#2563EB", width=3),
                hovertemplate="%{x|%b %Y}<br>Traffic: %{y:,.0f}<extra></extra>",
            )
        )
        fig = _apply_layout(fig, "Monthly Organic Traffic", "Date", "Sessions")
        st.plotly_chart(fig, use_container_width=True)

    elif uploaded_ga4 is not None:
        st.error("Could not parse the uploaded GA4 file. Please check the format.")

# ── SEMrush Tab ──────────────────────────────────────────────────────────────
with tab_semrush:
    uploaded_semrush = st.file_uploader(
        "Upload SEMrush organic positions export",
        type=["csv", "tsv", "xlsx", "xls"],
        key="semrush_upload",
    )
    use_semrush_sample = st.checkbox("Use sample data (Cable Melbourne)", key="semrush_sample")

    kw_df = None
    if uploaded_semrush is not None:
        kw_df = load_keyword_portfolio(uploaded_semrush)
    elif use_semrush_sample:
        sample_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "sample-semrush-export.xlsx"
        )
        kw_df = load_keyword_portfolio(sample_path)

    if kw_df is not None:
        existing_df, new_df = split_existing_vs_new(kw_df)

        st.session_state["kw_df"] = kw_df
        st.session_state["kw_existing"] = existing_df
        st.session_state["kw_new"] = new_df

        # KPI cards
        avg_pos = existing_df["position"].mean() if not existing_df.empty else 0
        aio_count = int(kw_df["has_aio"].sum()) if "has_aio" in kw_df.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Keywords", f"{len(kw_df):,}")
        c2.metric("Currently Ranking", f"{len(existing_df):,}")
        c3.metric("Avg Position", f"{avg_pos:.1f}")
        c4.metric("AIO-Affected", f"{aio_count:,}")

        # Position distribution bar chart
        if not existing_df.empty and "position" in existing_df.columns:
            buckets = [
                ("1-3", 1, 3),
                ("4-10", 4, 10),
                ("11-20", 11, 20),
                ("21-50", 21, 50),
                ("51-100", 51, 100),
            ]
            bucket_labels = []
            bucket_counts = []
            for label, lo, hi in buckets:
                count = int(
                    ((existing_df["position"] >= lo) & (existing_df["position"] <= hi)).sum()
                )
                bucket_labels.append(label)
                bucket_counts.append(count)

            fig_pos = go.Figure()
            fig_pos.add_trace(
                go.Bar(
                    x=bucket_labels,
                    y=bucket_counts,
                    marker_color="#2563EB",
                    hovertemplate="Position %{x}<br>Keywords: %{y}<extra></extra>",
                )
            )
            fig_pos = _apply_layout(
                fig_pos, "Position Distribution", "Position Bucket", "Keyword Count"
            )
            st.plotly_chart(fig_pos, use_container_width=True)

        # Show first 20 rows
        st.subheader("Keyword Preview")
        st.dataframe(kw_df.head(20), use_container_width=True, hide_index=True)

        # ── Brand Classification ──────────────────────────────────────
        st.divider()
        st.subheader("Brand Classification")

        # Detect domain from URL column if present
        detected_domain = ""
        url_cols = [c for c in kw_df.columns if "url" in c.lower() or "page" in c.lower()]
        if url_cols:
            sample_urls = kw_df[url_cols[0]].dropna().head(50)
            from urllib.parse import urlparse
            domains = [urlparse(str(u)).netloc for u in sample_urls if u]
            domains = [d for d in domains if d]
            if domains:
                from collections import Counter
                detected_domain = Counter(domains).most_common(1)[0][0]

        domain_input = st.text_input(
            "Domain", value=detected_domain, key="brand_domain",
            help="Used to give the AI context for brand detection.",
        )

        current_terms = get_assumption(store, "brand_terms") or []
        terms_text = st.text_area(
            "Brand terms (one per line)",
            value="\n".join(current_terms),
            key="brand_terms_area",
            height=100,
            help="Add or edit brand terms. The AI can auto-detect them.",
        )

        ai_key = st.session_state.get("bifrost_api_key")
        ai_model = st.session_state.get("ai_model", "openai/gpt-4o-mini")

        col_detect, col_save = st.columns(2)
        with col_detect:
            if st.button("Detect Brand Terms (AI)", key="brand_detect_btn", disabled=not ai_key):
                try:
                    from engine.ai_engine import get_bifrost_client, detect_brand_terms
                    client = get_bifrost_client(ai_key)
                    top_kws = kw_df.sort_values("volume", ascending=False)["keyword"].head(100).tolist()
                    result_dict, used_model = detect_brand_terms(client, domain_input, top_kws, ai_model)
                    detected = result_dict.get("brand_terms", [])
                    confidence = result_dict.get("confidence", 0)
                    reasoning = result_dict.get("reasoning", "")
                    st.session_state["detected_brand_terms"] = detected
                    st.success(
                        f"Detected {len(detected)} brand terms "
                        f"(confidence: {confidence:.0%}) via {used_model}.\n\n"
                        f"_{reasoning}_"
                    )
                except Exception as e:
                    st.error(f"Brand detection failed: {e}")
            elif not ai_key:
                st.caption("Add your Bi Frost API key in the AI Settings panel to enable auto-detection.")

        # Merge auto-detected with manual
        if "detected_brand_terms" in st.session_state:
            existing_manual = [t.strip() for t in terms_text.split("\n") if t.strip()]
            merged = list(dict.fromkeys(existing_manual + st.session_state["detected_brand_terms"]))
            terms_text = "\n".join(merged)

        with col_save:
            if st.button("Save Brand Terms", key="brand_save_btn"):
                saved_terms = [t.strip() for t in terms_text.split("\n") if t.strip()]
                prov = "AI-detected" if "detected_brand_terms" in st.session_state else "user-overridden"
                override_assumption(store, "brand_terms", saved_terms, prov)
                # Classify keywords
                updated_kw = classify_keywords_as_branded(
                    st.session_state["kw_df"], saved_terms
                )
                st.session_state["kw_df"] = updated_kw
                if "kw_existing" in st.session_state:
                    st.session_state["kw_existing"] = classify_keywords_as_branded(
                        st.session_state["kw_existing"], saved_terms
                    )
                n_branded = updated_kw["is_branded"].sum()
                n_total = len(updated_kw)
                st.success(
                    f"Saved. {n_branded} branded / {n_total} total keywords "
                    f"({n_branded / n_total * 100:.1f}%)."
                )

    elif uploaded_semrush is not None:
        st.error("Could not parse the uploaded SEMrush file. Please check the format.")

# ── Roadmap Tab ───────────────────────────────────────────────────────────────
with tab_roadmap:
    st.markdown(
        "Upload your SEO roadmap to auto-detect **content cadence**, "
        "**effort level**, and **maintenance coverage** for the forecast engines."
    )
    st.caption("Accepts the SEO Roadmap XLSX export from this tool, or any CSV with Task / Focus / Occurrence / Hours columns.")

    uploaded_roadmap = st.file_uploader(
        "Upload roadmap file",
        type=["csv", "xlsx", "xls"],
        key="roadmap_upload",
    )

    if uploaded_roadmap is not None:
        try:
            roadmap_data = load_roadmap(uploaded_roadmap.read())
            if roadmap_data:
                run_detection(store, roadmap_data=roadmap_data)
                st.session_state["roadmap_data"] = roadmap_data

                detected_keys = [k for k in ("content_cadence", "effort_level", "maintenance_coverage") if k in roadmap_data]
                st.success(f"Roadmap loaded. Detected: {', '.join(detected_keys)}.")

                display_rows = []
                for k in detected_keys:
                    display_rows.append({"Parameter": k.replace("_", " ").title(), "Value": roadmap_data[k]})
                st.table(pd.DataFrame(display_rows))
            else:
                st.warning("Roadmap file parsed but no recognisable parameters were found. Check column names.")
        except Exception as e:
            st.error(f"Could not parse roadmap: {e}")

    elif "roadmap_data" in st.session_state:
        rd = st.session_state["roadmap_data"]
        st.info(
            f"Roadmap from previous upload: cadence={rd.get('content_cadence', '—')}, "
            f"effort={rd.get('effort_level', '—')}, "
            f"maintenance={rd.get('maintenance_coverage', '—')}"
        )

# ── Seasonality Tuning ────────────────────────────────────────────────────────
st.divider()
st.subheader("Seasonality Tuning")
st.caption(
    "Monthly modifiers applied to all forecast streams. "
    "Auto-detected from GA4 when ≥12 months available; "
    "falls back to AU retail defaults otherwise."
)

seasonality = st.session_state.get("seasonality", DEFAULT_SEASONALITY)
learned_seasonality = st.session_state.get("learned_seasonality")
source = get_assumption(store, "seasonality_source")
blend_weight = get_assumption(store, "seasonality_blend_weight")

if source == "learned":
    st.success(f"Seasonality fully learned from GA4 data (blend weight: {blend_weight:.0%}).")
elif source == "blended":
    st.info(f"Seasonality blended: {blend_weight:.0%} GA4 data + {1-blend_weight:.0%} AU retail defaults.")
else:
    st.info("Seasonality using AU retail defaults (upload ≥12 months of GA4 data to learn from your data).")

if learned_seasonality:
    with st.expander("Compare learned vs. AU retail defaults"):
        import plotly.graph_objects as go_s
        months_labels = [seasonality[m]["label"].split(" ")[0] for m in range(1, 13)]
        learned_vals = [learned_seasonality[m]["traffic_mod"] * 100 for m in range(1, 13)]
        default_vals = [DEFAULT_SEASONALITY[m]["traffic_mod"] * 100 for m in range(1, 13)]
        fig_s = go_s.Figure()
        fig_s.add_trace(go_s.Bar(name="Learned from GA4", x=months_labels, y=learned_vals, marker_color="#2563EB"))
        fig_s.add_trace(go_s.Bar(name="AU Retail Default", x=months_labels, y=default_vals, marker_color="#9CA3AF"))
        fig_s = _apply_layout(fig_s, "Seasonality: Learned vs Default", "Month", "Traffic Modifier (%)")
        st.plotly_chart(fig_s, use_container_width=True)

# ── Data Status Footer ────────────────────────────────────────────────────────
st.divider()
st.subheader("Data Status")
col1, col2, col3 = st.columns(3)
with col1:
    if "ga4_df" in st.session_state:
        ga4 = st.session_state["ga4_df"]
        st.success(f"GA4: {len(ga4)} months loaded ({ga4['date'].min().strftime('%b %Y')} – {ga4['date'].max().strftime('%b %Y')})")
    else:
        st.info("GA4: Not loaded")
with col2:
    if "kw_df" in st.session_state:
        kw = st.session_state["kw_df"]
        st.success(f"Keywords: {len(kw)} loaded ({len(st.session_state.get('kw_existing', []))} ranking)")
    else:
        st.info("Keywords: Not loaded")
with col3:
    if "roadmap_data" in st.session_state:
        st.success("Roadmap: loaded")
    else:
        st.info("Roadmap: Not loaded")

# ── Assumptions Panel ─────────────────────────────────────────────────────────
st.divider()
render_assumptions_banner(store)
render_assumptions_panel(store)
