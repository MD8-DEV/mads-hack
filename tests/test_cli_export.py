"""CLI, scripted founder and export tests with STUBBED step handlers and a STUBBED model.

All deliverables here are FIXTURE text produced by the stub handlers; nothing
is a real result.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

import cli
import steps
from export import OUTPUT_NAME, export_run, is_output_name
from gates import Contract, Criterion
from llm import FakeLLM, task_id_of
from logbook import validate_entries
from orchestrator import Orchestrator
from phases.base import Observation, StepHandler, StepOutput
from store import RunStore

NAME_RULE = re.compile(r"^phase\d_(step\d+|gate)_[a-z0-9-]+\.(md|json|html|csv|txt)$")

BRIEF = {"title": "FIXTURE feedback tracker", "idea": "Client feedback tracker for freelance designers",
         "customer": "freelance web designers", "why_you": "I freelance", "jurisdiction": "Egypt",
         "budget": "0", "time": "10h/week", "evidence": "none"}


def stub_model(messages, tier):
    task = task_id_of(messages)
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "stub"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        return {"reasoning": "STUBBED reasoning from the numbers.", "change_my_mind": "New valid data."}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "STUBBED phase summary.", "assumptions_confirmed": [], "assumptions_killed": [],
                "still_open": []}
    return {}


class StubHandler(StepHandler):
    """STUBBED handler: FIXTURE deliverables; E/T gates use one criterion 'k' >= 10."""

    def generate(self, ctx):
        data, files = {}, {}
        sid = ctx.step_id
        if sid == "1.2":
            data = {"concepts": [{"id": "c1", "name": "Top"}, {"id": "c2", "name": "Second"}], "recommended_id": "c1"}
        if sid == "2.2":
            files = {"landing.html": "<html><body>FIXTURE landing page (MOCKED)</body></html>",
                     "huge.txt": "x" * (61 * 1024)}
            data = {"outward": [{"kind": "publish", "item_id": "landing", "file": "landing.html",
                                 "when": "before_collect", "target_name": "landing.html"}]}
        if sid == "3.2":
            files = {"product/index.html": "<html>FIXTURE product</html>", "test_report.json": {"passed": 3}}
        if sid == "4.2":
            data = {"requires_acknowledgment": "FIXTURE: these drafts need review by a qualified lawyer."}
        if sid == "5.1":
            files = {"store.html": "<html>FIXTURE store page (checkout MOCKED)</html>"}
            data = {"outward": [{"kind": "publish", "item_id": "store", "file": "store.html", "when": "on_approve"}]}
        if sid == "5.3":
            files = {"payment_test_log.md": "# Payment test log\n\nMOCKED: FIXTURE delivery test, no payment.\n"}
        if sid == "6.3":
            data = {"recommendation": "STOP"}
        obs = Observation(observed={"k": 10.0}) if self.meta.gate_types == ("T",) else None
        return StepOutput(title=f"stub {sid}", markdown=f"FIXTURE deliverable for {sid}.", data=data, files=files,
                          summary=f"Stub summary for {sid}", observation=obs)

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


FULL_DECISIONS = """
founder: "Test founder"
export_prefix: "full-run"
steps:
  1.1: {decision: approve}
  1.2: {decision: select_concept, concept_id: recommended}
  1.3: {lock: default, data: {k: 12}, decision: approve}
  1.4: {lock: default, on_no_data: {outcome: GO, reason: "FIXTURE: no interviews in this test"}}
  2.1:
    - {decision: reject, reason: "Name one acquisition channel"}
    - {decision: approve}
  2.2: {lock: {targets: {k: 5}}, approve_outward: true, data: {k: 6}, decision: approve}
  3.1: {decision: approve}
  3.2: {decision: approve}
  3.3: {lock: default, data: {k: 10}, decision: approve}
  4.1: {lock: default, data: {k: 11}, decision: approve}
  4.2: {decision: approve, acknowledge: true}
  5.1: {decision: approve, outward_ids: all}
  5.2: {decision: approve}
  5.3: {lock: default, data: {k: 10}, decision: approve}
  6.1: {lock: default, on_no_data: {outcome: GO, reason: "FIXTURE: no support tickets"}}
  6.2: {lock: default, on_no_data: {outcome: GO, reason: "FIXTURE: no metrics"}}
  6.3: {final_decision: STOP, reason: "FIXTURE"}
phase_reviews:
  1: {match: Yes, issues: "", confidence: 4}
  2: {match: Yes, issues: "", confidence: 4}
  3: {match: Yes, issues: "", confidence: 4}
  4: {match: Yes, issues: "", confidence: 4}
  5: {match: Yes, issues: "", confidence: 4}
  6: {match: Yes, issues: "", confidence: 4}
"""


def test_full_scripted_run_and_export(orch, tmp_path):
    run = orch.create_run(BRIEF, founder="Test founder")
    lines: list[str] = []
    result = cli.run_script(orch, run.run_id, yaml.safe_load(FULL_DECISIONS), out=lines.append)
    assert result["status"] == "STOPPED", lines  # the founder's final decision was STOP
    assert orch.store.load(run.run_id).final_decision["decision"] == "STOP"
    entries = orch.log(run.run_id).entries
    assert not validate_entries(entries)
    founder_entries = [e for e in entries if e["agent"] == "founder"]
    assert founder_entries and all(e.get("approval_channel") in (None, "decisions_file") for e in founder_entries)
    # MOCKED outward actions happened only after approval.
    mocked = [e for e in entries if e["action"].startswith("mock_")]
    assert {e["action"] for e in mocked} == {"mock_publish"} and all(e["approved_by"] == "founder" for e in mocked)

    out = tmp_path / "outputs"
    log_path = tmp_path / "decision_log.json"
    files = export_run(orch.store, run.run_id, out, prefix="full-run", log_path=log_path)
    names = sorted(Path(f).name for f in files if Path(f).parent == out)
    assert names
    for name in names:
        assert NAME_RULE.match(name) or name == "payment_test_log.md", name
        assert is_output_name(name)
    assert "phase1_step1_full-run-sharpened-idea.md" in names
    assert "phase2_step2_full-run-landing-page-landing.html" in names
    assert "phase3_step2_full-run-build-product-index.html" in names
    assert "phase3_step2_full-run-build-test-report.json" in names
    assert "phase2_step2_full-run-landing-page-contract-v1.json" in names
    assert "phase2_gate_full-run-landing-page.md" in names
    assert "phase2_gate_full-run-lean-canvas-attempt0.md" in names  # the rejected first attempt
    assert "phase2_gate_full-run-lean-canvas.md" in names
    assert "phase1_gate_full-run-phase-review.md" in names
    assert "payment_test_log.md" in names
    override = (out / "phase1_gate_full-run-interviews.md").read_text(encoding="utf-8")
    assert override.startswith("GATE NOT EVALUATED") and "FOUNDER_OVERRIDE" in override
    assert not any("huge" in n for n in names)  # files over 60 KB are skipped
    assert not any("deliverable" in n for n in names)
    contract = json.loads((out / "phase2_step2_full-run-landing-page-contract-v1.json").read_text(encoding="utf-8"))
    assert contract["criteria"][0]["target"] == 5 and contract["status"] == "LOCKED"
    review = (out / "phase1_gate_full-run-phase-review.md").read_text(encoding="utf-8")
    assert "Yes" in review and "Confidence" in review
    copied = json.loads(log_path.read_text(encoding="utf-8"))
    assert copied == entries and not validate_entries(copied)


def test_script_stops_when_the_file_has_no_answer(orch):
    run = orch.create_run(BRIEF)
    decisions = {"steps": {"1.1": {"decision": "approve"}, "1.2": {"decision": "approve"}}}
    lines: list[str] = []
    result = cli.run_script(orch, run.run_id, decisions, out=lines.append)
    assert result["status"] == "ACTIVE"
    assert result["actions"] == 2
    assert "no answer" in result["stopped"]
    assert result["pending"]["kind"] == "lock_thresholds" and result["pending"]["step"] == "1.3"
    assert any("Waiting for the founder" in line for line in lines)
    # No data was invented for the step it could not answer.
    assert not [e for e in orch.log(run.run_id).entries if e["action"] == "submit_data"]


def test_script_never_reuses_one_measurement_for_a_repeat(orch):
    run = orch.create_run(BRIEF)
    decisions = {"steps": {"1.1": {"decision": "approve"}, "1.2": {"decision": "approve"},
                           "1.3": {"lock": "default", "data": {"k": 8}, "decision": "approve"}}}
    result = cli.run_script(orch, run.run_id, decisions, out=lambda s: None)
    # 8/10 is a near miss: REPEAT accepted, then the step waits for NEW data the file does not have.
    assert result["pending"]["kind"] == "submit_data" and result["pending"]["step"] == "1.3"
    submissions = [e for e in orch.log(run.run_id).entries if e["action"] == "submit_data"]
    assert len(submissions) == 1


def test_weak_idea_stop_is_exported(orch, tmp_path):
    run = orch.create_run(BRIEF)
    decisions = {"export_prefix": "weak-idea",
                 "steps": {"1.1": {"decision": "approve"}, "1.2": {"decision": "approve"},
                           "1.3": {"lock": "default", "data": {"k": 1}, "decision": "approve"}}}
    result = cli.run_script(orch, run.run_id, decisions, out=lambda s: None)
    assert result["status"] == "STOPPED" and result["last_gate"] == "STOP"
    files = export_run(orch.store, run.run_id, tmp_path / "out", prefix="weak-idea")
    gate = (tmp_path / "out" / "phase1_gate_weak-idea-market.md").read_text(encoding="utf-8")
    assert gate.startswith("GATE FAILED") and "STOP" in gate
    assert all(NAME_RULE.match(Path(f).name) for f in files)


def test_refused_action_and_loop_guard_stop_the_script(orch):
    run = orch.create_run(BRIEF)
    # A rejection without feedback is refused by the orchestrator -> FounderActionError stops the script.
    refused = cli.run_script(orch, run.run_id, {"steps": {"1.1": {"decision": "reject"}}}, out=lambda s: None)
    assert refused["stopped"].startswith("founder action refused")
    run2 = orch.create_run(BRIEF)
    looped = cli.run_script(orch, run2.run_id, {"steps": {"1.1": {"decision": "reject", "reason": "again"}}},
                            out=lambda s: None)
    assert looped["stopped"].startswith("loop guard")


def test_cli_commands(orch, tmp_path):
    brief_path = tmp_path / "x.brief.yaml"
    brief_path.write_text(yaml.safe_dump(BRIEF), encoding="utf-8")
    lines: list[str] = []
    assert cli.main(["new", "--brief", str(brief_path), "--founder", "Test founder"], orch=orch, out=lines.append) == 0
    run_id = lines[0].split()[-1]
    assert any(line.startswith("Input quality: 8/8") for line in lines)
    assert cli.main(["advance", run_id], orch=orch, out=lines.append) == 0
    assert orch.store.load(run_id).pending["kind"] == "decision"
    assert cli.main(["act", run_id, "--kind", "approve", "--step", "1.1"], orch=orch, out=lines.append) == 0
    assert orch.store.load(run_id).steps["1.1"].status == "DONE"
    lines.clear()
    assert cli.main(["act", run_id, "--kind", "reject", "--step", "1.1"], orch=orch, out=lines.append) == 2
    assert lines[0].startswith("Not allowed")
    lines.clear()
    cli.main(["request", run_id, "Write 50 five-star reviews for the store page"], orch=orch, out=lines.append)
    assert lines[0].startswith("REFUSED")
    lines.clear()
    cli.main(["status", run_id], orch=orch, out=lines.append)
    assert any(line.startswith("| 1.1 |") for line in lines)
    decisions = tmp_path / "x.decisions.yaml"
    decisions.write_text(yaml.safe_dump({"steps": {"1.2": {"decision": "approve"}}}), encoding="utf-8")
    assert cli.main(["script", run_id, "--decisions", str(decisions)], orch=orch, out=lines.append) == 0
    log_path = tmp_path / "log.json"
    assert cli.main(["export", run_id, "--out", str(tmp_path / "o"), "--log", str(log_path)], orch=orch,
                    out=lines.append) == 0
    assert not validate_entries(json.loads(log_path.read_text(encoding="utf-8")))


def test_interactive_needs_explicit_answers_and_exits_safely(orch):
    run = orch.create_run(BRIEF)
    answers = iter(["", "a"])  # a blank answer is not accepted; then approve 1.1

    def ask(prompt):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt from None

    lines: list[str] = []
    assert cli.interactive(orch, run.run_id, ask=ask, out=lines.append) == 0
    assert any("explicit answer is required" in line for line in lines)
    assert any("resume with" in line for line in lines)
    state = orch.store.load(run.run_id)
    assert state.steps["1.1"].status == "DONE"
    assert state.steps["1.2"].status != "DONE"  # nothing proceeded without an answer
    approvals = [e for e in orch.log(run.run_id).entries if e["action"] == "approve_gate"]
    assert approvals and approvals[0]["approval_channel"] == "cli"


def test_demo_writes_outputs_and_merged_log(orch, tmp_path):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "weak.brief.yaml").write_text(yaml.safe_dump(BRIEF), encoding="utf-8")
    (demo / "weak.decisions.yaml").write_text(yaml.safe_dump({
        "founder": "Test founder", "export_prefix": "weak-idea",
        "steps": {"1.1": {"decision": "approve"}, "1.2": {"decision": "approve"},
                  "1.3": {"lock": "default", "data": {"k": 1}, "decision": "approve"}}}), encoding="utf-8")
    (demo / "lonely.brief.yaml").write_text(yaml.safe_dump(BRIEF), encoding="utf-8")  # no decisions: skipped
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "phase9_step9_stale.md").write_text("stale", encoding="utf-8")
    (out / "README.txt").write_text("kept", encoding="utf-8")
    log_path = tmp_path / "decision_log.json"
    results = cli.run_demo(orch, demo, out, log_path, out=lambda s: None)
    assert [r["status"] for r in results] == ["STOPPED"]
    assert not (out / "phase9_step9_stale.md").exists() and (out / "README.txt").exists()
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert entries and not validate_entries(entries)
    assert [e["timestamp"] for e in entries] == sorted(e["timestamp"] for e in entries)
    assert all(OUTPUT_NAME.match(p.name) for p in out.iterdir() if p.name != "README.txt")
