"""Founder web app tests: STUBBED step handlers, a STUBBED model (FakeLLM) and a temporary run store.

They drive the real Orchestrator through the HTTP routes: run creation, every pending
panel, founder actions and their errors, the local MOCKED site, first-party events,
hashed waitlist emails, the request box guardrails and the MOCKED order flow.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import FormData

import app as app_module
import refunds
import steps
from commerce import CommerceStore
from gates import Contract, Criterion
from llm import FakeLLM, task_id_of
from logbook import validate_entries
from orchestrator import Orchestrator
from phases.base import DataField, Observation, StepHandler, StepOutput
from store import RunStore

LANDING = "<html><body><h1>FIXTURE landing page</h1><form action='waitlist'></form></body></html>"
PRODUCT = "<html><body><h1>FIXTURE product main file</h1></body></html>"


def stub_model(messages, tier):
    task = task_id_of(messages)
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "stub"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        return {"reasoning": "Stub reasoning from the numbers.", "change_my_mind": "New valid data."}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "Stub phase summary.", "assumptions_confirmed": ["stub confirmed"],
                "assumptions_killed": [], "still_open": []}
    return {}


class WebStub(StepHandler):
    """STUBBED handler: fixed deliverables; E/T gates use one criterion 'k' >= 10."""

    def generate(self, ctx):
        data, files = {}, {}
        if ctx.step_id == "1.1":
            files = {"landing.html": LANDING}
            data["outward"] = [{"kind": "publish", "item_id": "landing", "file": "landing.html",
                                "when": "on_approve", "target_name": "landing.html"}]
        if ctx.step_id == "1.2":
            data = {"concepts": [{"id": "c1", "name": "Top", "rank": 1, "weighted_total": 50},
                                 {"id": "c2", "name": "Second", "rank": 2, "weighted_total": 40}],
                    "recommended_id": "c1"}
        if ctx.step_id == "6.3":
            data = {"recommendation": "STOP"}
        obs = Observation(observed={"k": 10.0}) if self.meta.gate_types == ("T",) else None
        return StepOutput(title=f"stub {ctx.step_id}", markdown=f"Stub deliverable for **{ctx.step_id}**.",
                          data=data, files=files, summary=f"Stub summary for {ctx.step_id}", observation=obs)

    def default_contract(self, ctx):
        if not self.meta.has_evidence_gate:
            return None
        return Contract(step_id=ctx.step_id, criteria=[Criterion(key="k", label="Key metric", target=10)])

    def data_fields(self):
        return [DataField(key="k", label="Key metric", type="number")]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for meta in steps.STEPS:
        handler = WebStub()
        handler.meta = meta
        monkeypatch.setitem(steps._HANDLER_CACHE, meta.handler, handler)
    orch = Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(stub_model))
    monkeypatch.setattr(app_module, "ORCH", orch)
    monkeypatch.setattr(app_module, "ADVANCE_MODE", "sync")
    with TestClient(app_module.app) as client:
        yield client, orch


BRIEF = {"title": "Feedback tracker", "idea": "Client feedback tracker for freelance designers",
         "customer": "freelance web designers", "why_you": "I freelance", "jurisdiction": "Egypt",
         "budget": "0", "time": "10h/week", "evidence": "none", "values": "no ads"}


def create(client) -> str:
    resp = client.post("/runs", data=BRIEF, follow_redirects=False)
    assert resp.status_code == 303
    match = re.fullmatch(r"/runs/([^/?]+)", resp.headers["location"])
    assert match
    return match.group(1)


def act(client, rid, **form):
    return client.post(f"/runs/{rid}/act", data=form, follow_redirects=False)


def error_of(resp) -> str | None:
    loc = resp.headers.get("location", "")
    return loc.split("?error=", 1)[1] if "?error=" in loc else None


# ---------------------------------------------------------------------------------------------- dashboard
def test_index_renders_with_form_models_and_mocked_box(env):
    client, _ = env
    resp = client.get("/")
    assert resp.status_code == 200
    for text in ("Start a venture", "What is MOCKED", "Open-source prototype. Payments, publishing and sending are MOCKED."):
        assert text in resp.text
    assert resp.cookies.get("vv_founder") == "1"


def test_index_explains_setup_when_no_model_is_configured(env, monkeypatch):
    client, orch = env
    monkeypatch.setattr(orch.settings, "describe_models", lambda: {"main": [], "fast": []})
    resp = client.get("/")
    assert "No model is configured" in resp.text and "docker compose --profile local up" in resp.text


def test_create_run_redirects_and_shows_the_first_decision(env):
    client, orch = env
    rid = create(client)
    page = client.get(f"/runs/{rid}").text
    assert "Decision: step 1.1" in page and "Stub deliverable for <strong>1.1</strong>" in page
    assert "[Phase 1: Discover | Step 1.1 | Repeat 0/2 | Last gate: none]" in page
    assert "Brief check: Input quality: 8/8" in page
    assert client.get("/").text.count(rid) >= 1
    missing = client.post("/runs", data={"title": "no idea"}, follow_redirects=False)
    assert missing.status_code == 303 and "error=" in missing.headers["location"]


def test_founder_actions_and_errors(env):
    client, orch = env
    rid = create(client)
    assert act(client, rid, kind="approve", step="1.1").headers["location"] == f"/runs/{rid}"
    assert orch.store.load(rid).current_step == "1.2"
    # A rejection without feedback is refused by the orchestrator and shown in an error box.
    resp = act(client, rid, kind="reject", step="1.2", reason="")
    assert "Say what to change" in (error_of(resp) or "").replace("%20", " ")
    page = client.get(resp.headers["location"]).text
    assert 'class="box error"' in page and "Say what to change" in page
    # Picking the lower-ranked concept needs a reason.
    resp = act(client, rid, kind="select_concept", step="1.2", concept_id="c2")
    assert error_of(resp)
    act(client, rid, kind="select_concept", step="1.2", concept_id="c2", reason="I have access to this segment")
    run = orch.store.load(rid)
    assert run.selected_concept["id"] == "c2" and run.pending["kind"] == "lock_thresholds"
    # Unknown kinds and actions on the wrong step are errors, never crashes.
    assert error_of(act(client, rid, kind="explode"))
    assert error_of(act(client, rid, kind="approve", step="2.1"))


def test_lock_thresholds_submit_data_and_accept(env):
    client, orch = env
    rid = create(client)
    act(client, rid, kind="approve", step="1.1")
    act(client, rid, kind="select_concept", step="1.2", concept_id="c1")
    page = client.get(f"/runs/{rid}").text
    assert "Lock the thresholds for step 1.3" in page and 'name="targets.k"' in page
    assert error_of(act(client, rid, kind="lock_thresholds", step="1.3", **{"targets.k": "lots"}))
    act(client, rid, kind="lock_thresholds", step="1.3", **{"targets.k": "20"})
    run = orch.store.load(rid)
    assert run.steps["1.3"].contract["criteria"][0]["target"] == 20.0 and run.pending["kind"] == "submit_data"
    assert 'name="data.k"' in client.get(f"/runs/{rid}").text
    assert error_of(act(client, rid, kind="submit_data", step="1.3", **{"data.k": "abc"}))
    assert error_of(act(client, rid, kind="submit_data", step="1.3"))
    act(client, rid, kind="submit_data", step="1.3", **{"data.k": "25"})
    run = orch.store.load(rid)
    assert run.steps["1.3"].gate["outcome"] == "GO" and run.pending["kind"] == "decision"
    page = client.get(f"/runs/{rid}").text
    assert "GATE PASSED" in page and "Accept GO" in page
    act(client, rid, kind="approve", step="1.3")
    assert orch.store.load(rid).current_step == "1.4"


def test_skip_and_stop_need_a_reason(env):
    client, orch = env
    rid = create(client)
    act(client, rid, kind="approve", step="1.1")
    act(client, rid, kind="select_concept", step="1.2", concept_id="c1")
    act(client, rid, kind="lock_thresholds", step="1.3")
    assert orch.store.load(rid).pending["kind"] == "submit_data"
    assert "Skip this gate" in client.get(f"/runs/{rid}").text
    assert error_of(act(client, rid, kind="skip_gate", step="1.3", reason=""))
    assert error_of(act(client, rid, kind="stop", step="1.3", reason=""))
    act(client, rid, kind="skip_gate", step="1.3", reason="demo: no field data yet")
    entries = orch.log(rid).entries
    override = [e for e in entries if e["action_type"] == "FOUNDER_OVERRIDE"][-1]
    assert override["override"]["evidence_gate_passed"] is False and override["approved_by"] == "founder"
    assert orch.store.load(rid).current_step == "1.4"


def test_decide_another_outcome_and_stop(env):
    client, orch = env
    rid = create(client)
    act(client, rid, kind="approve", step="1.1")
    assert error_of(act(client, rid, kind="decide", step="1.2", outcome="PIVOT_BACK", pivot_target="1.1"))
    act(client, rid, kind="decide", step="1.2", outcome="PIVOT_BACK", pivot_target="1.1", reason="reframe it")
    assert orch.store.load(rid).current_step == "1.1"
    act(client, rid, kind="stop", step="1.1", reason="not worth it")
    run = orch.store.load(rid)
    assert run.status == "STOPPED" and "not worth it" in run.status_reason
    assert "STOPPED" in client.get(f"/runs/{rid}").text


def test_phase_review_through_the_web(env):
    client, orch = env
    rid = create(client)
    act(client, rid, kind="approve", step="1.1")
    act(client, rid, kind="select_concept", step="1.2", concept_id="c1")
    act(client, rid, kind="lock_thresholds", step="1.3")
    act(client, rid, kind="submit_data", step="1.3", **{"data.k": "10"})
    act(client, rid, kind="approve", step="1.3")
    act(client, rid, kind="lock_thresholds", step="1.4")
    act(client, rid, kind="submit_data", step="1.4", **{"data.k": "12"})
    act(client, rid, kind="approve", step="1.4")
    page = client.get(f"/runs/{rid}").text
    assert "End of phase 1: Discover" in page and "Stub phase summary." in page
    assert error_of(act(client, rid, kind="phase_review", match="Yes", confidence="9"))
    act(client, rid, kind="phase_review", match="Yes", confidence="4", issues="")
    run = orch.store.load(rid)
    assert run.phase_reviews["1"]["confidence"] == 4 and run.current_step == "2.1"


def test_final_decision_form_for_step_6_3(env):
    client, orch = env
    rid = create(client)
    run = orch.store.load(rid)
    for sid in steps.STEP_IDS[:-1]:
        run.steps[sid].status, run.steps[sid].outcome = "DONE", "GO"
    run.current_step, run.pending = "6.3", None
    orch.store.save(run)
    orch.advance(rid)
    page = client.get(f"/runs/{rid}").text
    assert "Record your final decision" in page and "(memo recommendation)" in page
    assert error_of(act(client, rid, kind="final_decision", step="6.3", final_decision="PERSEVERE"))
    act(client, rid, kind="final_decision", step="6.3", final_decision="PERSEVERE", reason="new evidence from users")
    run = orch.store.load(rid)
    assert run.final_decision["decision"] == "PERSEVERE" and run.status == "COMPLETED"


def test_retry_and_clarify_brief_panels(env):
    client, orch = env
    rid = create(client)
    run = orch.store.load(rid)
    run.pending = {"kind": "retry", "step": "1.1", "prompt": "No model answered. You can retry the step.",
                   "detail": "Traceback (FIXTURE)"}
    orch.store.save(run)
    page = client.get(f"/runs/{rid}").text
    assert "Retry</button>" in page and "Traceback (FIXTURE)" in page
    act(client, rid, kind="retry")
    assert orch.store.load(rid).pending["kind"] == "decision"
    run = orch.store.load(rid)
    run.pending = {"kind": "clarify_brief", "step": "0.0", "prompt": "Too thin.", "questions": ["Who pays?"]}
    orch.store.save(run)
    page = client.get(f"/runs/{rid}").text
    assert "Clarify the brief" in page and "Who pays?" in page and 'name="brief.idea"' in page
    act(client, rid, kind="clarify_brief", **{"brief.idea": "A sharper idea", "brief.customer": "studio owners"})
    run = orch.store.load(rid)
    assert run.brief["idea"] == "A sharper idea" and run.brief["customer"] == "studio owners"


def test_background_thread_advances_the_run(env, monkeypatch):
    client, orch = env
    monkeypatch.setattr(app_module, "ADVANCE_MODE", "thread")
    rid = create(client)
    deadline = time.time() + 10
    while time.time() < deadline and not orch.store.load(rid).pending:
        time.sleep(0.05)
    assert orch.store.load(rid).pending["kind"] == "decision"
    while app_module.is_advancing(rid) and time.time() < deadline:
        time.sleep(0.05)
    assert not app_module.is_advancing(rid)


def test_auto_refresh_only_while_working(env):
    client, orch = env
    rid = create(client)
    assert 'http-equiv="refresh"' not in client.get(f"/runs/{rid}").text  # waiting for the founder
    run = orch.store.load(rid)
    run.pending = None
    orch.store.save(run)
    app_module.ADVANCE_MODE = "off"
    try:
        assert 'http-equiv="refresh"' in client.get(f"/runs/{rid}").text
    finally:
        app_module.ADVANCE_MODE = "sync"


# ---------------------------------------------------------------------------------------------- pages
def test_step_log_evidence_and_outbox_pages(env):
    client, orch = env
    rid = create(client)
    act(client, rid, kind="approve", step="1.1")
    step = client.get(f"/runs/{rid}/steps/1.1")
    assert step.status_code == 200 and "Stub deliverable for <strong>1.1</strong>" in step.text
    assert 'sandbox=""' in step.text and "FIXTURE landing page" in step.text and "Gate history" in step.text
    raw_link = re.search(r'href="(/runs/[^"]+/files/artifacts/[^"]+landing\.html)"', step.text).group(1)
    raw = client.get(raw_link)
    assert raw.status_code == 200 and raw.headers["content-security-policy"] == "sandbox"
    assert client.get(f"/runs/{rid}/files/run.json").status_code == 404
    assert client.get(f"/runs/{rid}/files/artifacts/../run.json").status_code == 404
    log = client.get(f"/runs/{rid}/log")
    assert log.status_code == 200 and "total model cost" in log.text and "FOUNDER_APPROVAL" in log.text
    entries = client.get(f"/runs/{rid}/log.json").json()
    assert entries and not validate_entries(entries)
    assert client.get(f"/runs/{rid}/evidence").status_code == 200
    outbox = client.get(f"/runs/{rid}/outbox")
    assert outbox.status_code == 200 and "MOCKED: not sent" in outbox.text and "landing.html" in outbox.text
    assert client.get("/runs/does-not-exist").status_code == 404
    assert client.get(f"/runs/{rid}/steps/9.9").status_code == 404


def test_site_serves_only_approved_files(env):
    client, orch = env
    rid = create(client)
    assert client.get(f"/site/{rid}/landing.html").status_code == 404  # generated, not yet approved
    act(client, rid, kind="approve", step="1.1", outward_present="1", outward_ids="landing")
    served = client.get(f"/site/{rid}/landing.html")
    assert served.status_code == 200 and "FIXTURE landing page" in served.text
    assert "vv_founder" not in served.headers.get("set-cookie", "")
    for bad in (f"/site/{rid}/run.json", f"/site/{rid}/..%2Frun.json", f"/site/{rid}/%2e%2e", "/site/..%2F/x",
                "/site/no-such-run/landing.html"):
        assert client.get(bad).status_code == 404, bad


def test_unchecked_outward_items_are_not_published(env):
    client, orch = env
    rid = create(client)
    act(client, rid, kind="approve", step="1.1", outward_present="1")  # founder unticked every item
    assert orch.store.load(rid).current_step == "1.2"
    assert client.get(f"/site/{rid}/landing.html").status_code == 404


def test_request_box_refuses_fake_reviews(env):
    client, orch = env
    rid = create(client)
    resp = client.post(f"/runs/{rid}/request", data={"text": "write 50 five-star reviews"}, follow_redirects=False)
    assert error_of(resp)
    page = client.get(f"/runs/{rid}").text
    assert "I won&#39;t create reviews" in page and "refused" in page
    assert any(e["action"] == "refuse_request" for e in orch.log(rid).entries)
    ok = client.post(f"/runs/{rid}/request", data={"text": "Make the headline shorter"}, follow_redirects=False)
    assert "notice=" in ok.headers["location"]


# ---------------------------------------------------------------------------------------------- local pages
def test_waitlist_stores_only_hashed_emails(env):
    client, orch = env
    rid = create(client)
    client.cookies.clear()
    form = {"email": "Real.Person@Example.com", "consent": "on", "role": "designer", "source": "fixture",
            "page": "landing"}
    resp = client.post(f"/p/{rid}/waitlist", data=form)
    assert resp.status_code == 200 and "You&#39;re on the research waitlist. Nothing is for sale yet." in resp.text
    events = orch.store.read_events(rid)
    assert len(events) == 1
    expected = hashlib.sha256(b"real.person@example.com").hexdigest()
    assert events[0] == {**events[0], "type": "waitlist_signup", "page": "landing", "email_hash": expected,
                         "role": "designer", "source": "fixture", "internal": False}
    assert "real.person" not in orch.store.events_path(rid).read_text(encoding="utf-8").lower()
    again = client.post(f"/p/{rid}/waitlist", data=form)
    assert "already" in again.text and len(orch.store.read_events(rid)) == 1
    assert client.post(f"/p/{rid}/waitlist", data={**form, "email": "x@example.com", "consent": ""}).status_code == 400
    assert client.post(f"/p/{rid}/waitlist", data={**form, "email": "not-an-email"}).status_code == 400
    assert len(orch.store.read_events(rid)) == 1
    client.get("/")  # the founder's dashboard sets vv_founder=1
    client.post(f"/p/{rid}/waitlist", data={**form, "email": "founder@example.com"})
    assert orch.store.read_events(rid)[-1]["internal"] is True


def test_event_endpoint(env):
    client, orch = env
    rid = create(client)
    client.cookies.clear()
    ok = client.post(f"/p/{rid}/event", json={"type": "page_view", "page": "landing", "visitor_id": "v-12345678",
                                             "source": "fixture", "ignored_field": "x"})
    assert ok.status_code == 200 and ok.json()["ok"]
    event = orch.store.read_events(rid)[-1]
    assert event["type"] == "page_view" and event["visitor_id"] == "v-12345678" and event["internal"] is False
    assert "ignored_field" not in event
    client.post(f"/p/{rid}/event?internal=1", content=json.dumps({"type": "cta_click", "page": "landing"}))
    assert orch.store.read_events(rid)[-1]["internal"] is True
    assert client.post(f"/p/{rid}/event", json={"type": "purchase"}).status_code == 400
    assert client.post(f"/p/{rid}/event", content=b"{not json").status_code == 400
    assert client.post(f"/p/{rid}/event", json={"type": "page_view", "page": "x" * 5000}).status_code == 413
    assert client.post("/p/no-such-run/event", json={"type": "page_view"}).status_code == 404


def prepare_store(orch, rid):
    run = orch.store.load(rid)
    run.steps["5.1"].output = {"product_id": "fixture-product", "price": 19, "currency": "USD"}
    run.steps["4.1"].output = {"packages": [{"id": "pro", "name": "Pro", "price": 29, "currency": "USD"}]}
    rel = orch.store.write_artifact(rid, "3.2", 0, "product/index.html", PRODUCT)
    run.steps["3.2"].artifacts["product/index.html"] = rel
    orch.store.save(run)


def test_order_flow_gives_access_and_refund_revokes_it(env):
    client, orch = env
    rid = create(client)
    prepare_store(orch, rid)
    client.cookies.clear()
    form = {"email": "Buyer.One@example.com", "consent": "on", "product_id": "fixture-product", "package_id": "pro"}
    resp = client.post(f"/p/{rid}/order", data=form)
    assert resp.status_code == 200 and "MOCKED: no payment was taken" in resp.text
    assert "29.0 USD (not charged)" in resp.text
    link = re.search(rf'href="(/p/{re.escape(rid)}/access/[A-Za-z0-9_-]+)"', resp.text).group(1)
    product = client.get(link)
    assert product.status_code == 200 and "FIXTURE product main file" in product.text
    assert "MOCKED: no payment was taken" in product.text and 'sandbox="allow-scripts allow-forms"' in product.text
    # Duplicate submit: same idempotency key, same order and link, one order_request event.
    again = client.post(f"/p/{rid}/order", data=form)
    assert link in again.text
    cs = CommerceStore(orch.store.path(rid) / "commerce.json")
    assert len(cs.list("orders")) == 1 and len(cs.list("deliveries")) == 1
    events = [e for e in orch.store.read_events(rid) if e["type"] == "order_request"]
    assert len(events) == 1 and events[0]["email_hash"] == hashlib.sha256(b"buyer.one@example.com").hexdigest()
    assert events[0]["product_id"] == "fixture-product" and events[0]["internal"] is False
    assert "buyer.one" not in (orch.store.path(rid) / "commerce.json").read_text(encoding="utf-8").lower()
    assert "buyer.one" not in orch.store.events_path(rid).read_text(encoding="utf-8").lower()
    # Refund (MOCKED) revokes access.
    refunds.refund(cs, cs.list("orders")[0]["order_id"], reason="FIXTURE refund", idempotency_key="r1")
    denied = client.get(link)
    assert denied.status_code == 403 and "MOCKED: no payment was taken" in denied.text
    assert client.get(f"/p/{rid}/access/bad token!").status_code in (403, 404)
    assert client.get(f"/p/{rid}/access/AAAAAAAAAAAAAAAA").status_code == 403
    outbox = client.get(f"/runs/{rid}/outbox").text
    assert "B***@example.com" in outbox and "clean" in outbox


def test_order_rejects_invalid_product_and_missing_consent(env):
    client, orch = env
    rid = create(client)
    form = {"email": "buyer@example.com", "consent": "on", "product_id": "fixture-product"}
    no_store_page = client.post(f"/p/{rid}/order", data=form)
    assert no_store_page.status_code == 400 and "No order was recorded" in no_store_page.text
    prepare_store(orch, rid)
    assert client.post(f"/p/{rid}/order", data={**form, "product_id": "other"}).status_code == 400
    assert client.post(f"/p/{rid}/order", data={**form, "consent": ""}).status_code == 400
    assert client.post(f"/p/{rid}/order", data={**form, "email": "nope"}).status_code == 400
    path = orch.store.path(rid) / "commerce.json"
    assert not path.exists() or CommerceStore(path).list("orders") == []
    assert not [e for e in orch.store.read_events(rid) if e["type"] == "order_request"]


def test_request_size_limit(env):
    client, _ = env
    resp = client.post("/runs", data={"idea": "x" * (app_module.MAX_BODY + 10)})
    assert resp.status_code == 413


# ---------------------------------------------------------------------------------------------- form mapping
class _Run:
    pending = {"kind": "submit_data", "fields": [{"key": "n", "type": "integer"}, {"key": "notes", "type": "json"}]}


def test_build_action_maps_forms():
    build = app_module.build_action
    action = build(FormData([("kind", "submit_data"), ("step", "1.4"), ("data.n", "12"),
                             ("data.notes", '[{"quote": "FIXTURE"}]')]), _Run())
    assert action == {"channel": "web", "step": "1.4", "kind": "submit_data",
                      "data": {"n": 12, "notes": [{"quote": "FIXTURE"}]}}
    action = build(FormData([("kind", "decide"), ("outcome", "pivot_back"), ("pivot_target", "1.1"),
                             ("reason", "r"), ("outward_present", "1")]), _Run())
    assert action["outcome"] == "PIVOT_BACK" and action["pivot_target"] == "1.1" and action["outward_ids"] == []
    action = build(FormData([("kind", "approve"), ("acknowledge", "on"), ("outward_present", "1"),
                             ("outward_ids", "a"), ("outward_ids", "b")]), _Run())
    assert action["acknowledge"] is True and action["outward_ids"] == ["a", "b"]
    action = build(FormData([("kind", "phase_review"), ("match", "Partly"), ("confidence", "2"),
                             ("issues", "pricing unclear"), ("repeat_step", "4.1")]), _Run())
    assert action["repeat_step"] == "4.1" and action["match"] == "Partly"
    assert build(FormData([("kind", "final_decision"), ("final_decision", "stop")]), _Run())["final_decision"] == "STOP"
    with pytest.raises(ValueError):
        build(FormData([("kind", "submit_data"), ("data.notes", "{bad")]), _Run())
