"""Founder Answer Rubric: scores substantive founder inputs (not plain approvals).

Four criteria, 0-2 each: specificity, evidence basis, consistency, completeness.
The model proposes scores with reasons; code sums them and applies the rule:
7-8 accept, 4-6 accept provisionally (up to 3 follow-up questions), 0-3 block.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent
from llm import LLMError

CRITERIA = ("specificity", "evidence_basis", "consistency", "completeness")
RED_FLAGS = (
    "compliments counted as validation", "my friends love it", "future-tense promises (would pay)",
    "sample size under 5", "cherry-picked data", "moving goalposts",
)


def decide(total: int) -> str:
    if total >= 7:
        return "ACCEPT"
    if total >= 4:
        return "PROVISIONAL"
    return "BLOCK"


def score_input(ctx: StepContext, text: str, *, kind: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"input_kind": kind, "founder_input": text[:6000], "context": context or {},
               "red_flags_to_check": list(RED_FLAGS)}
    try:
        data = call_agent(ctx, role="rubric_scorer", task="score_input", payload=payload, tier="fast",
                          max_tokens=900, action_type="ANALYZE_DATA",
                          description=f"Scored founder input ({kind}) with the Founder Answer Rubric")
    except LLMError as exc:
        return {"scores": {}, "total": None, "decision": "UNSCORED", "red_flags": [],
                "follow_up_questions": [], "notes": f"Rubric unavailable: {exc}", "excluded_category": None}
    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}
    raw_scores = data.get("scores") or {}
    for criterion in CRITERIA:
        item = raw_scores.get(criterion, {})
        value = item.get("score") if isinstance(item, dict) else item
        try:
            scores[criterion] = max(0, min(2, int(round(float(value)))))
        except (TypeError, ValueError):
            scores[criterion] = 0
        reasons[criterion] = str(item.get("reason", "")) if isinstance(item, dict) else ""
    total = sum(scores.values())
    excluded = data.get("excluded_category")
    if isinstance(excluded, str) and excluded.strip().lower() in ("", "none", "null", "no"):
        excluded = None
    return {
        "scores": scores,
        "reasons": reasons,
        "total": total,
        "decision": decide(total),
        "red_flags": [str(x) for x in as_list(data.get("red_flags"))][:6],
        "follow_up_questions": [str(x) for x in as_list(data.get("follow_up_questions"))][:3],
        "weakest": str(data.get("weakest") or ""),
        "excluded_category": excluded,
        "excluded_reason": str(data.get("excluded_reason") or ""),
    }


def format_score(result: dict[str, Any]) -> str:
    if result.get("total") is None:
        return "Input quality: not scored (model unavailable)"
    weakest = result.get("weakest") or ""
    suffix = f" ({weakest})" if weakest else ""
    return f"Input quality: {result['total']}/8{suffix} - {result['decision']}"
