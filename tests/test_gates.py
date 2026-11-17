"""Smoke tests for the deterministic gate engine (gates.py)."""
from __future__ import annotations

import pytest

from gates import (GO, INSUFFICIENT_DATA, PIVOT_BACK, REPEAT, REPEAT_LIMIT, STOP, WAITING_FOR_DATA, Contract,
                   Criterion, GateError, approval_gate, evaluate, lock_contract, new_version, wilson_interval)


def contract(*criteria: Criterion, pivot_target: str | None = "1.4") -> Contract:
    return Contract(step_id="2.2", gate_types=["E"], criteria=list(criteria), pivot_target=pivot_target)


def signups(target: float = 100) -> Criterion:
    return Criterion(key="signups", label="Waitlist sign-ups", target=target)


def locked(c: Contract, **targets) -> Contract:
    return lock_contract(c, "founder", targets=targets or None)


def test_wilson_interval_30_of_300():
    low, high = wilson_interval(30, 300)
    assert low == pytest.approx(0.071, abs=0.002)
    assert high == pytest.approx(0.139, abs=0.002)
    assert wilson_interval(0, 0) == (None, None)


def test_thresholds_must_be_locked_before_evaluation():
    with pytest.raises(GateError):
        evaluate(contract(signups()), {"signups": 120})
    c = locked(contract(signups()))
    assert c.locked and c.locked_by == "founder" and c.locked_at
    with pytest.raises(GateError):
        lock_contract(c, "founder")  # a locked contract cannot be re-locked or quietly tuned


def test_lock_time_tuning_and_new_version_after_data():
    c = locked(contract(signups()), signups=80)
    assert c.criteria[0].target == 80
    v2 = new_version(c, targets={"signups": 50}, reason="founder lowered the bar")
    assert v2.version == 2 and v2.status == "PROPOSED" and not v2.locked
    with pytest.raises(GateError):
        evaluate(v2, {"signups": 60})


def test_go_when_all_criteria_met():
    gate = evaluate(locked(contract(signups())), {"signups": 100})
    assert gate.outcome == GO and gate.status == "PASSED" and gate.evidence_passed


def test_near_miss_repeats():
    gate = evaluate(locked(contract(signups())), {"signups": 80})
    assert gate.outcome == REPEAT and gate.status == "PARTIAL" and gate.alternative == PIVOT_BACK


def test_clear_miss_pivots_back():
    gate = evaluate(locked(contract(signups())), {"signups": 50})
    assert gate.outcome == PIVOT_BACK and gate.pivot_target == "1.4" and gate.alternative == STOP


def test_12_of_100_recommends_stop():
    gate = evaluate(locked(contract(signups())), {"signups": 12})
    assert gate.outcome == STOP and gate.status == "FAILED"
    assert gate.pct_of_target == pytest.approx(0.12)


def test_repeated_failure_after_a_pivot_recommends_stop():
    gate = evaluate(locked(contract(signups())), {"signups": 50}, prior_pivots=1)
    assert gate.outcome == STOP


def test_repeat_limit_forces_pivot_or_stop():
    c = locked(contract(signups()))
    gate = evaluate(c, {"signups": 80}, repeat_count=REPEAT_LIMIT)
    assert gate.outcome == PIVOT_BACK and gate.forced_by_repeat_limit
    no_target = locked(contract(signups(), pivot_target=None))
    assert evaluate(no_target, {"signups": 80}, repeat_count=REPEAT_LIMIT).outcome == STOP


def test_failing_tests_repeat_then_pivot():
    c = Contract(step_id="3.2", gate_types=["T"], pivot_target="3.1",
                 criteria=[Criterion(key="pass_rate", label="Critical tests passing", target=1.0, kind="hard")])
    c = lock_contract(c, "system:tests")
    assert evaluate(c, {"pass_rate": 0.9}, test_gate=True).outcome == REPEAT
    assert evaluate(c, {"pass_rate": 0.9}, test_gate=True, repeat_count=REPEAT_LIMIT).outcome == PIVOT_BACK


def test_floor_failure_leaves_other_criteria_unadjudicated():
    c = locked(contract(Criterion(key="visitors", label="Unique visitors", target=200, kind="floor"),
                        Criterion(key="rate", label="Sign-up rate", target=0.1, kind="proportion")))
    gate = evaluate(c, {"visitors": 40, "rate": 0.5})
    by_key = {r.key: r for r in gate.criteria}
    assert by_key["visitors"].passed is False
    assert by_key["rate"].passed is None and "not adjudicated" in by_key["rate"].note
    assert gate.outcome != GO and not gate.evidence_passed


def test_less_or_equal_criteria():
    c = locked(contract(Criterion(key="churn", label="Monthly churn", op="<=", target=0.05)))
    assert evaluate(c, {"churn": 0.04}).outcome == GO
    assert evaluate(c, {"churn": 0.06}).outcome == REPEAT       # 0.05/0.06 = 83% of target
    assert evaluate(c, {"churn": 0.5}).outcome == STOP          # 10% of target


def test_missing_value_is_not_evaluable():
    c = locked(contract(signups(), Criterion(key="rate", label="Rate", target=0.1)))
    gate = evaluate(c, {"signups": 120})
    assert gate.status == "NOT_EVALUABLE" and gate.outcome is None
    assert gate.measurement_state == INSUFFICIENT_DATA
    waiting = evaluate(c, {}, measurement_state=WAITING_FOR_DATA)
    assert waiting.status == "NOT_EVALUABLE" and waiting.outcome is None and not waiting.evidence_passed


def test_approval_gate():
    assert approval_gate("1.1", ["A"], approved=None).status == "PENDING_APPROVAL"
    assert approval_gate("1.1", ["A"], approved=True).outcome == GO
    assert approval_gate("1.1", ["A"], approved=False).outcome == REPEAT
    limit = approval_gate("2.1", ["A"], approved=False, repeat_count=REPEAT_LIMIT, pivot_target="1.4")
    assert limit.outcome == PIVOT_BACK and limit.forced_by_repeat_limit


def test_floor_miss_keeps_failing_test_criteria_adjudicated():
    c = lock_contract(Contract(step_id="5.2", gate_types=["T", "E"], pivot_target="2.1", criteria=[
        Criterion(key="delivery_tests_pass_rate", label="Delivery tests passing", target=1.0, kind="hard"),
        Criterion(key="store_visitors", label="Store visitors", target=500, kind="floor"),
        Criterion(key="buy_intent_rate", label="Buy-intent rate", target=0.03, kind="proportion")]), "system:tests")
    observed = {"delivery_tests_pass_rate": 0.5, "store_visitors": 40, "buy_intent_rate": 0.1}
    gate = evaluate(c, observed, test_gate=True)
    by_key = {r.key: r for r in gate.criteria}
    assert by_key["delivery_tests_pass_rate"].passed is False      # the failing test is not hidden by the floor
    assert by_key["buy_intent_rate"].passed is None                # demand stays unadjudicated
    assert gate.outcome == REPEAT and not gate.evidence_passed
    limit = evaluate(c, observed, test_gate=True, repeat_count=REPEAT_LIMIT)
    assert limit.outcome == PIVOT_BACK and limit.forced_by_repeat_limit


def test_floor_miss_with_passing_hard_criteria_still_fails_on_the_floor():
    c = locked(contract(Criterion(key="tests", label="Tests passing", target=1.0, kind="hard"),
                        Criterion(key="visitors", label="Unique visitors", target=200, kind="floor"),
                        Criterion(key="rate", label="Sign-up rate", target=0.1, kind="proportion")))
    gate = evaluate(c, {"tests": 1.0, "visitors": 150, "rate": 0.5})
    by_key = {r.key: r for r in gate.criteria}
    assert by_key["tests"].passed is True and by_key["rate"].passed is None
    assert gate.outcome == REPEAT and gate.status == "PARTIAL"     # 75% of the floor: a near miss


def test_binary_miss_alone_pivots_back_instead_of_stop():
    bugs = Criterion(key="open_bugs", label="Open critical bugs", op="<=", target=0, kind="hard")
    gate = evaluate(locked(contract(signups(), bugs)), {"signups": 120, "open_bugs": 3})
    assert gate.outcome == PIVOT_BACK and gate.pivot_target == "1.4" and gate.alternative == STOP
    flag = Criterion(key="in_range", label="Price inside the acceptable range (1 = yes)", target=1, kind="hard")
    assert evaluate(locked(contract(signups(), flag)), {"signups": 120, "in_range": 0}).outcome == PIVOT_BACK
    # Without a pivot target, or after an earlier pivot, STOP remains the recommendation.
    assert evaluate(locked(contract(signups(), bugs, pivot_target=None)),
                    {"signups": 120, "open_bugs": 3}).outcome == STOP
    assert evaluate(locked(contract(signups(), bugs)), {"signups": 120, "open_bugs": 3},
                    prior_pivots=1).outcome == STOP
    # A demand criterion below the stop band still recommends STOP, blocker or not.
    assert evaluate(locked(contract(signups(), bugs)), {"signups": 10, "open_bugs": 3}).outcome == STOP
