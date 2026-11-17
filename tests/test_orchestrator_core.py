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


def _report(o, rid, step_id, rel=None):
    run = o.store.load(rid)
    return o.store.read_artifact(rid, rel or run.steps[step_id].artifacts["gate_report.md"])


def test_approval_gate_report_records_the_founder_decision(orch):
    rid = orch.create_run(BRIEF).run_id
    orch.advance(rid)
    pending = _report(orch, rid, "1.1")
    assert pending.startswith("GATE PENDING") and "Log ID(s): pending" in pending
    orch.act(rid, {"kind": "approve", "step": "1.1", "reason": "looks right"})
    report = _report(orch, rid, "1.1")
    approval = [e for e in orch.log(rid).entries if e["action"] == "approve_gate"][-1]
    assert report.startswith("GATE APPROVED: step 1.1") and "(founder approved)" in report
    assert "Log ID(s): pending" not in report and f"Log ID(s): {approval['log_id']}" in report
    assert "## Founder decision" in report and "accepted recommendation GO" in report
    assert "Reason: looks right" in report and "Channel: web" in report
    assert "Status: PENDING_APPROVAL" in report      # the computed gate block itself is unchanged


def test_rejection_is_recorded_in_that_attempts_gate_report(orch):
    rid = orch.create_run(BRIEF).run_id
    orch.advance(rid)
    rel = orch.store.load(rid).steps["1.1"].artifacts["gate_report.md"]
    orch.act(rid, {"kind": "reject", "step": "1.1", "reason": "name the customer segment"})
    report = _report(orch, rid, "1.1", rel)
    assert report.startswith("GATE REJECTED: step 1.1")
    assert "rejected the deliverable (gate outcome: REPEAT)" in report and "name the customer segment" in report


def test_accepted_stop_is_recorded_in_the_gate_report(orch):
    rid = orch.create_run(BRIEF).run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    orch.advance(rid)
    orch.act(rid, {"kind": "submit_data", "step": "1.3", "data": {"k": 1}})
    orch.advance(rid)
    before = _report(orch, rid, "1.3")
    orch.act(rid, {"kind": "approve", "step": "1.3"})
    report = _report(orch, rid, "1.3")
    stop = [e for e in orch.log(rid).entries if e["action"] == "stop_venture"][-1]
    assert report.startswith(before.rstrip("\n"))                 # computed gate block kept intact above
    assert "## Founder decision" in report and "accepted recommendation STOP" in report
    assert stop["log_id"] in report


def test_override_is_recorded_in_the_gate_report(orch):
    rid = orch.create_run(BRIEF).run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    orch.advance(rid)
    orch.act(rid, {"kind": "submit_data", "step": "1.3", "data": {"k": 1}})
    orch.advance(rid)
    orch.act(rid, {"kind": "decide", "step": "1.3", "outcome": "GO", "reason": "founder has other evidence"})
    report = _report(orch, rid, "1.3")
    assert "override: chose GO instead of STOP" in report and "founder has other evidence" in report


def test_deliverable_cites_every_evidence_id_in_the_body_and_labels_assumptions(orch):
    from steps import STEPS_BY_ID
    run = orch.create_run(BRIEF)
    ledger = orch.ledger(run.run_id)
    first = ledger.add({"url": "https://data.worldbank.org/indicator/SL.TLF.TOTL.IN", "title": "Labour force"})
    second = ledger.add({"url": "https://example.org/survey", "title": "Survey"})
    out = StepOutput(title="Market model", data={"basis": f"see {second.evidence_id}"},
                     markdown=(f"| Input | Value | Basis |\n|---|---|---|\n| Workers | 1 | {first.evidence_id} |\n"
                               "| Share | 0.1 | `ESTIMATE` |\n| Churn | ? | `UNKNOWN` |\n| Missing | ? | E-999 |"))
    md = orch._render_deliverable(run, STEPS_BY_ID["1.1"], run.steps["1.1"], out, [], ledger)
    evidence_section = md.split("## Evidence cited", 1)[1]
    assert "https://data.worldbank.org/indicator/SL.TLF.TOTL.IN" in evidence_section
    assert "https://example.org/survey" in evidence_section and "E-999" not in evidence_section
    assert "`ASSUMPTION (estimate)`" in md and "`ASSUMPTION (unknown)`" in md
    assert "`ESTIMATE`" not in md and "`UNKNOWN`" not in md


def test_unsourced_claims_render_with_the_word_assumption(tmp_path):
    from evidence import Claim, EvidenceLedger
    ledger = EvidenceLedger(tmp_path / "evidence.json")
    row = ledger.add({"url": "https://example.org/a", "title": "A"})
    assert "`ASSUMPTION (estimate)`" in ledger.render_claim(Claim(text="x", label="ESTIMATE", basis="b"))
    assert "`ASSUMPTION (unknown)`" in ledger.render_claim(Claim(text="x", label="UNKNOWN", basis="b"))
    assert "`ASSUMPTION`" in ledger.render_claim(Claim(text="x", label="ASSUMPTION", basis="b"))
    sourced = ledger.render_claim(Claim(text="x", label="FOUNDER_REPORTED", evidence_ids=[row.evidence_id]))
    assert "https://example.org/a" in sourced and "ASSUMPTION" not in sourced
    _, problems = ledger.verify_claims([{"text": "word " * 60, "label": "SOURCED", "evidence_ids": ["E-404"]}])
    assert all(p.endswith("...") and len(p.split(": ", 1)[1]) <= 160 for p in problems)


def test_actions_must_answer_the_pending_item(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    run = orch.advance(rid)
    assert run.pending["kind"] == "decision" and run.pending["step"] == "1.1"
    before = len(orch.log(rid).entries)
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "lock_thresholds", "step": "1.1"})      # does not answer a decision
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "phase_review", "match": "Yes", "confidence": 4})
    assert len(orch.log(rid).entries) == before                        # refused actions write nothing


def test_skip_cannot_dismiss_an_open_phase_review(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    for _ in range(40):
        run = orch.advance(rid)
        p = run.pending
        if p["kind"] == "phase_review":
            break
        if p["kind"] == "lock_thresholds":
            orch.act(rid, {"kind": "lock_thresholds", "step": p["step"]})
        elif p["kind"] == "submit_data":
            orch.act(rid, {"kind": "decide", "step": p["step"], "outcome": "GO", "reason": "test"})
        else:
            orch.act(rid, {"kind": "approve", "step": p["step"]})
    assert run.pending["kind"] == "phase_review"
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "skip", "step": "2.1", "outcome": "GO", "reason": "skip ahead"})
    assert orch.store.load(rid).pending["kind"] == "phase_review"


def test_refused_override_writes_no_approval_or_log(orch):
    run = orch.create_run(BRIEF)
    rid = run.run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    orch.advance(rid)
    entries, approvals = len(orch.log(rid).entries), len(orch.approvals(rid).all())
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "decide", "step": "1.3", "outcome": "GO"})   # override without a reason
    assert len(orch.log(rid).entries) == entries
    assert len(orch.approvals(rid).all()) == approvals
