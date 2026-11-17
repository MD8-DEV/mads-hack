"""Doc writer agent: user docs and the usability-test plan for the built product (step 3.3).

The model writes from the actual files built in 3.2 (and an inventory of the
UI labels code extracted from them). Code renders the markdown files, adds
known limitations it can observe itself, and flags UI labels in the docs
that do not exist in the product.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_float, as_list, call_agent

ROLE = "doc_writer"


def _s(value: Any, limit: int = 800) -> str:
    return " ".join(str(value or "").split())[:limit]


def _lines(value: Any, limit: int = 10, size: int = 400) -> list[str]:
    return [_s(v, size) for v in as_list(value) if _s(v)][:limit]


def validate_docs(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("expected one JSON object")
    quick = data.get("quick_start") if isinstance(data.get("quick_start"), dict) else {"steps": data.get("quick_start")}
    steps = _lines(quick.get("steps"), 10)
    if not steps:
        raise ValueError("'quick_start.steps' needs at least one step")
    how_to = []
    for item in as_list(data.get("how_to")):
        if isinstance(item, dict) and _s(item.get("flow")) and _lines(item.get("steps")):
            how_to.append({"flow": _s(item.get("flow"), 120), "goal": _s(item.get("goal"), 300),
                           "steps": _lines(item.get("steps"), 12), "result": _s(item.get("result"), 300)})
    if not how_to:
        raise ValueError("'how_to' needs at least one core flow with steps")
    faq = [{"q": _s(i.get("q") or i.get("question"), 300), "a": _s(i.get("a") or i.get("answer"), 900)}
           for i in as_list(data.get("faq")) if isinstance(i, dict) and _s(i.get("q") or i.get("question"))][:12]
    test = data.get("usability_test") if isinstance(data.get("usability_test"), dict) else {}
    tasks = []
    for index, item in enumerate(as_list(test.get("tasks")), start=1):
        if not isinstance(item, dict) or not _s(item.get("neutral_goal") or item.get("goal")):
            continue
        minutes = as_float(item.get("max_minutes"), 10.0) or 10.0
        tasks.append({"id": _s(item.get("id"), 10) or f"T{index}",
                      "neutral_goal": _s(item.get("neutral_goal") or item.get("goal"), 400),
                      "success_criterion": _s(item.get("success_criterion"), 300),
                      "realistic_data": _s(item.get("realistic_data"), 300),
                      "max_minutes": max(1.0, min(60.0, minutes)), "core": bool(item.get("core", index == 1))})
    if not tasks:
        raise ValueError("'usability_test.tasks' needs at least one task with a neutral goal")
    recruiting = test.get("recruiting") if isinstance(test.get("recruiting"), dict) else {}
    invite = data.get("invite") if isinstance(data.get("invite"), dict) else {}
    return {
        "quick_start": {"intro": _s(quick.get("intro"), 600), "steps": steps,
                        "first_value": _s(quick.get("first_value"), 300)},
        "faq": faq,
        "how_to": how_to[:6],
        "limitations": _lines(data.get("limitations"), 12),
        "help": _s(data.get("help"), 800),
        "usability_test": {
            "recruiting": {"from_waitlist": _s(recruiting.get("from_waitlist"), 500),
                           "other_route": _s(recruiting.get("other_route"), 500),
                           "screening": _lines(recruiting.get("screening"), 6, 200)},
            "tasks": tasks[:5],
            "critical_failure_definition": _s(test.get("critical_failure_definition"), 500),
            "moderator_notes": _lines(test.get("moderator_notes"), 8, 300),
        },
        "invite": {"subject": _s(invite.get("subject"), 150), "body": str(invite.get("body") or "").strip()[:2500]},
    }


def user_docs(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="user_docs", payload=payload, tier="main", max_tokens=5000,
                      validate=validate_docs,
                      description="Wrote user docs and a usability-test plan from the built product files")
