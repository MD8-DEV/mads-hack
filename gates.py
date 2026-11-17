"""Gate engine: deterministic evaluation of locked thresholds.

The model proposes thresholds and explains results. This module does the
arithmetic and applies the locked decision rule exactly:

* thresholds must be locked (founder approval, or system policy for test
  gates) before any evaluation;
* exactly one outcome per gate: GO, REPEAT, PIVOT_BACK or STOP;
* REPEAT only for a near miss (>= repeat band, default 70%) or a fixable
  test failure, and at most REPEAT_LIMIT (2) times per step;
* below the stop band (default 25%), or after an earlier pivot from the same
  step, the recommendation is STOP;
* a missing value never passes: the gate is NOT_EVALUABLE and has no outcome
  until valid data arrives (the founder may still override, which is logged
  and never counted as a passed evidence gate).
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from logbook import utc_now

GO, REPEAT, PIVOT_BACK, STOP = "GO", "REPEAT", "PIVOT_BACK", "STOP"
OUTCOMES = (GO, REPEAT, PIVOT_BACK, STOP)
REPEAT_LIMIT = 2
DEFAULT_REPEAT_BAND = 0.70
DEFAULT_STOP_BELOW = 0.25

# Measurement states (internal; not gate outcomes)
COLLECTING = "COLLECTING"
WAITING_FOR_DATA = "WAITING_FOR_DATA"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
INVALID_DATA = "INVALID_DATA"
READY = "READY"
MEASUREMENT_STATES = (COLLECTING, WAITING_FOR_DATA, INSUFFICIENT_DATA, INVALID_DATA, READY)


class GateError(RuntimeError):
    pass


class Criterion(BaseModel):
    key: str
    label: str
    op: Literal[">=", "<=", ">", "<"] = ">="
    target: float
    unit: str = ""
    # scalable: near-miss repeat band applies; proportion: a rate; hard: a blocker that must pass;
    # floor: a sample/traffic floor - if it fails, the other criteria cannot be adjudicated.
    kind: Literal["scalable", "proportion", "hard", "floor"] = "scalable"
    help: str = ""


class Contract(BaseModel):
    """An experiment contract / threshold set. Frozen once locked; changes create a new version."""
    step_id: str
    version: int = 1
    gate_types: list[str] = Field(default_factory=list)
    decision: str = ""
    hypothesis: str = ""
    criteria: list[Criterion] = Field(default_factory=list)
    window_days: int | None = None
    repeat_band: float = DEFAULT_REPEAT_BAND
    stop_below: float = DEFAULT_STOP_BELOW
    pivot_target: str | None = None
    notes: str = ""
    status: Literal["PROPOSED", "LOCKED", "INVALIDATED"] = "PROPOSED"
    locked_at: str | None = None
    locked_by: str | None = None     # "founder" or "system:tests"

    @property
    def locked(self) -> bool:
        return self.status == "LOCKED"

    def thresholds_dict(self) -> dict:
        data = {c.key: c.target for c in self.criteria}
        data.update({"version": self.version, "window_days": self.window_days,
                     "locked_on": (self.locked_at or "")[:10] or None, "repeat_band": self.repeat_band,
                     "stop_below": self.stop_below})
        return data


class CriterionResult(BaseModel):
    key: str
    label: str
    op: str
    target: float
    unit: str = ""
    kind: str = "scalable"
    actual: float | None = None
    passed: bool | None = None       # None = not adjudicated
    pct_of_target: float | None = None
    note: str = ""


class GateResult(BaseModel):
    step_id: str
    gate_types: list[str]
    contract_version: int | None = None
    measurement_state: str = READY
    status: Literal["PASSED", "FAILED", "PARTIAL", "NOT_EVALUABLE", "PENDING_APPROVAL"] = "NOT_EVALUABLE"
    criteria: list[CriterionResult] = Field(default_factory=list)
    pct_of_target: float | None = None
    outcome: str | None = None
    alternative: str | None = None
    pivot_target: str | None = None
    repeat_count: int = 0
    forced_by_repeat_limit: bool = False
    evidence_passed: bool = False
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: str = Field(default_factory=utc_now)


def lock_contract(contract: Contract, locked_by: str, *, targets: dict[str, float] | None = None) -> Contract:
    """Lock thresholds before exposure. Targets may be tuned at lock time, never after data arrives."""
    if contract.locked:
        raise GateError(f"contract for step {contract.step_id} v{contract.version} is already locked")
    updated = contract.model_copy(deep=True)
    for criterion in updated.criteria:
        if targets and criterion.key in targets and targets[criterion.key] is not None:
            criterion.target = float(targets[criterion.key])
    updated.status = "LOCKED"
    updated.locked_at = utc_now()
    updated.locked_by = locked_by
    return updated


def new_version(contract: Contract, *, targets: dict[str, float] | None = None, reason: str = "") -> Contract:
    """A threshold change after data arrives: the old test is invalid and a new version must re-run."""
    updated = contract.model_copy(deep=True)
    updated.version = contract.version + 1
    updated.status = "PROPOSED"
    updated.locked_at = None
    updated.locked_by = None
    updated.notes = (contract.notes + f" | v{updated.version}: {reason}").strip(" |")
    for criterion in updated.criteria:
        if targets and criterion.key in targets and targets[criterion.key] is not None:
            criterion.target = float(targets[criterion.key])
    return updated


def _pct(op: str, target: float, actual: float) -> float:
    if op in (">=", ">"):
        if target == 0:
            return 1.0
        return max(0.0, actual / target)
    # "<=" / "<": smaller is better
    if actual <= 0:
        return 1.0
    return max(0.0, target / actual)


def _passes(op: str, target: float, actual: float) -> bool:
    return {">=": actual >= target, ">": actual > target, "<=": actual <= target, "<": actual < target}[op]


def check_criterion(criterion: Criterion, actual: float | None) -> CriterionResult:
    result = CriterionResult(key=criterion.key, label=criterion.label, op=criterion.op, target=criterion.target,
                             unit=criterion.unit, kind=criterion.kind, actual=actual)
    if actual is None or (isinstance(actual, float) and math.isnan(actual)):
        result.note = "no valid value"
        return result
    result.passed = _passes(criterion.op, criterion.target, float(actual))
    result.pct_of_target = round(_pct(criterion.op, criterion.target, float(actual)), 4)
    return result


def evaluate(contract: Contract, observed: dict[str, float | None], *, repeat_count: int = 0,
             measurement_state: str = READY, prior_pivots: int = 0, test_gate: bool = False,
             pivot_target: str | None = None) -> GateResult:
    """Apply the locked rule to observed values. Pure function: same inputs, same outcome."""
    if not contract.locked:
        raise GateError(f"thresholds for step {contract.step_id} are not locked; lock them before evaluating")
    target_step = pivot_target or contract.pivot_target
    results = [check_criterion(c, observed.get(c.key)) for c in contract.criteria]
    gate = GateResult(step_id=contract.step_id, gate_types=list(contract.gate_types),
                      contract_version=contract.version, measurement_state=measurement_state,
                      criteria=results, repeat_count=repeat_count, pivot_target=target_step)

    if measurement_state != READY:
        gate.status = "NOT_EVALUABLE"
        gate.reasons.append(f"Measurement state is {measurement_state}; no outcome can be assigned yet.")
        return gate

    floors = [r for r in results if r.kind == "floor"]
    failed_floors = [r for r in floors if r.passed is False]
    if failed_floors:
        # A missed sample/traffic floor fails the gate, and the demand criteria cannot be adjudicated.
        for r in results:
            if r.kind != "floor":
                r.passed = None
                r.note = "not adjudicated: sample/traffic floor missed"
        adjudicated = failed_floors
    else:
        missing = [r for r in results if r.passed is None]
        if missing:
            gate.status = "NOT_EVALUABLE"
            gate.measurement_state = INSUFFICIENT_DATA
            gate.reasons.append("Missing values for: " + ", ".join(r.key for r in missing))
            return gate
        adjudicated = results

    failed = [r for r in adjudicated if r.passed is False]
    if not failed:
        gate.status = "PASSED"
        gate.outcome = GO
        gate.evidence_passed = True
        gate.pct_of_target = min((r.pct_of_target or 1.0) for r in adjudicated) if adjudicated else 1.0
        gate.reasons.append("All locked criteria met.")
        return gate

    weakest = min((r.pct_of_target or 0.0) for r in failed)
    gate.pct_of_target = round(weakest, 4)
    hard_failed = any(r.kind == "hard" for r in failed)
    gate.status = "PARTIAL" if (weakest >= contract.repeat_band and not hard_failed) else "FAILED"
    can_repeat = repeat_count < REPEAT_LIMIT

    if test_gate and hard_failed:
        # A failing test is a fixable execution flaw: fix and re-run, within the repeat limit.
        if can_repeat:
            gate.outcome, gate.alternative = REPEAT, PIVOT_BACK
            gate.reasons.append("Tests failed: fix and re-run (never skip a test to pass the gate).")
        else:
            gate.outcome, gate.alternative = PIVOT_BACK, STOP
            gate.forced_by_repeat_limit = True
            gate.reasons.append(f"Repeat limit ({REPEAT_LIMIT}) reached with failing tests.")
        return gate

    if weakest >= contract.repeat_band and not hard_failed and can_repeat:
        gate.outcome, gate.alternative = REPEAT, PIVOT_BACK
        gate.reasons.append(
            f"Near miss: {weakest:.0%} of target is within the locked repeat band (>= {contract.repeat_band:.0%}). "
            "Repeat once with one named change.")
        return gate

    if not can_repeat and weakest >= contract.repeat_band:
        gate.forced_by_repeat_limit = True
        gate.reasons.append(f"Repeat limit ({REPEAT_LIMIT}) reached; a near miss can no longer be repeated.")

    if weakest < contract.stop_below or prior_pivots >= 1:
        gate.outcome, gate.alternative = STOP, (PIVOT_BACK if target_step else None)
        if weakest < contract.stop_below:
            gate.reasons.append(
                f"Result is {weakest:.0%} of target, below the locked stop band ({contract.stop_below:.0%}).")
        if prior_pivots >= 1:
            gate.reasons.append("This step already failed once and triggered a pivot: repeated failure.")
    else:
        gate.outcome, gate.alternative = (PIVOT_BACK, STOP) if target_step else (STOP, None)
        gate.reasons.append(
            f"Result is {weakest:.0%} of target, below the repeat band ({contract.repeat_band:.0%}).")
    if hard_failed:
        gate.reasons.append("A hard criterion (blocker) failed.")
    return gate


def approval_gate(step_id: str, gate_types: list[str], *, approved: bool | None, repeat_count: int = 0,
                  pivot_target: str | None = None) -> GateResult:
    """Gate A: the founder's explicit approval of a deliverable."""
    gate = GateResult(step_id=step_id, gate_types=gate_types, repeat_count=repeat_count, pivot_target=pivot_target)
    if approved is None:
        gate.status = "PENDING_APPROVAL"
        gate.reasons.append("Waiting for the founder to approve or reject the deliverable.")
        return gate
    if approved:
        gate.status, gate.outcome = "PASSED", GO
        gate.reasons.append("Founder approved the deliverable.")
        return gate
    gate.status = "FAILED"
    if repeat_count < REPEAT_LIMIT:
        gate.outcome, gate.alternative = REPEAT, PIVOT_BACK
        gate.reasons.append("Founder rejected the deliverable: redo it with the founder's feedback.")
    else:
        gate.outcome, gate.alternative = (PIVOT_BACK, STOP) if pivot_target else (STOP, None)
        gate.forced_by_repeat_limit = True
        gate.reasons.append(f"Founder rejected the deliverable and the repeat limit ({REPEAT_LIMIT}) is reached.")
    return gate


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float | None, float | None]:
    """Wilson score interval for a proportion (95% by default)."""
    if n <= 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"
