"""Phase 4 (Commercial setup) driven through the real Orchestrator with a STUBBED model.

All survey responses, click counts and evidence rows here are FIXTURE data.
"""
from __future__ import annotations

import json

import pytest

import steps
import stubs_commercial_operate as stubs
from evidence import Evidence
from llm import FakeLLM, task_id_of
from orchestrator import FounderActionError, Orchestrator
from phases.commercial import (ACKNOWLEDGMENT, BANNER, currency_for, parse_vw_responses, remove_compliance_claims,
                               van_westendorp)
from store import DONE, RunStore

BRIEF = {"idea": "Client feedback tracker for freelance web designers", "customer": "freelance web designers",
         "why_you": "I freelance", "jurisdiction": "Egypt", "budget": "0", "time": "10h/week", "evidence": "none"}


def kernel_reply(task: str):
    if task == "rubric_scorer.score_input":
        return {"scores": {c: {"score": 2, "reason": "stub"} for c in
                           ("specificity", "evidence_basis", "consistency", "completeness")},
                "weakest": "", "red_flags": [], "follow_up_questions": [], "excluded_category": None}
    if task == "gatekeeper.explain_gate":
        return {"reasoning": "Stub reasoning from the numbers.", "change_my_mind": "New valid data."}
    if task == "gatekeeper.summarize_phase":
        return {"summary": "Stub phase summary.", "assumptions_confirmed": [], "assumptions_killed": [], "still_open": []}
    return None


def make_responder(overrides: dict | None = None):
    def respond(messages, tier):
        task = task_id_of(messages)
        user = next(m["content"] for m in reversed(messages) if m["role"] == "user" and "TASK_ID" in m["content"])
        if overrides and task in overrides:
            return overrides[task](stubs.respond(task, user))
        reply = kernel_reply(task)
        if reply is None:
            reply = stubs.respond(task, user)
        return reply if reply is not None else {}
    return respond


def make_orch(tmp_path, overrides=None) -> Orchestrator:
    return Orchestrator(store=RunStore(tmp_path / "runs"), llm=FakeLLM(make_responder(overrides)))


def start_at(orch: Orchestrator, step_id: str, brief=None, seed: dict | None = None, evidence: list | None = None) -> str:
    run = orch.create_run(dict(brief or BRIEF))
    rid = run.run_id
    for row in evidence or []:
        orch.ledger(rid).add(row)
    run = orch.store.load(rid)
    for sid in steps.STEP_IDS[:steps.STEP_IDS.index(step_id)]:
        run.steps[sid].status, run.steps[sid].outcome = DONE, "GO"
    for sid, output in (seed or {}).items():
        run.steps[sid].output = output
    run.current_step, run.pending = step_id, None
    orch.store.save(run)
    return rid


FIXTURE_EVIDENCE = [Evidence(provenance="SOURCE_FACT", source_type="fixture", url="https://example.com/fixture-pricing",
                             title="FIXTURE: competitor A public pricing page", excerpt="FIXTURE row used only by tests",
                             value=15, unit="USD per month")]
SEED_13 = {"1.3": {"competitors": [
    {"name": "FIXTURE Competitor A", "url": "https://example.com/fixture-pricing", "price": "15 USD/month",
     "evidence_ids": ["E-001"]},
    {"name": "FIXTURE Competitor B", "url": "https://example.com/fixture-b", "price": "Contact sales", "evidence_ids": []},
    {"name": "FIXTURE Competitor C", "url": None, "price": "29 USD/month", "evidence_ids": ["E-404"]},
]}}


# ------------------------------------------------------------------------------------------------ unit level

def test_van_westendorp_on_fixture_responses():
    valid, problems = parse_vw_responses(json.dumps(stubs.vw_fixture_responses() +
                                                    [{"too_cheap": 9, "cheap": 5, "expensive": 20, "too_expensive": 30}]))
    assert len(valid) == 32 and len(problems) == 1
    result = van_westendorp(valid)
    assert result["pmc"] == pytest.approx(11.5) and result["pme"] == pytest.approx(25.0)
    assert result["pmc"] <= result["opp"] <= result["pme"]
    assert result["pmc"] <= result["ipp"] <= result["pme"]
    single = van_westendorp([{"too_cheap": 5, "cheap": 10, "expensive": 20, "too_expensive": 30}])
    assert single["ipp"] == pytest.approx(15.0)  # linear interpolation between grid prices 10 and 20


def test_currency_follows_jurisdiction_and_defaults_to_usd():
    assert currency_for({"jurisdiction": "Cairo, Egypt"})[0] == "EGP"
    assert currency_for({"jurisdiction": "Germany"})[0] == "EUR"
    code, basis = currency_for({})
    assert code == "USD" and basis.startswith("ASSUMPTION")


def test_compliance_claims_are_removed():
    text, removed = remove_compliance_claims("- We collect little. This app is GDPR-compliant.\nUsers must comply with these terms.")
    assert removed == 1 and "compliant" not in text.lower()
    assert "Users must comply with these terms." in text


# ------------------------------------------------------------------------------------------------ 4.1 pricing

def _generate_and_lock_pricing(orch: Orchestrator) -> str:
    rid = start_at(orch, "4.1", seed=SEED_13, evidence=FIXTURE_EVIDENCE)
    run = orch.advance(rid)
    assert run.pending["kind"] == "lock_thresholds" and run.pending["step"] == "4.1"
    criteria = {c["key"]: c for c in run.pending["contract"]["criteria"]}
    assert criteria["pricing_responses"]["kind"] == "floor" and criteria["pricing_responses"]["target"] == 30
    assert criteria["price_in_acceptable_range"]["kind"] == "hard"
    assert criteria["paid_plan_click_rate"]["target"] == 0.05
    orch.act(rid, {"kind": "lock_thresholds", "step": "4.1", "approve_outward": True, "channel": "cli"})
    run = orch.advance(rid)
    assert run.pending["kind"] == "submit_data"
    return rid


def test_pricing_deliverable_anchors_and_mocked_click_page(tmp_path):
    orch = make_orch(tmp_path)
    rid = _generate_and_lock_pricing(orch)
    run = orch.store.load(rid)
    out = run.steps["4.1"].output
    assert out["currency"] == "EGP" and out["recommended_package_id"] == "team"
    assert all(p["currency"] == "EGP" for p in out["packages"])
    assert out["economics_floor"]["value"] == pytest.approx(8.33)        # 2.5 / (1 - 0.7), computed in code
    studio = next(p for p in out["packages"] if p["id"] == "studio")
    assert studio["sample_bills"] == {"low": 12.0, "typical": 24.0, "high": 60.0}  # metered: price x seats
    assert out["vw_reference_price"] == 19
    comps = {c["name"]: c for c in out["comparables"]}
    assert comps["FIXTURE Competitor A"]["status"] == "sourced"
    assert comps["FIXTURE Competitor B"]["price"] == "quote required"
    assert comps["FIXTURE Competitor C"]["price"] == "unknown"           # cited evidence does not exist
    assert "E-999" not in out["outside_option"]["evidence_ids"]
    assert len(out["research_design"]["van_westendorp"]["questions"]) == 4
    # The no-charge page was published to the local MOCKED site only after approval at lock time.
    page = (orch.store.site_dir(rid) / "pricing.html").read_text(encoding="utf-8")
    assert "Coming soon: no payment is taken" in page and "MOCKED" in page
    assert "<form" not in page and "card" not in page.lower()
    assert any(e["action"] == "mock_publish" and e["approved_by"] == "founder" for e in orch.log(rid).entries)


def test_pricing_gate_passes_with_price_inside_acceptable_range(tmp_path):
    orch = make_orch(tmp_path)
    rid = _generate_and_lock_pricing(orch)
    orch.act(rid, {"kind": "submit_data", "step": "4.1", "data": {
        "van_westendorp_responses_json": json.dumps(stubs.vw_fixture_responses(1.0)),
        "pricing_page_visitors": 200, "paid_plan_clicks": 14}})
    st = orch.store.load(rid).steps["4.1"]
    assert st.gate["status"] == "PASSED" and st.gate["outcome"] == "GO"
    observed = st.observation["observed"]
    assert observed == {"pricing_responses": 32.0, "price_in_acceptable_range": 1.0, "paid_plan_click_rate": 0.07}
    vw = st.observation["details"]["van_westendorp"]
    assert vw["acceptable_range"] == [11.5, 25.0]
    low, high = st.observation["details"]["click_test"]["wilson_95"]
    assert low < 0.07 < high
    assert orch.ledger(rid).get(st.observation["evidence_ids"][0]).provenance == "FOUNDER_REPORTED"
    orch.act(rid, {"kind": "approve", "step": "4.1"})
    assert orch.store.load(rid).current_step == "4.2"


def test_pricing_gate_fails_when_price_outside_acceptable_range(tmp_path):
    orch = make_orch(tmp_path)
    rid = _generate_and_lock_pricing(orch)
    orch.act(rid, {"kind": "submit_data", "step": "4.1", "data": {
        "van_westendorp_responses_json": stubs.vw_fixture_responses(0.4),
        "pricing_page_visitors": 200, "paid_plan_clicks": 14}})
    st = orch.store.load(rid).steps["4.1"]
    assert st.observation["observed"]["price_in_acceptable_range"] == 0.0
    assert st.gate["status"] == "FAILED"
    assert st.gate["outcome"] in ("STOP", "PIVOT_BACK")
    hard = next(c for c in st.gate["criteria"] if c["key"] == "price_in_acceptable_range")
    assert hard["passed"] is False


def test_pricing_invalid_click_counts_are_not_evaluable(tmp_path):
    orch = make_orch(tmp_path)
    rid = _generate_and_lock_pricing(orch)
    orch.act(rid, {"kind": "submit_data", "step": "4.1", "data": {
        "van_westendorp_responses_json": stubs.vw_fixture_responses(1.0),
        "pricing_page_visitors": 10, "paid_plan_clicks": 50}})
    st = orch.store.load(rid).steps["4.1"]
    assert st.gate["status"] == "NOT_EVALUABLE" and st.gate["outcome"] is None


def test_pricing_small_sample_fails_the_floor(tmp_path):
    orch = make_orch(tmp_path)
    rid = _generate_and_lock_pricing(orch)
    orch.act(rid, {"kind": "submit_data", "step": "4.1",
                   "data": {"van_westendorp_responses_json": stubs.vw_fixture_responses(1.0, n=12)}})
    st = orch.store.load(rid).steps["4.1"]
    assert st.observation["observed"]["paid_plan_click_rate"] is None
    assert st.gate["status"] == "FAILED"
    floor = next(c for c in st.gate["criteria"] if c["key"] == "pricing_responses")
    assert floor["passed"] is False


# ------------------------------------------------------------------------------------------------ 4.2 legal drafts

SEED_41 = {"4.1": {"packages": [{"id": "team", "name": "Team", "price": 19, "currency": "EGP", "billing": "month"}],
                   "recommended_package_id": "team", "currency": "EGP"}}


def _artifact(orch, rid, step, name):
    st = orch.store.load(rid).steps[step]
    return orch.store.read_artifact(rid, st.artifacts[name])


def test_legal_drafts_enforce_banner_mocked_refund_and_no_compliance_claims(tmp_path):
    orch = make_orch(tmp_path)
    rid = start_at(orch, "4.2", seed=SEED_41)
    run = orch.advance(rid)
    assert run.pending["kind"] == "decision" and run.pending["step"] == "4.2"
    out = run.steps["4.2"].output
    assert out["requires_acknowledgment"] == ACKNOWLEDGMENT
    assert out["policies"] == {"terms": "terms.html", "privacy": "privacy.html", "refund": "refund.html"}
    assert [o["item_id"] for o in out["outward"]] == ["policy-terms", "policy-privacy", "policy-refund"]
    for name in ("terms.md", "privacy.md", "refund.md"):
        text = _artifact(orch, rid, "4.2", name)
        assert text.startswith(BANNER + "\n"), name
        assert text.count("not legal advice") == 1
        assert "compliant" not in text.lower()
    for name in ("terms.html", "privacy.html", "refund.html"):
        assert BANNER in _artifact(orch, rid, "4.2", name)
    assert any("omitted the draft banner" in n for n in out["enforcement_notes"])   # the stub privacy draft had none
    refund = _artifact(orch, rid, "4.2", "refund.md")
    assert "No payment is taken today" in refund and "MOCKED" in refund and "CONDITIONAL" in refund
    assert "issued to your card" not in refund
    privacy = _artifact(orch, rid, "4.2", "privacy.md")
    assert "Data the prototype handles today" in privacy and "hash" in privacy
    assert "Egypt" in privacy


def test_legal_drafts_without_jurisdiction_ask_and_mark_counsel(tmp_path):
    orch = make_orch(tmp_path)
    brief = {k: v for k, v in BRIEF.items() if k != "jurisdiction"}
    rid = start_at(orch, "4.2", brief=brief, seed=SEED_41)
    run = orch.advance(rid)
    assert "Which country" in run.steps["4.2"].questions[0]
    for name in ("terms.md", "privacy.md", "refund.md"):
        assert "Jurisdiction: not provided. Every jurisdiction-specific clause is TO CONFIRM WITH COUNSEL" in \
            _artifact(orch, rid, "4.2", name)


def test_legal_approval_requires_acknowledgment_then_publishes_to_mocked_site(tmp_path):
    orch = make_orch(tmp_path)
    rid = start_at(orch, "4.2", seed=SEED_41)
    orch.advance(rid)
    with pytest.raises(FounderActionError):
        orch.act(rid, {"kind": "approve", "step": "4.2", "channel": "cli"})
    site = orch.store.site_dir(rid)
    assert not (site / "terms.html").exists()
    orch.act(rid, {"kind": "approve", "step": "4.2", "acknowledge": True, "channel": "cli"})
    for name in ("terms.html", "privacy.html", "refund.html"):
        assert BANNER in (site / name).read_text(encoding="utf-8")
    entries = orch.log(rid).entries
    assert any(e["action"] == "acknowledge" and e.get("acknowledged") for e in entries)
    published = [e for e in entries if e["action"] == "mock_publish" and e["step"] == "4.2"]
    assert len(published) == 3 and all(e["mocked"] and e["approved_by"] == "founder" for e in published)
    run = orch.store.load(rid)
    assert run.steps["4.2"].outcome == "GO"
