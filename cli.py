"""Command-line interface for Venture Validator.

    python cli.py new --brief demo/weak-idea.brief.yaml [--title T] [--founder NAME]
    python cli.py advance <run_id>
    python cli.py status <run_id>
    python cli.py act <run_id> --kind approve [--step 1.1] [--reason ...] ...
    python cli.py interactive <run_id>
    python cli.py script <run_id> --decisions demo/weak-idea.decisions.yaml
    python cli.py request <run_id> "make the headline clearer"
    python cli.py export <run_id> --out outputs [--prefix weak-idea] [--log decision_log.json] [--append-log]
    python cli.py demo [--dir demo] [--out outputs] [--log decision_log.json]
    python cli.py list

Every founder decision is explicit. The interactive mode never proceeds
without an answer, and the scripted founder (a decisions file written by the
team member acting as founder) stops as soon as the file has no answer for
what the pipeline is waiting for. Nothing in this module invents data.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import yaml

from export import export_run, is_output_name, merge_logs
from gates import OUTCOMES, REPEAT_LIMIT
from orchestrator import FINAL_DECISIONS, FounderActionError, Orchestrator
from steps import STEP_IDS, STEPS, steps_in_phase

Printer = Callable[[str], None]
Asker = Callable[[str], str]
LOOP_GUARD = 3            # the same pending item answered more than this many times stops the script
DEFAULT_MAX_ACTIONS = 200


# ---------------------------------------------------------------------------------------------- files
def load_data_file(path: str | Path) -> dict[str, Any]:
    """Read a YAML or JSON file that must contain a mapping."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping (key: value pairs)")
    return data


def _step_key(key: Any) -> str:
    """YAML reads an unquoted 1.1 as a float; step ids are strings."""
    if isinstance(key, float):
        return f"{key:g}" if f"{key:g}".count(".") == 1 else str(key)
    return str(key).strip()


def _yes_no(value: Any) -> Any:
    """YAML 1.1 reads Yes/No as booleans; phase-review answers are words."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return value


def normalise_decisions(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw or {})
    data["steps"] = {_step_key(k): v for k, v in (data.get("steps") or {}).items()}
    reviews = {}
    for key, value in (data.get("phase_reviews") or {}).items():
        value = dict(value or {})
        if "match" in value:
            value["match"] = _yes_no(value["match"])
        reviews[str(int(float(key)))] = value
    data["phase_reviews"] = reviews
    data["intake"] = dict(data.get("intake") or {})
    data["export_prefix"] = str(data.get("export_prefix") or "")
    data["founder"] = str(data.get("founder") or "founder")
    data["max_actions"] = int(data.get("max_actions") or DEFAULT_MAX_ACTIONS)
    data["retry_on_error"] = int(data.get("retry_on_error") or 0)
    return data


# ---------------------------------------------------------------------------------------------- display
def _last_gate(run) -> str:
    return next((str(h.get("outcome")) for h in reversed(run.history) if h.get("outcome")), "none")


def describe_run(orch: Orchestrator, run) -> list[str]:
    lines = [orch.status_line(run), f"Run {run.run_id} | {run.title} | status {run.status}"]
    if run.status_reason:
        lines.append(f"Reason: {run.status_reason}")
    if run.final_decision:
        lines.append(f"Final decision: {run.final_decision.get('decision')}")
    pending = run.pending
    if pending and run.status == "ACTIVE":
        lines.append(f"Waiting for the founder ({pending.get('kind')}): {pending.get('prompt', '')}")
        if pending.get("recommendation"):
            lines.append(f"Recommended outcome: {pending['recommendation']}")
        if pending.get("options"):
            lines.append("Options: " + ", ".join(pending["options"]))
        for question in pending.get("questions") or []:
            lines.append(f"  - {question}")
    return lines


def _gate_report_text(orch: Orchestrator, run, step_id: str, max_lines: int = 40) -> str:
    st = run.steps.get(step_id)
    rel = st.artifacts.get("gate_report.md") if st else None
    if not rel:
        return ""
    try:
        text = orch.store.read_artifact(run.run_id, rel)
    except OSError:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[:max_lines]) + ("\n..." if len(lines) > max_lines else "")


def _deliverable_lines(orch: Orchestrator, run, step_id: str) -> list[str]:
    st = run.steps.get(step_id)
    if not st:
        return []
    lines = []
    if st.summary:
        lines.append(f"Summary: {st.summary}")
    rel = st.artifacts.get("deliverable.md")
    if rel:
        lines.append(f"Deliverable: {orch.store.artifact_path(run.run_id, rel)}")
    for name, rel in st.artifacts.items():
        if name not in ("deliverable.md", "deliverable.json", "gate_report.md"):
            lines.append(f"Artifact: {name} -> {orch.store.artifact_path(run.run_id, rel)}")
    for i, question in enumerate(st.questions[:3], start=1):
        lines.append(f"Question {i}: {question}")
    if st.guardrail_flags:
        lines.append("Guardrail flags (reject with feedback to regenerate): " +
                     "; ".join(f.get("message", "") for f in st.guardrail_flags))
    return lines


def _contract_lines(contract: dict | None) -> list[str]:
    if not contract:
        return []
    lines = [f"Thresholds v{contract.get('version')} ({contract.get('status')}):"]
    for c in contract.get("criteria") or []:
        unit = f" {c.get('unit')}" if c.get("unit") else ""
        lines.append(f"  {c.get('key')}: {c.get('label')} {c.get('op')} {c.get('target'):g}{unit} [{c.get('kind')}]")
    if contract.get("window_days"):
        lines.append(f"  window: {contract['window_days']} days")
    return lines


# ---------------------------------------------------------------------------------------------- scripted founder
class ScriptedFounder:
    """Answers pending items from a decisions file. It never invents an answer or data."""

    def __init__(self, orch: Orchestrator, decisions: dict[str, Any], *, channel: str = "decisions_file",
                 out: Printer = print):
        self.orch = orch
        self.d = normalise_decisions(decisions)
        self.channel = channel
        self.out = out
        self.retries_left = self.d["retry_on_error"]

    # --- lookups
    def step_cfg(self, step_id: str, attempt: int) -> dict[str, Any] | None:
        value = self.d["steps"].get(step_id)
        if isinstance(value, list):
            return dict(value[attempt]) if attempt < len(value) and isinstance(value[attempt], dict) else None
        return dict(value) if isinstance(value, dict) else None

    def _submissions(self, run_id: str, step_id: str) -> int:
        return sum(1 for e in self.orch.log(run_id).entries
                   if e.get("agent") == "founder" and e.get("action") == "submit_data" and e.get("step") == step_id)

    def _data_for(self, run, step_id: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
        data = cfg.get("data")
        if not isinstance(data, dict) or not data:
            return None
        # A dict entry describes ONE measurement: it is submitted once per step and never re-used for a repeat.
        if isinstance(self.d["steps"].get(step_id), dict) and self._submissions(run.run_id, step_id) > 0:
            return None
        return dict(data)

    def _decide(self, step_id: str, spec: dict[str, Any]) -> dict[str, Any] | None:
        outcome = str(spec.get("outcome") or "").upper()
        if not outcome:
            return None
        action = {"kind": "decide", "step": step_id, "outcome": outcome, "reason": str(spec.get("reason") or "")}
        if spec.get("pivot_target"):
            action["pivot_target"] = _step_key(spec["pivot_target"])
        return action

    # --- the answer for one pending item
    def answer(self, run) -> tuple[dict[str, Any] | None, str]:
        pending = run.pending or {}
        kind = pending.get("kind")
        step_id = str(pending.get("step") or run.current_step)
        st = run.steps.get(step_id)
        attempt = st.attempt if st else 0
        where = f"steps.\"{step_id}\"" + (f"[{attempt}]" if isinstance(self.d["steps"].get(step_id), list) else "")

        if kind == "clarify_brief":
            clarify = self.d["intake"].get("clarify")
            if isinstance(clarify, dict) and clarify and not all(run.brief.get(k) == v for k, v in clarify.items()):
                return {"kind": "clarify_brief", "brief": dict(clarify)}, "clarify the brief"
            return None, "intake.clarify (new brief fields) - not given, or already applied"

        if kind == "retry":
            if self.retries_left > 0:
                self.retries_left -= 1
                return {"kind": "retry"}, "retry after an error"
            return None, "retry_on_error (the step failed; see the error above)"

        if kind == "phase_review":
            phase = str(pending.get("phase"))
            review = self.d["phase_reviews"].get(phase)
            if not review:
                return None, f"phase_reviews.\"{phase}\""
            action = {"kind": "phase_review", "match": str(review.get("match") or ""),
                      "issues": str(review.get("issues") or ""), "confidence": review.get("confidence")}
            if review.get("repeat_step"):
                action["repeat_step"] = _step_key(review["repeat_step"])
            return action, f"phase {phase} review"

        cfg = self.step_cfg(step_id, attempt)
        if cfg is None:
            return None, where

        if kind == "lock_thresholds":
            lock = cfg.get("lock")
            if lock is None:
                return None, f"{where}.lock"
            action = {"kind": "lock_thresholds", "step": step_id, "reason": str(cfg.get("lock_reason") or "")}
            if isinstance(lock, dict):
                action["targets"] = dict(lock.get("targets") or {})
            elif str(lock).lower() not in ("default", "true"):
                return None, f"{where}.lock must be 'default' or {{targets: ...}}"
            if cfg.get("approve_outward"):
                action["approve_outward"] = True
            return action, "lock thresholds"

        if kind == "submit_data":
            data = self._data_for(run, step_id, cfg)
            if data:
                return {"kind": "submit_data", "step": step_id, "data": data}, "submit founder-reported data"
            if isinstance(cfg.get("on_no_data"), dict):
                action = self._decide(step_id, cfg["on_no_data"])
                if action:
                    return action, "no data: explicit outcome (FOUNDER_OVERRIDE)"
            return None, f"{where}.data or {where}.on_no_data"

        if kind == "decision":
            reason = str(cfg.get("reason") or "")
            if step_id == "6.3":
                if cfg.get("final_decision"):
                    return ({"kind": "decide", "step": "6.3", "final_decision": str(cfg["final_decision"]).upper(),
                             "reason": reason}, "final decision")
                if cfg.get("decision") == "approve":
                    return {"kind": "approve", "step": "6.3", "reason": reason}, "accept the memo's recommendation"
                return None, f"{where}.final_decision"
            not_evaluable = pending.get("recommendation") is None and pending.get("status") != "PENDING_APPROVAL"
            if not_evaluable:
                for spec, label in ((cfg.get("on_no_data"), "no data: explicit outcome (FOUNDER_OVERRIDE)"),
                                    (cfg, "explicit outcome")):
                    if isinstance(spec, dict):
                        action = self._decide(step_id, spec)
                        if action:
                            return action, label
                return None, f"{where}.on_no_data (the gate is not evaluable)"
            decision = str(cfg.get("decision") or "").lower()
            if decision == "approve":
                action = {"kind": "approve", "step": step_id, "reason": reason}
                if cfg.get("acknowledge"):
                    action["acknowledge"] = True
                ids = cfg.get("outward_ids")
                if isinstance(ids, str) and ids.strip().lower() != "all":
                    action["outward_ids"] = [i.strip() for i in ids.split(",") if i.strip()]
                elif isinstance(ids, list):
                    action["outward_ids"] = [str(i) for i in ids]
                return action, "approve / accept the recommendation"
            if decision == "reject":
                return {"kind": "reject", "step": step_id, "reason": reason}, "reject with feedback"
            if decision == "select_concept":
                concept = cfg.get("concept_id")
                action = {"kind": "select_concept", "step": step_id, "reason": reason}
                if concept and str(concept).lower() != "recommended":
                    action["concept_id"] = str(concept)
                return action, "select a concept"
            action = self._decide(step_id, cfg)
            if action:
                return action, "explicit outcome"
            return None, f"{where}.decision"

        return None, f"an answer for pending item '{kind}'"

    # --- the loop
    def run(self, run_id: str) -> dict[str, Any]:
        seen: Counter = Counter()
        actions = 0
        stopped = ""
        while True:
            run = self.orch.advance(run_id)
            if run.status != "ACTIVE":
                stopped = f"run is {run.status}"
                break
            pending = run.pending
            if not pending:
                stopped = "nothing pending"
                break
            if pending.get("kind") == "retry":
                self.out(f"  ! {pending.get('prompt', '')}")
            key = _pending_key(run)
            seen[key] += 1
            if seen[key] > LOOP_GUARD:
                stopped = f"loop guard: the same pending item came back {seen[key]} times"
                break
            if actions >= self.d["max_actions"]:
                stopped = f"max_actions ({self.d['max_actions']}) reached"
                break
            action, note = self.answer(run)
            if action is None:
                stopped = f"the decisions file has no answer for this pending item (needs {note})"
                break
            action["channel"] = self.channel
            try:
                self.orch.act(run_id, action)
            except FounderActionError as exc:
                stopped = f"founder action refused: {exc}"
                self.out(f"  ! {action['kind']} on {action.get('step', '-')}: {exc}")
                break
            actions += 1
            self.out(f"  {actions:>3}. {_action_text(action)} ({note})")
        run = self.orch.store.load(run_id)
        return {"run_id": run_id, "status": run.status, "actions": actions, "stopped": stopped,
                "pending": run.pending if run.status == "ACTIVE" else None, "last_gate": _last_gate(run),
                "cost": self.orch.log(run_id).total_cost()}


def _pending_key(run) -> tuple:
    pending = run.pending or {}
    step_id = str(pending.get("step") or run.current_step)
    st = run.steps.get(step_id)
    gate = (st.gate or {}) if st else {}
    return (pending.get("kind"), step_id, pending.get("phase"), st.attempt if st else None,
            st.repeat_count if st else None, gate.get("status"), gate.get("outcome"))


def _action_text(action: dict[str, Any]) -> str:
    parts = [action["kind"]]
    if action.get("step"):
        parts.append(f"step {action['step']}")
    for key in ("outcome", "final_decision", "concept_id", "match", "confidence"):
        if action.get(key) not in (None, ""):
            parts.append(f"{key}={action[key]}")
    if action.get("targets"):
        parts.append(f"targets={action['targets']}")
    if action.get("data"):
        parts.append(f"data fields={sorted(action['data'])}")
    if action.get("approve_outward"):
        parts.append("approve_outward")
    if action.get("reason"):
        parts.append(f"reason: {action['reason'][:80]}")
    return " ".join(parts)


def run_script(orch: Orchestrator, run_id: str, decisions: dict[str, Any], *, out: Printer = print,
               channel: str = "decisions_file") -> dict[str, Any]:
    result = ScriptedFounder(orch, decisions, channel=channel, out=out).run(run_id)
    run = orch.store.load(run_id)
    out(f"Stopped: {result['stopped']}")
    for line in describe_run(orch, run):
        out(line)
    out(f"Actions applied: {result['actions']} | Last gate: {result['last_gate']} | "
        f"Total model cost: ${result['cost']:.4f}")
    return result


# ---------------------------------------------------------------------------------------------- interactive founder
class QuitInteractive(Exception):
    pass


def _ask(ask: Asker, out: Printer, prompt: str, *, choices: dict[str, str] | None = None,
         allow_blank: bool = False) -> str:
    """Ask until the founder gives an explicit answer. 'q' quits (the run state stays saved)."""
    while True:
        answer = ask(prompt).strip()
        if answer.lower() in ("q", "quit", "exit"):
            raise QuitInteractive()
        if not answer and not allow_blank:
            out("An explicit answer is required (or q to quit).")
            continue
        if choices is not None:
            key = answer.lower()
            if key in choices:
                return choices[key]
            out("Choose one of: " + ", ".join(sorted(set(choices))))
            continue
        return answer


def _ask_number(ask: Asker, out: Printer, prompt: str, *, allow_blank: bool = True) -> float | None:
    while True:
        answer = _ask(ask, out, prompt, allow_blank=allow_blank)
        if not answer:
            return None
        try:
            return float(answer.replace(",", ""))
        except ValueError:
            out("Enter a number.")


def _interactive_action(orch: Orchestrator, run, ask: Asker, out: Printer) -> dict[str, Any]:
    pending = run.pending or {}
    kind = pending.get("kind")
    step_id = str(pending.get("step") or run.current_step)
    st = run.steps.get(step_id)
    yes_no = {"y": True, "yes": True, "n": False, "no": False}

    if kind == "retry":
        _ask(ask, out, "Retry the step? [r]etry / [q]uit: ", choices={"r": "r", "retry": "r"})
        return {"kind": "retry"}

    if kind == "clarify_brief":
        _ask(ask, out, "[c]larify the brief / [q]uit: ", choices={"c": "c", "clarify": "c"})
        brief = {}
        for key in ("idea", "customer", "why_you", "jurisdiction", "budget", "time", "evidence"):
            value = _ask(ask, out, f"{key} (now: {str(run.brief.get(key) or '-')[:80]}; blank keeps it): ",
                         allow_blank=True)
            if value:
                brief[key] = value
        return {"kind": "clarify_brief", "brief": brief}

    if kind == "phase_review":
        summary = (pending.get("summary") or {}).get("summary") if isinstance(pending.get("summary"), dict) else ""
        if summary:
            out(f"Phase summary: {summary}")
        match = _ask(ask, out, "Do these deliverables match what you need? (Yes / Partly / No): ",
                     choices={"yes": "Yes", "y": "Yes", "partly": "Partly", "p": "Partly", "no": "No", "n": "No"})
        issues = _ask(ask, out, "Is anything unclear, missing or wrong? (type 'none' if nothing): ")
        issues = "" if issues.lower() == "none" else issues
        confidence = _ask(ask, out, "Rate your confidence to proceed, 1-5: ",
                          choices={str(i): str(i) for i in range(1, 6)})
        action = {"kind": "phase_review", "match": match, "issues": issues, "confidence": int(confidence)}
        if match != "Yes" or int(confidence) <= 2:
            ids = [s.step_id for s in steps_in_phase(int(pending.get("phase")))]
            target = _ask(ask, out, f"Which step should be repeated? ({', '.join(ids)}): ",
                          choices={i: i for i in ids})
            action["repeat_step"] = target
        return action

    if kind == "lock_thresholds":
        for line in _contract_lines(pending.get("contract")):
            out(line)
        outward = pending.get("outward") or []
        choice = _ask(ask, out, "[l]ock as proposed / [t]une targets, then lock / [s]kip the step with a reason / [q]uit: ",
                      choices={"l": "lock", "lock": "lock", "t": "tune", "tune": "tune", "s": "skip", "skip": "skip"})
        if choice == "skip":
            outcome = _ask(ask, out, f"Outcome ({'/'.join(OUTCOMES)}): ", choices={o.lower(): o for o in OUTCOMES})
            reason = _ask(ask, out, "Reason (logged as FOUNDER_OVERRIDE): ")
            return {"kind": "decide", "step": step_id, "outcome": outcome, "reason": reason}
        action: dict[str, Any] = {"kind": "lock_thresholds", "step": step_id}
        if choice == "tune":
            targets = {}
            for c in (pending.get("contract") or {}).get("criteria") or []:
                value = _ask_number(ask, out, f"{c.get('key')} target (now {c.get('target'):g}; blank keeps it): ")
                if value is not None:
                    targets[c["key"]] = value
            action["targets"] = targets
        if outward:
            names = ", ".join(o.get("item_id", "?") for o in outward)
            if _ask(ask, out, f"Also approve MOCKED publishing of {names} to the local mock site? [y/n]: ",
                    choices=yes_no):
                action["approve_outward"] = True
        return action

    if kind == "submit_data":
        for field in pending.get("fields") or []:
            out(f"  {field.get('key')}: {field.get('label')} ({field.get('type')})"
                f"{' - ' + field['help'] if field.get('help') else ''}")
        choice = _ask(ask, out, "[s]ubmit measured data / [o]utcome without data (FOUNDER_OVERRIDE) / [q]uit: ",
                      choices={"s": "submit", "submit": "submit", "o": "override", "outcome": "override"})
        if choice == "override":
            outcome = _ask(ask, out, f"Outcome ({'/'.join(OUTCOMES)}): ", choices={o.lower(): o for o in OUTCOMES})
            reason = _ask(ask, out, "Reason (logged as FOUNDER_OVERRIDE): ")
            return {"kind": "decide", "step": step_id, "outcome": outcome, "reason": reason}
        data: dict[str, Any] = {}
        for field in pending.get("fields") or []:
            value = _ask(ask, out, f"{field.get('label')} [{field.get('key')}] (blank if you did not measure it): ",
                         allow_blank=True)
            if not value:
                continue
            if field.get("type") == "json":
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    out("Not valid JSON; submitted as text.")
            data[field["key"]] = value
        return {"kind": "submit_data", "step": step_id, "data": data}

    if kind == "decision":
        report = _gate_report_text(orch, run, step_id)
        if report:
            out(report)
        for line in _deliverable_lines(orch, run, step_id):
            out(line)
        if step_id == "6.3":
            rec = (st.output.get("recommendation") if st else None) or "none"
            out(f"Memo recommendation: {rec}")
            final = _ask(ask, out, "Your final decision (PERSEVERE / PIVOT / STOP): ",
                         choices={d.lower(): d for d in FINAL_DECISIONS})
            reason = _ask(ask, out, "Reason (required if it differs from the memo; blank otherwise): ",
                          allow_blank=True)
            return {"kind": "decide", "step": "6.3", "final_decision": final, "reason": reason}
        options = pending.get("options") or ["approve", "decide"]
        menu = {"a": "approve", "approve": "approve", "d": "decide", "decide": "decide"}
        labels = ["[a]pprove / accept the recommendation"]
        if "reject" in options:
            menu.update({"r": "reject", "reject": "reject"})
            labels.append("[r]eject with feedback")
        labels.append("[d]ecide another outcome")
        if "select_concept" in options:
            menu.update({"c": "select_concept", "select": "select_concept"})
            labels.append("[c]hoose a concept")
        choice = _ask(ask, out, " / ".join(labels) + " / [q]uit: ", choices=menu)
        if choice == "reject":
            return {"kind": "reject", "step": step_id, "reason": _ask(ask, out, "What should change? ")}
        if choice == "decide":
            outcome = _ask(ask, out, f"Outcome ({'/'.join(OUTCOMES)}): ", choices={o.lower(): o for o in OUTCOMES})
            action = {"kind": "decide", "step": step_id, "outcome": outcome,
                      "reason": _ask(ask, out, "Reason (logged; required for an override): ", allow_blank=True)}
            if outcome == "PIVOT_BACK":
                earlier = STEP_IDS[:STEP_IDS.index(step_id)] if step_id in STEP_IDS else []
                action["pivot_target"] = _ask(ask, out, f"Return to which step? ({', '.join(earlier)}): ",
                                              choices={s: s for s in earlier})
            return action
        action = {"kind": choice, "step": step_id}
        if choice == "select_concept":
            concepts = (st.output.get("concepts") if st else None) or []
            for c in concepts:
                out(f"  {c.get('id')}: {c.get('name')} (rank {c.get('rank', '-')})")
            ids = {str(c.get("id")).lower(): str(c.get("id")) for c in concepts}
            if ids:
                action["concept_id"] = _ask(ask, out, "Concept id: ", choices=ids)
            action["reason"] = _ask(ask, out, "Reason (required if not the top-ranked concept): ", allow_blank=True)
        ack = (st.output.get("requires_acknowledgment") if st else None)
        if ack:
            if not _ask(ask, out, f"Do you acknowledge: {ack} [y/n]: ", choices=yes_no):
                raise FounderActionError("Approval needs the acknowledgment; reject with feedback instead.")
            action["acknowledge"] = True
        outward = [o for o in ((st.output.get("outward") if st else None) or []) if o.get("when", "on_approve") == "on_approve"]
        if outward:
            approved = []
            for item in outward:
                if _ask(ask, out, f"Approve MOCKED {item.get('kind')} of {item.get('item_id')} "
                                  f"(local mock site/outbox only)? [y/n]: ", choices=yes_no):
                    approved.append(item.get("item_id"))
            action["outward_ids"] = approved
        return action

    raise FounderActionError(f"Unknown pending item {kind!r}.")


def interactive(orch: Orchestrator, run_id: str, *, ask: Asker = input, out: Printer = print) -> int:
    try:
        while True:
            run = orch.advance(run_id)
            out("")
            for line in describe_run(orch, run):
                out(line)
            if run.status != "ACTIVE" or not run.pending:
                out(f"Total model cost: ${orch.log(run_id).total_cost():.4f}")
                return 0
            try:
                action = _interactive_action(orch, run, ask, out)
                action["channel"] = "cli"
                orch.act(run_id, action)
            except FounderActionError as exc:
                out(f"Not allowed: {exc}")
    except (QuitInteractive, KeyboardInterrupt, EOFError):
        out("")
        out(f"Stopped. The run is saved; resume with: python cli.py interactive {run_id}")
        return 0


# ---------------------------------------------------------------------------------------------- demo
def run_demo(orch: Orchestrator, demo_dir: Path | str, out_dir: Path | str, log_path: Path | str, *,
             clean: bool = True, out: Printer = print) -> list[dict[str, Any]]:
    demo_dir, out_dir = Path(demo_dir), Path(out_dir)
    pairs = []
    for brief_path in sorted(demo_dir.glob("*.brief.yaml")):
        name = brief_path.name[: -len(".brief.yaml")]
        decisions_path = demo_dir / f"{name}.decisions.yaml"
        if decisions_path.exists():
            pairs.append((name, brief_path, decisions_path))
        else:
            out(f"Skipping {brief_path.name}: no {decisions_path.name}")
    if not pairs:
        out(f"No demo pairs (<name>.brief.yaml + <name>.decisions.yaml) in {demo_dir}")
        return []
    prefixes = Counter(str(load_data_file(p).get("export_prefix") or "") for _, _, p in pairs)
    clashes = [p or '""' for p, n in prefixes.items() if n > 1]
    if clashes:
        out(f"Warning: several demos share export_prefix {', '.join(clashes)}; later files overwrite earlier ones.")
    # Export into a staging folder first. outputs/ and the root log are replaced only when every demo run
    # finished (COMPLETED or STOPPED), so a network outage mid-run can never wipe a committed demo.
    staging = Path(tempfile.mkdtemp(prefix="vv-demo-"))
    staged_out, staged_log = staging / "outputs", staging / "decision_log.json"
    results = []
    run_ids = []
    for name, brief_path, decisions_path in pairs:
        brief = load_data_file(brief_path)
        decisions = normalise_decisions(load_data_file(decisions_path))
        out(f"=== Demo '{name}' (founder: {decisions['founder']}) ===")
        run = orch.create_run(brief, founder=decisions["founder"], title=brief.get("title"))
        out(f"Run {run.run_id} | {(run.intake or {}).get('score_line', '')}")
        result = run_script(orch, run.run_id, decisions, out=out)
        files = export_run(orch.store, run.run_id, staged_out, prefix=decisions["export_prefix"])
        out(f"Staged {len(files)} files")
        result.update({"name": name, "files": [Path(f).name for f in files]})
        results.append(result)
        run_ids.append(run.run_id)
    count = merge_logs(orch.store, run_ids, staged_log)
    for r in results:
        out(f"  {r['name']}: {r['status']} | last gate {r['last_gate']} | cost ${r['cost']:.4f} | {r['stopped']}")
    if not all(r.get("status") in ("COMPLETED", "STOPPED") for r in results):
        out(f"Not every demo run finished: {out_dir} and {log_path} were left unchanged. "
            f"Staged export: {staging}. Resume with `cli.py script <run_id>` and export again.")
        return results
    if clean and out_dir.is_dir():
        # Remove earlier exports so outputs/ only holds files from this demo run.
        for path in out_dir.iterdir():
            if path.is_file() and is_output_name(path.name):
                path.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in staged_out.iterdir() if staged_out.exists() else []:
        if path.is_file():
            shutil.copy2(path, out_dir / path.name)
    shutil.copy2(staged_log, log_path)
    out(f"Exported to {out_dir}; wrote {count} decision-log entries from {len(run_ids)} demo run(s) to {log_path}")
    return results


# ---------------------------------------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="Venture Validator command line")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create a run from a brief (YAML or JSON)")
    p.add_argument("--brief", required=True)
    p.add_argument("--title")
    p.add_argument("--founder", default="founder")

    for name, text in (("advance", "run system work until the founder is needed"), ("status", "show a run"),
                       ("interactive", "answer pending items at the prompt")):
        sp = sub.add_parser(name, help=text)
        sp.add_argument("run_id")

    p = sub.add_parser("act", help="apply one founder action")
    p.add_argument("run_id")
    p.add_argument("--kind", required=True,
                   choices=["approve", "reject", "decide", "select_concept", "skip", "lock_thresholds", "submit_data",
                            "change_threshold", "phase_review", "clarify_brief", "retry"])
    p.add_argument("--step")
    p.add_argument("--outcome", choices=list(OUTCOMES))
    p.add_argument("--pivot-target")
    p.add_argument("--reason", default="")
    p.add_argument("--data", help="JSON: founder data (submit_data), brief fields (clarify_brief), or "
                                  '{"match": "Yes", "confidence": 4, "issues": ""} (phase_review)')
    p.add_argument("--targets", help='JSON: {"criterion_key": target}')
    p.add_argument("--approve-outward", action="store_true")
    p.add_argument("--acknowledge", action="store_true")
    p.add_argument("--concept-id")
    p.add_argument("--final-decision", choices=list(FINAL_DECISIONS))
    p.add_argument("--outward-ids", help="comma-separated item ids, or 'all'")

    p = sub.add_parser("script", help="apply a decisions file (scripted founder)")
    p.add_argument("run_id")
    p.add_argument("--decisions", required=True)

    p = sub.add_parser("request", help="send a free-text request (guardrails apply)")
    p.add_argument("run_id")
    p.add_argument("text")

    p = sub.add_parser("export", help="export a run to outputs/")
    p.add_argument("run_id")
    p.add_argument("--out", default="outputs")
    p.add_argument("--prefix", default="")
    p.add_argument("--log", help="copy the run's decision log here")
    p.add_argument("--append-log", action="store_true", help="merge into the log file instead of replacing it")

    p = sub.add_parser("demo", help="run every demo/<name>.brief.yaml with its decisions file and export")
    p.add_argument("--dir", default="demo")
    p.add_argument("--out", default="outputs")
    p.add_argument("--log", default="decision_log.json")
    p.add_argument("--keep-existing", action="store_true", help="do not remove earlier exported files first")

    sub.add_parser("list", help="list runs")
    return parser


def _json_arg(value: str | None, name: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--{name} is not valid JSON: {exc}") from None


def _act_from_args(args) -> dict[str, Any]:
    action: dict[str, Any] = {"kind": args.kind, "channel": "cli", "reason": args.reason}
    if args.step:
        action["step"] = args.step
    if args.outcome:
        action["outcome"] = args.outcome
    if args.pivot_target:
        action["pivot_target"] = args.pivot_target
    data = _json_arg(args.data, "data")
    if data is not None:
        if args.kind == "clarify_brief":
            action["brief"] = data
        elif args.kind == "phase_review":
            action.update({k: v for k, v in data.items() if k not in ("kind", "channel")})
        else:
            action["data"] = data
    targets = _json_arg(args.targets, "targets")
    if targets:
        action["targets"] = targets
    if args.approve_outward:
        action["approve_outward"] = True
    if args.acknowledge:
        action["acknowledge"] = True
    if args.concept_id:
        action["concept_id"] = args.concept_id
    if args.final_decision:
        action["final_decision"] = args.final_decision
    if args.outward_ids and args.outward_ids.strip().lower() != "all":
        action["outward_ids"] = [i.strip() for i in args.outward_ids.split(",") if i.strip()]
    return action


def main(argv: list[str] | None = None, *, orch: Orchestrator | None = None, out: Printer | None = None,
         ask: Asker | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    out = out or print
    args = build_parser().parse_args(argv)
    orch = orch or Orchestrator()

    def need_run(run_id: str):
        if not orch.store.exists(run_id):
            raise SystemExit(f"No run {run_id!r} in {orch.store.root}")
        return orch.store.load(run_id)

    try:
        if args.command == "new":
            brief = load_data_file(args.brief)
            run = orch.create_run(brief, founder=args.founder, title=args.title)
            out(f"Created run {run.run_id}")
            out((run.intake or {}).get("score_line", "Input quality: not scored"))
            for line in describe_run(orch, run):
                out(line)
            out(f"Next: python cli.py advance {run.run_id}   (or: interactive {run.run_id})")
        elif args.command == "advance":
            need_run(args.run_id)
            run = orch.advance(args.run_id)
            for line in describe_run(orch, run):
                out(line)
            if run.pending and run.pending.get("kind") == "decision":
                report = _gate_report_text(orch, run, str(run.pending.get("step")))
                if report:
                    out(report)
                for line in _deliverable_lines(orch, run, str(run.pending.get("step"))):
                    out(line)
            elif run.pending and run.pending.get("kind") == "lock_thresholds":
                for line in _contract_lines(run.pending.get("contract")):
                    out(line)
        elif args.command == "status":
            run = need_run(args.run_id)
            for line in describe_run(orch, run):
                out(line)
            out(f"Founder: {run.founder} | Last gate: {_last_gate(run)} | "
                f"Total model cost: ${orch.log(run.run_id).total_cost():.4f}")
            out("| Step | Name | Status | Outcome | Attempt | Repeats |")
            out("|---|---|---|---|---|---|")
            for meta in STEPS:
                st = run.steps.get(meta.step_id)
                if st:
                    out(f"| {meta.step_id} | {meta.name} | {st.status} | {st.outcome or '-'} | {st.attempt} | "
                        f"{st.repeat_count}/{REPEAT_LIMIT} |")
        elif args.command == "act":
            need_run(args.run_id)
            run = orch.act(args.run_id, _act_from_args(args))
            for line in describe_run(orch, run):
                out(line)
            out(f"Next: python cli.py advance {args.run_id}")
        elif args.command == "interactive":
            need_run(args.run_id)
            return interactive(orch, args.run_id, ask=ask or input, out=out)
        elif args.command == "script":
            need_run(args.run_id)
            result = run_script(orch, args.run_id, load_data_file(args.decisions), out=out)
            # Stopping because the file has no answer is normal; a refused action or the loop guard is not.
            return 1 if result["stopped"].startswith(("founder action refused", "loop guard")) else 0
        elif args.command == "request":
            need_run(args.run_id)
            result = orch.request(args.run_id, args.text, channel="cli")
            out(("REFUSED: " if result["refused"] else "") + result["message"])
        elif args.command == "export":
            need_run(args.run_id)
            files = export_run(orch.store, args.run_id, args.out, prefix=args.prefix, log_path=args.log,
                               append_log=args.append_log)
            for path in files:
                out(f"wrote {path}")
            out(f"{len(files)} files written")
        elif args.command == "demo":
            results = run_demo(orch, args.dir, args.out, args.log, clean=not args.keep_existing, out=out)
            return 0 if results else 1
        elif args.command == "list":
            for run in orch.store.list():
                out(f"{run.run_id} | {run.status} | step {run.current_step} | {run.title}")
    except FounderActionError as exc:
        out(f"Not allowed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
