"""Base classes shared by every step handler.

A handler implements one pipeline step:

    generate(ctx)                  -> StepOutput     the deliverable (calls role agents)
    default_contract(ctx)          -> Contract|None  proposed thresholds for E/T gates (founder locks them)
    collect(ctx, contract)         -> Observation|None
                                      automatic data collection AFTER the lock (desk research,
                                      test runs, local page analytics). None means the founder
                                      has to submit the data.
    data_fields()                  -> list[DataField] what the founder can submit for this step
    observe(ctx, contract, data)   -> Observation    turn founder-submitted data into observed values

The orchestrator owns state, logging of gates and approvals, and the order of
calls. Handlers never decide gate outcomes: gates.py does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evidence import Claim
from gates import INSUFFICIENT_DATA, READY, WAITING_FOR_DATA, Contract


@dataclass
class DataField:
    key: str
    label: str
    type: str = "number"          # number | integer | text | json | choice
    required: bool = True
    help: str = ""
    choices: list[str] = field(default_factory=list)


@dataclass
class Observation:
    observed: dict[str, float | None]
    measurement_state: str = READY
    sources: list[str] = field(default_factory=list)       # URLs backing the observed values
    evidence_ids: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)  # per-criterion provenance, counts, intervals
    notes: str = ""
    pivot_target: str | None = None                        # override the default pivot route


@dataclass
class StepOutput:
    title: str
    markdown: str                                           # founder-facing deliverable
    data: dict[str, Any] = field(default_factory=dict)      # structured deliverable (JSON)
    files: dict[str, str] = field(default_factory=dict)     # extra artifacts: "landing.html" -> content
    claims: list[Claim] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    summary: str = ""                                       # "what I'm doing now" (1-2 sentences)
    questions: list[str] = field(default_factory=list)      # at most 3 questions for the founder
    observation: Observation | None = None                  # auto-collected during generation (T gates)
    marketing_text: str = ""                                # copy that must pass guardrails.check_marketing


class StepHandler:
    meta = None  # set by steps.get_handler

    def generate(self, ctx) -> StepOutput:  # pragma: no cover - abstract
        raise NotImplementedError

    def default_contract(self, ctx) -> Contract | None:
        return None

    def collect(self, ctx, contract: Contract) -> Observation | None:
        return None

    def data_fields(self) -> list[DataField]:
        return []

    def observe(self, ctx, contract: Contract, data: dict[str, Any]) -> Observation:
        """Default: read one number per criterion key from the submitted data."""
        observed: dict[str, float | None] = {}
        missing = []
        for criterion in contract.criteria:
            value = data.get(criterion.key)
            try:
                observed[criterion.key] = None if value in (None, "") else float(value)
            except (TypeError, ValueError):
                observed[criterion.key] = None
            if observed[criterion.key] is None:
                missing.append(criterion.key)
        state = READY if not missing else (WAITING_FOR_DATA if len(missing) == len(contract.criteria) else INSUFFICIENT_DATA)
        return Observation(observed=observed, measurement_state=state,
                           details={"source": "founder_data", "missing": missing},
                           notes="Founder-reported data" + (f"; missing: {', '.join(missing)}" if missing else ""))
