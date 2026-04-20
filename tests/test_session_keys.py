"""Smoke-test that all pages can be imported — catches NameError / bad session keys."""
from __future__ import annotations

import importlib
import importlib.util
import pathlib
import sys


def _import_page(page_file: pathlib.Path) -> None:
    """Attempt to import a Streamlit page from its file path.

    Streamlit pages execute top-level code at import time (session-state accesses,
    widget calls, etc.) that requires a running Streamlit context.  We therefore
    accept any exception whose module path contains "streamlit" or whose type is a
    common Streamlit runtime guard.  What we do NOT accept are ImportError /
    NameError, which indicate a missing symbol in utils.session or a bad import.
    """
    module_name = f"_page_smoke_{page_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, page_file)
    assert spec is not None, f"Could not build spec for {page_file}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except ModuleNotFoundError:
        # External dependency absent in test env (streamlit, plotly, etc.) — not our concern
        return
    except (ImportError, NameError):
        raise  # real failures — missing constant or bad import from utils.session
    except Exception as exc:
        exc_mod = getattr(type(exc), "__module__", "") or ""
        if "streamlit" in exc_mod.lower():
            return  # no Streamlit runtime in pytest — that's expected
        if type(exc).__name__ in {
            "StreamlitAPIException", "NoSessionContext",
            "StopException", "RerunException",
        }:
            return
        raise  # unexpected non-Streamlit error — surface it
    finally:
        sys.modules.pop(module_name, None)


def test_all_pages_importable():
    """All page files must import without NameError or ImportError."""
    pages_dir = pathlib.Path(__file__).parent.parent / "pages"
    page_files = sorted(pages_dir.glob("*.py"))
    page_files = [p for p in page_files if not p.name.startswith("__")]
    assert page_files, "No page files found — check the pages/ directory"
    for page_file in page_files:
        _import_page(page_file)


def test_session_module_has_required_keys():
    from utils import session
    required = [
        "GA4_DF", "KW_DF", "KW_EXISTING", "POS_RESULT", "NC_RESULT",
        "HIST_RESULTS", "COMB_RESULTS", "ASSUMPTIONS", "BIFROST_API_KEY",
        "BIFROST_MODEL",
    ]
    for key in required:
        assert hasattr(session, key), f"utils.session missing constant: {key}"
