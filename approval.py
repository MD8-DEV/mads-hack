"""Founder approval, enforced in code.

Nothing is published, sent, spent or signed unless an explicit founder
approval exists for the exact content (matched by a content hash). In this
prototype every outward action is MOCKED: "publish" writes a page to the
local mock site under data/, and "send" writes a message to a local outbox.
Nothing leaves the machine, no account is created and no money moves.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel

from logbook import DecisionLog, _atomic_write_json, utc_now

OUTWARD_KINDS = ("publish", "send", "spend", "sign")
CHANNELS = ("web", "cli", "decisions_file", "api")


class ApprovalRequired(PermissionError):
    """Raised when an outward action is attempted without a matching founder approval."""


class Approval(BaseModel):
    approval_id: str
    run_id: str
    step_id: str | None = None
    subject: str
    decision: Literal["approved", "rejected"]
    approver: Literal["founder"] = "founder"
    channel: str = "web"
    reason: str = ""
    timestamp: str


def content_hash(content: str | bytes) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()[:16]


def outward_subject(kind: str, item_id: str, content: str | bytes) -> str:
    if kind not in OUTWARD_KINDS:
        raise ValueError(f"unknown outward action {kind!r}")
    return f"{kind}:{item_id}@{content_hash(content)}"


class ApprovalBook:
    def __init__(self, path: Path | str, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self._items: list[Approval] = []
        if self.path.exists():
            self._items = [Approval(**a) for a in json.loads(self.path.read_text(encoding="utf-8") or "[]")]

    def record(self, *, subject: str, decision: str, channel: str, step_id: str | None = None,
               reason: str = "") -> Approval:
        if channel not in CHANNELS:
            raise ValueError(f"unknown approval channel {channel!r}")
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        item = Approval(approval_id=f"A-{len(self._items) + 1:03d}", run_id=self.run_id, step_id=step_id,
                        subject=subject, decision=decision, channel=channel, reason=reason, timestamp=utc_now())
        self._items.append(item)
        _atomic_write_json(self.path, [a.model_dump() for a in self._items])
        return item

    def latest(self, subject: str) -> Approval | None:
        for item in reversed(self._items):
            if item.subject == subject:
                return item
        return None

    def is_approved(self, subject: str) -> bool:
        item = self.latest(subject)
        return bool(item and item.decision == "approved")

    def all(self) -> list[Approval]:
        return list(self._items)


def perform_outward_action(*, book: ApprovalBook, log: DecisionLog, kind: str, item_id: str,
                           content: str | bytes, executor: Callable[[], dict], phase: int | None = None,
                           step_id: str | None = None, agent: str = "approval") -> dict:
    """Run a (MOCKED) outward action only if the founder approved this exact content."""
    subject = outward_subject(kind, item_id, content)
    approval = book.latest(subject)
    if not approval or approval.decision != "approved":
        log.append(agent=agent, action=f"blocked_{kind}", action_type="FOUNDER_APPROVAL", phase=phase,
                   step=step_id, description=f"Blocked {kind} of {item_id}: no founder approval for this exact content",
                   approved_by=None, approval_status="PENDING", subject=subject, mocked=True)
        raise ApprovalRequired(f"Founder approval is required before '{kind}' of {item_id}.")
    result = executor()
    log.append(agent=agent, action=f"mock_{kind}", action_type="GENERATE_DELIVERABLE", phase=phase, step=step_id,
               description=f"MOCKED {kind} of {item_id} after founder approval {approval.approval_id}",
               approved_by="founder", approval_status="APPROVED", approval_channel=approval.channel,
               subject=subject, mocked=True, result=result)
    return result
