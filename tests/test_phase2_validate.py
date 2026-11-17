"""Phase 2 Validate (2.1 Lean Canvas, 2.2 landing-page test) driven through the real Orchestrator.

The model is STUBBED (FakeLLM with FIXTURE replies from stubs_validate_launch);
page events are FIXTURE data written straight into the run's events.json.
The clock of the measurement window is moved with monkeypatch.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest

import guardrails
from tests import stubs_validate_launch as stubs
from llm import FakeLLM, task_id_of
from orchestrator import Orchestrator
from phases import validate
from steps import STEP_IDS
from store import DONE, RunStore

BRIEF = {"idea": "Client feedback tracker for freelance designers", "customer": "freelance web designers",
         "why_you": "I freelance", "jurisdiction": "Egypt", "budget": "0", "time": "10h/week", "evidence": "none"}

PHASE1 = {
    "1.1": {"title": "Feedback hub", "problem_statement": "Designers lose client feedback across channels",
            "segment": "freelance web designers", "alternatives": []},
    "1.3": {"competitors": [], "channels": []},
}


def task_user_text(messages) -> str:
    for message in messages:
        if message.get("role") == "user" and "TASK_ID:" in (message.get("content") or ""):
            return message["content"]
    return ""


def kernel_stub(task: str):
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "stub"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        return {"reasoning": "STUBBED explanation.", "change_my_mind": "New valid data."}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "STUBBED phase summary.", "assumptions_confirmed": [], "assumptions_killed": [],
                "still_open": []}
    return {}


def make_model(override=None):
    def model(messages, tier):
        task = task_id_of(messages)
        text = task_user_text(messages)
        if override:
            reply = override(task, text)
            if reply is not None:
                return reply
        reply = stubs.respond(task, text)
        return reply if reply is not None else kernel_stub(task)
    return model


@pytest.fixture()
def orch(tmp_path):
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(make_model()))


def start_at(o: Orchestrator, step_id: str, outputs: dict) -> str:
    """Create a run and jump to step_id with earlier steps marked done and their outputs seeded."""
    run = o.create_run(BRIEF)
    assert run.pending is None and run.status == "ACTIVE"
    run = o.store.load(run.run_id)
    for sid in STEP_IDS[:STEP_IDS.index(step_id)]:
        run.steps[sid].status, run.steps[sid].outcome = DONE, "GO"
    for sid, output in outputs.items():
        run.steps[sid].output = dict(output)
    run.current_step = step_id
    o.store.save(run)
    return run.run_id


def write_events(o: Orchestrator, rid: str, events: list[dict]) -> None:
    o.store.events_path(rid).write_text(json.dumps(events), encoding="utf-8")


def landing_events(start, visitors: int, signups: int, *, prefix: str = "v") -> list[dict]:
    """FIXTURE landing-page events inside the window that starts at `start`."""
    events = []
    for i in range(visitors):
        ts = validate.iso(start + timedelta(minutes=10 + i))
        events.append({"type": "page_view", "page": "landing", "visitor_id": f"{prefix}{i}",
                       "source": "design-community" if i % 2 else None, "internal": False, "timestamp": ts})
    for i in range(signups):
        ts = validate.iso(start + timedelta(hours=30, minutes=i))
        events.append({"type": "waitlist_signup", "page": "landing", "email_hash": f"{prefix}hash{i}",
                       "role": "designer" if i % 3 == 0 else None, "source": None, "internal": False, "timestamp": ts})
    return events


def noise_events(start, end) -> list[dict]:
    """Events that must never count: internal traffic, duplicates, and events outside the window."""
    events = []
    for i in range(80):
        events.append({"type": "page_view", "page": "landing", "visitor_id": f"team{i}", "internal": True,
                       "timestamp": validate.iso(start + timedelta(hours=2))})
        events.append({"type": "waitlist_signup", "page": "landing", "email_hash": f"teamhash{i}", "internal": True,
                       "timestamp": validate.iso(start + timedelta(hours=2))})
    events.append({"type": "page_view", "page": "landing", "visitor_id": "late", "internal": False,
                   "timestamp": validate.iso(end + timedelta(days=1))})
    events.append({"type": "page_view", "page": "landing", "visitor_id": "early", "internal": False,
                   "timestamp": validate.iso(start - timedelta(days=1))})
    return events


def to_lock(o: Orchestrator) -> str:
    rid = start_at(o, "2.1", PHASE1)
    run = o.advance(rid)
    assert run.pending["kind"] == "decision" and run.pending["step"] == "2.1"
    o.act(rid, {"kind": "approve", "step": "2.1", "channel": "cli"})
    run = o.advance(rid)
    assert run.pending["kind"] == "lock_thresholds" and run.pending["step"] == "2.2"
    return rid


def lock_and_window(o: Orchestrator, rid: str, monkeypatch, *, publish: bool = True):
    o.act(rid, {"kind": "lock_thresholds", "step": "2.2", "channel": "cli", "approve_outward": publish})
    locked_at = validate.parse_ts(o.store.load(rid).steps["2.2"].contract["locked_at"])
    return locked_at, locked_at + timedelta(days=14)


def close_window(monkeypatch, end) -> None:
    monkeypatch.setattr(validate, "_now", lambda: end + timedelta(days=1))


# ------------------------------------------------------------------------------------------------ 2.1
def test_lean_canvas_has_nine_labelled_boxes_ranked_assumptions_and_channels(orch):
    rid = start_at(orch, "2.1", PHASE1)
    run = orch.advance(rid)
    st = run.steps["2.1"]
    assert run.pending["kind"] == "decision" and st.gate["status"] == "PENDING_APPROVAL"
    canvas = st.output["canvas"]
    assert len(canvas) == 9
    assert all(box["label"] in ("SOURCED", "FOUNDER_REPORTED", "ASSUMPTION", "UNKNOWN") for box in canvas.values())
    ledger = orch.ledger(rid)
    for box in canvas.values():
        assert all(ledger.get(i) is not None for i in box["evidence_ids"])
        if box["label"] == "FOUNDER_REPORTED":
            assert box["evidence_ids"] and ledger.get(box["evidence_ids"][0]).provenance == "FOUNDER_REPORTED"
    ranks = st.output["riskiest_assumptions"]
    assert [a["rank"] for a in ranks] == [1, 2, 3]
    assert ranks[0]["loss_score"] == 5  # ranked by loss if wrong, not by the model's order
    assert all(a["test"] and a["blocks_decision"] for a in ranks)
    assert [c["id"] for c in st.output["channels"]] == ["design-community", "freelance-newsletter"]
    assert st.output["uvp"]
    md = orch.store.read_artifact(rid, st.artifacts["deliverable.md"])
    assert "| Box | Content | Label | Evidence / basis |" in md and "Unique Value Proposition" in md
    assert not st.claim_problems
    orch.act(rid, {"kind": "approve", "step": "2.1", "channel": "cli"})
    assert orch.store.load(rid).current_step == "2.2"


def test_lean_canvas_drops_unresolvable_citations_and_unknown_urls(tmp_path):
    def override(task, text):
        if task != "business_designer.lean_canvas":
            return None
        reply = stubs.respond(task, text)
        reply["boxes"]["problem"].update(label="SOURCED", evidence_ids=["E-999"])
        reply["channels"][0]["url"] = "https://example.invalid/not-in-evidence"
        return reply

    o = Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(make_model(override)))
    rid = start_at(o, "2.1", PHASE1)
    st = o.advance(rid).steps["2.1"]
    assert st.output["canvas"]["problem"]["label"] == "ASSUMPTION"
    assert st.output["canvas"]["problem"]["evidence_ids"] == []
    assert st.output["channels"][0]["url"] is None
    md = o.store.read_artifact(rid, st.artifacts["deliverable.md"])
    assert "E-999" in md and "removed" in md


# ------------------------------------------------------------------------------------------------ 2.2 page
def test_landing_page_published_to_mock_site_only_after_lock_approval(orch, monkeypatch):
    rid = to_lock(orch)
    run = orch.store.load(rid)
    st = run.steps["2.2"]
    site = orch.store.path(rid) / "site" / "landing.html"
    assert not site.exists()
    assert [o["item_id"] for o in run.pending["outward"]] == ["landing-page"]
    contract = st.contract
    assert {c["key"]: (c["target"], c["kind"]) for c in contract["criteria"]} == {
        "unique_visitors": (300, "floor"), "signup_rate": (0.10, "proportion")}
    assert contract["window_days"] == 14 and contract["pivot_target"] == "1.4"
    assert "internal" in contract["notes"] and "duplicate" in contract["notes"]

    orch.act(rid, {"kind": "lock_thresholds", "step": "2.2", "channel": "cli", "approve_outward": True})
    assert site.exists()
    page = site.read_text(encoding="utf-8")
    assert page == orch.store.read_artifact(rid, st.artifacts["landing.html"])
    outbox = orch.store.path(rid) / "outbox"
    assert not outbox.exists() or not any(outbox.iterdir())
    assert any(e["action"] == "mock_publish" and e["approved_by"] == "founder" for e in orch.log(rid).entries)

    run = orch.advance(rid)  # window just opened: partial values only
    assert run.pending["kind"] == "submit_data"
    obs = run.steps["2.2"].observation
    assert obs["measurement_state"] == "WAITING_FOR_DATA"
    assert obs["observed"]["unique_visitors"] == 0 and obs["observed"]["signup_rate"] is None
    assert obs["details"]["days_remaining"] > 13
    assert obs["details"]["published_page_matches_this_attempt"] is True


def test_landing_page_without_outward_approval_is_not_published(orch, monkeypatch):
    rid = to_lock(orch)
    lock_and_window(orch, rid, monkeypatch, publish=False)
    assert not (orch.store.path(rid) / "site" / "landing.html").exists()
    run = orch.advance(rid)
    assert run.steps["2.2"].observation["measurement_state"] == "WAITING_FOR_DATA"


def test_landing_html_is_honest_self_contained_and_wired(orch):
    rid = to_lock(orch)
    st = orch.store.load(rid).steps["2.2"]
    page = orch.store.read_artifact(rid, st.artifacts["landing.html"])
    assert validate.LANDING_BANNER in page and "MOCKED" in page
    assert f'method="post" action="/p/{rid}/waitlist"' in page
    assert re.search(r'<input id="email" name="email" type="email" required', page)
    assert re.search(r'<input id="consent" name="consent" type="checkbox" value="yes" required>', page)
    assert '<input type="hidden" id="source" name="source"' in page
    assert '<input type="hidden" name="page" value="landing">' in page
    assert f'"/p/{rid}/event"' in page and "utm_source" in page and "localStorage" in page
    assert '"page_view"' in page and 'page: "landing"' in page
    assert page.count("Join the research waitlist") >= 2
    assert "Not built yet" in page
    # The app keeps only an email hash: the page says so and never promises to contact anyone.
    assert "one-way hash" in page and "will not email" in page
    assert "may email you" not in page and "contacted by email" not in page
    answers = [f["answer"] for f in st.output["copy"]["faq"]]
    assert validate.WAITLIST_AFTER_JOIN in answers
    assert not any(validate.CONTACT_PROMISE.search(a) for a in answers
                   if a not in (validate.WAITLIST_AFTER_JOIN, validate.AVAILABILITY))
    assert not re.search(r"https?://", page)               # no external fonts, scripts, images or trackers
    assert not re.search(r"countdown|testimonial|★", page, re.I)
    assert guardrails.check_marketing(page) == []
    assert '<meta name="viewport"' in page and '<html lang="en">' in page
    assert st.guardrail_flags == []
    data = st.output
    assert data["cta"] == "Join the research waitlist"
    assert [r["channel_id"] for r in data["traffic_plan"]] == ["design-community", "freelance-newsletter"]
    assert all(r["owner"] == "founder" and r["duration_days"] == 14 and r["budget"] == "0" for r in data["traffic_plan"])
    assert data["traffic_plan"][0]["tracked_link"] == f"/site/{rid}/landing.html?utm_source=design-community"
    assert {e["event"] for e in data["event_dictionary"]} == {"page_view", "waitlist_signup"}


# ------------------------------------------------------------------------------------------------ 2.2 gate
def test_landing_gate_go_from_local_events_after_the_window(orch, monkeypatch):
    rid = to_lock(orch)
    start, end = lock_and_window(orch, rid, monkeypatch)
    events = landing_events(start, 320, 40) + noise_events(start, end)
    first_signup = next(e for e in events if e["type"] == "waitlist_signup")
    events.append(dict(first_signup, timestamp=validate.iso(start + timedelta(days=2))))  # duplicate sign-up email
    write_events(orch, rid, events)
    close_window(monkeypatch, end)
    run = orch.advance(rid)
    st = run.steps["2.2"]
    assert st.observation["measurement_state"] == "READY"
    assert st.observation["observed"] == {"unique_visitors": 320.0, "signup_rate": 0.125}
    assert st.gate["outcome"] == "GO" and st.gate["status"] == "PASSED"
    details = st.observation["details"]
    assert details["excluded_events"]["internal"] == 160 and details["excluded_events"]["outside_window"] == 2
    assert "%" in details["signup_rate_95ci_wilson"]
    assert any(r.provenance == "DIRECT_OBSERVATION" for r in orch.ledger(rid).all())
    orch.act(rid, {"kind": "approve", "step": "2.2", "channel": "cli"})
    run = orch.store.load(rid)
    assert run.steps["2.2"].outcome == "GO" and run.pending["kind"] == "phase_review"


def test_landing_gate_twelve_percent_of_target_recommends_stop(orch, monkeypatch):
    rid = to_lock(orch)
    start, end = lock_and_window(orch, rid, monkeypatch)
    write_events(orch, rid, landing_events(start, 1000, 12))
    close_window(monkeypatch, end)
    run = orch.advance(rid)
    gate = run.steps["2.2"].gate
    assert gate["status"] == "FAILED" and gate["outcome"] == "STOP"
    assert gate["pct_of_target"] == pytest.approx(0.12)
    orch.act(rid, {"kind": "approve", "step": "2.2", "channel": "cli"})
    assert orch.store.load(rid).status == "STOPPED"


def test_landing_gate_missed_visitor_floor_pivots_back_to_lean_canvas(orch, monkeypatch):
    rid = to_lock(orch)
    start, end = lock_and_window(orch, rid, monkeypatch)
    write_events(orch, rid, landing_events(start, 150, 30))
    close_window(monkeypatch, end)
    run = orch.advance(rid)
    gate = run.steps["2.2"].gate
    # A missed traffic floor means demand was not measured: fix traffic and re-run (REPEAT), or pivot back to
    # the channel step 2.1, which is offered as the alternative. Never STOP on sample size alone.
    assert gate["outcome"] == "REPEAT" and gate["alternative"] == "PIVOT_BACK" and gate["pivot_target"] == "2.1"
    orch.act(rid, {"kind": "decide", "step": "2.2", "outcome": "PIVOT_BACK", "reason": "fix channels first",
                   "channel": "cli"})
    assert orch.store.load(rid).current_step == "2.1"


def test_landing_gate_refresh_by_empty_submission_after_waiting(orch, monkeypatch):
    rid = to_lock(orch)
    start, end = lock_and_window(orch, rid, monkeypatch)
    run = orch.advance(rid)
    assert run.pending["kind"] == "submit_data"
    write_events(orch, rid, landing_events(start, 400, 44))
    close_window(monkeypatch, end)
    orch.act(rid, {"kind": "submit_data", "step": "2.2", "data": {}, "channel": "cli"})
    gate = orch.store.load(rid).steps["2.2"].gate
    assert gate["outcome"] == "GO"


def test_founder_reported_data_waits_for_the_window_then_counts(orch, monkeypatch):
    rid = to_lock(orch)
    start, end = lock_and_window(orch, rid, monkeypatch)
    orch.advance(rid)
    data = {"unique_visitors": 400, "signups": 48, "analytics_source": "FIXTURE analytics tool"}
    orch.act(rid, {"kind": "submit_data", "step": "2.2", "data": data, "channel": "cli"})
    gate = orch.store.load(rid).steps["2.2"].gate
    assert gate["status"] == "NOT_EVALUABLE" and gate["outcome"] is None   # window still open: no peeking
    close_window(monkeypatch, end)
    orch.advance(rid)   # the pipeline re-opens the data request; actions must answer a pending item
    orch.act(rid, {"kind": "submit_data", "step": "2.2", "data": data, "channel": "cli"})
    st = orch.store.load(rid).steps["2.2"]
    assert st.gate["outcome"] == "GO"
    assert st.observation["observed"]["signup_rate"] == pytest.approx(0.12)
    rows = [r for r in orch.ledger(rid).all() if r.provenance == "FOUNDER_REPORTED" and "FIXTURE analytics" in r.title]
    assert rows and st.observation["evidence_ids"] == [rows[-1].evidence_id]


def test_founder_data_with_more_signups_than_visitors_is_invalid(orch, monkeypatch):
    rid = to_lock(orch)
    _start, end = lock_and_window(orch, rid, monkeypatch)
    close_window(monkeypatch, end)
    orch.advance(rid)
    orch.act(rid, {"kind": "submit_data", "step": "2.2", "data": {"unique_visitors": 10, "signups": 50},
                   "channel": "cli"})
    gate = orch.store.load(rid).steps["2.2"].gate
    assert gate["status"] == "NOT_EVALUABLE" and gate["outcome"] is None
