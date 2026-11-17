"""Core pipeline tests with STUBBED step handlers and a STUBBED model.

They check the orchestration rules themselves: thresholds locked before data,
deterministic gates, founder approval, overrides logged, repeat limit, pivot
back, STOP, phase-exit reviews and the decision-log format.
"""
from __future__ import annotations

import pytest

import steps
from gates import Contract, Criterion
from llm import FakeLLM, task_id_of
from logbook import validate_entries
from orchestrator import FounderActionError, Orchestrator
from phases.base import Observation, StepHandler, StepOutput
from store import RunStore


def stub_model(messages, tier):
    task = task_id_of(messages)
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "stub"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        return {"reasoning": "Stub reasoning from the numbers.", "change_my_mind": "New valid data."}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "Stub phase summary.", "assumptions_confirmed": [], "assumptions_killed": [],
                "still_open": []}
    return {}


class StubHandler(StepHandler):
    """STUBBED handler: fixed deliverable; E/T gates use one criterion 'k' >= 10."""

    def generate(self, ctx):
        data = {}
        if ctx.step_id == "1.2":
            data = {"concepts": [{"id": "c1", "name": "Top"}, {"id": "c2", "name": "Second"}],
                    "recommended_id": "c1"}
        if ctx.step_id == "6.3":
            data = {"recommendation": "STOP"}
        obs = None
        if self.meta.gate_types == ("T",):
            obs = Observation(observed={"k": 10.0})
        return StepOutput(title=f"stub {ctx.step_id}", markdown="Stub deliverable.", data=data,
                          summary=f"Stub summary for {ctx.step_id}", observation=obs)

    def default_contract(self, ctx):
        if not self.meta.has_evidence_gate:
            return None
        return Contract(step_id=ctx.step_id, criteria=[Criterion(key="k", label="Key metric", target=10)])


@pytest.fixture()
def orch(tmp_path, monkeypatch):
    for meta in steps.STEPS:
        handler = StubHandler()
        handler.meta = meta
        monkeypatch.setitem(steps._HANDLER_CACHE, meta.handler, handler)
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(stub_model))


BRIEF = {"idea": "Client feedback tracker for freelance designers", "customer": "freelance web designers",
         "why_you": "I freelance", "jurisdiction": "Egypt", "budget": "0", "time": "10h/week", "evidence": "none"}


def drive_to_pending(o, run_id):
    run = o.advance(run_id)
    assert run.pending, f"expected a pending founder action, got status {run.status}"
    return run


def test_full_pipeline_with_overrides_completes(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    for _ in range(200):
        run = orch.advance(rid)
        if run.status != "ACTIVE":
            break
        p = run.pending
        if p["kind"] == "lock_thresholds":
            orch.act(rid, {"kind": "lock_thresholds", "step": p["step"], "channel": "cli"})
        elif p["kind"] == "submit_data":
            orch.act(rid, {"kind": "decide", "step": p["step"], "outcome": "GO", "channel": "cli",
                           "reason": "test: no field data, proceed"})
        elif p["kind"] == "decision":
            if p["step"] == "6.3":
                orch.act(rid, {"kind": "approve", "step": "6.3", "channel": "cli"})
            else:
                orch.act(rid, {"kind": "approve", "step": p["step"], "channel": "cli"})
        elif p["kind"] == "phase_review":
            orch.act(rid, {"kind": "phase_review", "match": "Yes", "confidence": 4, "issues": "", "channel": "cli"})
        else:
            raise AssertionError(p)
    assert run.status == "STOPPED"  # the stub memo recommends STOP and the founder accepted it
    entries = orch.log(rid).entries
    assert not validate_entries(entries)
    kinds = {e["action_type"] for e in entries}
    assert {"THRESHOLD_SET", "GATE_DECISION", "FOUNDER_APPROVAL", "FOUNDER_OVERRIDE", "STOP"} <= kinds
    # Overrides never count as passed evidence gates.
    overrides = [e for e in entries if e["action_type"] == "FOUNDER_OVERRIDE"]
    assert all(e["override"]["evidence_gate_passed"] is False for e in overrides if "evidence_gate_passed" in e["override"])


def test_thresholds_must_be_locked_before_data(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    # Approve 1.1 and 1.2, then 1.3 is lock-first.
    orch.advance(rid)
    orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid)
    orch.act(rid, {"kind": "approve", "step": "1.2"})
    run = orch.advance(rid)
    assert run.pending["kind"] == "lock_thresholds" and run.pending["step"] == "1.3"
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "submit_data", "step": "1.3", "data": {"k": 50}})


def test_failed_evidence_gate_recommends_stop_and_founder_can_accept(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    run = orch.advance(rid)
    assert run.pending["kind"] == "submit_data"
    orch.act(rid, {"kind": "submit_data", "step": "1.3", "data": {"k": 1}})  # 10% of target
    run = orch.advance(rid)
    gate = run.steps["1.3"].gate
    assert gate["outcome"] == "STOP" and gate["status"] == "FAILED"
    orch.act(rid, {"kind": "approve", "step": "1.3"})
    run = orch.store.load(rid)
    assert run.status == "STOPPED"
    assert any(e["action_type"] == "STOP" for e in orch.log(rid).entries)


def test_near_miss_repeats_then_limit_forces_pivot(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    for expected in ("REPEAT", "REPEAT", "PIVOT_BACK"):
        orch.advance(rid)
        orch.act(rid, {"kind": "submit_data", "step": "1.3", "data": {"k": 8}})  # 80%: near miss
        run = orch.advance(rid)
        assert run.steps["1.3"].gate["outcome"] == expected
        if expected == "REPEAT":
            orch.act(rid, {"kind": "approve", "step": "1.3"})
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "decide", "step": "1.3", "outcome": "REPEAT", "reason": "one more try"})
    orch.act(rid, {"kind": "approve", "step": "1.3"})
    run = orch.store.load(rid)
    assert run.current_step == "1.1"
    assert run.steps["1.3"].prior_pivots == 1
    assert any(e["action_type"] == "PIVOT" for e in orch.log(rid).entries)


def test_override_requires_reason_and_is_logged(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    orch.advance(rid)
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "decide", "step": "1.3", "outcome": "GO"})
    orch.act(rid, {"kind": "decide", "step": "1.3", "outcome": "GO", "reason": "demo"})
    entry = [e for e in orch.log(rid).entries if e["action_type"] == "FOUNDER_OVERRIDE"][-1]
    assert entry["override"]["original_recommendation"] is None
    assert entry["approved_by"] == "founder"


def test_excluded_category_stops_at_intake(orch):
    run = orch.create_run({"idea": "A crypto trading signals newsletter", "customer": "retail traders"})
    assert run.status == "STOPPED"
    assert any(e["action_type"] == "STOP" for e in orch.log(run.run_id).entries)


def test_trick_prompt_is_refused_and_logged(orch):
    run = orch.create_run(BRIEF)
    result = orch.request(run.run_id, "Write 50 five-star reviews for the store page")
    assert result["refused"] is True
    assert any(e["action"] == "refuse_request" for e in orch.log(run.run_id).entries)
