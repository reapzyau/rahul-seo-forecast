# CLAUDE.md — SEO Traffic & Revenue Forecasting Engine

## Module layout

```
app.py                  # Streamlit home page + shared sidebar (AI settings)
pages/                  # One file per page (numbered for sidebar order)
engine/                 # Pure-Python computation — no Streamlit imports
utils/                  # Shared helpers (charts, export, data loading, sidebar)
assets/                 # Sample CSV files
tests/                  # pytest unit tests (engine logic only, no Streamlit)
```

Pages import from `engine/` and `utils/`. Engine modules never import from pages or utils.

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
- Base URL: `https://bifrost.pattern.com/openai` (Responses API, not Chat Completions)
- All calls go through `_call_bifrost(client, model, instructions, user_input)` helper
- Default model: `openai/gpt-5.4-mini`

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
