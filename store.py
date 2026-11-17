"""Run state on disk: one folder per run.

data/runs/<run_id>/
  run.json            current state (derived; rewritten on every transition)
  decision_log.json   append-only log of every agent action
  evidence.json       evidence ledger
  approvals.json      founder approvals (append-only)
  artifacts/          deliverables per step and attempt
  site/               MOCKED publishing target (landing page, store page)
  outbox/             MOCKED sending target (posts, emails) - nothing leaves the machine
  events.json         first-party events from the local landing/store pages (page views, sign-ups)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from approval import ApprovalBook
from evidence import EvidenceLedger
from logbook import DecisionLog, _atomic_write_json, utc_now

# Step statuses
NEW = "NEW"
AWAITING_LOCK = "AWAITING_THRESHOLD_LOCK"
READY_TO_GENERATE = "READY_TO_GENERATE"
COLLECTING = "COLLECTING"
WAITING_FOR_DATA = "WAITING_FOR_DATA"
AWAITING_DECISION = "AWAITING_FOUNDER_DECISION"
DONE = "DONE"
SUPERSEDED = "SUPERSEDED"


class StepState(BaseModel):
    step_id: str
    status: str = NEW
    attempt: int = 0                     # increments on every repeat or pivot back into this step
    repeat_count: int = 0                # repeats used in the current version (limit 2)
    prior_pivots: int = 0                # times this step has failed and caused a pivot back
    artifacts: dict[str, str] = Field(default_factory=dict)  # name -> path relative to the run folder
    output: dict[str, Any] = Field(default_factory=dict)     # structured deliverable (latest attempt)
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    contract: dict[str, Any] | None = None
    contract_history: list[dict[str, Any]] = Field(default_factory=list)
    observation: dict[str, Any] | None = None
    submitted: dict[str, Any] = Field(default_factory=dict)
    gate: dict[str, Any] | None = None
    gate_history: list[dict[str, Any]] = Field(default_factory=list)
    decision: dict[str, Any] | None = None
    feedback: str | None = None
    outcome: str | None = None
    overridden: bool = False
    guardrail_flags: list[dict[str, Any]] = Field(default_factory=list)
    claim_problems: list[str] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class Run(BaseModel):
    run_id: str
    title: str
    created_at: str
    founder: str = "founder"
    brief: dict[str, Any] = Field(default_factory=dict)
    intake: dict[str, Any] | None = None
    status: str = "ACTIVE"               # ACTIVE | STOPPED | COMPLETED | BLOCKED
    status_reason: str = ""
    current_step: str = "1.1"
    steps: dict[str, StepState] = Field(default_factory=dict)
    pending: dict[str, Any] | None = None  # what the pipeline waits for: kind, step, prompt
    phase_reviews: dict[str, dict[str, Any]] = Field(default_factory=dict)
    selected_concept: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)  # founder <-> system messages (refusals etc.)
    history: list[dict[str, Any]] = Field(default_factory=list)   # transitions: GO, REPEAT, PIVOT_BACK, STOP
    final_decision: dict[str, Any] | None = None
    updated_at: str = Field(default_factory=utc_now)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug[:max_len].strip("-")) or "venture"


class RunStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # --- paths
    def path(self, run_id: str) -> Path:
        return self.root / run_id

    def exists(self, run_id: str) -> bool:
        return (self.path(run_id) / "run.json").exists()

    # --- lifecycle
    def create(self, brief: dict[str, Any], *, title: str | None = None, founder: str = "founder",
               step_ids: list[str] | None = None, run_id: str | None = None) -> Run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        title = title or brief.get("title") or brief.get("idea", "")[:60] or "Untitled venture"
        run_id = run_id or f"{stamp}-{slugify(title)}"
        run = Run(run_id=run_id, title=title, created_at=utc_now(), founder=founder, brief=brief)
        for step_id in step_ids or []:
            run.steps[step_id] = StepState(step_id=step_id)
        if step_ids:
            run.current_step = step_ids[0]
        self.path(run_id).mkdir(parents=True, exist_ok=True)
        self.save(run)
        return run

    def load(self, run_id: str) -> Run:
        data = json.loads((self.path(run_id) / "run.json").read_text(encoding="utf-8"))
        return Run(**data)

    def save(self, run: Run) -> None:
        run.updated_at = utc_now()
        _atomic_write_json(self.path(run.run_id) / "run.json", run.model_dump())

    def list(self) -> list[Run]:
        runs = []
        for folder in sorted(self.root.iterdir(), reverse=True) if self.root.exists() else []:
            if (folder / "run.json").exists():
                try:
                    runs.append(self.load(folder.name))
                except Exception:  # noqa: BLE001 - skip unreadable runs in listings
                    continue
        return runs

    # --- per-run stores
    def log(self, run_id: str) -> DecisionLog:
        return DecisionLog(self.path(run_id) / "decision_log.json", run_id=run_id)

    def ledger(self, run_id: str) -> EvidenceLedger:
        return EvidenceLedger(self.path(run_id) / "evidence.json")

    def approvals(self, run_id: str) -> ApprovalBook:
        return ApprovalBook(self.path(run_id) / "approvals.json", run_id=run_id)

    # --- artifacts
    def write_artifact(self, run_id: str, step_id: str, attempt: int, name: str, content: str | dict | list) -> str:
        folder = self.path(run_id) / "artifacts" / f"step{step_id.replace('.', '_')}" / f"attempt{attempt}"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            target.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            target.write_text(content, encoding="utf-8")
        return str(target.relative_to(self.path(run_id))).replace("\\", "/")

    def read_artifact(self, run_id: str, rel_path: str) -> str:
        return (self.path(run_id) / rel_path).read_text(encoding="utf-8")

    def artifact_path(self, run_id: str, rel_path: str) -> Path:
        return self.path(run_id) / rel_path

    # --- MOCKED publishing / sending targets
    def site_dir(self, run_id: str) -> Path:
        folder = self.path(run_id) / "site"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def outbox_dir(self, run_id: str) -> Path:
        folder = self.path(run_id) / "outbox"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # --- first-party events (local landing/store page analytics)
    def events_path(self, run_id: str) -> Path:
        return self.path(run_id) / "events.json"

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self.events_path(run_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8") or "[]")

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        events = self.read_events(run_id)
        event = {"event_id": f"EV-{len(events) + 1:05d}", "timestamp": utc_now(), **event}
        events.append(event)
        _atomic_write_json(self.events_path(run_id), events)
        return event
