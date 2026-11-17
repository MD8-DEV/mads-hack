"""Phase 3 (Build) tests: the real Orchestrator drives 3.1 -> 3.2 -> 3.3 with a STUBBED model.

Model replies are FIXTURE data from tests/stubs_build.py. Earlier steps are
seeded as done, with FIXTURE outputs. Offline: no model API or network call.
"""
from __future__ import annotations

import json

import pytest

from agents import builder, product_manager, qa
from evidence import Evidence
from llm import FakeLLM, task_id_of
from logbook import validate_entries
from orchestrator import Orchestrator
from phases.build import UserTestAndDocs
from store import DONE, RunStore
from tests import stubs_build

BRIEF = {"idea": "Client feedback log for freelance web designers", "customer": "freelance web designers",
         "why_you": "I freelance", "jurisdiction": "Egypt", "budget": "0", "time": "10h/week", "evidence": "none"}


def core_stub(task: str):
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


def make_llm(build_queue: list[dict] | None = None) -> FakeLLM:
    """STUBBED model: queued builder replies first, then the Phase 3 FIXTURE stubs, then core stubs."""
    queue = list(build_queue or [])

    def responder(messages, tier):
        task = task_id_of(messages)
        if task == "builder.build_product" and queue:
            return queue.pop(0)
        reply = stubs_build.respond(task, messages[1]["content"])
        return reply if reply is not None else core_stub(task)

    return FakeLLM(responder)


def make_orch(tmp_path, build_queue=None) -> Orchestrator:
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=make_llm(build_queue))


def seed_to_phase3(orch: Orchestrator) -> str:
    """Create a run and mark Phase 1-2 as done with FIXTURE outputs, so the run starts at 3.1."""
    run = orch.create_run(BRIEF)
    rid = run.run_id
    run = orch.store.load(rid)
    for sid in ("1.1", "1.2", "1.3", "1.4", "2.1", "2.2"):
        run.steps[sid].status, run.steps[sid].outcome = DONE, "GO"
    run.steps["1.1"].output = {"title": "Client feedback log", "segment": "freelance web designers",
                               "problem_statement": "FIXTURE: designers lose client feedback across email and chat",
                               "alternatives": []}
    run.steps["2.1"].output = {"title": "FIXTURE Lean Canvas", "canvas": {"problem": "FIXTURE problem"}}
    run.steps["2.2"].output = {"title": "FIXTURE landing page test"}
    run.current_step, run.pending = "3.1", None
    orch.store.save(run)
    orch.ledger(rid).add(Evidence(provenance="FOUNDER_REPORTED", source_type="founder_data",
                                  title="FIXTURE: founder reports clients send feedback by email and chat",
                                  excerpt="FIXTURE row for tests"))
    return rid


def builder_payloads(orch: Orchestrator) -> list[str]:
    return [c["messages"][1]["content"] for c in orch.llm.calls if task_id_of(c["messages"]) == "builder.build_product"]


def drive_to_33_data(orch: Orchestrator) -> str:
    """3.1 approved, passing 3.2 build accepted, 3.3 thresholds locked: waiting for founder data."""
    rid = seed_to_phase3(orch)
    orch.advance(rid)
    orch.act(rid, {"kind": "approve", "step": "3.1"})
    run = orch.advance(rid)
    assert run.steps["3.2"].gate["outcome"] == "GO"
    orch.act(rid, {"kind": "approve", "step": "3.2"})
    run = orch.advance(rid)
    assert run.pending["kind"] == "lock_thresholds" and run.pending["step"] == "3.3"
    orch.act(rid, {"kind": "lock_thresholds", "step": "3.3"})
    run = orch.advance(rid)
    assert run.pending["kind"] == "submit_data" and run.pending["step"] == "3.3"
    return rid


# ------------------------------------------------------------------ end-to-end through the orchestrator
def test_failing_build_repeats_then_passes_and_user_test_goes(tmp_path):
    orch = make_orch(tmp_path, build_queue=[stubs_build.build_reply(passing=False)])
    rid = seed_to_phase3(orch)

    # 3.1: scope waits for founder approval; evidence and labels resolved by code
    run = orch.advance(rid)
    assert run.pending["kind"] == "decision" and run.pending["step"] == "3.1"
    scope = run.steps["3.1"].output
    assert len(scope["must_haves"]) <= 5
    f1 = next(m for m in scope["must_haves"] if m["id"] == "F1")
    assert f1["label"] == "FOUNDER_REPORTED" and f1["evidence_ids"] == ["E-001"]
    assert all(m["label"] == "ASSUMPTION" for m in scope["must_haves"] if m["id"] != "F1")
    assert {c["check"]["type"] for c in scope["acceptance_criteria"]} <= set(qa.CHECK_TYPES)
    orch.act(rid, {"kind": "approve", "step": "3.1"})

    # 3.2 attempt 0: external script -> tests fail -> REPEAT recommended, thresholds locked by system policy
    run = orch.advance(rid)
    st = run.steps["3.2"]
    assert run.pending["kind"] == "decision" and run.pending["step"] == "3.2"
    assert st.contract["locked_by"] == "system:tests"
    assert st.gate["outcome"] == "REPEAT"
    assert st.observation["observed"]["critical_pass_rate"] < 1.0
    failed = {f["id"] for f in st.output["failed_tests"]}
    assert {"G5", "AC5"} <= failed
    report = orch.store.read_artifact(rid, st.artifacts["test_report.md"])
    assert "| G5 |" in report and "FAIL" in report
    orch.act(rid, {"kind": "approve", "step": "3.2"})   # accept the recommended REPEAT

    # 3.2 attempt 1: the builder is told what failed, the fixed build passes -> GO
    run = orch.advance(rid)
    st = run.steps["3.2"]
    assert st.attempt == 1 and st.repeat_count == 1
    assert st.gate["outcome"] == "GO" and st.gate["status"] == "PASSED"
    second = builder_payloads(orch)[1]
    assert '"previous_failures"' in second and "G5" in second and "cdn.example.com" in second
    observed = st.observation["observed"]
    assert observed == {"critical_pass_rate": 1.0, "acceptance_met_rate": 1.0, "open_critical_high_bugs": 0.0}
    report = orch.store.read_artifact(rid, st.artifacts["test_report.md"])
    assert "| FAIL |" not in report and "MODEL_REVIEW" in report
    assert "<script src=" not in orch.store.read_artifact(rid, st.artifacts["product/index.html"])
    ledger_row = orch.ledger(rid).get(st.observation["evidence_ids"][0])
    assert ledger_row.provenance == "DIRECT_OBSERVATION"
    orch.act(rid, {"kind": "approve", "step": "3.2"})

    # 3.3: docs from the actual build, thresholds proposed, invitation is a MOCKED send waiting for approval
    run = orch.advance(rid)
    st = run.steps["3.3"]
    assert run.pending["kind"] == "lock_thresholds" and run.pending["step"] == "3.3"
    for name in ("docs/quick-start.md", "docs/faq.md", "docs/how-to.md", "docs/limitations.md",
                 "usability_test_plan.md", "usability_invite.md"):
        assert name in st.artifacts
    assert "Save feedback" in orch.store.read_artifact(rid, st.artifacts["docs/how-to.md"])
    limitations = orch.store.read_artifact(rid, st.artifacts["docs/limitations.md"])
    assert "localStorage" in limitations and "Sync between devices" in limitations
    assert st.output["doc_warnings"] == []
    criteria = {c["key"]: c for c in st.contract["criteria"]}
    assert criteria["participants"]["kind"] == "floor" and criteria["participants"]["target"] == 5
    assert criteria["unassisted_completion_rate"]["target"] == 0.8
    assert criteria["critical_failures"]["op"] == "<=" and criteria["critical_failures"]["kind"] == "hard"
    assert [o["item_id"] for o in run.pending["outward"]] == ["usability-invite"]
    assert not (orch.store.outbox_dir(rid) / "usability-invite.md").exists()
    orch.act(rid, {"kind": "lock_thresholds", "step": "3.3", "approve_outward": True})
    sent = (orch.store.outbox_dir(rid) / "usability-invite.md").read_text(encoding="utf-8")
    assert sent.startswith("<!-- MOCKED") and "[first name]" in sent

    # 3.3 founder data: 4 of 5 unassisted, no critical failures -> GO
    run = orch.advance(rid)
    assert run.pending["kind"] == "submit_data"
    orch.act(rid, {"kind": "submit_data", "step": "3.3",
                   "data": {"participants": 5, "completed_unassisted": 4, "critical_failures": 0,
                            "session_notes": "FIXTURE notes: P3 needed a hint to find the export."}})
    run = orch.advance(rid)
    st = run.steps["3.3"]
    assert st.gate["outcome"] == "GO"
    assert st.observation["observed"]["unassisted_completion_rate"] == 0.8
    low, high = st.observation["details"]["wilson_95"]
    assert 0 < low < 0.8 < high <= 1
    row = orch.ledger(rid).get(st.observation["evidence_ids"][0])
    assert row.provenance == "FOUNDER_REPORTED" and row.denominator == 5
    orch.act(rid, {"kind": "approve", "step": "3.3"})
    run = orch.store.load(rid)
    assert run.pending["kind"] == "phase_review" and run.pending["phase"] == 3

    entries = orch.log(rid).entries
    assert not validate_entries(entries)
    assert sum(1 for e in entries if e["action"] == "run_acceptance_tests") == 2
    sends = [e for e in entries if e["action"] == "mock_send"]
    assert len(sends) == 1 and sends[0]["approved_by"] == "founder" and sends[0]["mocked"] is True


def test_user_test_fails_on_completion_and_routes_to_lean_canvas(tmp_path):
    orch = make_orch(tmp_path)
    rid = drive_to_33_data(orch)
    orch.act(rid, {"kind": "submit_data", "step": "3.3",
                   "data": {"participants": 5, "completed_unassisted": 2, "critical_failures": 0}})
    run = orch.advance(rid)
    gate = run.steps["3.3"].gate
    assert gate["status"] == "FAILED" and gate["outcome"] == "PIVOT_BACK" and gate["pivot_target"] == "2.1"


def test_user_test_critical_failure_points_at_the_build(tmp_path):
    orch = make_orch(tmp_path)
    rid = drive_to_33_data(orch)
    orch.act(rid, {"kind": "submit_data", "step": "3.3",
                   "data": {"participants": 5, "completed_unassisted": 5, "critical_failures": 1}})
    run = orch.advance(rid)
    gate = run.steps["3.3"].gate
    assert gate["status"] == "FAILED" and gate["outcome"] != "GO"
    assert gate["pivot_target"] == "3.2"   # users reach the value, something breaks: fix the build


@pytest.mark.parametrize("data", [
    {"participants": 5, "completed_unassisted": 6, "critical_failures": 0},   # more completions than people
    {"participants": 0, "completed_unassisted": 0, "critical_failures": 0},   # no sessions run
    {"participants": "five", "completed_unassisted": 4, "critical_failures": 0},
])
def test_user_test_bad_or_missing_data_is_not_evaluable(tmp_path, data):
    orch = make_orch(tmp_path)
    rid = drive_to_33_data(orch)
    orch.act(rid, {"kind": "submit_data", "step": "3.3", "data": data})
    run = orch.advance(rid)
    gate = run.steps["3.3"].gate
    assert gate["status"] == "NOT_EVALUABLE" and gate["outcome"] is None


def test_invite_stays_unsent_without_founder_approval(tmp_path):
    orch = make_orch(tmp_path)
    rid = drive_to_33_data(orch)   # thresholds locked without approving the outward item
    assert not (orch.store.outbox_dir(rid) / "usability-invite.md").exists()
    assert not any(e["action"].startswith("mock_") for e in orch.log(rid).entries)


# ------------------------------------------------------------------ scope rules enforced by code
def test_scope_normalisation_enforces_limits_and_check_types():
    raw = {
        "must_haves": [{"id": f"F{i}", "feature": f"Feature {i}", "evidence_ids": ["E-001", "E-999"]} for i in range(1, 7)]
        + [{"id": "F7", "feature": "Log in with a password", "user_value": "accounts"}],
        "acceptance_criteria": [
            {"id": "AC1", "feature": "F1", "check": {"type": "screenshot_matches", "value": "x"}},
            {"id": "AC2", "feature": "F2", "check": {"type": "regex", "file": "product/index.html", "value": "(unclosed"}},
            {"id": "AC3", "feature": "Feature 3", "check": {"type": "html_element", "value": "form#add button.primary"}},
            {"id": "AC4", "feature": "F6", "check": {"type": "contains", "value": "six"}},
            {"id": "AC5", "feature": "F7", "check": {"type": "contains", "value": "password"}},
            {"id": "AC6", "feature": "F4", "check": {"type": "contains", "file": "../secrets.txt", "value": "x"}},
        ],
    }
    scope, notes = product_manager.normalize_scope(product_manager.validate_scope(raw), {"E-001"},
                                                   {"E-001": "SOURCE_FACT"})
    assert [m["id"] for m in scope["must_haves"]] == ["F1", "F2", "F3", "F4", "F5"]
    assert all(m["evidence_ids"] == ["E-001"] and m["label"] == "SOURCED" for m in scope["must_haves"])
    wont = {w["feature"] for w in scope["wont_build"]}
    assert {"Feature 6", "Log in with a password"} <= wont
    checks = {c["id"]: c for c in scope["acceptance_criteria"]}
    assert checks["AC1"]["check"] == {"type": "file_exists", "file": "product/index.html", "value": ""}
    assert checks["AC2"]["check"]["type"] == "file_exists"
    assert checks["AC3"]["check"]["value"] == "button.primary" and checks["AC3"]["feature"] == "F3"
    assert "AC4" not in checks and "AC5" not in checks   # their features were cut or excluded by policy
    assert checks["AC6"]["check"]["file"] == "product/index.html"
    assert any("E-999" in n for n in notes) and any("more than 5" in n or "kept the first 5" in n for n in notes)


def test_scope_without_acceptance_criteria_is_rejected():
    with pytest.raises(ValueError):
        product_manager.validate_scope({"must_haves": [{"feature": "x"}], "acceptance_criteria": []})


# ------------------------------------------------------------------ deterministic QA checks
def _files(html: str = stubs_build.FIXTURE_INDEX_HTML, readme: str = stubs_build.FIXTURE_README) -> dict[str, str]:
    return {qa.INDEX: html, qa.README: readme}


def _failed(files: dict[str, str], acceptance=None) -> set[str]:
    return {t["id"] for t in qa.run_checks(files, acceptance or []) if not t["passed"]}


def test_fixture_build_passes_every_check():
    tests = qa.run_checks(_files(), stubs_build.SCOPE_REPLY["acceptance_criteria"])
    assert all(t["passed"] for t in tests), [t for t in tests if not t["passed"]]
    m = qa.metrics(tests, [])
    assert m["critical_pass_rate"] == 1.0 and m["acceptance_met_rate"] == 1.0


@pytest.mark.parametrize("change, failing", [
    (('</head>', '<link rel="stylesheet" href="https://fonts.example.com/a.css"></head>'), "G5"),
    (('render();\n</script>', 'fetch("https://api.example.com/x");\nrender();\n</script>'), "G5"),
    (('</head>', '<style>body{background:url(//img.example.com/b.png)}</style></head>'), "G5"),
    (('<label for="note">', '<label for="pw">Password</label><input id="pw" name="pw" type="password"><label for="note">'), "G6"),
    (('<label for="note">', '<label for="cn">Card number</label><input id="cn"><label for="note">'), "G6"),
    (('<h2>Saved feedback</h2>', '<h2>Saved feedback</h2><p>Lorem ipsum dolor</p>'), "G4"),
    (('<h2>Saved feedback</h2>', '<h2>Saved feedback</h2><p>Trusted by 5,000 designers</p>'), "G7"),
    (('<h2>Saved feedback</h2>', '<h2>Saved feedback</h2><button>Upgrade to Pro</button>'), "G10"),
    (('</script>\n</body>', '</body>'), "G3"),
    (('render();\n</script>', 'const API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456";\nrender();\n</script>'), "G9"),
])
def test_generic_checks_catch_problems(change, failing):
    old, new = change
    html = stubs_build.FIXTURE_INDEX_HTML.replace(old, new, 1)
    assert html != stubs_build.FIXTURE_INDEX_HTML
    assert failing in _failed(_files(html))


def test_flashcard_style_names_are_not_payment_fields():
    html = stubs_build.FIXTURE_INDEX_HTML.replace(
        '<label for="note">', '<label for="card-front">Card front</label><input id="card-front"><label for="note">')
    assert "G6" not in _failed(_files(html))


def test_readme_usage_size_and_paths():
    assert "G8" in _failed(_files(readme="# Name\n\nSome text.\n"))
    big = stubs_build.FIXTURE_INDEX_HTML.replace("</body>", "<p>" + "a" * (qa.SIZE_CAP_BYTES + 10) + "</p></body>")
    assert "G2" in _failed(_files(big))
    assert "G1" in _failed({qa.INDEX: stubs_build.FIXTURE_INDEX_HTML})


def test_acceptance_check_types():
    files = _files()
    ok = [("html_element", "input[type=date]", False), ("html_element", "button#export", True),
          ("html_element", "form.missing", False), ("contains", "LOCALSTORAGE", True),
          ("regex", r"^<h1>Client", True), ("no_external_requests", "", True), ("file_exists", "", True)]
    for kind, value, expected in ok:
        passed, detail = qa.run_acceptance_check({"type": kind, "file": qa.INDEX, "value": value}, files)
        assert passed is expected, (kind, value, detail)
    assert qa.run_acceptance_check({"type": "file_exists", "file": "product/missing.md"}, files)[0] is False


def test_model_review_bugs_count_only_with_severity_and_reproduction():
    review = qa.validate_review({"bugs": [
        {"title": "Data lost on reload", "severity": "critical",
         "reproduction": "Save an item, reload the page: load() reads the wrong key."},
        {"title": "Vague worry", "severity": "high", "reproduction": "n/a"},
        {"title": "Cosmetic", "severity": "low", "reproduction": "Look at the footer spacing on a phone."},
    ]})
    assert [b["counts"] for b in review["bugs"]] == [True, False, False]
    assert all(b["label"] == qa.MODEL_REVIEW for b in review["bugs"])
    assert qa.metrics([], review["bugs"])["open_critical_high_bugs"] == 1


def test_builder_reply_validation():
    reply = builder.validate_build({"files": [
        {"path": "index.html", "content": "```html\n" + stubs_build.FIXTURE_INDEX_HTML + "\n```"},
        {"path": "product/README.md", "content": stubs_build.FIXTURE_README},
        {"path": "../../etc/evil.sh", "content": "x"}]})
    assert set(reply["files"]) == {qa.INDEX, qa.README}
    assert reply["files"][qa.INDEX].startswith("<!DOCTYPE html>")
    assert reply["dropped_paths"] == ["../../etc/evil.sh"]
    with pytest.raises(ValueError):
        builder.validate_build({"files": {"product/README.md": "# x"}})


def test_docs_mentioning_missing_ui_labels_are_flagged():
    docs = json.loads(json.dumps(stubs_build.DOCS_REPLY))
    docs["how_to"][0]["steps"].append("Press **Archive** to hide old items.")
    from agents.doc_writer import validate_docs
    warnings = UserTestAndDocs._label_warnings(validate_docs(docs), qa.searchable_text(stubs_build.FIXTURE_INDEX_HTML))
    assert warnings == ["The docs mention 'Archive', which does not appear in the built product."]
