import os
from collections import Counter
from urllib.parse import urlparse

import plotly.graph_objects as go
import streamlit as st

from engine.ai_engine import get_bifrost_client, get_default_model
from engine.assumptions import get_assumption, override_assumption
from engine.brand_classifier import (
    BrandConfig,
    build_classifier,
    detect_collisions,
    suggest_branded_candidates,
)
from engine.v5.da_estimator import compare_da_estimate_to_supplied, estimate_da_from_rankings
from utils.assumptions_panel import render_assumptions_banner
from utils.chart_builder import _apply_layout
from utils.design_tokens import PRIMARY
from utils.keyword_loader import load_keyword_portfolio, split_existing_vs_new
from utils.page_base import setup_page
from utils.session import (
    BIFROST_API_KEY,
    BIFROST_MODEL,
    DETECTED_BRAND_TERMS,
    GA4_DF,
    KW_DF,
    KW_EXISTING,
    KW_NEW,
    ROADMAP_BUNDLE,
    ROADMAP_DATA,
)

store = setup_page(
    "SEMrush Keywords",
    "Upload your SEMrush organic positions export. Brand classification and DA estimation run on this data.",
    show_assumptions_banner=False,
)

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
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "sample-semrush-export.xlsx"
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

# ── Data Status ───────────────────────────────────────────────────────────────
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
        st.success(f"Keywords: {len(kw)} loaded ({len(st.session_state.get(KW_EXISTING, []))} ranking)")
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

# ── Assumptions Banner ────────────────────────────────────────────────────────
st.divider()
render_assumptions_banner(store)
