"""STUBBED model replies (FIXTURE data) for the Phase 4 and Phase 6 role agents.

respond(task_id, user_text) returns a FIXTURE reply for the tasks of pricing_analyst, legal_drafter,
support_lead, metrics_analyst and memo_writer, and None for every other task. Nothing here is real
data: every basis and text is labelled FIXTURE. Some replies contain deliberate mistakes (a missing
draft banner, a compliance claim, a refund sentence that describes money moving, a promise in a
support template, an unknown evidence ID) so tests can check that the code corrects them.
"""
from __future__ import annotations

import json
from typing import Any

BANNER = "DRAFT, not legal advice. Must be reviewed by a qualified lawyer before use."


def _payload(user_text: str) -> dict[str, Any]:
    try:
        return json.loads(user_text.split("INPUT (JSON):", 1)[1].rsplit("Reply with ONLY", 1)[0])
    except (IndexError, ValueError):
        return {}


def pricing_options(payload: dict[str, Any]) -> dict[str, Any]:
    comparable_ids = [i for c in payload.get("comparable_prices") or [] for i in c.get("evidence_ids") or []]
    return {
        "packages": [
            {"id": "solo", "name": "Solo", "price": 9, "billing": "month", "price_metric": "per account",
             "metered": False, "usage_unit": "client projects per month", "usage_examples": {"low": 1, "typical": 2, "high": 4},
             "includes": ["Feedback threads for every project", "Export of all feedback"],
             "upgrade_trigger": "FIXTURE: needs a second seat", "likely_objections": ["FIXTURE: email works for me"],
             "cost_to_serve_note": "FIXTURE: hosting only"},
            {"id": "team", "name": "Team", "price": 19, "billing": "month", "price_metric": "per account",
             "metered": False, "usage_unit": "client projects per month", "usage_examples": {"low": 2, "typical": 5, "high": 12},
             "includes": ["Everything in Solo", "Shared workspace for a small studio"],
             "upgrade_trigger": "FIXTURE: client portal branding", "likely_objections": ["FIXTURE: price vs free tools"],
             "cost_to_serve_note": "FIXTURE: hosting plus support time"},
            {"id": "studio", "name": "Studio", "price": 4, "billing": "month", "price_metric": "per seat",
             "metered": True, "usage_unit": "seats", "usage_examples": {"low": 3, "typical": 6, "high": 15},
             "includes": ["Everything in Team", "Per-seat billing for larger studios"],
             "upgrade_trigger": "FIXTURE: more seats", "likely_objections": ["FIXTURE: bill grows with seats"],
             "cost_to_serve_note": "FIXTURE: support time per seat"},
        ],
        "recommended_package_id": "team",
        "economics": {"variable_cost_per_customer": 2.5, "period": "month", "variable_cost_label": "ESTIMATE",
                      "variable_cost_basis": "FIXTURE: stub hosting and model-call estimate",
                      "target_margin": 0.7, "target_margin_label": "ASSUMPTION",
                      "target_margin_basis": "FIXTURE: stub margin target", "high_usage_note": "FIXTURE: heavy users double cost"},
        "outside_option": {"summary": "FIXTURE: comparable tools listed in the evidence.",
                           "workaround": "FIXTURE: email threads and spreadsheets",
                           "evidence_ids": comparable_ids[:2] + ["E-999"]},
        "customer_value": {"estimate": 40, "period": "month", "label": "ESTIMATE",
                           "basis": "FIXTURE: stub hours saved times stub hourly rate", "evidence_ids": []},
        "rationale": "FIXTURE: Team sits above the floor and near the comparable price.",
        "bundle_description": "the Team plan of the client feedback tracker",
        "page_headline": "Plans for collecting client feedback in one place",
        "claims": [{"text": "FIXTURE: buyers budget per month for tools", "label": "ASSUMPTION", "evidence_ids": [],
                    "basis": "FIXTURE"}],
        "questions": ["FIXTURE: Which plan do your first users need?"],
    }


def legal_policies(payload: dict[str, Any]) -> dict[str, Any]:
    product = (payload.get("product") or {}).get("name") or "the product"
    return {
        "terms": (f"{BANNER}\n\n# Terms of Service\n\n## Using {product}\n\nFIXTURE terms text. You may use the "
                  "prototype to collect client feedback. Governing law: TO CONFIRM WITH COUNSEL.\n\n## Orders\n\n"
                  "Orders are MOCKED and no payment is taken."),
        # Deliberate mistakes: no banner, and a compliance claim the code must remove.
        "privacy": ("# Privacy Policy\n\n## What we collect\n\nFIXTURE privacy text. We store a hash of your waitlist "
                    "email and a consent flag, and page views with a random visitor id. This service is fully "
                    "compliant with GDPR. We do not collect payment details."),
        # Deliberate mistake: one sentence describes refunds of money happening today.
        "refund_current": ("FIXTURE refund text. No payment is taken today, so there is nothing to refund. "
                           "Refunds will be issued to your card within 5 days."),
        "refund_future_conditional": "FIXTURE: If paid plans launch, a refund window would be offered. TO CONFIRM WITH COUNSEL.",
        "implementation_checklist": ["FIXTURE: add a contact email"],
        "counsel_questions": ["FIXTURE: Which consumer law applies to monthly plans?"],
        "build_discrepancies": [],
        "questions": [],
    }


def support_setup(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "faq": [{"q": "How do I start a feedback thread?", "a": "FIXTURE: open a project and choose New thread.",
                 "source": "quick-start"},
                {"q": "Can clients see each other's feedback?", "a": "FIXTURE: no, each project is separate.",
                 "source": "TO VERIFY"}],
        "ticket_categories": [
            {"id": "onboarding", "name": "Onboarding", "description": "FIXTURE: first use", "examples": []},
            {"id": "reliability", "name": "Reliability", "description": "FIXTURE: errors", "examples": []},
            {"id": "trust_privacy", "name": "Trust and privacy", "description": "FIXTURE: data questions", "examples": []},
        ],
        "severity_levels": [{"level": "critical", "definition": "FIXTURE: data exposure", "first_response_target_hours": 2},
                            {"level": "low", "definition": "FIXTURE: questions", "first_response_target_hours": 72}],
        "response_templates": [
            {"id": "onboarding-1", "category": "onboarding", "title": "Getting started",
             "body": "Hi, thanks for trying it. Could you tell me which step you are on? I will reply here.\n[Your name]"},
            # Deliberate mistake: a promise the code must replace.
            {"id": "reliability-1", "category": "reliability", "title": "Bug report",
             "body": "Sorry about that. We guarantee a fix within 24 hours."},
        ],
        "escalation_rules": ["FIXTURE: critical tickets go to the founder at once."],
        "hours_policy": {"basis": "calendar", "business_hours": "", "timezone": "UTC"},
        "docs_gaps": ["FIXTURE: no page on exporting feedback"],
        "questions": [],
    }


def dashboard_spec(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "value_event": "FIXTURE: first feedback thread resolved with a client",
        "activation_window_days": 7,
        "metrics": [{"key": "activation", "name": "Activation", "question": "FIXTURE: do new users resolve a thread?",
                     "numerator": "FIXTURE: users resolving a thread within 7 days",
                     "denominator": "FIXTURE: new users with 7 complete days", "window": "7 days",
                     "cohort_rule": "FIXTURE: weekly signup cohorts", "data_source": "FIXTURE: product events"}],
        "data_quality_checks": ["FIXTURE: dedupe visitors by random id"],
        "instrumentation_gaps": ["FIXTURE: the prototype does not log thread resolution"],
        "questions": [],
    }


def decision_memo(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = payload.get("allowed_recommendations") or ["PIVOT", "STOP"]
    recommendation = "PIVOT" if "PIVOT" in allowed else allowed[0]
    scenario = {"billing": "month", "net_price": 19, "variable_cost": 2.5, "cac": 60, "fixed_cost_per_month": 200,
                "basis": {"net_price": "FIXTURE: recommended Team price", "variable_cost": "FIXTURE: 4.1 estimate",
                          "cac": "FIXTURE: stub channel cost", "fixed_cost_per_month": "FIXTURE: stub tools cost"}}
    return {
        "recommendation": recommendation, "pivot_type": "channel",
        "headline": "FIXTURE: memo headline from the gate table.",
        "original_hypothesis": "FIXTURE: freelance designers lose time chasing client feedback.",
        "supporting_evidence": [{"text": "FIXTURE: a supporting point", "evidence_ids": ["E-001", "E-999"]}],
        "countervailing_evidence": [{"text": "FIXTURE: a countervailing point", "evidence_ids": []}],
        "proven": [], "disproven": [], "assumptions_changed": ["FIXTURE: channel"], "unresolved": ["FIXTURE: retention"],
        "overrides_affecting_interpretation": [],
        "next_move": "FIXTURE: test a different acquisition channel.",
        "unit_economics": {"currency": "USD",
                           "scenarios": {"base": scenario,
                                         "downside": {**scenario, "net_price": 9, "cac": 120},
                                         "upside": {**scenario, "cac": None, "acquisition_cost_total": 300,
                                                    "customers_acquired": 10}},
                           "main_sensitivity": "FIXTURE: CAC", "practical_constraint": "FIXTURE: founder time"},
        "experiments": [{"hypothesis": "FIXTURE: designer communities convert", "design": "FIXTURE: two posts",
                         "cost_time": "FIXTURE: 0 USD, 2 weeks", "data_source": "local events", "owner": "founder",
                         "decision_rule": "FIXTURE: >= 30 sign-ups", "what_it_changes": "FIXTURE: channel choice"}],
        "questions": [],
    }


HANDLERS = {
    "pricing_analyst.pricing_options": pricing_options,
    "legal_drafter.policies": legal_policies,
    "support_lead.support_setup": support_setup,
    "metrics_analyst.dashboard_spec": dashboard_spec,
    "memo_writer.decision_memo": decision_memo,
}


def respond(task_id: str, user_text: str) -> dict | None:
    handler = HANDLERS.get(task_id)
    return handler(_payload(user_text)) if handler else None


def vw_fixture_responses(scale: float = 1.0, n: int = 32) -> list[dict[str, float]]:
    """FIXTURE Van Westendorp rows. At scale 1.0 the acceptable range is about 11.5-25 (contains 19);
    at scale 0.4 it is about 4.6-10 (excludes 19)."""
    rows = []
    for i in range(n):
        base = 10 + (i % 8)
        rows.append({k: round(v * scale, 2) for k, v in
                     (("too_cheap", base - 5), ("cheap", base), ("expensive", base + 8), ("too_expensive", base + 16))})
    return rows
