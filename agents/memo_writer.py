"""Memo writer agent (step 6.3): the persevere-or-pivot decision memo.

The model receives the cross-phase gate table that code built, the evidence
digest and the options code allows. It writes the argument and labelled
unit-economics inputs. Code validates the recommendation against the allowed
options and computes contribution, CAC, payback and break-even
(phases/operate.py).
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent
from agents.pricing_analyst import norm_billing, to_number

RECOMMENDATIONS = ("PERSEVERE", "PIVOT", "STOP")
PIVOT_TYPES = ("segment", "problem", "solution", "channel", "pricing")
SCENARIOS = ("base", "downside", "upside")
ECON_INPUTS = ("net_price", "variable_cost", "cac", "acquisition_cost_total", "customers_acquired",
               "fixed_cost_per_month")


def _s(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _points(value: Any, limit: int = 6) -> list[dict[str, Any]]:
    out = []
    for raw in as_list(value):
        if isinstance(raw, dict) and _s(raw.get("text")):
            out.append({"text": _s(raw.get("text")), "evidence_ids": [_s(i, 20) for i in as_list(raw.get("evidence_ids"))][:8]})
        elif isinstance(raw, str) and raw.strip():
            out.append({"text": raw.strip()[:500], "evidence_ids": []})
    return out[:limit]


def _scenario(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    values = {key: to_number(raw.get(key)) for key in ECON_INPUTS}
    bases = raw.get("basis") if isinstance(raw.get("basis"), dict) else {}
    return {**values, "billing": norm_billing(raw.get("billing")),
            "basis": {key: _s(bases.get(key), 300) for key in ECON_INPUTS if bases.get(key)},
            "note": _s(raw.get("note"), 300)}


def validate_decision_memo(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    recommendation = _s(data.get("recommendation"), 30).upper().replace("PIVOT_BACK", "PIVOT")
    if not recommendation:
        raise ValueError("'recommendation' is required (PERSEVERE, PIVOT or STOP)")
    econ = data.get("unit_economics") if isinstance(data.get("unit_economics"), dict) else {}
    scenarios = econ.get("scenarios") if isinstance(econ.get("scenarios"), dict) else {}
    experiments = []
    for raw in as_list(data.get("experiments")):
        if isinstance(raw, dict) and _s(raw.get("hypothesis")):
            experiments.append({key: _s(raw.get(key), 400) for key in
                                ("hypothesis", "design", "cost_time", "data_source", "owner", "decision_rule",
                                 "what_it_changes")})
    return {
        "recommendation": recommendation,
        "pivot_type": _s(data.get("pivot_type"), 30).lower() or None,
        "headline": _s(data.get("headline"), 400),
        "original_hypothesis": _s(data.get("original_hypothesis"), 600),
        "supporting_evidence": _points(data.get("supporting_evidence")),
        "countervailing_evidence": _points(data.get("countervailing_evidence")),
        "proven": [_s(x, 300) for x in as_list(data.get("proven")) if _s(x)][:6],
        "disproven": [_s(x, 300) for x in as_list(data.get("disproven")) if _s(x)][:6],
        "assumptions_changed": [_s(x, 300) for x in as_list(data.get("assumptions_changed")) if _s(x)][:6],
        "unresolved": [_s(x, 300) for x in as_list(data.get("unresolved")) if _s(x)][:6],
        "overrides_affecting_interpretation": [_s(x, 300) for x in as_list(data.get("overrides_affecting_interpretation")) if _s(x)][:6],
        "next_move": _s(data.get("next_move"), 800),
        "unit_economics": {"currency": _s(econ.get("currency"), 8).upper() or None,
                           "scenarios": {name: _scenario(scenarios.get(name)) for name in SCENARIOS},
                           "main_sensitivity": _s(econ.get("main_sensitivity"), 400),
                           "practical_constraint": _s(econ.get("practical_constraint"), 400)},
        "experiments": experiments[:3],
        "questions": [_s(x, 300) for x in as_list(data.get("questions")) if _s(x)][:3],
    }


def decision_memo(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    """The persevere-or-pivot memo: argument, labelled economics inputs and the next three experiments."""
    return call_agent(ctx, role="memo_writer", task="decision_memo", payload=payload, tier="main", max_tokens=4500,
                      validate=validate_decision_memo,
                      description="Memo writer drafted the persevere-or-pivot decision memo from the cross-phase gate table")
