"""Legal drafter agent (step 4.2): Terms, Privacy and Refund policy DRAFTS.

The model drafts text tailored to the product and to the data the prototype
actually handles. phases/commercial.py then enforces the draft banner, the
accurate description of today's MOCKED no-payment workflow, the conditional
marking of future paid terms, and removes any claim of legal compliance.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent

MIN_DOC_CHARS = 120


def _text(value: Any) -> str:
    if isinstance(value, list):
        value = "\n".join(str(x) for x in value)
    return str(value or "").strip()


def validate_policies(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    terms, privacy = _text(data.get("terms")), _text(data.get("privacy"))
    refund_current = _text(data.get("refund_current") or data.get("refund"))
    refund_future = _text(data.get("refund_future_conditional"))
    missing = [name for name, text in (("terms", terms), ("privacy", privacy), ("refund_current", refund_current))
               if len(text) < MIN_DOC_CHARS]
    if missing:
        raise ValueError(f"these drafts are missing or too short: {', '.join(missing)}")
    return {
        "terms": terms,
        "privacy": privacy,
        "refund_current": refund_current,
        "refund_future_conditional": refund_future,
        "implementation_checklist": [str(x).strip() for x in as_list(data.get("implementation_checklist")) if str(x).strip()][:15],
        "counsel_questions": [str(x).strip() for x in as_list(data.get("counsel_questions")) if str(x).strip()][:12],
        "build_discrepancies": [str(x).strip() for x in as_list(data.get("build_discrepancies")) if str(x).strip()][:10],
        "questions": [str(x).strip() for x in as_list(data.get("questions")) if str(x).strip()][:3],
    }


def policies(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Draft Terms, Privacy and Refund policies (drafts only; a lawyer must review them)."""
    return call_agent(ctx, role="legal_drafter", task="policies", payload=payload, tier="main", max_tokens=6000,
                      validate=validate_policies,
                      description="Legal drafter wrote Terms, Privacy and Refund policy drafts (not legal advice)")
