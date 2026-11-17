"""Strategist agent: sharpens the idea (1.1) and scores concepts (1.2).

The model drafts statements and gives 1-5 factor scores with a basis. Code
assembles the problem statement, computes every weighted total, rank and
sensitivity check (phases/discover.py), and never lets a blocked concept be
recommended.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent

ROLE = "strategist"


def _validate_sharpen(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    for key in ("segment", "problem"):
        if not str(data.get(key) or "").strip():
            raise ValueError(f"'{key}' is required")
    alternatives = [a for a in as_list(data.get("alternatives"))
                    if isinstance(a, dict) and str(a.get("statement") or a.get("name") or "").strip()]
    if len(alternatives) < 3:
        raise ValueError("give 3-5 alternative concepts, each changing one assumption")
    data["alternatives"] = alternatives
    return data


def sharpen_idea(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="sharpen_idea", payload=payload, tier="main", max_tokens=2500,
                      validate=_validate_sharpen, description="Sharpened the idea into a problem hypothesis "
                      "and generated alternative concepts")


def _score_validator(expected_ids: list[str]):
    def validate(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        concepts = [c for c in as_list(data.get("concepts")) if isinstance(c, dict)]
        scored = {str(c.get("id")) for c in concepts if isinstance(c.get("scores"), dict)}
        if not scored & set(expected_ids):
            raise ValueError(f"score the concepts with these ids: {', '.join(expected_ids)}")
        data["concepts"] = concepts
        return data
    return validate


def score_concepts(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    ids = [str(c.get("id")) for c in payload.get("concepts", [])]
    return call_agent(ctx, role=ROLE, task="score_concepts", payload=payload, tier="main", max_tokens=3500,
                      validate=_score_validator(ids), description="Scored each concept on the seven factors "
                      "(1-5 with low/base/high and a basis)")
