"""Run the decision-quality review set (evals/gate_cases.yaml) against the gate engine.

Usage: python evals/run_gate_evals.py   (exit code 0 when every case matches)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gates  # noqa: E402
from gates import Contract, Criterion, GateError, evaluate, lock_contract  # noqa: E402

CASES = Path(__file__).with_name("gate_cases.yaml")


def load_cases(path: Path = CASES) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


def run_case(case: dict) -> tuple[bool, str]:
    """Return (passed, explanation) for one case."""
    criteria = [Criterion(key=c["key"], label=c["key"], target=float(c["target"]), kind=c.get("kind", "scalable"),
                          op=c.get("op", ">=")) for c in case["criteria"]]
    contract = Contract(step_id="eval", gate_types=["E"], criteria=criteria, pivot_target=case.get("pivot_target"))
    if not case.get("unlocked"):
        contract = lock_contract(contract, "eval")
    expect = case["expect"]
    try:
        gate = evaluate(contract, case.get("observed") or {}, repeat_count=case.get("repeat_count", 0),
                        measurement_state=case.get("measurement_state", gates.READY),
                        prior_pivots=case.get("prior_pivots", 0), test_gate=case.get("test_gate", False))
    except GateError as exc:
        if expect.get("raises") == "GateError":
            return True, "raised GateError as required"
        return False, f"unexpected GateError: {exc}"
    if expect.get("raises"):
        return False, f"expected {expect['raises']} but got outcome {gate.outcome}"
    problems = []
    for key in ("status", "outcome", "alternative", "evidence_passed", "measurement_state", "forced_by_repeat_limit"):
        if key in expect and getattr(gate, key) != expect[key]:
            problems.append(f"{key}={getattr(gate, key)!r} (expected {expect[key]!r})")
    for key in expect.get("not_adjudicated", []):
        result = next((r for r in gate.criteria if r.key == key), None)
        if result is None or result.passed is not None:
            problems.append(f"{key} should be not adjudicated")
    if problems:
        return False, "; ".join(problems)
    return True, f"{gate.status} -> {gate.outcome}" + (f" (alt {gate.alternative})" if gate.alternative else "")


def main() -> int:
    cases = load_cases()
    failures = 0
    for case in cases:
        ok, why = run_case(case)
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} | {case['id']:<36} | {why}")
    print(f"\n{len(cases) - failures}/{len(cases)} gate cases match the playbook's rules")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
