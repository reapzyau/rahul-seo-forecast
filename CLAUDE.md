# CLAUDE.md — SEO Traffic & Revenue Forecasting Engine

## Module layout

```
app.py                  # Streamlit home page + shared sidebar (AI settings)
pages/                  # One file per page (numbered for sidebar order)
engine/                 # Pure-Python computation — no Streamlit imports
utils/                  # Shared helpers (charts, export, data loading, sidebar)
config/                 # models.json — model catalogue and fallback chain
prompts/                # Prompt templates (system + user) for AI features
assets/                 # Sample CSV files
tests/                  # pytest unit tests (engine logic only, no Streamlit)
```

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

## Known calibration concerns

The positional engine's "moderate" effort level currently projects ~75% uplift over baseline at month 12 on the Cable Melbourne test data. This is on the aggressive end of realistic — a properly-run SEO engagement typically delivers 30-50% over 12 months. The tuning knob is `engine/positional_engine.py::estimate_target_position` (the `base_gain` per KD tier). Calibration against real campaign outcomes is pending.

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

**Do not remove these guards.** If you need a new transform capability, add it to `_SAFE_BUILTINS` explicitly rather than widening the allowlist.
A better long-term approach: have the LLM return a JSON transform spec (rename map, filter rules) and interpret it in pure pandas with no `exec`.

## AI integration (Bi Frost)

- Client: `engine/ai_engine.get_bifrost_client()` — reads key from session state → secrets → env var
- Base URL: `https://bifrost.pattern.com/v1` (Chat Completions API, not Responses)
- All calls go through `_call_bifrost(client, model, instructions, user_input)` → `client.chat.completions.create()`
- Fallback: `generate_with_fallback()` tries the selected model, then walks the chain in `config/models.json`
- Model catalogue: `config/models.json` — single source of truth for model IDs, labels, and fallback chain
- Prompts: `prompts/*.txt` — system instructions + user template separated by `---`, loaded via `_load_prompt()`
- Default model: `openai/gpt-4o-mini` (set in `config/models.json`)

### Adding a new AI feature

1. Create `prompts/feature_name.txt` with system instructions and user template (use `$variable` placeholders)
2. Add function in `engine/ai_engine.py` that calls `generate_with_fallback()` — returns `(result, used_model)` tuple
3. In the page, handle the tuple and show fallback info if `used_model != ai_model`

### Changing models

Edit `config/models.json` — do not hardcode model IDs in Python files. The sidebar loads from this file.

## Running tests

```bash
pytest tests/ -v
```

Tests cover engine logic only. No Streamlit or network calls in tests.

## Adding a new page

1. Create `pages/N_Name.py`
2. Import `render_ai_settings` from `utils.sidebar` and call it after the page header
3. Gate any heavy computation behind `st.button` + `st.session_state`
4. Add at least one test in `tests/test_engines.py` for any new engine logic

## Adding a new engine module

1. Create `engine/my_engine.py` — pure Python, no Streamlit imports
2. Export from `engine/__init__.py` if needed
3. Write tests in `tests/test_engines.py`
