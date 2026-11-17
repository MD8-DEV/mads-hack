"""Support lead agent (step 6.1): FAQ, ticket categories, severities, templates, escalation.

The model drafts the support workflow from the user docs of step 3.3. Code
fills in any required category or severity the model left out, replaces
response templates that make promises, and computes every response-time
statistic from real tickets (phases/operate.py).
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, as_float, call_agent


def _s(value: Any, limit: int = 600) -> str:
    return str(value or "").strip()[:limit]


def validate_support_setup(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    faq = [{"q": _s(f.get("q") or f.get("question"), 240), "a": _s(f.get("a") or f.get("answer"), 900),
            "source": _s(f.get("source"), 120)}
           for f in as_list(data.get("faq")) if isinstance(f, dict) and (f.get("q") or f.get("question"))]
    categories = [{"id": _s(c.get("id") or c.get("name"), 40).lower().replace(" ", "_").replace("/", "_"),
                   "name": _s(c.get("name") or c.get("id"), 60), "description": _s(c.get("description"), 300),
                   "examples": [_s(x, 160) for x in as_list(c.get("examples"))][:3]}
                  for c in as_list(data.get("ticket_categories")) if isinstance(c, dict) and (c.get("id") or c.get("name"))]
    severities = [{"level": _s(s.get("level"), 20).lower(), "definition": _s(s.get("definition"), 300),
                   "first_response_target_hours": as_float(s.get("first_response_target_hours")),
                   "examples": [_s(x, 160) for x in as_list(s.get("examples"))][:3]}
                  for s in as_list(data.get("severity_levels")) if isinstance(s, dict) and s.get("level")]
    templates = [{"id": _s(t.get("id") or t.get("title"), 40), "category": _s(t.get("category"), 40).lower(),
                  "title": _s(t.get("title"), 120), "body": _s(t.get("body"), 1500)}
                 for t in as_list(data.get("response_templates")) if isinstance(t, dict) and t.get("body")]
    escalation = [_s(x, 300) for x in as_list(data.get("escalation_rules")) if _s(x)][:10]
    hours = data.get("hours_policy") if isinstance(data.get("hours_policy"), dict) else {}
    if not (faq or templates or categories):
        raise ValueError("reply needs at least 'faq', 'ticket_categories' or 'response_templates'")
    return {
        "faq": faq[:15],
        "ticket_categories": categories[:12],
        "severity_levels": severities[:6],
        "response_templates": templates[:12],
        "escalation_rules": escalation,
        "hours_policy": {"basis": "business" if "business" in _s(hours.get("basis")).lower() else "calendar",
                         "business_hours": _s(hours.get("business_hours"), 120),
                         "timezone": _s(hours.get("timezone"), 60)},
        "docs_gaps": [_s(x, 240) for x in as_list(data.get("docs_gaps")) if _s(x)][:8],
        "questions": [_s(x, 300) for x in as_list(data.get("questions")) if _s(x)][:3],
    }


def support_setup(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Support workflow draft: FAQ/knowledge base, categories, severities, templates, escalation."""
    return call_agent(ctx, role="support_lead", task="support_setup", payload=payload, tier="fast", max_tokens=4000,
                      validate=validate_support_setup,
                      description="Support lead drafted the FAQ, ticket categories, severities, templates and escalation rules")
