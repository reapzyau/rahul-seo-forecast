# CLAUDE.md — SEO Traffic & Revenue Forecasting Engine

## Module layout

```
app.py                  # Streamlit home page + shared sidebar (AI settings)
pages/                  # One file per page (numbered for sidebar order)
  1_Data_Upload.py      # Upload, brand filtering, seasonality tuning, assumptions
  2_Positional_Forecast.py   # MC uplift for existing keywords (P10/P50/P90)
  3_New_Content_Forecast.py  # Probabilistic ranking for net-new keywords
  3_Diagnostics.py      # AIO risk | keyword pipeline | decay projection (tabs)
  4_Historical_Forecast.py   # Holt / Prophet baseline from GA4 history
  4_Roadmap.py          # AI content roadmap | GAZMAN SEO task hours (tabs)
  5_Combined_Forecast.py     # Canonical hub: baseline + streams − decay
  5_Deliverables.py     # Forecast grid XLSX | variance analysis | methodology (tabs)
engine/                 # Pure-Python computation — no Streamlit imports
utils/                  # Shared helpers (charts, export, data loading, sidebar)
  page_base.py          # setup_page() — shared header/assumptions scaffold
config/                 # models.json — model catalogue and fallback chain
prompts/                # Prompt templates (system + user) for AI features
assets/                 # Sample CSV files
tests/                  # pytest unit tests (engine logic only, no Streamlit)
```

> **Note:** Pages 2_Positional_Forecast, 3_New_Content_Forecast, 4_Historical_Forecast,
> and 5_Combined_Forecast are pending consolidation into a single 2_Forecast.py (sub-phase 2.1).
> Until that is done, they remain as individual pages alongside the new consolidated pages.

Pages import from `engine/` and `utils/`. Engine modules never import from pages or utils.

## Session state wiring

The Data Upload page (1_Data_Upload.py) is the single source for uploaded data. It populates:

- `st.session_state["ga4_df"]` — post-filter GA4 monthly traffic frame
- `st.session_state["kw_df"]` — full SEMrush portfolio
- `st.session_state["kw_existing"]` — keywords with position <= 100 (ranking)
- `st.session_state["kw_new"]` — keywords not ranking (typically empty for SEMrush exports)

Downstream pages (Positional, AIO Risk, Combined, Grid Export) read from these keys. If a page can't find the data, it should warn and `st.stop()` rather than prompting for re-upload.

## GA4 anchoring

The positional engine accepts a `ga4_baseline: int` parameter. When set, the engine rescales SEMrush's estimated traffic so that the month-1 baseline matches the real GA4 baseline. SEMrush traffic estimates are typically 20-40% higher than real GA4 organic sessions; anchoring keeps forecasts defensible.

## Positional vs. New Content modes

- **Positional** = for keywords that already rank (position 1-100). Projects uplift from moving them up the SERP. This is the default workflow because SEMrush exports only contain keywords you rank for.
- **New Content** = for net-new keywords (gap analysis output, target keyword lists from a strategist). Uses probabilistic ranking based on DA vs. KD. Requires a separate upload — SEMrush alone can't populate this.

## v3 architecture: forecasts are bands, not lines

From v3, the positional engine returns P10/P50/P90 monthly data via Monte Carlo simulation (500 trials). Every downstream consumer handles bands. Pages that need a single number use P50 with a label saying "P50 (median scenario)".

## Combined Forecast is the canonical hub

Every downstream page (AIO Risk, SEO Roadmap, Forecast Grid Export, Variance) reads from Combined first. Fallback order: Combined → Positional → Historical → New Content → error. The v4 Combined engine layers: `baseline + positional_uplift + new_content - decay`. AIO is no longer a separate deduction — it is baked into positional and new content via per-stream CTR penalty.

## Attention curve is on by default

The portfolio attention curve (top 5% full effort, bottom 50% at 0.05 weight) is enabled by default. Can be disabled via sidebar toggle for raw forecasts. This addresses the v2 calibration concern: "moderate" effort now yields 30-50% uplift instead of 75%.

## Snapshots are user-owned files

Streamlit Community Cloud has no persistent storage. Forecast snapshots are downloadable JSON that the analyst keeps alongside the multi-channel plan. Upload back via the Variance page to grade forecasts. No server-side storage.

## Seasonality is per-stream (v4)

In v4, seasonality is applied per-stream inside each engine (positional, new content, historical v4). Engines accept `seasonality: dict` and `forecast_start_month: int` parameters. The old pattern of applying seasonality post-hoc in a Seasonality page has been removed — `pages/6_Seasonality.py` has been deleted; its monthly modifier editor and comparison chart now live in `pages/1_Data_Upload.py` under "Seasonality Tuning".

Learned seasonality is stored in `st.session_state["seasonality"]` by the Data Upload page and consumed by forecast pages.

## AIO and seasonality are per-stream (v4)

New engines should consume `aio_intent_penalties` and `seasonality` as parameters, not as post-processing steps. Apply AIO at the CTR computation step; apply seasonality to monthly totals. This ensures P10/P50/P90 bands reflect seasonal variation.

## Prophet dependency is optional

`engine/prophet_engine.py` wraps the `prophet` import in a try/except and raises `ImportError` with a clear message. `engine/historical_engine.py::run_historical_forecast_v4` catches this and falls back to Holt's or linear. Prophet's presence is reflected in `result.attrs["prophet_available"]`. Install via `pip install -r requirements-prophet.txt` if Prophet support is wanted.

## Maturation curve is unified

New content and positional engines both use `engine/maturation_curve.py::maturation_schedule()` / `logistic_progress()`. Do not reimplement ramp logic in new engines — import from maturation_curve.

## Historical movement stats are learned per-portfolio

`engine/positional_engine.py::learn_movement_from_history(kw_df)` derives per-tier movement stats when `previous_position` is available. The positional page calls this automatically and passes results to `run_positional_forecast_mc`. Tiers with <10 samples fall back to `_BASE_GAIN_BY_TIER`.

## Brand filtering is a pre-processing step

Brand classification happens at Data Upload time (via AI or manual entry), tagging `kw_df["is_branded"]`. Forecast pages filter branded keywords out **before** running engines when `exclude_brand_from_forecasts = True`. This is not a post-hoc filter — it prevents distorting uplift math with keywords already at position 1.

## The FY-date reconstruction gotcha

The GA4 Revenue sheet ships with date values where the Financial Year is encoded as day-of-month ("day=23" means FY23). `utils/ga4_loader.py` detects this and reconstructs real dates using the AU financial year convention (FY24 = Jul 2023 – Jun 2024). When adding new GA4 sheet handling, remember this.

## Forecast grid output format

`utils/forecast_grid.py::build_seo_forecast_grid` produces an xlsx matching the SEO row of the Pattern multi-channel plan (GAZMAN-style): monthly columns grouped as Forecast / Actual / % Var, with rows for Traffic / Transactions / Revenue. The analyst pastes this directly into the plan template.

## Conventions

### Seeded randomness
All stochastic outputs use `np.random.default_rng(seed)` (not the legacy `RandomState`).
Seeds are derived as `seed + keyword_index + OFFSET` (offsets: 1000 for ranking roll, 2000 for position, 3000 for time-to-rank) so each calculation is independent but deterministic.

### Chart wrapper
All Plotly figures go through `utils/chart_builder._apply_layout(fig, title, xaxis, yaxis)` for consistent styling (white background, unified hover, branded colours).

### Flexible column matching
Upload parsers in `utils/data_loader.py` use `*_COL_ALIASES` dicts (`KEYWORD_COL_ALIASES`, `TRAFFIC_COL_ALIASES`, etc.) to accept common column name variants before falling back to AI transform.

### DataFrame metadata
Per-run metadata (e.g. number of excluded keywords) is attached via `df.attrs["key"] = value` rather than adding columns. Access with `df.attrs.get("key", default)`.

### Forecast gating
**Never** run forecast computation inline — always gate behind `st.button(...)` and store results in `st.session_state`. Streamlit reruns the whole page on every widget change; inline computation would recalculate on every slider move.

## Critical: exec() on LLM output

`execute_transform()` in `engine/ai_engine.py` runs AI-generated pandas code via `exec()`.
It applies a blocklist (`_BLOCKED_CODE_PATTERNS`) and restricted builtins before executing.

**Do not remove these guards.** Replacing `exec()` with a declarative JSON transform spec is planned for Phase 4 — see `engine/transform_spec.py` once that phase ships.

## AI integration (Bi Frost)

- Client wrapper: `utils/bifrost.py` — follows the Bi Frost integration skill pattern; `get_client()`, `call()`, `call_with_fallback()`
- `engine/ai_engine.get_bifrost_client()` is a re-export of `utils.bifrost.get_client` for backward compatibility
- Base URL: `https://bifrost.pattern.com/v1` (Chat Completions API, not Responses)
- Fallback: `generate_with_fallback()` delegates to `utils.bifrost.call_with_fallback()`, which walks the chain in `config/models.json`
- Model catalogue: `config/models.json` — single source of truth for model IDs, labels, fallback chain, and per-feature defaults
- Per-feature model overrides live in `features.{feature_name}` in `config/models.json`; `get_model_for_feature()` resolves: user override → feature default → global default
- Default model: `anthropic/claude-haiku-4-5` — fast and cheap; Sonnet used for complex extraction tasks
- Prompts: `prompts/*.txt` — `[meta]` header block followed by system instructions, then `---`, then user template (`$variable` placeholders); loaded via `_load_prompt()`

### Adding a new AI feature

1. Create `prompts/feature_name.txt` with `[meta]` header block, system instructions, `---`, and user template (`$variable` placeholders)
2. Add an entry in `config/models.json` under `features` to set the preferred model for this feature
3. Add function in `engine/ai_engine.py` that calls `get_model_for_feature("feature_name", user_override=model)` and then `generate_with_fallback()` — returns `(result, used_model)` tuple
4. In the page, handle the tuple and show fallback info if `used_model != ai_model`

### Changing models

Edit `config/models.json` — do not hardcode model IDs in Python files. The sidebar loads from this file.

## Running tests

```bash
pytest tests/ -v
```

Tests cover engine logic only. No Streamlit or network calls in tests.

## Running checks locally

```bash
ruff check .                 # lint
python -m pytest tests/ -v   # unit tests
python -c "import importlib.util, pathlib, sys; spec = importlib.util.spec_from_file_location('p', 'pages/1_Data_Upload.py'); m = importlib.util.module_from_spec(spec); sys.modules['p'] = m; spec.loader.exec_module(m)"  # manual page-import smoke
```

CI runs all three on every push: ruff lint → page-import smoke → pytest.

## Adding a new page

1. Create `pages/N_Name.py`
2. Call `setup_page(title, caption, show_assumptions_banner=...)` from `utils.page_base` at the top — this handles the header, AI settings sidebar, and assumptions initialisation
3. Gate any heavy computation behind `st.button` + `st.session_state`
4. Add at least one test in `tests/test_engines.py` for any new engine logic

## Adding a new engine module

1. Create `engine/my_engine.py` — pure Python, no Streamlit imports
2. Export from `engine/__init__.py` if needed
3. Write tests in `tests/test_engines.py`

## Assumptions store (v4)

`engine/assumptions.py` is the single source of truth for all forecast parameters. It provides:

- `ASSUMPTIONS` registry — 30+ keyed entries including: blended_cr_pct, aov, currency, effort_level, content_cadence, maintenance_coverage, aio_monthly_growth, aio_ctr_penalty_informational, decay_rate_top3, decay_rate_top10, plus ~20 per-focus keys (`content_effort_level`, `content_monthly_hours`, etc.) and metadata keys (`client_name`, `industry`, `brand_terms`, `timeline_months_covered`, `strategy_restart_month`, `retainer_aud_monthly`)
- Provenance tracking: `"defaulted"` | `"detected"` | `"overridden"`
- Session state API (all functions take an explicit `store: dict` parameter — no Streamlit import):
  - `initialise_assumptions(store, force=False)` — populate with defaults; no-op if already done
  - `run_detection(store, ga4_df=None, kw_df=None, roadmap_data=None)` — auto-detect values from data
  - `override_assumption(store, key, value, source=...)` — explicit user override
  - `clear_override(store, key)` — revert to default
  - `get_assumption(store, key)` — current value
  - `get_provenance(store, key)` — full provenance dict
  - `assumptions_summary(store)` — list of all provenance dicts

**In pages**, always use:
```python
store = st.session_state.setdefault("assumptions", {})
initialise_assumptions(store)
```
Then read values with `get_assumption(store, "blended_cr_pct")` instead of hardcoding defaults.

`utils/assumptions_panel.py` provides two Streamlit components:
- `render_assumptions_banner(store)` — compact info bar with provenance counts; call after the page header
- `render_assumptions_panel(store)` — full table with override widgets; shown at bottom of Data Upload page

## Roadmap ingestion (v4.9)

The entry point is **`engine.roadmap_ai_engine.load_roadmap_v2(client, raw_bytes, filename)`** — do not call `extract_roadmap_with_ai()` or `utils.roadmap_loader.load_roadmap()` from new code.

`load_roadmap_v2()` dispatches based on format detection:
- **pattern_native** (Pattern SOW xlsx with Breakdown sheet) → `engine.roadmap_native_parser.parse_pattern_native()` (deterministic) + optional AI enrichment
- **task_table** (Task/Focus/Occurrence/Hours CSV) → legacy parser wrapped as v2 bundle + optional AI enrichment
- **param_table** (cadence/effort_level CSV) → legacy parser, no AI enrichment
- **unknown** → `extract_roadmap_full_ai()` (requires Bi Frost client)

The v2 bundle is the canonical output schema — `schema_version: "2.0"` with `per_focus`, `content_plan`, `timeline`, `global_rollup` keys.

**`roadmap_content_plan`** — the `content_plan` array is stored separately in `st.session_state["roadmap_content_plan"]` (list of dicts) and passed to `run_new_content_forecast(roadmap_content_plan=...)`. New Content keywords are matched to plan URLs by substring; matched keywords use the plan's `publish_month`.

Per-focus assumption keys are the source of truth; the three legacy scalars (`effort_level`, `content_cadence`, `maintenance_coverage`) are **computed rollups** — do not set them directly from new code. They are derived by `recompute_rollups(store)`.

Caching: extraction results are cached in `st.session_state["roadmap_ai_cache"]` keyed by `compute_cache_key(raw_bytes, nl_correction, model)`. The page checks this before calling `load_roadmap_v2`.

`utils/roadmap_loader.py` is the **legacy scalar loader** — retained for CI tests and no-AI fallback only.

## Seasonality and AIO (per-stream, v4)

Seasonality and AIO penalties are applied **inside each engine**, not post-hoc:
- All three stream engines (`run_historical_forecast_v4`, `run_positional_forecast_mc`, `run_new_content_forecast`) accept `seasonality: dict` and apply monthly multipliers to their output.
- AIO CTR penalties are applied at the keyword CTR computation step via `aio_intent_penalties: dict`.
- The AIO Risk page (page 7) is a **diagnostic view only** — traffic impact is already in the stream forecasts.
- Combined Forecast math: `combined = baseline + positional + new_content − decay` (no separate AIO deduction).

## Industry priors

`engine.seasonality_engine.INDUSTRY_SEASONALITY_PRIORS` contains per-month additive `traffic_mod` adjustments for 11 industries. These are **authored defaults, not data-derived** — label them as such in any UI. `apply_industry_bias(seasonality, industry, bias_weight)` blends priors into the base seasonality on top of GA4 learning.
