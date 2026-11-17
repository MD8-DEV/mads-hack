"""Interviewer agent: Mom Test interview kit (1.4) and coding of free-text notes.

The model drafts the script and recruiting plan; code removes any question
that pitches or asks about the future. When notes come back, the model may
only classify note text into template fields, quoting the words that support
each label; code checks the quote is really in the note and does all counts.
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, as_list, call_agent

ROLE = "interviewer"


def _validate_kit(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    script = data.get("script") if isinstance(data.get("script"), dict) else {"questions": data.get("questions")}
    questions = [q for q in as_list(script.get("questions")) if q]
    if not questions:
        raise ValueError("the script needs interview questions")
    script["questions"] = questions
    data["script"] = script
    return data


def prepare_kit(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="prepare_kit", payload=payload, tier="main", max_tokens=3000,
                      validate=_validate_kit, description="Drafted the Mom Test interview kit (script, screener, "
                      "recruiting plan)")


def _validate_codes(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
        raise ValueError("expected {\"notes\": [...]}")
    return data


def code_notes(ctx: StepContext, notes: list[dict[str, Any]]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="code_notes", payload={"notes": notes}, tier="fast", max_tokens=2500,
                      validate=_validate_codes, action_type="ANALYZE_DATA",
                      description=f"Classified {len(notes)} free-text interview note(s) into template fields")
