"""Launch marketer agent: store-page copy (step 5.1) and launch-post drafts (step 5.2).

Prices, links, labels and the MOCKED notices are set by code; the model only
writes descriptive copy and post drafts for the founder to post themselves.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_float, as_list, call_agent
from agents.business_designer import _text
from agents.growth_marketer import _faq

ROLE = "launch_marketer"


def validate_store_page(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    out = {"product_name": _text(data.get("product_name"), 80), "tagline": _text(data.get("tagline"), 160),
           "who_it_serves": _text(data.get("who_it_serves"), 500), "outcome": _text(data.get("outcome"), 500),
           "available_now": _text(data.get("available_now"), 700),
           "not_included": _text(data.get("not_included"), 500),
           "demo_description": _text(data.get("demo_description"), 700), "faq": _faq(data.get("faq")),
           "summary": _text(data.get("summary"), 600),
           "questions": [_text(q, 300) for q in as_list(data.get("questions")) if _text(q)][:3]}
    missing = [k for k in ("who_it_serves", "outcome", "available_now") if not out[k]]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    return out


def validate_launch_posts(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    posts = []
    for item in as_list(data.get("posts")):
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text") or item.get("post"), 3000)
        channel = _text(item.get("channel_id") or item.get("channel"), 60)
        if not text or not channel:
            continue
        day = as_float(item.get("day"), None)
        posts.append({"channel_id": channel, "channel_name": _text(item.get("channel_name"), 120),
                      "format": _text(item.get("format"), 120) or "post",
                      "text": text, "day": int(day) if day is not None and 1 <= day <= 14 else None,
                      "timing": _text(item.get("timing"), 200), "follow_up": _text(item.get("follow_up"), 300)})
    if not posts:
        raise ValueError("give at least one post with channel_id and text")
    return {"posts": posts, "summary": _text(data.get("summary"), 600),
            "questions": [_text(q, 300) for q in as_list(data.get("questions")) if _text(q)][:3]}


def store_page(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="store_page", payload=payload, tier="main", max_tokens=2500,
                      validate=validate_store_page, description="Wrote store-page copy")


def launch_posts(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="launch_posts", payload=payload, tier="main", max_tokens=3000,
                      validate=validate_launch_posts, description="Drafted launch posts for the founder to post")
