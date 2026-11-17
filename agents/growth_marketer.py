"""Growth marketer agent: landing-page copy and channel actions for the demand test (step 2.2).

The model writes the headline, benefits, FAQ and per-channel actions. Code
fixes the call to action, the availability statement and the tracking, and
renders the page, so the parts that carry honesty rules never depend on the model.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent
from agents.business_designer import _text

ROLE = "growth_marketer"
DEFAULT_FOLLOW_UP = "What best describes your role?"


def _faq(items: Any) -> list[dict[str, str]]:
    out = []
    for item in as_list(items):
        if isinstance(item, dict):
            q = _text(item.get("question") or item.get("q"), 200)
            a = _text(item.get("answer") or item.get("a"), 600)
            if q and a:
                out.append({"question": q, "answer": a})
    return out[:6]


def validate_landing_page(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    headline = _text(data.get("headline"), 140)
    if not headline:
        raise ValueError("headline is required (it states the unique value proposition)")
    benefits = []
    for item in as_list(data.get("benefits")):
        if isinstance(item, dict):
            item = ": ".join(x for x in (_text(item.get("title"), 80), _text(item.get("text") or item.get("detail"), 240)) if x)
        text = _text(item, 260)
        if text:
            benefits.append(text)
    if len(benefits) < 3:
        raise ValueError("give exactly three benefits")
    actions = []
    for item in as_list(data.get("channel_actions")):
        if isinstance(item, dict) and _text(item.get("channel_id")):
            actions.append({"channel_id": _text(item.get("channel_id"), 60), "action": _text(item.get("action"), 400),
                            "message_angle": _text(item.get("message_angle"), 300),
                            "founder_hours": _text(item.get("founder_hours"), 40)})
    return {"headline": headline, "subheadline": _text(data.get("subheadline"), 260), "benefits": benefits[:3],
            "follow_up_question": _text(data.get("follow_up_question"), 160) or DEFAULT_FOLLOW_UP,
            "faq": _faq(data.get("faq")), "channel_actions": actions,
            "repeat_variable": _text(data.get("repeat_variable"), 300),
            "summary": _text(data.get("summary"), 600),
            "questions": [_text(q, 300) for q in as_list(data.get("questions")) if _text(q)][:3]}


def landing_page(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="landing_page", payload=payload, tier="main", max_tokens=2500,
                      validate=validate_landing_page, description="Wrote landing-page copy and channel actions")
