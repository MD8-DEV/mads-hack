"""Append-only decision log: one JSON entry per agent action.

Every entry carries the keys the submission format requires
(timestamp, agent, action, sources, model, cost, approved_by) plus the
pipeline fields from the Venture Validator spec (log_id, action_type, phase,
step, thresholds, result, gate outcome, approval status, override).
Past entries are never edited; a correction is a new entry.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")
ACTION_TYPES = (
    "GENERATE_DELIVERABLE", "ANALYZE_DATA", "RESEARCH", "RUN_TESTS", "GATE_DECISION",
    "FOUNDER_APPROVAL", "THRESHOLD_SET", "THRESHOLD_CHANGE", "FOUNDER_OVERRIDE", "PIVOT", "STOP",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class DecisionLog:
    def __init__(self, path: Path | str, run_id: str | None = None):
        self.path = Path(path)
        self.run_id = run_id
        self._lock = threading.Lock()
        self._entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        if not isinstance(data, list):
            raise ValueError(f"{self.path} must contain a JSON array")
        return data

    @property
    def entries(self) -> list[dict]:
        return [dict(e) for e in self._entries]

    def _next_id(self, phase: int | None, step: str | None) -> str:
        minor = str(step).split(".")[-1] if step else "0"
        return f"P{phase or 0}-S{minor}-{len(self._entries) + 1:04d}"

    def append(self, *, agent: str, action: str, action_type: str, phase: int | None = None,
               step: str | None = None, description: str = "", sources: list[str] | None = None,
               source_details: list[dict] | None = None, model: str | None = None,
               cost: float | None = 0.0, approved_by: str | None = None,
               tokens_in: int | None = None, tokens_out: int | None = None, **extra: Any) -> dict:
        if action_type not in ACTION_TYPES:
            raise ValueError(f"unknown action_type {action_type!r}")
        if approved_by not in (None, "founder"):
            raise ValueError("approved_by must be 'founder' or None")
        urls = [s for s in (sources or []) if isinstance(s, str) and s.startswith(("http://", "https://"))]
        with self._lock:
            entry: dict[str, Any] = {
                "log_id": self._next_id(phase, step),
                "timestamp": utc_now(),
                "run_id": self.run_id,
                "agent": agent,
                "action": action,
                "action_type": action_type,
                "phase": phase,
                "step": step,
                "description": description,
                "sources": _dedupe(urls),
                "source_details": source_details or [],
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost": round(float(cost or 0.0), 6),
                "approved_by": approved_by,
            }
            for key, value in extra.items():
                if key not in entry:
                    entry[key] = value
            self._entries.append(entry)
            _atomic_write_json(self.path, self._entries)
        return dict(entry)

    def total_cost(self) -> float:
        return round(sum(float(e.get("cost") or 0.0) for e in self._entries), 6)


def validate_entries(entries: list[dict]) -> list[str]:
    """Return a list of problems; empty means every entry has the required keys and types."""
    problems: list[str] = []
    for index, entry in enumerate(entries):
        for key in REQUIRED_KEYS:
            if key not in entry:
                problems.append(f"entry {index}: missing {key}")
        if not isinstance(entry.get("action"), str):
            problems.append(f"entry {index}: action must be a string")
        if not isinstance(entry.get("sources"), list):
            problems.append(f"entry {index}: sources must be a list")
        if entry.get("model") is not None and not isinstance(entry.get("model"), str):
            problems.append(f"entry {index}: model must be a string or null")
        if not isinstance(entry.get("cost"), (int, float)):
            problems.append(f"entry {index}: cost must be a number")
        if entry.get("approved_by") not in (None, "founder"):
            problems.append(f"entry {index}: approved_by must be 'founder' or null")
    return problems
