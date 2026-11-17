"""Gatekeeper agent: explains a gate result that gates.py already computed.

The model may only explain. It never changes thresholds, numbers or the
outcome; if it is unavailable, a deterministic explanation is used instead.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent
from gates import Contract, GateResult
from llm import LLMError


def _fallback(gate: GateResult) -> dict[str, Any]:
    reasoning = " ".join(gate.reasons) or "No reasoning available."
    if gate.outcome is None:
        change = "Valid data for every locked criterion, collected within the locked window."
    elif gate.outcome == "GO":
        change = "New evidence that contradicts the criteria this gate relied on."
    else:
        change = "A new result that meets every locked criterion under the same contract."
    return {"reasoning": reasoning, "change_my_mind": change, "model_used": False}


def explain_gate(ctx: StepContext, gate: GateResult, contract: Contract | None, deliverable_summary: str) -> dict[str, Any]:
    payload = {
        "step": f"{ctx.step_id} {ctx.meta.name if ctx.meta else ''}",
        "gate": gate.model_dump(exclude={"evaluated_at"}),
        "contract": contract.model_dump() if contract else None,
        "deliverable_summary": deliverable_summary[:1500],
    }
    try:
        data = call_agent(ctx, role="gatekeeper", task="explain_gate", payload=payload, tier="fast",
                          max_tokens=900, action_type="ANALYZE_DATA",
                          description=f"Explained the gate result for step {ctx.step_id}")
    except LLMError:
        return _fallback(gate)
    reasoning = str(data.get("reasoning") or "").strip()
    change = str(data.get("change_my_mind") or "").strip()
    if not reasoning:
        return _fallback(gate)
    return {"reasoning": reasoning[:1200], "change_my_mind": change[:600] or _fallback(gate)["change_my_mind"],
            "model_used": True}


def summarize_phase(ctx: StepContext, phase: int, phase_name: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {"phase": phase, "phase_name": phase_name, "steps": steps}
    try:
        data = call_agent(ctx, role="gatekeeper", task="summarize_phase", payload=payload, tier="fast",
                          max_tokens=900, action_type="ANALYZE_DATA",
                          description=f"Summarized phase {phase} for the phase-exit review")
        return {
            "summary": str(data.get("summary") or "")[:1600],
            "confirmed": [str(x) for x in as_list(data.get("assumptions_confirmed"))][:6],
            "killed": [str(x) for x in as_list(data.get("assumptions_killed"))][:6],
            "open": [str(x) for x in as_list(data.get("still_open"))][:6],
        }
    except LLMError:
        lines = [f"{s['step']} {s['name']}: outcome {s.get('outcome') or 'pending'}" for s in steps]
        return {"summary": "Phase steps: " + "; ".join(lines), "confirmed": [], "killed": [], "open": []}
