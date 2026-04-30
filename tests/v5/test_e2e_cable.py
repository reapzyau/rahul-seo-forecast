"""End-to-end regression tests for the Cable fixture.

These tests require real input files defined via environment variables and are
skipped automatically when those vars are absent (e.g. in CI without fixtures).

Set the following env vars to enable:
    E2E_GA4_PATH      — path to a real Cable GA4 XLSX
    E2E_SEMRUSH_PATH  — path to a real Cable SEMrush CSV
    E2E_CLIENT_NAME   — client display name (default: "Cable E2E")
    E2E_MONTHS        — forecast horizon in months (default: 12)
    E2E_DA            — domain authority (default: 30)
    E2E_OUTPUT_DIR    — output directory (default: "outputs")
"""

from __future__ import annotations

import json
import os

import pytest

_GA4_PATH = os.getenv("E2E_GA4_PATH")
_SEMRUSH_PATH = os.getenv("E2E_SEMRUSH_PATH")
_FIXTURE_AVAILABLE = bool(_GA4_PATH and _SEMRUSH_PATH)

pytestmark = pytest.mark.skipif(
    not _FIXTURE_AVAILABLE,
    reason="Cable e2e fixture env vars not set (E2E_GA4_PATH / E2E_SEMRUSH_PATH)",
)


@pytest.fixture(scope="module")
def e2e_result(tmp_path_factory):
    from scripts.run_forecast_e2e import run
    tmpdir = str(tmp_path_factory.mktemp("e2e_outputs"))
    return run(
        ga4_path=_GA4_PATH,
        semrush_path=_SEMRUSH_PATH,
        client_name=os.getenv("E2E_CLIENT_NAME", "Cable E2E"),
        months=int(os.getenv("E2E_MONTHS", "12")),
        da=int(os.getenv("E2E_DA", "30")),
        output_dir=tmpdir,
    )


def test_e2e_methodology_snapshot_written(e2e_result):
    path = e2e_result["methodology_snapshot"]
    assert os.path.exists(path), f"snapshot not written: {path}"


def test_e2e_snapshot_valid_json(e2e_result):
    path = e2e_result["methodology_snapshot"]
    with open(path, encoding="utf-8") as fh:
        snap = json.load(fh)
    assert snap["snapshot_type"] == "methodology"
    assert "v5_extensions" in snap


def test_e2e_snapshot_ga4_summary_non_zero(e2e_result):
    path = e2e_result["methodology_snapshot"]
    with open(path, encoding="utf-8") as fh:
        snap = json.load(fh)
    assert snap["ga4_input"]["rows"] > 0, "GA4 data loaded empty"
    assert snap["ga4_input"]["latest_6mo_avg"] > 0, "GA4 6-month average is zero"


def test_e2e_snapshot_da_populated(e2e_result):
    path = e2e_result["methodology_snapshot"]
    with open(path, encoding="utf-8") as fh:
        snap = json.load(fh)
    assert snap["v5_extensions"]["da_derived"] is not None
    assert snap["v5_extensions"]["da_rationale"] is not None
