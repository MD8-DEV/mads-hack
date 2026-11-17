"""The gate engine must match every case in the decision-quality review set (evals/gate_cases.yaml)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

import run_gate_evals  # noqa: E402

CASES = run_gate_evals.load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_gate_case(case):
    ok, why = run_gate_evals.run_case(case)
    assert ok, why
