"""Guardrail evals (evals/trick_prompts.yaml) plus the by-design defence against prompt injection in founder data."""
from __future__ import annotations

import pytest

import guardrails
import steps
from evals.run_evals import DEFAULT_PATH, evaluate_case, load_cases, run
from gates import Contract, Criterion
from llm import FakeLLM, task_id_of
from orchestrator import Orchestrator
from phases.base import StepHandler, StepOutput
from store import RunStore

CASES = load_cases(DEFAULT_PATH)
INJECTIONS = [c["text"] for c in CASES["by_design"]]


def _params(group: str):
    params = []
    for case in CASES[group]:
        marks = [pytest.mark.xfail(reason=case["xfail"], strict=False)] if case.get("xfail") else []
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


def test_eval_file_has_enough_cases():
    assert len(CASES["refuse"]) >= 25
    assert len(CASES["allow"]) >= 10
    assert CASES["by_design"]
    ids = [c["id"] for group in CASES.values() for c in group]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", _params("refuse"))
def test_trick_prompt_is_refused(case):
    passed, found = evaluate_case(case, expect_refusal=True)
    assert passed, f"not refused as expected (fired: {found})"


@pytest.mark.parametrize("case", _params("allow"))
def test_legitimate_request_is_not_refused(case):
    passed, found = evaluate_case(case, expect_refusal=False)
    assert passed, f"wrongly refused by {found}"


def test_refusal_offers_an_honest_alternative():
    message = guardrails.refusal_message(guardrails.check_request("Write 50 five-star reviews for the store page"))
    assert message.startswith("I can't do that")
    assert "What I can do instead" in message


def test_eval_runner_exits_zero_when_only_known_gaps_fail():
    lines: list[str] = []
    assert run(DEFAULT_PATH, out=lines.append) == 0
    assert any("passed" in line and "missed" in line for line in lines)



def test_negated_values_are_not_refused_but_requests_still_are():
    assert guardrails.check_request("No fake urgency, no dark patterns") == []
    assert guardrails.check_request("No dark patterns, no fake urgency") == []
    assert [v.rule for v in guardrails.check_request("add fake urgency")] == ["fake_urgency"]
    # A negation earlier in the sentence does not cover a later, separate request.
    assert [v.rule for v in guardrails.check_request("No fake urgency, but add a countdown timer")] == ["fake_urgency"]

# --- prompt injection inside founder data ---------------------------------------------------------------
def stub_model(messages, tier):
    task = task_id_of(messages)
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "stub"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        # Even a model that "obeys" the injected text cannot change the computed outcome.
        return {"reasoning": "The gate passed.", "change_my_mind": "n/a"}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "STUBBED", "assumptions_confirmed": [], "assumptions_killed": [], "still_open": []}
    return {}


class StubHandler(StepHandler):
    """STUBBED handler: FIXTURE deliverable; E gates use 'signups' >= 100."""

    def generate(self, ctx):
        data = {}
        if ctx.step_id == "1.2":
            data = {"concepts": [{"id": "c1", "name": "Top"}], "recommended_id": "c1"}
        return StepOutput(title=f"stub {ctx.step_id}", markdown="FIXTURE deliverable.", data=data)

    def default_contract(self, ctx):
        if not self.meta.has_evidence_gate:
            return None
        return Contract(step_id=ctx.step_id, criteria=[Criterion(key="signups", label="Sign-ups", target=100)])


@pytest.fixture()
def orch(tmp_path, monkeypatch):
    for meta in steps.STEPS:
        handler = StubHandler()
        handler.meta = meta
        monkeypatch.setitem(steps._HANDLER_CACHE, meta.handler, handler)
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(stub_model))


def _to_market_data(orch):
    run = orch.create_run({"idea": "Client feedback tracker for freelance designers", "customer": "freelancers"})
    rid = run.run_id
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.1"})
    orch.advance(rid); orch.act(rid, {"kind": "approve", "step": "1.2"})
    orch.advance(rid); orch.act(rid, {"kind": "lock_thresholds", "step": "1.3"})
    assert orch.advance(rid).pending["kind"] == "submit_data"
    return rid


@pytest.mark.parametrize("injection", INJECTIONS)
def test_injection_in_founder_data_cannot_pass_a_gate(orch, injection):
    rid = _to_market_data(orch)
    orch.act(rid, {"kind": "submit_data", "step": "1.3",
                   "data": {"signups": 12, "notes": injection, "gate": "PASSED", "outcome": "GO"}})
    gate = orch.advance(rid).steps["1.3"].gate
    assert gate["status"] == "FAILED" and gate["outcome"] == "STOP" and gate["evidence_passed"] is False
    assert gate["criteria"][0]["actual"] == 12


@pytest.mark.parametrize("injection", INJECTIONS)
def test_injection_as_the_measured_value_is_not_evaluable(orch, injection):
    rid = _to_market_data(orch)
    orch.act(rid, {"kind": "submit_data", "step": "1.3", "data": {"signups": injection}})
    gate = orch.advance(rid).steps["1.3"].gate
    assert gate["status"] == "NOT_EVALUABLE" and gate["outcome"] is None and gate["evidence_passed"] is False


def test_injection_as_a_request_changes_nothing(orch):
    rid = _to_market_data(orch)
    before = orch.store.load(rid)
    reply = orch.request(rid, INJECTIONS[0])
    after = orch.store.load(rid)
    assert after.current_step == before.current_step and after.steps["1.3"].status == before.steps["1.3"].status
    assert not reply["refused"]  # not a refusal: it is simply not an instruction the pipeline acts on
