"""Phase 5 Launch (5.1 store page, 5.2 launch posts, 5.3 mocked delivery) driven through the real Orchestrator.

The model is STUBBED (FakeLLM with FIXTURE replies), the delivery test suite
(reconcile.run_delivery_test_suite) is replaced by a FIXTURE result, and store
events are FIXTURE data written into the run's events.json.
"""
from __future__ import annotations

import re
import sys
import types
from datetime import timedelta

import pytest

import guardrails
from llm import FakeLLM
from orchestrator import Orchestrator
from phases import launch, validate
from store import RunStore
from tests.test_phase2_validate import close_window, make_model, start_at, write_events

PRIOR = {
    "2.1": {"concept_name": "Feedback hub", "uvp": "Every client comment in one place",
            "segment": "freelance web designers", "problem": "feedback gets lost",
            "channels": [{"id": "design-community", "name": "FIXTURE design community", "url": None,
                          "audience_rule": "freelancers", "evidence_ids": []},
                         {"id": "freelance-newsletter", "name": "FIXTURE freelancer newsletter", "url": None,
                          "audience_rule": "readers", "evidence_ids": []}]},
    "3.1": {"must_have": ["shared feedback page"]},
    "4.1": {"packages": [{"id": "solo", "name": "Solo", "price": 9, "currency": "USD", "billing": "monthly"},
                         {"id": "studio", "name": "Studio", "price": 29, "currency": "USD", "billing": "monthly"}],
            "recommended_package_id": "studio", "currency": "USD"},
}


def suite_result(passed: list[bool] | None = None) -> dict:
    names = ["happy_path", "duplicate_order", "failed_email", "invalid_product"]
    passed = passed or [True] * 4
    return {"tests": [{"name": n, "passed": p, "critical": True, "details": "FIXTURE"} for n, p in zip(names, passed)],
            "pass_rate": sum(passed) / 4, "failure_cases_tested": 3,
            "log_markdown": "# Payment and delivery test log (FIXTURE)\n\nNo payment taken; all orders are FIXTURE data.\n"}


@pytest.fixture()
def suite(monkeypatch):
    """Replace the sale-to-cash suite with a FIXTURE result and record its calls."""
    state = {"calls": [], "result": suite_result()}

    def run_delivery_test_suite(work_dir, *, product_id, price, currency):
        state["calls"].append({"work_dir": work_dir, "product_id": product_id, "price": price, "currency": currency})
        (work_dir / "fixture_orders.json").write_text("[]", encoding="utf-8")
        return state["result"]

    monkeypatch.setitem(sys.modules, "reconcile", types.SimpleNamespace(run_delivery_test_suite=run_delivery_test_suite))
    return state


@pytest.fixture()
def orch(tmp_path):
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(make_model()))


def site(o, rid):
    return o.store.path(rid) / "site"


def outbox_files(o, rid) -> list[str]:
    folder = o.store.path(rid) / "outbox"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def to_step(o, step_id: str) -> str:
    """Start at 5.1 and approve every launch step before step_id."""
    rid = start_at(o, "5.1", PRIOR)
    for sid in ("5.1", "5.2"):
        if sid == step_id:
            break
        run = o.advance(rid)
        assert run.pending["kind"] == "decision" and run.pending["step"] == sid
        o.act(rid, {"kind": "approve", "step": sid, "channel": "cli"})
    return rid


def store_events(start, visitors: int, intents: int) -> list[dict]:
    """FIXTURE store events: every intent sends a cta_click and an order_request (one person, counted once)."""
    events = []
    for i in range(visitors):
        ts = validate.iso(start + timedelta(minutes=5 + i))
        events.append({"type": "page_view", "page": "store", "visitor_id": f"s{i}", "source": "design-community",
                       "internal": False, "timestamp": ts})
    for i in range(intents):
        ts = validate.iso(start + timedelta(days=2, minutes=i))
        events.append({"type": "cta_click", "page": "store", "visitor_id": f"s{i}", "internal": False, "timestamp": ts})
        events.append({"type": "order_request", "page": "store", "email_hash": f"h{i}", "product_id": "feedback-hub",
                       "internal": False, "timestamp": ts})
    events += [{"type": "page_view", "page": "store", "visitor_id": f"team{i}", "internal": True,
                "timestamp": validate.iso(start + timedelta(hours=1))} for i in range(50)]
    events += [{"type": "order_request", "page": "store", "email_hash": f"teamh{i}", "product_id": "feedback-hub",
                "internal": True, "timestamp": validate.iso(start + timedelta(hours=1))} for i in range(50)]
    return events


def to_collect(o, monkeypatch) -> tuple[str, object, object]:
    rid = to_step(o, "5.3")
    run = o.advance(rid)
    assert run.pending["kind"] == "lock_thresholds" and run.pending["step"] == "5.3"
    o.act(rid, {"kind": "lock_thresholds", "step": "5.3", "channel": "cli"})
    start = validate.parse_ts(o.store.load(rid).steps["5.3"].contract["locked_at"])
    return rid, start, start + timedelta(days=14)


def assert_honest_page(text: str) -> None:
    assert guardrails.check_marketing(text) == []
    assert not re.search(r"https?://", text)
    assert not re.search(r"countdown|testimonial|★|card number|cvv", text, re.I)


# ------------------------------------------------------------------------------------------------ 5.1
def test_store_page_is_mocked_honest_and_published_only_after_approval(orch):
    rid = start_at(orch, "5.1", PRIOR)
    run = orch.advance(rid)
    st = run.steps["5.1"]
    assert run.pending["kind"] == "decision" and run.pending["step"] == "5.1"
    assert "store-page" in run.pending["prompt"]
    assert not (site(orch, rid) / "store.html").exists()
    page = orch.store.read_artifact(rid, st.artifacts["store.html"])
    assert page.count(launch.STORE_LABEL) >= 2              # banner and next to the form
    assert f'method="post" action="/p/{rid}/order"' in page
    assert '<input type="hidden" name="product_id" value="feedback-hub">' in page
    assert '<input type="hidden" name="package_id" value="studio">' in page
    assert re.search(r'<input id="email" name="email" type="email" required', page)
    assert re.search(r'name="consent" type="checkbox" value="yes" required', page)
    assert "Proposed future price: 29.00 USD (monthly)" in page
    for name in ("terms", "privacy", "refund"):
        assert f'href="/site/{rid}/{name}.html"' in page
    assert '"cta_click"' in page and 'page: "store"' in page and f'"/p/{rid}/event"' in page
    assert_honest_page(page)
    assert st.guardrail_flags == []
    out = st.output
    assert (out["product_id"], out["package_id"], out["price"], out["currency"]) == ("feedback-hub", "studio", 29.0, "USD")
    assert out["price_label"] == "Proposed future price"
    orch.act(rid, {"kind": "approve", "step": "5.1", "channel": "cli"})
    published = site(orch, rid) / "store.html"
    assert published.exists() and published.read_text(encoding="utf-8") == page
    assert outbox_files(orch, rid) == []


def test_store_page_without_pricing_says_price_not_set(orch):
    rid = start_at(orch, "5.1", {k: v for k, v in PRIOR.items() if k != "4.1"})
    st = orch.advance(rid).steps["5.1"]
    page = orch.store.read_artifact(rid, st.artifacts["store.html"])
    assert "Proposed future price: not set yet" in page
    assert st.output["price"] is None and st.questions


# ------------------------------------------------------------------------------------------------ 5.2
def test_launch_posts_are_founder_drafts_and_reach_outbox_only_when_approved(orch):
    rid = to_step(orch, "5.2")
    run = orch.advance(rid)
    st = run.steps["5.2"]
    assert run.pending["kind"] == "decision" and run.pending["step"] == "5.2"
    assert set(st.artifacts) >= {"post_design-community.md", "post_freelance-newsletter.md"}
    for cid in ("design-community", "freelance-newsletter"):
        text = orch.store.read_artifact(rid, st.artifacts[f"post_{cid}.md"])
        assert text.startswith("# DRAFT for the founder to post from their own account")
        assert f"/site/{rid}/store.html?utm_source={cid}" in text
        assert_honest_page(text)
    outward = st.output["outward"]
    assert outward == [{"kind": "send", "item_id": "post-design-community", "file": "post_design-community.md",
                        "when": "on_approve"},
                       {"kind": "send", "item_id": "post-freelance-newsletter", "file": "post_freelance-newsletter.md",
                        "when": "on_approve"}]
    assert [s["day"] for s in st.output["schedule"]] == [1, 4]
    assert all(s["owner"] == "founder" for s in st.output["schedule"])
    assert outbox_files(orch, rid) == []
    # The founder approves only one post: only that one reaches the local outbox.
    orch.act(rid, {"kind": "approve", "step": "5.2", "channel": "cli", "outward_ids": ["post-design-community"]})
    assert outbox_files(orch, rid) == ["post_design-community.md"]
    sent = (orch.store.path(rid) / "outbox" / "post_design-community.md").read_text(encoding="utf-8")
    assert "MOCKED" in sent and "NOT sent" in sent


def test_launch_posts_without_channels_ask_the_founder(orch):
    prior = {**PRIOR, "2.1": {**PRIOR["2.1"], "channels": []}}
    rid = start_at(orch, "5.1", prior)
    orch.advance(rid)
    orch.act(rid, {"kind": "approve", "step": "5.1", "channel": "cli"})
    st = orch.advance(rid).steps["5.2"]
    assert st.output["posts"] == [] and st.output["outward"] == [] and st.questions
    orch.act(rid, {"kind": "reject", "step": "5.2", "channel": "cli", "reason": "Use the FIXTURE designers forum"})
    st = orch.advance(rid).steps["5.2"]
    assert [p["channel_id"] for p in st.output["posts"]] == ["founder-named-channel"]
    assert outbox_files(orch, rid) == []


# ------------------------------------------------------------------------------------------------ 5.3
def test_delivery_contract_and_flow_document(orch, suite):
    rid = to_step(orch, "5.3")
    run = orch.advance(rid)
    st = run.steps["5.3"]
    md = orch.store.read_artifact(rid, st.artifacts["deliverable.md"])
    assert "```mermaid" in md and "sequenceDiagram" in md and "What is MOCKED" in md
    crit = {c["key"]: (c["target"], c["kind"]) for c in st.contract["criteria"]}
    assert crit == {"delivery_tests_pass_rate": (1.0, "hard"), "failure_cases_tested": (3, "hard"),
                    "store_visitors": (500, "floor"), "buy_intent_rate": (0.03, "proportion")}
    assert st.contract["window_days"] == 14 and st.contract["pivot_target"] == "4.1"
    assert suite["calls"] == []  # nothing runs before the thresholds are locked


def test_delivery_tests_run_after_lock_and_demand_waits_for_window(orch, suite, monkeypatch):
    rid, start, _end = to_collect(orch, monkeypatch)
    write_events(orch, rid, store_events(start, 40, 3))
    run = orch.advance(rid)
    st = run.steps["5.3"]
    assert run.pending["kind"] == "submit_data"
    obs = st.observation
    assert obs["measurement_state"] == "WAITING_FOR_DATA"
    assert obs["observed"]["delivery_tests_pass_rate"] == 1.0 and obs["observed"]["failure_cases_tested"] == 3
    assert obs["observed"]["store_visitors"] == 40 and obs["observed"]["buy_intent_rate"] == 0.075
    call = suite["calls"][0]
    assert call["work_dir"] == orch.store.path(rid) / "commerce_test"
    assert (call["product_id"], call["price"], call["currency"]) == ("feedback-hub", 29.0, "USD")
    log_rel = st.artifacts["payment_test_log.md"]
    assert "FIXTURE" in orch.store.read_artifact(rid, log_rel)


def test_delivery_gate_go_then_phase_review(orch, suite, monkeypatch):
    rid, start, end = to_collect(orch, monkeypatch)
    write_events(orch, rid, store_events(start, 600, 30))
    close_window(monkeypatch, end)
    run = orch.advance(rid)
    st = run.steps["5.3"]
    assert st.observation["observed"] == {"delivery_tests_pass_rate": 1.0, "failure_cases_tested": 3.0,
                                          "store_visitors": 600.0, "buy_intent_rate": 0.05}
    assert st.observation["details"]["cta_clicks"] == 30 and st.observation["details"]["order_requests"] == 30
    assert st.gate["outcome"] == "GO"
    orch.act(rid, {"kind": "approve", "step": "5.3", "channel": "cli"})
    assert orch.store.load(rid).pending["kind"] == "phase_review"


def test_delivery_gate_low_intent_pivots_to_pricing(orch, suite, monkeypatch):
    rid, start, end = to_collect(orch, monkeypatch)
    write_events(orch, rid, store_events(start, 600, 6))
    close_window(monkeypatch, end)
    gate = orch.advance(rid).steps["5.3"].gate
    assert gate["outcome"] == "PIVOT_BACK" and gate["pivot_target"] == "4.1"


def test_delivery_gate_low_traffic_pivots_to_lean_canvas(orch, suite, monkeypatch):
    rid, start, end = to_collect(orch, monkeypatch)
    write_events(orch, rid, store_events(start, 300, 30))
    close_window(monkeypatch, end)
    gate = orch.advance(rid).steps["5.3"].gate
    assert gate["outcome"] == "PIVOT_BACK" and gate["pivot_target"] == "2.1"


def test_failing_delivery_test_recommends_repeat(orch, suite, monkeypatch):
    suite["result"] = suite_result([True, True, False, True])
    rid, start, end = to_collect(orch, monkeypatch)
    write_events(orch, rid, store_events(start, 600, 30))
    close_window(monkeypatch, end)
    st = orch.advance(rid).steps["5.3"]
    assert st.observation["observed"]["delivery_tests_pass_rate"] == 0.75
    assert st.observation["details"]["failed_tests"] == ["failed_email"]
    assert st.gate["outcome"] == "REPEAT"


def test_missing_delivery_suite_never_passes(orch, monkeypatch):
    monkeypatch.setitem(sys.modules, "reconcile", None)   # import fails
    rid, start, end = to_collect(orch, monkeypatch)
    write_events(orch, rid, store_events(start, 600, 30))
    close_window(monkeypatch, end)
    run = orch.advance(rid)
    st = run.steps["5.3"]
    assert run.pending["kind"] == "submit_data"
    # A partial observation is recorded as a NOT_EVALUABLE gate report: no outcome, never a pass.
    assert st.gate is None or (st.gate["status"] == "NOT_EVALUABLE" and st.gate["outcome"] is None
                               and not st.gate["evidence_passed"])
    assert st.observation["observed"]["delivery_tests_pass_rate"] is None
    assert "unavailable" in st.observation["notes"]


def test_founder_store_data_keeps_automatic_test_values(orch, suite, monkeypatch):
    rid, _start, end = to_collect(orch, monkeypatch)
    orch.advance(rid)
    close_window(monkeypatch, end)
    data = {"store_visitors": 800, "buy_intents": 40, "analytics_source": "FIXTURE analytics tool"}
    orch.act(rid, {"kind": "submit_data", "step": "5.3", "data": data, "channel": "cli"})
    st = orch.store.load(rid).steps["5.3"]
    assert st.observation["observed"]["delivery_tests_pass_rate"] == 1.0
    assert st.observation["observed"]["buy_intent_rate"] == 0.05
    assert st.gate["outcome"] == "GO"
    assert any(r.provenance == "FOUNDER_REPORTED" and "FIXTURE analytics" in r.title for r in orch.ledger(rid).all())


def test_store_counts_do_not_double_count_one_person():
    events = [{"type": "page_view", "page": "store", "visitor_id": "a"},
              {"type": "cta_click", "page": "store", "visitor_id": "a"},
              {"type": "order_request", "page": "store", "email_hash": "x"},
              {"type": "order_request", "page": "store", "email_hash": "x"}]
    assert launch.store_counts(events) == {"visitors": 1, "cta_clicks": 1, "order_requests": 1, "buy_intents": 1}


# ------------------------------------------------------------------------------------------------ identity check
def test_identity_check_flags_customer_claims_only():
    seg, why = "freelance web designers", "We are a student developer team"
    assert launch.identity_violations("I'm a freelance designer and I lose feedback.", seg, why)
    assert launch.identity_violations("As a fellow designer, I get it.", seg, why)
    assert launch.identity_violations("Like you, I juggle client feedback.", seg, why)
    assert launch.identity_violations("This comes up all the time in client work.", seg, why)
    assert not launch.identity_violations("We are a student developer team who built a feedback page.", seg, why)
    assert not launch.identity_violations("Built as a tool for freelance designers.", seg, why)
    # Allowed when the brief's why_you says so.
    assert not launch.identity_violations("I'm a freelance designer.", seg, "I am a freelance designer")


def test_launch_posts_never_impersonate_the_customer(tmp_path):
    calls = {"n": 0, "payloads": []}

    def override(task, text):
        if task != "launch_marketer.launch_posts":
            return None
        from tests.stubs_validate_launch import agent_input
        data = agent_input(text)
        calls["n"] += 1
        calls["payloads"].append(data)
        return {"posts": [{"channel_id": c["id"], "channel_name": c.get("name"), "format": "community post",
                           "text": ("I'm a freelance designer and this comes up all the time. We built an early "
                                    "tool that keeps client feedback on one page. Requesting access costs nothing."),
                           "day": 1 + 3 * i, "timing": "weekday morning", "follow_up": "Reply within a day."}
                          for i, c in enumerate(data.get("channels") or [])],
                "summary": "FIXTURE", "questions": []}

    o = Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(make_model(override)))
    rid = to_step(o, "5.2")
    st = o.advance(rid).steps["5.2"]
    assert calls["n"] == 2                                   # regenerated once with feedback
    assert calls["payloads"][0]["founder_identity"] == "I freelance"
    assert "IDENTITY CHECK FAILED" in calls["payloads"][1]["feedback"]
    for post in st.output["posts"]:
        assert "I'm a freelance designer" not in post["text"] and "all the time" not in post["text"]
        assert "We built an early tool" in post["text"]
    assert st.output["identity_check"] and "removed" in st.output["identity_check"][0]
    md = o.store.read_artifact(rid, st.artifacts["deliverable.md"])
    assert "## Identity check" in md
