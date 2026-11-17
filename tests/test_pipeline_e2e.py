"""End-to-end smoke test: all 17 REAL step handlers, the real orchestrator and the real
scripted founder, with a STUBBED model (FIXTURE replies from tests/stubs_*.py) and research
disabled, so it runs offline in a few seconds.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import cli
import config
import export
import stubs_build
import stubs_commercial_operate
import stubs_discover
import stubs_validate_launch
from llm import FakeLLM, task_id_of
from logbook import validate_entries
from orchestrator import Orchestrator
from steps import STEPS
from store import DONE, RunStore

ROOT = Path(__file__).resolve().parents[1]
STUBS = (stubs_discover, stubs_validate_launch, stubs_build, stubs_commercial_operate)
OUTPUT_NAME = re.compile(r"^(phase\d_(step\d+|gate)_[a-z0-9-]+\.(md|json|html|csv|txt)|payment_test_log\.md)$")


def kernel_stub(task: str):
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "FIXTURE"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        return {"reasoning": "FIXTURE explanation of the computed gate.", "change_my_mind": "New valid data."}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "FIXTURE phase summary.", "assumptions_confirmed": [], "assumptions_killed": [],
                "still_open": []}
    return None


def responder(messages, tier):
    task = task_id_of(messages)
    user_text = next((m["content"] for m in messages if m.get("role") == "user" and "TASK_ID:" in m.get("content", "")), "")
    for module in STUBS:
        reply = module.respond(task, user_text)
        if reply is not None:
            return reply
    reply = kernel_stub(task)
    if reply is not None:
        return reply
    raise AssertionError(f"no FIXTURE reply for model task {task!r}")


@pytest.fixture()
def orch(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "0")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    settings = config.load_settings()
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(responder), settings=settings)


def test_full_pipeline_offline(orch, tmp_path):
    brief = cli.load_data_file(ROOT / "demo" / "freelance-revisions.brief.yaml")
    decisions = cli.normalise_decisions(cli.load_data_file(ROOT / "demo" / "freelance-revisions.decisions.yaml"))
    run = orch.create_run(brief, founder=decisions.get("founder", "founder"))
    result = cli.ScriptedFounder(orch, decisions, out=lambda *a, **k: None).run(run.run_id)
    run = orch.store.load(run.run_id)

    assert run.status in ("COMPLETED", "STOPPED"), (run.status, run.pending, result)
    # Every step produced a deliverable.
    for meta in STEPS:
        st = run.steps[meta.step_id]
        assert st.status == DONE, (meta.step_id, st.status)
        assert "deliverable.md" in st.artifacts, meta.step_id

    entries = orch.log(run.run_id).entries
    assert validate_entries(entries) == []
    kinds = {e["action_type"] for e in entries}
    assert {"GATE_DECISION", "FOUNDER_OVERRIDE", "FOUNDER_APPROVAL", "THRESHOLD_SET", "RUN_TESTS"} & kinds >= {
        "GATE_DECISION", "FOUNDER_OVERRIDE", "FOUNDER_APPROVAL", "THRESHOLD_SET"}

    # With research disabled the market gate cannot pass; skipping it is an override, never a pass.
    gate13 = run.steps["1.3"].gate or {}
    assert not gate13.get("evidence_passed")
    assert run.steps["1.3"].overridden

    # The memo may not recommend PERSEVERE when evidence gates were overridden.
    assert run.steps["6.3"].output.get("recommendation") in ("PIVOT", "STOP")

    # Outward items exist only for approved items, and only in the local MOCKED site/outbox.
    site = orch.store.site_dir(run.run_id)
    published = {p.name for p in site.iterdir()}
    assert "landing.html" in published and "store.html" in published
    outbox = list(orch.store.outbox_dir(run.run_id).iterdir())
    assert outbox and all("MOCKED" in p.read_text(encoding="utf-8") for p in outbox)

    # Export produces correctly named files, including the payment test log.
    out_dir = tmp_path / "outputs"
    written = export.export_run(orch.store, run.run_id, out_dir, log_path=tmp_path / "decision_log.json")
    names = sorted(Path(p).name for p in written if Path(p).parent == out_dir)
    assert names and all(OUTPUT_NAME.match(n) for n in names), [n for n in names if not OUTPUT_NAME.match(n)]
    assert "payment_test_log.md" in names
    assert any(n.startswith("phase1_gate_") for n in names)
