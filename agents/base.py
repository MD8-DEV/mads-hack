"""Shared plumbing for role agents.

* StepContext - everything a step handler and its agents may use
* load_prompt - reads prompts/<role>.md (plus the shared core principles)
* call_agent  - one logged model call that must return JSON

Every call_agent() appends exactly one decision-log entry with the model id,
token counts and the cost reported by the provider.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from approval import ApprovalBook
from config import ROOT, Settings
from evidence import EvidenceLedger
from gates import Contract
from llm import BaseLLM
from logbook import DecisionLog

PROMPTS_DIR = ROOT / "prompts"
CORE_PROMPT = "venture_validator"


@dataclass
class StepContext:
    run: Any                      # store.Run
    meta: Any                     # steps.StepMeta (None during intake)
    store: Any                    # store.RunStore
    llm: BaseLLM
    log: DecisionLog
    ledger: EvidenceLedger
    approvals: ApprovalBook
    settings: Settings
    contract: Contract | None = None
    feedback: str | None = None   # founder feedback for a repeat, or guardrail feedback
    repeat_count: int = 0
    attempt: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    # --- identifiers
    @property
    def run_id(self) -> str:
        return self.run.run_id

    @property
    def step_id(self) -> str:
        return self.meta.step_id if self.meta else "0.0"

    @property
    def phase(self) -> int:
        return self.meta.phase if self.meta else 0

    # --- founder inputs and earlier deliverables
    @property
    def brief(self) -> dict[str, Any]:
        return self.run.brief or {}

    def prior(self, step_id: str) -> dict[str, Any]:
        """Structured deliverable of an earlier step (latest attempt), or {}."""
        state = self.run.steps.get(step_id)
        return dict(state.output) if state and state.output else {}

    def concept(self) -> dict[str, Any]:
        """The concept the founder selected in 1.2, else the sharpened statement from 1.1, else the brief."""
        if self.run.selected_concept:
            return dict(self.run.selected_concept)
        sharpened = self.prior("1.1")
        if sharpened:
            return {"name": sharpened.get("title") or self.run.title,
                    "statement": sharpened.get("problem_statement") or sharpened.get("statement", ""),
                    "segment": sharpened.get("segment", "")}
        return {"name": self.run.title, "statement": self.brief.get("idea", ""), "segment": self.brief.get("customer", "")}

    def evidence_digest(self, limit: int = 40) -> list[dict[str, Any]]:
        """Compact evidence rows to show a model (IDs it may cite)."""
        rows = []
        for ev in self.ledger.all()[-limit:]:
            rows.append({"id": ev.evidence_id, "provenance": ev.provenance, "source": ev.source_type,
                         "url": ev.url, "title": ev.title[:140], "excerpt": ev.excerpt[:280],
                         "value": ev.value, "unit": ev.unit, "observed_at": ev.observed_at})
        return rows

    def run_path(self) -> Path:
        return self.store.path(self.run.run_id)


def load_prompt(role: str, *, include_core: bool = True) -> str:
    path = PROMPTS_DIR / f"{role}.md"
    text = path.read_text(encoding="utf-8") if path.exists() else f"You are the {role} agent."
    if include_core and role != CORE_PROMPT:
        core_path = PROMPTS_DIR / f"{CORE_PROMPT}.md"
        if core_path.exists():
            text = core_path.read_text(encoding="utf-8") + "\n\n---\n\n" + text
    return text


def call_agent(ctx: StepContext, *, role: str, task: str, payload: dict[str, Any], tier: str = "main",
               max_tokens: int = 3500, validate: Callable[[Any], Any] | None = None,
               action_type: str = "GENERATE_DELIVERABLE", description: str = "",
               sources: list[str] | None = None, temperature: float = 0.2) -> Any:
    """One logged model call that returns parsed (and optionally validated) JSON."""
    system = load_prompt(role)
    user = (f"TASK_ID: {role}.{task}\n"
            f"Follow the instructions for task '{task}' in your prompt.\n\n"
            f"INPUT (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=1, default=str)}\n\n"
            "Reply with ONLY one JSON object in the shape your prompt specifies for this task. No markdown fences.")
    data, result = ctx.llm.chat_json(system, user, tier=tier, max_tokens=max_tokens, temperature=temperature,
                                     validate=validate)
    ctx.log.append(agent=role, action=task, action_type=action_type, phase=ctx.phase, step=ctx.step_id,
                   description=description or f"{role} ran {task}", sources=sources or [], model=result.model,
                   cost=result.cost, tokens_in=result.tokens_in, tokens_out=result.tokens_out, approved_by=None,
                   provider=result.provider, latency_s=result.latency_s, model_attempts=result.attempts)
    return data


def as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return default
