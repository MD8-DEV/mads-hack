"""Business designer agent: turns Phase 1 evidence into a Lean Canvas (step 2.1).

The model drafts the nine boxes, the riskiest assumptions and the channels.
Code checks every citation, ranks the assumptions from the model's scores
and drops any channel URL that does not appear in the evidence.
"""
from __future__ import annotations

import re
from typing import Any

from agents.base import StepContext, as_float, as_list, call_agent

ROLE = "business_designer"

# (key, display name, accepted aliases)
BOXES: list[tuple[str, str, tuple[str, ...]]] = [
    ("problem", "Problem", ("problem", "problems")),
    ("customer_segments", "Customer Segments", ("customer_segments", "customer_segment", "segments", "customers")),
    ("unique_value_proposition", "Unique Value Proposition", ("unique_value_proposition", "uvp", "value_proposition")),
    ("solution", "Solution", ("solution", "solutions")),
    ("channels", "Channels", ("channels", "channel")),
    ("revenue_streams", "Revenue Streams", ("revenue_streams", "revenue_stream", "revenue")),
    ("cost_structure", "Cost Structure", ("cost_structure", "costs", "cost")),
    ("key_metrics", "Key Metrics", ("key_metrics", "metrics", "key_metric")),
    ("unfair_advantage", "Unfair Advantage", ("unfair_advantage", "advantage")),
]
BOX_LABELS = ("SOURCED", "FOUNDER_REPORTED", "ASSUMPTION", "UNKNOWN")
MIN_FILLED_BOXES = 7


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")


def _text(value: Any, limit: int = 1200) -> str:
    if isinstance(value, list):
        value = "; ".join(_text(v, limit) for v in value if v not in (None, ""))
    elif isinstance(value, dict):
        value = "; ".join(f"{k}: {_text(v, limit)}" for k, v in value.items() if v not in (None, ""))
    return str(value or "").strip()[:limit]


def _ids(value: Any) -> list[str]:
    out: list[str] = []
    for item in as_list(value):
        found = re.findall(r"E-\d{3,}", str(item))
        out += [i for i in found if i not in out]
    return out


def _label(value: Any) -> str:
    label = _norm(value).upper()
    return label if label in BOX_LABELS else "ASSUMPTION"


def _score(value: Any, default: float = 3.0) -> float:
    number = as_float(value, None)
    if number is None:
        word = _norm(value)
        number = {"very_high": 5, "high": 4, "medium": 3, "moderate": 3, "low": 2, "very_low": 1}.get(word, default)
    return max(1.0, min(5.0, float(number)))


def _boxes_by_key(raw: Any) -> dict[str, Any]:
    """Accept {"problem": {...}} or [{"box": "Problem", ...}] and key it by normalized name."""
    if isinstance(raw, list):
        keyed = {}
        for item in raw:
            if isinstance(item, dict):
                name = item.get("box") or item.get("name") or item.get("key") or item.get("title")
                keyed[_norm(name)] = item
        return keyed
    if isinstance(raw, dict):
        return {_norm(k): v for k, v in raw.items()}
    return {}


def validate_lean_canvas(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    raw = _boxes_by_key(data.get("boxes") or data.get("canvas"))
    boxes: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for key, title, aliases in BOXES:
        item = next((raw[a] for a in aliases if a in raw), None)
        if not isinstance(item, dict):
            item = {"content": item} if item not in (None, "") else {}
        content = _text(item.get("content") or item.get("text") or item.get("value"))
        if not content:
            missing.append(title)
            boxes[key] = {"title": title, "content": "Not determined yet.", "label": "UNKNOWN", "evidence_ids": [],
                          "basis": "The model gave no content for this box."}
            continue
        boxes[key] = {"title": title, "content": content, "label": _label(item.get("label")),
                      "evidence_ids": _ids(item.get("evidence_ids") or item.get("evidence")),
                      "basis": _text(item.get("basis"), 500)}
    if len(BOXES) - len(missing) < MIN_FILLED_BOXES:
        raise ValueError(f"the canvas needs content in all nine boxes; missing: {', '.join(missing)}")

    assumptions = []
    for index, item in enumerate(as_list(data.get("riskiest_assumptions") or data.get("assumptions"))):
        if isinstance(item, str):
            item = {"assumption": item}
        if not isinstance(item, dict):
            continue
        text = _text(item.get("assumption") or item.get("text"), 500)
        if not text:
            continue
        assumptions.append({
            "assumption": text,
            "loss_if_wrong": _text(item.get("loss_if_wrong") or item.get("impact"), 400),
            "loss_score": _score(item.get("loss_score") or item.get("loss_if_wrong_score")),
            "uncertainty_score": _score(item.get("uncertainty_score") or item.get("uncertainty")),
            "test": _text(item.get("test"), 500) or "No test proposed yet.",
            "cost_to_test": _text(item.get("cost_to_test") or item.get("cost"), 200),
            "blocks_decision": _text(item.get("blocks_decision") or item.get("downstream_decision"), 300),
            "order": index,
        })
    if not assumptions:
        raise ValueError("list the riskiest assumptions (three, each with a test and the decision it blocks)")
    # Rank in code: biggest loss if wrong first, then the most uncertain, then the model's order.
    assumptions.sort(key=lambda a: (-a["loss_score"], -a["uncertainty_score"], a["order"]))
    assumptions = assumptions[:3]
    for rank, item in enumerate(assumptions, start=1):
        item["rank"] = rank
        item.pop("order", None)

    channels = []
    for item in as_list(data.get("channels")):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict) or not _text(item.get("name")):
            continue
        url = str(item.get("url") or "").strip()
        channels.append({"id": _text(item.get("id"), 60), "name": _text(item.get("name"), 120),
                         "url": url if url.startswith(("http://", "https://")) else None,
                         "audience_rule": _text(item.get("audience_rule") or item.get("audience"), 400),
                         "evidence_ids": _ids(item.get("evidence_ids"))})

    revenue = data.get("revenue_hypothesis") or {}
    if not isinstance(revenue, dict):
        revenue = {"statement": _text(revenue)}
    revenue = {"who_pays": _text(revenue.get("who_pays"), 300), "price_unit": _text(revenue.get("price_unit"), 200),
               "billing_period": _text(revenue.get("billing_period"), 100),
               "substitute_spend": _text(revenue.get("substitute_spend"), 300),
               "statement": _text(revenue.get("statement"), 500),
               "label": _label(revenue.get("label")), "evidence_ids": _ids(revenue.get("evidence_ids")),
               "basis": _text(revenue.get("basis"), 400)}
    return {"boxes": boxes, "missing_boxes": missing, "riskiest_assumptions": assumptions, "channels": channels,
            "revenue_hypothesis": revenue, "summary": _text(data.get("summary"), 600),
            "questions": [_text(q, 300) for q in as_list(data.get("questions")) if _text(q)][:3]}


def lean_canvas(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="lean_canvas", payload=payload, tier="main", max_tokens=4000,
                      validate=validate_lean_canvas, description="Drafted the evidence-linked Lean Canvas")
