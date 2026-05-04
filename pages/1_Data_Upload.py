import io
import json
import os
from collections import Counter
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.ai_engine import get_bifrost_client, get_default_model
from engine.assumptions import (
    get_assumption,
    override_assumption,
    run_detection,
)
from engine.brand_classifier import (
    BrandConfig,
    build_classifier,
    detect_collisions,
    suggest_branded_candidates,
)
from engine.roadmap_ai_engine import (
    ROADMAP_BUNDLE_SCHEMA,
    compute_cache_key,
    estimate_extraction_tokens,
    load_roadmap_v2,
)
from engine.seasonality_engine import (
    DEFAULT_SEASONALITY,
    learn_seasonality_from_ga4,
    seasonality_for_portfolio,
)
from engine.v5.da_estimator import compare_da_estimate_to_supplied, estimate_da_from_rankings
from engine.v5.ga4_extractor import extract_organic_metrics, summarize_for_methodology
from utils.assumptions_panel import render_assumptions_banner, render_assumptions_panel
from utils.chart_builder import _apply_layout
from utils.design_tokens import PRIMARY, SLATE_400
from utils.ga4_loader import load_ga4_organic
from utils.keyword_loader import load_keyword_portfolio, split_existing_vs_new
from utils.page_base import setup_page
from utils.roadmap_loader import load_roadmap
from utils.session import (
    BIFROST_API_KEY,
    BIFROST_MODEL,
    DETECTED_BRAND_TERMS,
    GA4_DF,
    KW_DF,
    KW_EXISTING,
    KW_NEW,
    LEARNED_SEASONALITY,
    ROADMAP_AI_CACHE,
    ROADMAP_BUNDLE,
    ROADMAP_CONTENT_PLAN,
    ROADMAP_DATA,
    ROADMAP_FILE_EXT,
    ROADMAP_RAW_BYTES,
    ROADMAP_USED_MODEL,
    SEASONALITY,
)

store = setup_page(
    "Data Upload",
    "Upload GA4 organic traffic, SEMrush keyword exports, and an optional roadmap file. Data flows to all downstream pages.",
    show_assumptions_banner=False,
)

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
    ga4_metrics = None
    if uploaded_ga4 is not None:
        raw_bytes = uploaded_ga4.read()
        ga4_df = load_ga4_organic(io.BytesIO(raw_bytes))
        ga4_metrics = extract_organic_metrics(io.BytesIO(raw_bytes))
    elif use_ga4_sample:
        sample_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "sample-ga4-organic.xlsx"
        )
        ga4_df = load_ga4_organic(sample_path)
        ga4_metrics = extract_organic_metrics(sample_path)

    if ga4_df is not None:
        st.session_state[GA4_DF] = ga4_df
        run_detection(store, ga4_df=ga4_df)

        # ── Seasonality Detection ─────────────────────────────────────
        seasonality_dict, season_meta = seasonality_for_portfolio(ga4_df)
        source = season_meta["source"]
        blend_weight = season_meta["blend_weight"]
        n_months = season_meta["months_available"]

        st.session_state[SEASONALITY] = seasonality_dict
        st.session_state[LEARNED_SEASONALITY] = learn_seasonality_from_ga4(ga4_df)
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
                line=dict(color=PRIMARY, width=3),
                hovertemplate="%{x|%b %Y}<br>Traffic: %{y:,.0f}<extra></extra>",
            )
        )
        fig = _apply_layout(fig, "Monthly Organic Traffic", "Date", "Sessions")
        st.plotly_chart(fig, use_container_width=True)

        # ── Channel-level CR / AOV from v5 extractor ─────────────────
        st.divider()
        st.subheader("Organic Search Metrics")

        if ga4_metrics is not None and not ga4_metrics.get("warnings"):
            cr_organic = ga4_metrics["cr_organic"]
            cr_blended = ga4_metrics["cr_blended"]
            aov_organic = ga4_metrics["aov_organic"]
            aov_blended = ga4_metrics["aov_blended"]
            cr_ratio = ga4_metrics.get("cr_ratio")

            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Organic Search CR",
                f"{cr_organic * 100:.2f}%",
                delta=f"{(cr_organic - cr_blended) * 100:+.2f}% vs blended",
            )
            m2.metric(
                "Organic AOV",
                f"${aov_organic:,.2f}",
                delta=f"${aov_organic - aov_blended:+,.2f} vs blended",
            )
            m3.metric(
                "CR Ratio (organic / blended)",
                f"{cr_ratio:.2f}x" if cr_ratio is not None else "—",
                help="< 1 means organic converts below blended average; > 1 means above.",
            )

            st.session_state["cr_organic"] = cr_organic
            st.session_state["cr_blended"] = cr_blended
            st.session_state["aov_organic"] = aov_organic
            st.session_state["aov_blended"] = aov_blended
            st.session_state["ga4_metrics_summary"] = summarize_for_methodology(ga4_metrics)

            with st.expander("Monthly CR breakdown"):
                cbm = ga4_metrics.get("cr_by_month")
                if cbm is not None and not cbm.empty:
                    display_cbm = cbm.copy()
                    for col in ["cr_organic", "cr_blended"]:
                        if col in display_cbm.columns:
                            display_cbm[col] = (display_cbm[col] * 100).round(3).astype(str) + "%"
                    st.dataframe(display_cbm, use_container_width=True)

        else:
            if ga4_metrics is not None and ga4_metrics.get("warnings"):
                st.warning(
                    "Channel breakdown not found in this GA4 export — "
                    "the 'Session default channel group' column is missing. "
                    "Enter Organic CR and AOV manually below."
                )
            else:
                st.info("Upload a GA4 export to auto-detect Organic Search CR and AOV.")

            col_a, col_b = st.columns(2)
            manual_cr = col_a.number_input(
                "Organic Conversion Rate (%)", min_value=0.01, max_value=100.0,
                value=float(st.session_state.get("cr_organic", 0.0) * 100 or 1.5),
                step=0.01, key="ga4_manual_cr",
            )
            manual_aov = col_b.number_input(
                "Organic AOV ($)", min_value=1.0, max_value=1_000_000.0,
                value=float(st.session_state.get("aov_organic") or 100.0),
                step=1.0, key="ga4_manual_aov",
            )
            st.session_state["cr_organic"] = manual_cr / 100.0
            st.session_state["aov_organic"] = manual_aov

    elif uploaded_ga4 is not None:
        st.error("Could not parse the uploaded GA4 file. Please check the format.")

    # ── Seasonality Tuning ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Seasonality Tuning")
    st.caption(
        "Monthly modifiers applied to all forecast streams. "
        "Auto-detected from GA4 when ≥12 months available; "
        "falls back to AU retail defaults otherwise."
    )

    seasonality = st.session_state.get(SEASONALITY, DEFAULT_SEASONALITY)
    learned_seasonality = st.session_state.get(LEARNED_SEASONALITY)
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
            months_labels = [seasonality[m]["label"].split(" ")[0] for m in range(1, 13)]
            learned_vals = [learned_seasonality[m]["traffic_mod"] * 100 for m in range(1, 13)]
            default_vals = [DEFAULT_SEASONALITY[m]["traffic_mod"] * 100 for m in range(1, 13)]
            fig_s = go.Figure()
            fig_s.add_trace(go.Bar(name="Learned from GA4", x=months_labels, y=learned_vals, marker_color=PRIMARY))
            fig_s.add_trace(go.Bar(name="AU Retail Default", x=months_labels, y=default_vals, marker_color=SLATE_400))
            fig_s = _apply_layout(fig_s, "Seasonality: Learned vs Default", "Month", "Traffic Modifier (%)")
            st.plotly_chart(fig_s, use_container_width=True)

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

        st.session_state[KW_DF] = kw_df
        st.session_state[KW_EXISTING] = existing_df
        st.session_state[KW_NEW] = new_df

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
                    marker_color=PRIMARY,
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

        # Seed text-area session-state defaults once (preserves edits across reruns)
        if "brand_terms_area" not in st.session_state:
            st.session_state["brand_terms_area"] = "\n".join(
                get_assumption(store, "brand_terms") or []
            )
        if "brand_wb_terms" not in st.session_state:
            st.session_state["brand_wb_terms"] = ""
        if "brand_excl_terms" not in st.session_state:
            st.session_state["brand_excl_terms"] = ""

        # ── Stage 1: auto-suggest ─────────────────────────────────────
        with st.expander("Stage 1 — Brand candidate auto-detection", expanded=True):
            st.caption(
                "Keywords scored by 4 brand-pattern signals: position 1 + low KD, "
                "short keyword, URL match, high CTR proxy. "
                "Check the rows you want to include, then click **Apply to text areas**."
            )
            candidates = suggest_branded_candidates(kw_df, top_n_by_volume=100, min_volume=100)
            if not candidates.empty:
                candidates_display = candidates.copy()
                candidates_display.insert(0, "include", candidates_display["brand_score"] >= 0.6)
                edited_candidates = st.data_editor(
                    candidates_display,
                    key="brand_candidates_editor",
                    hide_index=True,
                    column_config={
                        "include": st.column_config.CheckboxColumn("Include", default=False),
                        "brand_score": st.column_config.NumberColumn("Score", format="%.2f"),
                    },
                    use_container_width=True,
                )
                if st.button("Apply selected to text areas below", key="apply_brand_suggestions"):
                    included = edited_candidates[edited_candidates["include"]]
                    new_sub, new_wb = [], []
                    for _, row in included.iterrows():
                        kw = str(row["keyword"])
                        if row.get("suggested_classification") == "word_boundary":
                            new_wb.append(kw)
                        else:
                            new_sub.append(kw)
                    existing_sub = [
                        t.strip() for t in st.session_state["brand_terms_area"].split("\n") if t.strip()
                    ]
                    existing_wb = [
                        t.strip() for t in st.session_state["brand_wb_terms"].split("\n") if t.strip()
                    ]
                    st.session_state["brand_terms_area"] = "\n".join(
                        list(dict.fromkeys(existing_sub + new_sub))
                    )
                    st.session_state["brand_wb_terms"] = "\n".join(
                        list(dict.fromkeys(existing_wb + new_wb))
                    )
                    st.rerun()
            else:
                st.info("No brand candidates found — fill in the text areas below manually.")

        # Detect domain from URL column if present
        detected_domain = ""
        url_cols = [c for c in kw_df.columns if "url" in c.lower() or "page" in c.lower()]
        if url_cols:
            sample_urls = kw_df[url_cols[0]].dropna().head(50)
            domains = [urlparse(str(u)).netloc for u in sample_urls if u]
            domains = [d for d in domains if d]
            if domains:
                detected_domain = Counter(domains).most_common(1)[0][0]

        domain_input = st.text_input(
            "Domain", value=detected_domain, key="brand_domain",
            help="Used to give the AI context for brand detection.",
        )

        # Text areas read from / write to session state; no value= so edits persist
        terms_text = st.text_area(
            "Brand substrings — always match (one per line)",
            key="brand_terms_area",
            height=100,
            help=(
                "Safe set: full brand name, abbreviations, domain. "
                "Any keyword containing one of these strings is classified as branded."
            ),
        )

        with st.expander("If your brand name is also a common word — expand for advanced options"):
            st.caption(
                "Use whole-word terms when the brand is ambiguous (e.g. 'Apple', 'Cable'). "
                "Add exclusion words to prevent category terms from being mislabelled."
            )
            wb_terms_text = st.text_area(
                "Brand whole-words (matched as whole words only, one per line)",
                key="brand_wb_terms",
                height=60,
                help="e.g. 'cable' — matches 'cable' but not 'cable knit' if 'knit' is in exclusions.",
            )
            excl_terms_text = st.text_area(
                "Excluded followers (one per line) — prevent whole-word false positives",
                key="brand_excl_terms",
                height=60,
                help="e.g. 'knit', 'car', 'tie' — if any of these appear adjacent to the brand word, keyword is NOT branded.",
            )

        # ── Stage 2: collision detection ──────────────────────────────
        wb_list_current = [t.strip() for t in st.session_state.get("brand_wb_terms", "").split("\n") if t.strip()]
        if wb_list_current:
            with st.expander(
                f"Stage 2 — Collision detection for {len(wb_list_current)} whole-word term(s)",
                expanded=False,
            ):
                st.caption(
                    "Tokens that frequently appear adjacent to your whole-word brand terms. "
                    "Check the ones that indicate a non-brand category — they become **excluded followers**."
                )
                all_new_exclusions: list[str] = []
                for wb_term in wb_list_current:
                    st.markdown(f"**`{wb_term}`** — adjacent tokens:")
                    collisions = detect_collisions(
                        kw_df, wb_term, min_follower_count=3, min_volume_share=0.01
                    )
                    if not collisions.empty:
                        collisions_display = collisions.copy()
                        collisions_display.insert(
                            0, "exclude", collisions_display["collision_score"] >= 5
                        )
                        edited_coll = st.data_editor(
                            collisions_display,
                            key=f"collisions_{wb_term}",
                            hide_index=True,
                            column_config={
                                "exclude": st.column_config.CheckboxColumn("Exclude", default=False),
                                "collision_score": st.column_config.NumberColumn("Score", format="%.2f"),
                                "volume_share": st.column_config.NumberColumn("Vol share", format="%.1%"),
                            },
                            use_container_width=True,
                        )
                        selected = edited_coll[edited_coll["exclude"]]["follower"].tolist()
                        all_new_exclusions.extend(selected)
                    else:
                        st.caption(f"No significant collisions found for '{wb_term}'.")

                if st.button("Apply selected exclusions to text area", key="apply_exclusions"):
                    existing_excl = [
                        t.strip() for t in st.session_state.get("brand_excl_terms", "").split("\n") if t.strip()
                    ]
                    merged_excl = list(dict.fromkeys(existing_excl + all_new_exclusions))
                    st.session_state["brand_excl_terms"] = "\n".join(merged_excl)
                    st.rerun()

        ai_key = st.session_state.get(BIFROST_API_KEY)
        ai_model = st.session_state.get(BIFROST_MODEL, get_default_model())

        col_detect, col_save = st.columns(2)
        with col_detect:
            if st.button("Detect Brand Terms (AI)", key="brand_detect_btn", disabled=not ai_key):
                try:
                    from engine.ai_engine import detect_brand_terms, get_bifrost_client
                    client = get_bifrost_client(ai_key)
                    top_kws = kw_df.sort_values("volume", ascending=False)["keyword"].head(100).tolist()
                    result_dict, used_model = detect_brand_terms(client, domain_input, top_kws, ai_model)
                    detected = result_dict.get("brand_terms", [])
                    confidence = result_dict.get("confidence", 0)
                    reasoning = result_dict.get("reasoning", "")
                    st.session_state[DETECTED_BRAND_TERMS] = detected
                    st.success(
                        f"Detected {len(detected)} brand terms "
                        f"(confidence: {confidence:.0%}) via {used_model}.\n\n"
                        f"_{reasoning}_"
                    )
                except Exception as e:
                    st.error(f"Brand detection failed: {e}")
            elif not ai_key:
                st.caption("Add your Bi Frost API key in the AI Settings panel to enable auto-detection.")

        # Merge AI-detected terms into substring text before saving
        if DETECTED_BRAND_TERMS in st.session_state:
            existing_manual = [t.strip() for t in terms_text.split("\n") if t.strip()]
            merged = list(dict.fromkeys(existing_manual + st.session_state[DETECTED_BRAND_TERMS]))
            terms_text = "\n".join(merged)

        with col_save:
            if st.button("Save Brand Terms", key="brand_save_btn"):
                saved_terms = [t.strip() for t in terms_text.split("\n") if t.strip()]
                saved_wb = [t.strip() for t in st.session_state.get("brand_wb_terms", "").split("\n") if t.strip()]
                saved_excl = [t.strip() for t in st.session_state.get("brand_excl_terms", "").split("\n") if t.strip()]
                prov = "AI-detected" if DETECTED_BRAND_TERMS in st.session_state else "user-overridden"
                override_assumption(store, "brand_terms", saved_terms, prov)

                # Build v5 BrandConfig and store for downstream pages
                brand_config = BrandConfig(
                    substring_terms=saved_terms,
                    word_boundary_terms=saved_wb,
                    excluded_followers=saved_excl,
                )
                st.session_state["brand_config"] = brand_config
                classifier = build_classifier(brand_config)

                # Apply to kw_df and kw_existing
                updated_kw = st.session_state[KW_DF].copy()
                updated_kw["is_branded"] = updated_kw["keyword"].map(classifier)
                st.session_state[KW_DF] = updated_kw
                if KW_EXISTING in st.session_state:
                    upd_ex = st.session_state[KW_EXISTING].copy()
                    upd_ex["is_branded"] = upd_ex["keyword"].map(classifier)
                    st.session_state[KW_EXISTING] = upd_ex

                n_branded = int(updated_kw["is_branded"].sum())
                n_total = len(updated_kw)
                st.success(
                    f"Saved. {n_branded} branded / {n_total} total keywords "
                    f"({n_branded / n_total * 100:.1f}%). "
                    f"Config stored in session for downstream pages."
                )

                # Stage 3: final preview
                if n_branded > 0:
                    preview_df = updated_kw[updated_kw["is_branded"]].copy()
                    if "volume" in preview_df.columns:
                        preview_df = preview_df.sort_values("volume", ascending=False)
                    preview_cols = [c for c in ["keyword", "volume", "position", "is_branded"] if c in preview_df.columns]
                    with st.expander(f"Stage 3 — Brand match preview (top {min(20, n_branded)} by volume)"):
                        st.write(f"Brand classifier will match **{n_branded}** keywords.")
                        st.dataframe(preview_df[preview_cols].head(20), use_container_width=True, hide_index=True)

        # ── Domain Authority Auto-Derivation ─────────────────────────
        st.divider()
        st.subheader("Domain Authority")

        _brand_config = st.session_state.get("brand_config")
        _brand_fn = build_classifier(_brand_config) if _brand_config is not None else None
        da_auto, da_rationale_auto = estimate_da_from_rankings(kw_df, brand_classifier=_brand_fn)

        if da_auto is not None:
            st.success(f"Auto-detected: **DA = {da_auto}**")
            st.caption(da_rationale_auto)
            use_override = st.checkbox("Override with manual value", value=False, key="da_override_checkbox")
            if use_override:
                da_val = st.number_input(
                    "Manual DA", min_value=1, max_value=100,
                    value=st.session_state.get("da_override", da_auto),
                    key="da_manual_input",
                )
                st.session_state["da_override"] = int(da_val)
                comparison = compare_da_estimate_to_supplied(da_auto, int(da_val), tolerance=10)
                st.info(comparison)
                da_final = int(da_val)
                da_rationale_final = f"User-supplied: {da_final} (auto-estimate was {da_auto})"
            else:
                st.session_state.pop("da_override", None)
                da_final = da_auto
                da_rationale_final = da_rationale_auto
        else:
            st.warning(
                "Auto-estimation needs more non-branded top-10 rankings than this site has. "
                f"_{da_rationale_auto}_"
            )
            da_val = st.number_input(
                "DA (manual)", min_value=1, max_value=100,
                value=st.session_state.get("da", 40),
                key="da_manual_input_fallback",
            )
            da_final = int(da_val)
            da_rationale_final = f"User-supplied: {da_final}"

        st.session_state["da"] = da_final
        st.session_state["da_rationale"] = da_rationale_final

        with st.expander("Sensitivity: DA at different KD percentiles"):
            st.caption("Shows how the DA estimate changes across different percentile thresholds.")
            for pct in [0.50, 0.75, 0.90, 0.95, 0.99]:
                pct_da, _ = estimate_da_from_rankings(kw_df, brand_classifier=_brand_fn, percentile=pct)
                label = f"p{int(pct * 100):02d}"
                val_str = str(pct_da) if pct_da is not None else "n/a"
                st.write(f"  **{label}** → DA = {val_str}")

    elif uploaded_semrush is not None:
        st.error("Could not parse the uploaded SEMrush file. Please check the format.")

# ── Roadmap Tab ───────────────────────────────────────────────────────────────
with tab_roadmap:
    st.markdown(
        "Upload your SEO roadmap to extract **per-focus-area effort levels**, "
        "**monthly hours**, and **content cadence** using AI — giving the forecast engines "
        "richer signal than a single effort-level scalar."
    )
    st.caption("Accepts xlsx or CSV files. AI extraction requires Bi Frost API access; falls back to legacy scalar detection if unavailable.")

    _ai_client = get_bifrost_client(st.session_state.get(BIFROST_API_KEY))
    _ai_model = st.session_state.get(BIFROST_MODEL, get_default_model())
    _ai_available = _ai_client is not None
    _roadmap_cache = st.session_state.setdefault(ROADMAP_AI_CACHE, {})

    uploaded_roadmap = st.file_uploader(
        "Upload roadmap file",
        type=["csv", "xlsx", "xls", "tsv"],
        key="roadmap_upload",
    )

    if uploaded_roadmap is not None:
        _raw_bytes = uploaded_roadmap.read()
        _ext = uploaded_roadmap.name.rsplit(".", 1)[-1] if "." in uploaded_roadmap.name else "csv"
        st.session_state[ROADMAP_RAW_BYTES] = _raw_bytes
        st.session_state[ROADMAP_FILE_EXT] = _ext

    _raw_bytes = st.session_state.get(ROADMAP_RAW_BYTES)

    if _raw_bytes is not None:
        if _ai_available:
            # ── AI extraction flow ─────────────────────────────────────────
            _ext = st.session_state.get(ROADMAP_FILE_EXT, "csv")

            col_ext, col_btn = st.columns([3, 1])
            with col_btn:
                _do_extract = st.button("Extract with AI", key="roadmap_ai_extract", type="primary")

            if _do_extract or ROADMAP_BUNDLE not in st.session_state:
                _ck = compute_cache_key(_raw_bytes, None, _ai_model)
                if not _do_extract and _ck in _roadmap_cache:
                    _bundle = _roadmap_cache[_ck]["bundle"]
                    _used_model = _roadmap_cache[_ck]["model"]
                    st.session_state[ROADMAP_BUNDLE] = _bundle
                    st.session_state[ROADMAP_CONTENT_PLAN] = _bundle.get("content_plan", [])
                    st.session_state[ROADMAP_USED_MODEL] = _used_model
                else:
                    with st.spinner("Ingesting roadmap…"):
                        try:
                            _fname = f"roadmap.{_ext}"
                            _bundle, _used_model = load_roadmap_v2(
                                _ai_client, _raw_bytes, _fname, model=_ai_model,
                            )
                            _roadmap_cache[_ck] = {"bundle": _bundle, "model": _used_model}
                            st.session_state[ROADMAP_BUNDLE] = _bundle
                            st.session_state[ROADMAP_CONTENT_PLAN] = _bundle.get("content_plan", [])
                            st.session_state[ROADMAP_USED_MODEL] = _used_model
                        except ValueError as _ve:
                            st.error("Roadmap parsed but failed validation:")
                            st.code(str(_ve), language="text")
                            st.warning(
                                "This usually means the file structure differs from expected. "
                                "Try re-uploading after correcting the highlighted rows, "
                                "or fall back to the legacy loader below."
                            )
                            try:
                                _legacy = load_roadmap(_raw_bytes)
                                if _legacy:
                                    run_detection(store, roadmap_data=_legacy)
                                    st.session_state[ROADMAP_DATA] = _legacy
                                    st.info("Legacy fallback succeeded with reduced fidelity (3 scalars only).")
                            except Exception as _e2:
                                st.error(f"Legacy fallback also failed: {_e2}")
                        except Exception as _e:
                            import traceback
                            st.error(f"Roadmap ingestion failed: {_e}")
                            with st.expander("Show error details"):
                                st.code(traceback.format_exc(), language="text")
                            st.warning("Falling back to legacy loader — extraction will be limited to three scalars.")
                            try:
                                _legacy = load_roadmap(_raw_bytes)
                                if _legacy:
                                    run_detection(store, roadmap_data=_legacy)
                                    st.session_state[ROADMAP_DATA] = _legacy
                            except Exception as _e2:
                                st.error(f"Legacy fallback also failed: {_e2}")

            _bundle = st.session_state.get(ROADMAP_BUNDLE)
            if _bundle:
                _ss = _bundle.get("source_summary", {})
                _used_model_label = st.session_state.get(ROADMAP_USED_MODEL, _ai_model)

                # Confidence banner
                _conf = _ss.get("parsing_confidence", 0.9)
                if _conf < 0.7:
                    st.warning(
                        f"Parsing confidence is low ({_conf:.0%}). Review the extraction carefully "
                        "before applying to assumptions."
                    )

                # ── Strategy at a glance ─────────────────────────────────
                _strategy_summary = _bundle.get("strategy_summary", "")
                _primary_domain = _bundle.get("primary_domain", "")
                _loc_domains = _bundle.get("localisation_domains", [])
                _client_name = _bundle.get("client_metadata", {}).get("client_name", "")

                if _strategy_summary or _primary_domain:
                    with st.container(border=True):
                        st.markdown("**Strategy at a Glance**")
                        if _client_name:
                            st.caption(f"Client: {_client_name}")
                        if _strategy_summary:
                            st.markdown(_strategy_summary)
                        _domain_cols = st.columns(2)
                        with _domain_cols[0]:
                            if _primary_domain:
                                st.markdown(f"**Primary domain:** `{_primary_domain}`")
                        with _domain_cols[1]:
                            if _loc_domains:
                                _loc_list = ", ".join(f"`{d}`" for d in _loc_domains)
                                st.markdown(f"**Localisation:** {_loc_list}")

                # ── Validation warnings (tiered — not errors) ───────────
                _warnings = _bundle.get("validation_warnings", [])
                if _warnings:
                    with st.expander(f"⚠ {len(_warnings)} data-quality warning(s)", expanded=False):
                        for _w in _warnings:
                            st.markdown(f"- {_w}")

                # KPI cards
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Items Detected", _ss.get("total_tasks_detected", "—"))
                _launches = _ss.get("content_launches_detected", 0)
                if _launches:
                    k1.caption(f"({_launches} content launches)")
                k2.metric("Focus Areas", len(_ss.get("focus_areas_detected", [])))
                k3.metric("Timeline", f"{_ss.get('timeline_months_covered', '—')} months")
                k4.metric("Confidence", f"{_conf:.0%}")
                st.caption(f"Extracted via {_used_model_label}")

                # Recommendations
                _recs = _bundle.get("recommendations", [])
                if _recs:
                    st.subheader("Recommendations")
                    for _r in _recs:
                        _sev = _r.get("severity", "info")
                        _msg = _r.get("message", "")
                        if _sev == "warning":
                            st.warning(_msg)
                        else:
                            st.info(_msg)

                # Per-focus breakdown table
                st.subheader("Per-Focus Breakdown")
                _focus_rows = []
                for _fk in ("content", "technical", "on_page", "off_page", "local", "analytics", "strategy"):
                    _fd = _bundle.get("per_focus", {}).get(_fk, {})
                    _focus_rows.append({
                        "Focus Area": _fk.replace("_", " ").title(),
                        "Effort Level": _fd.get("effort_level", "—"),
                        "Monthly Hours": _fd.get("monthly_hours", 0.0),
                        "Cadence": _fd.get("cadence", 0),
                        "Tasks": _fd.get("task_count", 0),
                    })
                st.dataframe(pd.DataFrame(_focus_rows), use_container_width=True, hide_index=True)

                st.divider()
                st.subheader("Correct the Extraction")

                _nl_correction = st.text_area(
                    "Natural language correction",
                    placeholder="e.g., 'Technical audit is quarterly not bi-annual, and content production is 20 hours not 10'",
                    key="roadmap_nl_correction",
                    height=80,
                )
                _json_edit = st.text_area(
                    "JSON editor (edit directly, then click Re-extract or Apply)",
                    value=json.dumps(_bundle, indent=2),
                    key="roadmap_json_edit",
                    height=280,
                )

                # Token estimate for transparency
                _schema_str = json.dumps(ROADMAP_BUNDLE_SCHEMA)
                _est_tokens = estimate_extraction_tokens(
                    roadmap_md=str(_raw_bytes[:4000]),
                    correction_ctx=_nl_correction or "",
                    schema_str=_schema_str,
                )
                st.caption(f"AI call cost: ~{_est_tokens:,} tokens estimated")

                col_reext, col_apply = st.columns(2)
                with col_reext:
                    if st.button("Re-extract (AI)", key="roadmap_reextract"):
                        if _nl_correction.strip():
                            _ck2 = compute_cache_key(_raw_bytes, _nl_correction.strip(), _ai_model)
                            if _ck2 in _roadmap_cache:
                                _new_bundle = _roadmap_cache[_ck2]["bundle"]
                                _new_model = _roadmap_cache[_ck2]["model"]
                                st.session_state[ROADMAP_BUNDLE] = _new_bundle
                                st.session_state[ROADMAP_CONTENT_PLAN] = _new_bundle.get("content_plan", [])
                                st.session_state[ROADMAP_USED_MODEL] = _new_model
                                st.rerun()
                            else:
                                with st.spinner("Re-running ingestion with correction…"):
                                    try:
                                        _fname = f"roadmap.{_ext}"
                                        _new_bundle, _new_model = load_roadmap_v2(
                                            _ai_client, _raw_bytes, _fname,
                                            nl_correction=_nl_correction.strip(),
                                            previous_bundle=_bundle,
                                            model=_ai_model,
                                        )
                                        _roadmap_cache[_ck2] = {"bundle": _new_bundle, "model": _new_model}
                                        st.session_state[ROADMAP_BUNDLE] = _new_bundle
                                        st.session_state[ROADMAP_CONTENT_PLAN] = _new_bundle.get("content_plan", [])
                                        st.session_state[ROADMAP_USED_MODEL] = _new_model
                                        st.rerun()
                                    except Exception as _e:
                                        st.error(f"Re-extraction failed: {_e}")
                        else:
                            # No NL — try to parse JSON editor
                            try:
                                _edited = json.loads(_json_edit)
                                st.session_state[ROADMAP_BUNDLE] = _edited
                                st.rerun()
                            except json.JSONDecodeError as _je:
                                st.error(f"JSON parse error: {_je}. Fix the JSON or enter a natural-language correction.")

                with col_apply:
                    if st.button("Apply to assumptions", key="roadmap_apply", type="primary"):
                        try:
                            _to_apply = json.loads(_json_edit)
                        except json.JSONDecodeError:
                            _to_apply = _bundle
                        run_detection(store, roadmap_data=_to_apply)
                        st.session_state[ROADMAP_DATA] = _to_apply
                        st.session_state[ROADMAP_BUNDLE] = _to_apply
                        st.session_state[ROADMAP_CONTENT_PLAN] = _to_apply.get("content_plan", [])
                        st.success("Roadmap assumptions applied.")

        else:
            # ── No AI key — legacy fallback ────────────────────────────────
            st.warning(
                "Bi Frost API key not configured — using legacy scalar extraction. "
                "Set up your API key in the sidebar to enable rich per-focus-area extraction."
            )
            try:
                _legacy = load_roadmap(_raw_bytes)
                if _legacy:
                    run_detection(store, roadmap_data=_legacy)
                    st.session_state[ROADMAP_DATA] = _legacy
                    _dkeys = [k for k in ("content_cadence", "effort_level", "maintenance_coverage") if k in _legacy]
                    st.success(f"Roadmap loaded (legacy). Detected: {', '.join(_dkeys)}.")
                    _disp = [{"Parameter": k.replace("_", " ").title(), "Value": _legacy[k]} for k in _dkeys]
                    st.table(pd.DataFrame(_disp))
                else:
                    st.warning("Roadmap file parsed but no recognisable parameters found. Check column names.")
            except Exception as _e:
                st.error(f"Could not parse roadmap: {_e}")

    elif ROADMAP_BUNDLE in st.session_state:
        _prev = st.session_state[ROADMAP_BUNDLE].get("source_summary", {})
        st.info(
            f"Roadmap from previous upload: {_prev.get('total_tasks_detected', '—')} tasks, "
            f"{len(_prev.get('focus_areas_detected', []))} focus areas, "
            f"confidence {_prev.get('parsing_confidence', 0):.0%}. "
            "Upload a new file to re-extract."
        )
    elif ROADMAP_DATA in st.session_state:
        _rd = st.session_state[ROADMAP_DATA]
        st.info(
            f"Roadmap from previous upload: cadence={_rd.get('content_cadence', '—')}, "
            f"effort={_rd.get('effort_level', '—')}, "
            f"maintenance={_rd.get('maintenance_coverage', '—')}"
        )

# ── Data Status Footer ────────────────────────────────────────────────────────
st.divider()
st.subheader("Data Status")
col1, col2, col3 = st.columns(3)
with col1:
    if GA4_DF in st.session_state:
        ga4 = st.session_state[GA4_DF]
        st.success(f"GA4: {len(ga4)} months loaded ({ga4['date'].min().strftime('%b %Y')} – {ga4['date'].max().strftime('%b %Y')})")
    else:
        st.info("GA4: Not loaded")
with col2:
    if KW_DF in st.session_state:
        kw = st.session_state[KW_DF]
        st.success(f"Keywords: {len(kw)} loaded ({len(st.session_state.get('kw_existing', []))} ranking)")
    else:
        st.info("Keywords: Not loaded")
with col3:
    if ROADMAP_BUNDLE in st.session_state:
        _rb_ss = st.session_state[ROADMAP_BUNDLE].get("source_summary", {})
        st.success(f"Roadmap: {_rb_ss.get('total_tasks_detected', '?')} tasks (AI extracted)")
    elif ROADMAP_DATA in st.session_state:
        st.success("Roadmap: loaded (legacy)")
    else:
        st.info("Roadmap: Not loaded")

# ── Assumptions Panel ─────────────────────────────────────────────────────────
st.divider()
render_assumptions_banner(store)
render_assumptions_panel(store)
