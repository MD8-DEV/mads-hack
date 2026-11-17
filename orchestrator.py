"""Orchestrator: runs the six-phase pipeline step by step, with a gate after every step.

The orchestrator owns state transitions and the decision log of gates and
founder decisions. Role agents (agents/*) generate deliverables, gates.py
applies locked thresholds, approval.py enforces founder approval for anything
outward. The pipeline pauses whenever it needs the founder:

  lock_thresholds  - approve (and optionally tune) thresholds BEFORE data is collected
  submit_data      - founder-reported evidence for an E gate
  decision         - approve / reject a deliverable, accept the recommended outcome,
                     or override it (logged as FOUNDER_OVERRIDE with a reason)
  phase_review     - the three phase-exit questions
  clarify_brief    - the brief scored 0-3 on the Founder Answer Rubric, or needs a category check
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import asdict
from typing import Any

import guardrails
from agents import gatekeeper, rubric_scorer
from agents.base import StepContext
from approval import ApprovalBook, ApprovalRequired, content_hash, outward_subject, perform_outward_action
from config import Settings, get_settings
from evidence import EvidenceLedger
from gates import (GO, OUTCOMES, PIVOT_BACK, READY, REPEAT, REPEAT_LIMIT, STOP, Contract, GateError, GateResult,
                   approval_gate, evaluate, format_pct, lock_contract, new_version)
from llm import BaseLLM, LLMError, get_llm
from logbook import DecisionLog, utc_now
from phases.base import Observation, StepOutput
from steps import PHASE_NAMES, STEP_IDS, STEPS_BY_ID, get_handler, is_last_in_phase, next_step_id, steps_in_phase
from store import (AWAITING_DECISION, AWAITING_LOCK, COLLECTING, DONE, NEW, READY_TO_GENERATE, SUPERSEDED,
                   WAITING_FOR_DATA, Run, RunStore, StepState)

GENERATED = "GENERATED"
FINAL_DECISIONS = ("PERSEVERE", "PIVOT", "STOP")


class FounderActionError(ValueError):
    """A founder action the rules do not allow. The message explains why."""


class Orchestrator:
    def __init__(self, store: RunStore | None = None, llm: BaseLLM | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.store = store or RunStore(self.settings.runs_dir)
        self.llm = llm or get_llm(self.settings)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()
        self._logs: dict[str, DecisionLog] = {}
        self._ledgers: dict[str, EvidenceLedger] = {}
        self._books: dict[str, ApprovalBook] = {}

    # ------------------------------------------------------------------ plumbing
    def lock(self, run_id: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(run_id, threading.RLock())

    def log(self, run_id: str) -> DecisionLog:
        if run_id not in self._logs:
            self._logs[run_id] = self.store.log(run_id)
        return self._logs[run_id]

    def ledger(self, run_id: str) -> EvidenceLedger:
        if run_id not in self._ledgers:
            self._ledgers[run_id] = self.store.ledger(run_id)
        return self._ledgers[run_id]

    def approvals(self, run_id: str) -> ApprovalBook:
        if run_id not in self._books:
            self._books[run_id] = self.store.approvals(run_id)
        return self._books[run_id]

    def _ctx(self, run: Run, meta, st: StepState | None) -> StepContext:
        return StepContext(
            run=run, meta=meta, store=self.store, llm=self.llm, log=self.log(run.run_id),
            ledger=self.ledger(run.run_id), approvals=self.approvals(run.run_id), settings=self.settings,
            contract=Contract(**st.contract) if st and st.contract else None,
            feedback=st.feedback if st else None, repeat_count=st.repeat_count if st else 0,
            attempt=st.attempt if st else 0)

    @staticmethod
    def _brief_text(brief: dict[str, Any]) -> str:
        parts = []
        for key in ("title", "idea", "customer", "why_you", "jurisdiction", "budget", "time", "evidence", "values", "notes"):
            value = brief.get(key)
            if value:
                parts.append(f"{key}: {value}")
        for key, value in brief.items():
            if key not in ("title", "idea", "customer", "why_you", "jurisdiction", "budget", "time", "evidence",
                           "values", "notes") and isinstance(value, str) and value:
                parts.append(f"{key}: {value}")
        return "\n".join(parts)

    # ------------------------------------------------------------------ status helpers
    def status_line(self, run: Run) -> str:
        meta = STEPS_BY_ID.get(run.current_step)
        st = run.steps.get(run.current_step)
        last = next((h.get("outcome") for h in reversed(run.history) if h.get("outcome")), None)
        if meta is None or st is None:
            return f"[{run.status}]"
        return (f"[Phase {meta.phase}: {meta.phase_name} | Step {meta.step_id} | Repeat {st.repeat_count}/{REPEAT_LIMIT} "
                f"| Last gate: {last or 'none'}]")

    # ------------------------------------------------------------------ intake
    def create_run(self, brief: dict[str, Any], *, founder: str = "founder", title: str | None = None,
                   run_id: str | None = None) -> Run:
        run = self.store.create(brief, title=title, founder=founder, step_ids=STEP_IDS, run_id=run_id)
        with self.lock(run.run_id):
            self._intake(run)
            self.store.save(run)
        return run

    def _intake(self, run: Run) -> None:
        log = self.log(run.run_id)
        text = self._brief_text(run.brief)
        ctx = self._ctx(run, None, None)
        category = guardrails.check_idea(text)
        request_flags = guardrails.check_request(text)
        rubric = rubric_scorer.score_input(ctx, text, kind="venture brief (idea, customer, founder fit, constraints, evidence)")
        run.intake = {"rubric": rubric, "score_line": rubric_scorer.format_score(rubric),
                      "category_violations": [v.as_dict() for v in category],
                      "request_flags": [v.as_dict() for v in request_flags], "checked_at": utc_now()}
        if category:
            reason = "; ".join(v.message for v in category)
            run.status, run.status_reason = "STOPPED", f"Excluded product category. {reason}"
            run.pending = None
            log.append(agent="guardrails", action="excluded_product_category", action_type="STOP", phase=0, step="0.0",
                       description=f"Intake refused: {reason}", approved_by=None, outcome="stop", gate_outcome=STOP,
                       result={"violations": [v.as_dict() for v in category]})
            run.messages.append({"role": "system", "at": utc_now(), "refused": True,
                                 "text": "This idea is outside what the pipeline may work on. " + reason})
            return
        if request_flags:
            refusal = guardrails.refusal_message(request_flags)
            run.messages.append({"role": "system", "at": utc_now(), "refused": True, "text": refusal})
            log.append(agent="guardrails", action="refuse_request", action_type="ANALYZE_DATA", phase=0, step="0.0",
                       description="Part of the brief asked for something the system never does; that part is refused",
                       approved_by=None, result={"violations": [v.as_dict() for v in request_flags]})
        if rubric.get("excluded_category"):
            run.pending = {"kind": "clarify_brief", "step": "0.0",
                           "prompt": (f"The intake check thinks this may be an excluded product ({rubric['excluded_category']}): "
                                      f"{rubric.get('excluded_reason') or ''} Clarify the idea so it is clearly a digital product "
                                      "outside the excluded categories, or stop here."),
                           "questions": rubric.get("follow_up_questions", [])}
            return
        if rubric.get("decision") == "BLOCK":
            run.pending = {"kind": "clarify_brief", "step": "0.0",
                           "prompt": (f"{rubric_scorer.format_score(rubric)}. The brief is too thin to start: add the "
                                      "missing details before Step 1.1."),
                           "questions": rubric.get("follow_up_questions", [])}
            return
        run.pending = None

    # ------------------------------------------------------------------ main loop
    def advance(self, run_id: str, max_ticks: int = 80) -> Run:
        """Run system work until the pipeline needs the founder, stops, or completes."""
        with self.lock(run_id):
            run = self.store.load(run_id)
            for _ in range(max_ticks):
                if run.status != "ACTIVE" or run.pending:
                    break
                try:
                    progressed = self._tick(run)
                except LLMError as exc:
                    self._block(run, f"No model answered during step {run.current_step}: {exc}")
                    progressed = False
                except Exception as exc:  # noqa: BLE001 - never crash the app; surface the error and allow a retry
                    self._block(run, f"Error in step {run.current_step}: {type(exc).__name__}: {exc}",
                                detail=traceback.format_exc(limit=6))
                    progressed = False
                self.store.save(run)
                if not progressed:
                    break
            self.store.save(run)
            return run

    def _block(self, run: Run, message: str, detail: str = "") -> None:
        run.pending = {"kind": "retry", "step": run.current_step, "prompt": message + " You can retry the step.",
                       "detail": detail[-2000:]}
        run.messages.append({"role": "system", "at": utc_now(), "error": True, "text": message})

    def _tick(self, run: Run) -> bool:
        step_id = run.current_step
        meta = STEPS_BY_ID[step_id]
        st = run.steps[step_id]
        handler = get_handler(meta)
        ctx = self._ctx(run, meta, st)

        if st.status == NEW:
            if meta.has_evidence_gate and meta.lock_first and not (st.contract and Contract(**st.contract).locked):
                self._propose_contract(run, meta, st, handler, ctx)
                return True
            self._generate(run, meta, st, handler, ctx)
            return True
        if st.status == READY_TO_GENERATE:
            self._generate(run, meta, st, handler, ctx)
            return True
        if st.status == GENERATED:
            return self._after_generate(run, meta, st, handler, ctx)
        if st.status == COLLECTING:
            return self._collect(run, meta, st, handler, ctx)
        if st.status in (AWAITING_LOCK, WAITING_FOR_DATA, AWAITING_DECISION):
            self._set_pending(run, meta, st, handler)
            return False
        if st.status in (DONE, SUPERSEDED):
            nxt = next_step_id(step_id)
            if nxt:
                run.current_step = nxt
                return True
            run.status = "COMPLETED"
            return False
        return False

    # ------------------------------------------------------------------ generation
    def _generate(self, run: Run, meta, st: StepState, handler, ctx: StepContext) -> None:
        out: StepOutput = handler.generate(ctx)
        flags = guardrails.check_marketing(out.marketing_text) if out.marketing_text else []
        if flags:
            # One regeneration with explicit feedback; marketing copy may never carry fake proof or urgency.
            ctx.feedback = ((ctx.feedback or "") + "\nGUARDRAIL: remove these from all copy: " +
                            "; ".join(f"{v.message} (found: '{v.match}')" for v in flags)).strip()
            self.log(run.run_id).append(
                agent="guardrails", action="flag_marketing_copy", action_type="ANALYZE_DATA", phase=meta.phase,
                step=meta.step_id, description="Generated copy broke a marketing rule; regenerating once",
                approved_by=None, result={"violations": [v.as_dict() for v in flags]})
            out = handler.generate(ctx)
            flags = guardrails.check_marketing(out.marketing_text) if out.marketing_text else []
        st.guardrail_flags = [v.as_dict() for v in flags]

        claims, problems = ctx.ledger.verify_claims(out.claims)
        st.claim_problems = problems
        attempt = st.attempt
        rid, sid = run.run_id, meta.step_id
        md = self._render_deliverable(run, meta, st, out, claims, ctx.ledger)
        st.artifacts = {
            "deliverable.md": self.store.write_artifact(rid, sid, attempt, "deliverable.md", md),
            "deliverable.json": self.store.write_artifact(rid, sid, attempt, "deliverable.json", {
                "step": sid, "attempt": attempt, "title": out.title, "summary": out.summary, "data": out.data,
                "claims": [c.model_dump() for c in claims], "claim_problems": problems,
                "guardrail_flags": st.guardrail_flags, "sources": out.sources}),
        }
        for name, content in out.files.items():
            st.artifacts[name] = self.store.write_artifact(rid, sid, attempt, name, content)
        st.output = dict(out.data)
        st.output.setdefault("title", out.title)
        st.summary = out.summary
        st.questions = list(out.questions)[:3]
        if out.observation is not None:
            st.observation = asdict(out.observation)
        st.status = GENERATED
        st.updated_at = utc_now()
        st.history.append({"event": "generated", "attempt": attempt, "at": utc_now(), "title": out.title})

    def _after_generate(self, run: Run, meta, st: StepState, handler, ctx: StepContext) -> bool:
        if meta.has_evidence_gate:
            contract = Contract(**st.contract) if st.contract else None
            if contract is None or contract.status == "INVALIDATED":
                self._propose_contract(run, meta, st, handler, ctx)
                return True
            if not contract.locked:
                st.status = AWAITING_LOCK
                return True
            st.status = COLLECTING
            return True
        # Approval-only step: the deliverable waits for the founder.
        gate = approval_gate(meta.step_id, list(meta.gate_types), approved=None, repeat_count=st.repeat_count,
                             pivot_target=meta.pivot_target)
        self._record_gate(run, meta, st, gate, None, ctx, log_it=False)
        st.status = AWAITING_DECISION
        return True

    # ------------------------------------------------------------------ thresholds
    def _propose_contract(self, run: Run, meta, st: StepState, handler, ctx: StepContext) -> None:
        contract = handler.default_contract(ctx)
        if contract is None:
            raise GateError(f"step {meta.step_id} has an evidence gate but its handler proposed no thresholds")
        contract.step_id = meta.step_id
        contract.gate_types = [g for g in meta.gate_types if g in ("E", "T")]
        contract.pivot_target = contract.pivot_target or meta.pivot_target
        if st.contract_history:
            contract.version = max(c.get("version", 1) for c in st.contract_history) + 1
        log = self.log(run.run_id)
        if meta.auto_lock:
            contract = lock_contract(contract, "system:tests")
            log.append(agent="gate_engine", action="lock_test_thresholds", action_type="THRESHOLD_SET",
                       phase=meta.phase, step=meta.step_id,
                       description="Test-gate thresholds fixed by system policy (100% critical tests, no open critical/high bugs)",
                       approved_by=None, approval_status="system:tests", thresholds=contract.thresholds_dict())
            st.contract = contract.model_dump()
            st.contract_history.append(contract.model_dump())
            st.status = COLLECTING if st.status == GENERATED else st.status
            return
        log.append(agent=meta.agent, action="propose_thresholds", action_type="THRESHOLD_SET", phase=meta.phase,
                   step=meta.step_id, description=f"Proposed thresholds v{contract.version}; waiting for the founder to lock them before any data is collected",
                   approved_by=None, approval_status="PENDING", thresholds=contract.thresholds_dict())
        st.contract = contract.model_dump()
        rel = self.store.write_artifact(run.run_id, meta.step_id, st.attempt, f"contract_v{contract.version}.json",
                                        contract.model_dump())
        st.artifacts[f"contract_v{contract.version}.json"] = rel
        st.status = AWAITING_LOCK

    # ------------------------------------------------------------------ data collection
    def _collect(self, run: Run, meta, st: StepState, handler, ctx: StepContext) -> bool:
        contract = Contract(**st.contract)
        obs: Observation | None = None
        if st.observation and st.observation.get("measurement_state") == READY and all(
                st.observation.get("observed", {}).get(c.key) is not None for c in contract.criteria):
            obs = Observation(**st.observation)
        else:
            obs = handler.collect(ctx, contract)
        if obs is None:
            st.status = WAITING_FOR_DATA
            return True
        st.observation = asdict(obs)
        self.log(run.run_id).append(
            agent=meta.agent, action="collect_observation", action_type="ANALYZE_DATA", phase=meta.phase,
            step=meta.step_id, description=f"Collected observations for the locked criteria ({obs.measurement_state})",
            sources=obs.sources, approved_by=None, result={"observed": obs.observed, "measurement_state": obs.measurement_state},
            source_details=[{"type": "system_observation", "ref": obs.notes[:200]}] if obs.notes else [])
        missing = [c.key for c in contract.criteria if obs.observed.get(c.key) is None]
        if obs.measurement_state != READY or missing:
            # Record what is known so far (e.g. passing delivery tests while the demand window is still open)
            # as a NOT_EVALUABLE gate report. It has no outcome until valid data for every criterion exists.
            state = obs.measurement_state if obs.measurement_state != READY else WAITING_FOR_DATA
            partial = evaluate(contract, obs.observed, repeat_count=st.repeat_count, measurement_state=state,
                               prior_pivots=st.prior_pivots, test_gate="T" in meta.gate_types,
                               pivot_target=obs.pivot_target)
            self._record_gate(run, meta, st, partial, contract, ctx, sources=obs.sources, observation=obs)
            st.status = WAITING_FOR_DATA
            return True
        self._evaluate(run, meta, st, contract, obs, ctx)
        return True

    def _evaluate(self, run: Run, meta, st: StepState, contract: Contract, obs: Observation, ctx: StepContext) -> GateResult:
        gate = evaluate(contract, obs.observed, repeat_count=st.repeat_count, measurement_state=obs.measurement_state,
                        prior_pivots=st.prior_pivots, test_gate="T" in meta.gate_types,
                        pivot_target=obs.pivot_target)
        self._record_gate(run, meta, st, gate, contract, ctx, sources=obs.sources, observation=obs)
        st.status = AWAITING_DECISION
        return gate

    def _record_gate(self, run: Run, meta, st: StepState, gate: GateResult, contract: Contract | None,
                     ctx: StepContext, *, sources: list[str] | None = None, observation: Observation | None = None,
                     log_it: bool = True) -> None:
        explanation = {"reasoning": " ".join(gate.reasons), "change_my_mind": "", "model_used": False}
        if log_it:
            explanation = gatekeeper.explain_gate(ctx, gate, contract, st.summary or "")
        st.gate = gate.model_dump()
        st.gate["explanation"] = explanation
        st.gate_history.append(dict(st.gate, attempt=st.attempt))
        log_ids: list[str] = []
        if log_it:
            entry = self.log(run.run_id).append(
                agent="gate_engine", action=self._gate_action_name(meta), action_type="GATE_DECISION",
                phase=meta.phase, step=meta.step_id,
                description=self._gate_headline(meta, gate), sources=sources or [], approved_by=None,
                approval_status="PENDING", gate_type=list(meta.gate_types), gate_outcome=gate.outcome,
                outcome=(gate.outcome or "not_evaluable").lower(), pivot_target=gate.pivot_target if gate.outcome == PIVOT_BACK else None,
                thresholds=contract.thresholds_dict() if contract else None,
                result={"status": gate.status, "pct_of_target": gate.pct_of_target,
                        "measurement_state": gate.measurement_state,
                        "criteria": [{"key": c.key, "target": c.target, "actual": c.actual, "passed": c.passed}
                                     for c in gate.criteria]},
                notes=f"Repeat count for {meta.step_id}: {st.repeat_count}")
            log_ids.append(entry["log_id"])
        st.gate["log_ids"] = log_ids
        report = self._gate_report(run, meta, st, gate, contract, explanation, observation, log_ids)
        st.artifacts["gate_report.md"] = self.store.write_artifact(run.run_id, meta.step_id, st.attempt,
                                                                   "gate_report.md", report)

    @staticmethod
    def _gate_action_name(meta) -> str:
        kinds = "_".join(g.lower() for g in meta.gate_types)
        return f"{meta.short_name.replace('-', '_')}_gate_{kinds}"

    # ------------------------------------------------------------------ pending prompts
    def _set_pending(self, run: Run, meta, st: StepState, handler) -> None:
        if st.status == AWAITING_LOCK:
            run.pending = {"kind": "lock_thresholds", "step": meta.step_id,
                           "prompt": (f"Step {meta.step_id} {meta.name}: review the proposed thresholds and lock them "
                                      "before any data is collected. You may tune targets now; after data arrives, "
                                      "any change invalidates the test and needs a re-run."),
                           "contract": st.contract,
                           "outward": [o for o in (st.output.get("outward") or []) if o.get("when") == "before_collect"]}
        elif st.status == WAITING_FOR_DATA:
            fields = [asdict(f) for f in handler.data_fields()]
            run.pending = {"kind": "submit_data", "step": meta.step_id,
                           "prompt": (f"Step {meta.step_id} {meta.name}: the locked criteria need data the system cannot "
                                      "observe by itself. Submit what you actually measured. If you have no data yet, "
                                      "you can keep collecting, or skip the gate with a reason (logged as FOUNDER_OVERRIDE; "
                                      "it never counts as a passed evidence gate)."),
                           "fields": fields, "partial": (st.observation or {}).get("observed")}
        elif st.status == AWAITING_DECISION:
            gate = st.gate or {}
            options = self._decision_options(meta, st)
            run.pending = {"kind": "decision", "step": meta.step_id, "recommendation": gate.get("outcome"),
                           "status": gate.get("status"), "options": options,
                           "prompt": self._decision_prompt(meta, st)}

    def _decision_options(self, meta, st: StepState) -> list[str]:
        options = ["approve"]
        if "A" in meta.gate_types:
            options.append("reject")
        options += ["decide"]
        if meta.step_id == "1.2":
            options.append("select_concept")
        return options

    def _decision_prompt(self, meta, st: StepState) -> str:
        gate = st.gate or {}
        rec = gate.get("outcome")
        if meta.step_id == "6.3":
            return ("Record your final decision: PERSEVERE, PIVOT or STOP. If it differs from the memo's "
                    "recommendation it is logged as a FOUNDER_OVERRIDE with your reason.")
        if gate.get("status") == "PENDING_APPROVAL":
            ack = st.output.get("requires_acknowledgment")
            extra = f" Approval requires acknowledging: {ack}" if ack else ""
            outward = st.output.get("outward") or []
            if outward:
                extra += (" Approving publishes/sends these items to the local MOCKED site/outbox only: " +
                          ", ".join(o.get("item_id", "?") for o in outward) + ".")
            return (f"Approve the deliverable for step {meta.step_id} {meta.name}, or reject it with specific feedback "
                    f"(repeat {st.repeat_count}/{REPEAT_LIMIT} used).{extra}")
        if rec is None:
            return (f"The gate for step {meta.step_id} could not be evaluated (no valid data). Submit data, or choose an "
                    "outcome explicitly: that is a FOUNDER_OVERRIDE and the evidence gate stays unpassed.")
        return (f"Recommended outcome: {rec}. Accept it, or choose another outcome with a reason "
                "(logged as FOUNDER_OVERRIDE).")

    # ------------------------------------------------------------------ founder actions
    def act(self, run_id: str, action: dict[str, Any]) -> Run:
        """Apply one founder action. Raises FounderActionError when the rules forbid it."""
        with self.lock(run_id):
            run = self.store.load(run_id)
            kind = action.get("kind")
            channel = action.get("channel", "web")
            if kind == "retry":
                run.pending = None
                if run.status == "BLOCKED":
                    run.status = "ACTIVE"
                self.store.save(run)
                return run
            if kind == "clarify_brief":
                run.brief.update({k: v for k, v in (action.get("brief") or {}).items() if v})
                self._intake(run)
                self.store.save(run)
                return run
            if run.status != "ACTIVE":
                raise FounderActionError(f"Run is {run.status}; no further actions apply.")
            if kind == "phase_review":
                self._phase_review(run, action, channel)
                self.store.save(run)
                return run
            step_id = action.get("step") or run.current_step
            if step_id != run.current_step:
                raise FounderActionError(f"Step {step_id} is not the current step ({run.current_step}).")
            meta = STEPS_BY_ID[step_id]
            st = run.steps[step_id]
            handler = get_handler(meta)
            ctx = self._ctx(run, meta, st)
            if kind == "lock_thresholds":
                self._act_lock(run, meta, st, action, channel)
            elif kind == "submit_data":
                self._act_submit(run, meta, st, handler, ctx, action, channel)
            elif kind == "change_threshold":
                self._act_change_threshold(run, meta, st, action, channel)
            elif kind in ("approve", "reject", "decide", "select_concept", "skip"):
                self._act_decision(run, meta, st, handler, ctx, action, channel)
            else:
                raise FounderActionError(f"Unknown action {kind!r}.")
            self.store.save(run)
            return run

    def _act_lock(self, run: Run, meta, st: StepState, action: dict, channel: str) -> None:
        if st.status != AWAITING_LOCK or not st.contract:
            raise FounderActionError("There are no proposed thresholds waiting to be locked.")
        contract = Contract(**st.contract)
        targets = {k: float(v) for k, v in (action.get("targets") or {}).items() if v not in (None, "")}
        locked = lock_contract(contract, "founder", targets=targets)
        st.contract = locked.model_dump()
        st.contract_history.append(locked.model_dump())
        subject = f"contract:{meta.step_id}@v{locked.version}:{content_hash(locked.model_dump_json())}"
        self.approvals(run.run_id).record(subject=subject, decision="approved", channel=channel, step_id=meta.step_id,
                                          reason=action.get("reason", ""))
        self.log(run.run_id).append(
            agent="founder", action="lock_thresholds", action_type="THRESHOLD_SET", phase=meta.phase,
            step=meta.step_id, description=f"Founder locked thresholds v{locked.version} before data collection" +
            (f" (tuned: {targets})" if targets else ""), approved_by="founder", approval_status="APPROVED",
            approval_channel=channel, thresholds=locked.thresholds_dict())
        # Outward items that must happen before collection (e.g. publishing the landing page) need their own approval.
        if action.get("approve_outward"):
            self._approve_and_execute_outward(run, meta, st, "before_collect", channel, action.get("reason", ""))
        st.status = READY_TO_GENERATE if (meta.lock_first and not st.artifacts.get("deliverable.md")) else COLLECTING
        run.pending = None

    def _act_change_threshold(self, run: Run, meta, st: StepState, action: dict, channel: str) -> None:
        if not st.contract or not Contract(**st.contract).locked:
            raise FounderActionError("Thresholds are not locked yet: tune them when you lock them.")
        reason = (action.get("reason") or "").strip()
        if not reason:
            raise FounderActionError("A threshold change after locking needs a reason.")
        old = Contract(**st.contract)
        invalid = old.model_copy(update={"status": "INVALIDATED"})
        st.contract_history.append(invalid.model_dump())
        targets = {k: float(v) for k, v in (action.get("targets") or {}).items() if v not in (None, "")}
        st.contract = new_version(old, targets=targets, reason=reason).model_dump()
        st.observation = None
        st.submitted = {}
        st.gate = None
        self.log(run.run_id).append(
            agent="founder", action="change_threshold", action_type="THRESHOLD_CHANGE", phase=meta.phase,
            step=meta.step_id, description=(f"Founder changed thresholds after locking: v{old.version} is INVALID and "
                                            f"the test must re-run under v{old.version + 1}. Reason: {reason}"),
            approved_by="founder", approval_status="APPROVED", approval_channel=channel,
            thresholds={"old": old.thresholds_dict(), "new_targets": targets})
        st.status = AWAITING_LOCK
        run.pending = None

    def _act_submit(self, run: Run, meta, st: StepState, handler, ctx: StepContext, action: dict, channel: str) -> None:
        if st.status not in (WAITING_FOR_DATA, COLLECTING, AWAITING_DECISION):
            raise FounderActionError("This step is not waiting for data.")
        contract = Contract(**st.contract) if st.contract else None
        if contract is None or not contract.locked:
            raise FounderActionError("Thresholds must be locked before data is submitted.")
        data = dict(action.get("data") or {})
        st.submitted = data
        rubric = rubric_scorer.score_input(ctx, str(data)[:5000], kind=f"data report for step {meta.step_id}",
                                           context={"locked_thresholds": contract.thresholds_dict()})
        self.log(run.run_id).append(
            agent="founder", action="submit_data", action_type="ANALYZE_DATA", phase=meta.phase, step=meta.step_id,
            description=f"Founder submitted data for step {meta.step_id}. {rubric_scorer.format_score(rubric)}",
            approved_by=None, source_details=[{"type": "founder_data", "ref": f"submitted via {channel} {utc_now()}"}],
            result={"fields": sorted(data.keys()), "rubric_total": rubric.get("total")})
        obs = handler.observe(ctx, contract, data)
        partial = (st.observation or {}).get("observed") or {}
        for key, value in partial.items():
            if obs.observed.get(key) is None and value is not None:
                obs.observed[key] = value
        missing = [c.key for c in contract.criteria if obs.observed.get(c.key) is None]
        if not missing and obs.measurement_state != READY and obs.details.get("missing"):
            obs.measurement_state = READY
        st.observation = asdict(obs)
        st.observation["rubric"] = rubric
        self._evaluate(run, meta, st, contract, obs, ctx)
        run.pending = None

    def _act_decision(self, run: Run, meta, st: StepState, handler, ctx: StepContext, action: dict, channel: str) -> None:
        kind = action["kind"]
        reason = (action.get("reason") or "").strip()
        if st.status not in (AWAITING_DECISION, WAITING_FOR_DATA, AWAITING_LOCK) and kind != "skip":
            raise FounderActionError("This step has no decision waiting.")
        if st.status in (AWAITING_LOCK,) and kind not in ("skip", "decide"):
            raise FounderActionError("Lock the thresholds first, or skip the step with a reason.")
        gate = GateResult(**{k: v for k, v in st.gate.items() if k in GateResult.model_fields}) if st.gate else None
        log = self.log(run.run_id)

        # --- step 6.3: the founder's final decision
        if meta.step_id == "6.3" and kind in ("approve", "decide"):
            self._final_decision(run, meta, st, action, channel)
            return

        # --- reject a deliverable (gate A)
        if kind == "reject":
            if "A" not in meta.gate_types:
                raise FounderActionError("This step has no approval gate; use 'decide' to choose an outcome.")
            if not reason:
                raise FounderActionError("Say what to change: a rejection needs specific feedback.")
            agate = approval_gate(meta.step_id, list(meta.gate_types), approved=False, repeat_count=st.repeat_count,
                                  pivot_target=meta.pivot_target)
            self._approval_record(run, meta, st, "rejected", channel, reason)
            log.append(agent="founder", action="reject_deliverable", action_type="FOUNDER_APPROVAL", phase=meta.phase,
                       step=meta.step_id, description=f"Founder rejected the deliverable: {reason}", approved_by="founder",
                       approval_status="REJECTED", approval_channel=channel, gate_outcome=agate.outcome)
            if agate.outcome == REPEAT:
                self._apply_outcome(run, meta, st, REPEAT, None, reason, channel)
            else:
                st.gate = agate.model_dump()
                st.gate["explanation"] = {"reasoning": " ".join(agate.reasons), "change_my_mind": ""}
                st.status = AWAITING_DECISION
                run.pending = None
            return

        # --- approval of the deliverable (+ acceptance of the recommendation)
        if st.guardrail_flags and kind in ("approve", "select_concept"):
            raise FounderActionError("This deliverable still breaks a marketing rule (" +
                                     "; ".join(f["message"] for f in st.guardrail_flags) +
                                     "). Reject it with feedback so it is regenerated.")
        recommended = gate.outcome if gate else None
        if gate and gate.status == "PENDING_APPROVAL":
            recommended = GO
        if kind in ("approve", "select_concept"):
            if recommended is None:
                raise FounderActionError("There is no recommendation to accept yet: submit data, or choose an outcome "
                                         "with 'decide' (logged as FOUNDER_OVERRIDE).")
            chosen, target = recommended, (gate.pivot_target if gate else None)
        else:  # decide / skip
            chosen = (action.get("outcome") or "").upper() or (GO if kind == "skip" else "")
            if chosen not in OUTCOMES:
                raise FounderActionError(f"Choose one of {', '.join(OUTCOMES)}.")
            target = action.get("pivot_target") or (gate.pivot_target if gate else None) or meta.pivot_target

        # Concept selection in 1.2
        if meta.step_id == "1.2" and chosen == GO:
            self._select_concept(run, st, action, channel)

        if chosen == REPEAT and st.repeat_count >= REPEAT_LIMIT:
            raise FounderActionError(f"Repeat limit reached ({REPEAT_LIMIT}). Choose PIVOT_BACK or STOP.")
        if chosen == PIVOT_BACK:
            if not target or target not in STEP_IDS or STEP_IDS.index(target) >= STEP_IDS.index(meta.step_id):
                raise FounderActionError("PIVOT_BACK needs an earlier step to return to.")

        evidence_gate = any(g in meta.gate_types for g in ("E", "T"))
        is_override = (recommended is None) or (chosen != recommended) or kind == "skip"
        if "A" in meta.gate_types:
            self._approval_record(run, meta, st, "approved" if chosen in (GO,) else "rejected", channel, reason)
        if is_override:
            if not reason:
                raise FounderActionError("An override needs a reason; it is logged next to the original recommendation.")
            risk = self._skip_risk(meta, gate) if (recommended is None or kind == "skip") else ""
            log.append(agent="founder", action="override_gate", action_type="FOUNDER_OVERRIDE", phase=meta.phase,
                       step=meta.step_id, description=(f"Founder chose {chosen} instead of "
                                                       f"{recommended or 'no outcome (gate not evaluable)'}. Reason: {reason}" +
                                                       (f" Untested risk: {risk}" if risk else "")),
                       approved_by="founder", approval_status="APPROVED", approval_channel=channel,
                       gate_outcome=chosen, outcome=chosen.lower(),
                       override={"original_recommendation": recommended, "chosen": chosen, "reason": reason,
                                 "evidence_gate_passed": bool(gate and gate.evidence_passed), "untested_risk": risk})
            st.overridden = True
        else:
            log.append(agent="founder", action="approve_gate" if kind != "select_concept" else "select_concept",
                       action_type="FOUNDER_APPROVAL", phase=meta.phase, step=meta.step_id,
                       description=f"Founder accepted the recommended outcome {chosen} for step {meta.step_id}" +
                                   (f". Note: {reason}" if reason else ""),
                       approved_by="founder", approval_status="APPROVED", approval_channel=channel,
                       gate_outcome=chosen, outcome=chosen.lower())
        ack_text = st.output.get("requires_acknowledgment")
        if chosen == GO and ack_text and not action.get("acknowledge"):
            raise FounderActionError(f"Approval needs your explicit acknowledgment: {ack_text}")
        if chosen == GO and ack_text:
            log.append(agent="founder", action="acknowledge", action_type="FOUNDER_APPROVAL", phase=meta.phase,
                       step=meta.step_id, description=f"Founder acknowledged: {ack_text}", approved_by="founder",
                       approval_status="APPROVED", approval_channel=channel, acknowledged=True)
        if chosen == GO and "A" in meta.gate_types:
            self._approve_and_execute_outward(run, meta, st, "on_approve", channel, reason,
                                              only_ids=action.get("outward_ids"))
        st.decision = {"kind": kind, "chosen": chosen, "recommended": recommended, "reason": reason,
                       "channel": channel, "at": utc_now(), "override": is_override,
                       "evidence_gate": evidence_gate}
        self._apply_outcome(run, meta, st, chosen, target, reason, channel)

    @staticmethod
    def _skip_risk(meta, gate: GateResult | None) -> str:
        names = ", ".join(c.label for c in (gate.criteria if gate else [])) or "the locked criteria"
        return f"step {meta.step_id} ({meta.name}) proceeds without evidence for {names}; downstream work rests on an untested assumption."

    def _approval_record(self, run: Run, meta, st: StepState, decision: str, channel: str, reason: str) -> None:
        deliverable = st.artifacts.get("deliverable.md")
        digest = content_hash(self.store.read_artifact(run.run_id, deliverable)) if deliverable else "none"
        self.approvals(run.run_id).record(subject=f"step:{meta.step_id}@attempt{st.attempt}:{digest}",
                                          decision=decision, channel=channel, step_id=meta.step_id, reason=reason)

    def _select_concept(self, run: Run, st: StepState, action: dict, channel: str) -> None:
        concepts = st.output.get("concepts") or []
        recommended_id = st.output.get("recommended_id")
        chosen_id = action.get("concept_id") or recommended_id
        chosen = next((c for c in concepts if str(c.get("id")) == str(chosen_id)), None)
        if chosen is None and concepts:
            chosen = concepts[0]
        if chosen is None:
            return
        run.selected_concept = dict(chosen)
        if recommended_id and str(chosen.get("id")) != str(recommended_id):
            reason = (action.get("reason") or "").strip()
            if not reason:
                raise FounderActionError("You picked a lower-ranked concept: give the reason so it can be logged.")
            self.log(run.run_id).append(
                agent="founder", action="select_lower_ranked_concept", action_type="FOUNDER_OVERRIDE", phase=1,
                step="1.2", description=f"Founder selected '{chosen.get('name')}' over the top-ranked concept. Reason: {reason}",
                approved_by="founder", approval_status="APPROVED", approval_channel=channel,
                override={"original_recommendation": recommended_id, "chosen": chosen.get("id"), "reason": reason})

    def _approve_and_execute_outward(self, run: Run, meta, st: StepState, when: str, channel: str, reason: str,
                                     only_ids: list[str] | None = None) -> None:
        items = [o for o in (st.output.get("outward") or []) if o.get("when", "on_approve") == when]
        if only_ids is not None:
            items = [o for o in items if o.get("item_id") in set(only_ids)]
        if not items:
            return
        book = self.approvals(run.run_id)
        log = self.log(run.run_id)
        results = st.output.setdefault("outward_results", [])
        for item in items:
            rel = st.artifacts.get(item.get("file", ""))
            if not rel:
                continue
            content = self.store.read_artifact(run.run_id, rel)
            subject = outward_subject(item["kind"], item["item_id"], content)
            book.record(subject=subject, decision="approved", channel=channel, step_id=meta.step_id, reason=reason)
            try:
                result = perform_outward_action(
                    book=book, log=log, kind=item["kind"], item_id=item["item_id"], content=content,
                    executor=lambda item=item, content=content: self._mock_execute(run, item, content),
                    phase=meta.phase, step_id=meta.step_id, agent=meta.agent)
                results.append({"item_id": item["item_id"], "kind": item["kind"], **result})
            except ApprovalRequired as exc:  # pragma: no cover - approval was just recorded
                results.append({"item_id": item["item_id"], "kind": item["kind"], "error": str(exc)})

    def _mock_execute(self, run: Run, item: dict, content: str) -> dict:
        """MOCKED outward action: write to the local mock site or outbox. Nothing leaves the machine."""
        name = item.get("target_name") or item.get("file", item["item_id"])
        if item["kind"] == "publish":
            path = self.store.site_dir(run.run_id) / name
            path.write_text(content, encoding="utf-8")
            return {"mocked": True, "published_to": f"local mock site: /site/{run.run_id}/{name}"}
        path = self.store.outbox_dir(run.run_id) / name
        header = ("<!-- MOCKED: this message was NOT sent. It sits in the local outbox for the founder to send "
                  "manually from their own account if they choose. -->\n")
        path.write_text(header + content, encoding="utf-8")
        return {"mocked": True, "sent_to": f"local outbox: {name} (not sent)"}

    # ------------------------------------------------------------------ outcomes
    def _apply_outcome(self, run: Run, meta, st: StepState, outcome: str, pivot_target: str | None, reason: str,
                       channel: str) -> None:
        log = self.log(run.run_id)
        run.history.append({"at": utc_now(), "step": meta.step_id, "outcome": outcome, "pivot_target": pivot_target,
                            "reason": reason, "override": bool(st.decision and st.decision.get("override"))})
        run.pending = None
        if outcome == GO:
            st.status, st.outcome = DONE, GO
            if meta.step_id == "6.3":
                run.status = "COMPLETED"
                return
            if is_last_in_phase(meta.step_id):
                self._open_phase_review(run, meta.phase)
            nxt = next_step_id(meta.step_id)
            if nxt:
                run.current_step = nxt
            else:
                run.status = "COMPLETED"
            return
        if outcome == REPEAT:
            if st.repeat_count >= REPEAT_LIMIT:
                raise FounderActionError(f"Repeat limit reached ({REPEAT_LIMIT}). Choose PIVOT_BACK or STOP.")
            st.history.append({"event": "repeat", "attempt": st.attempt, "at": utc_now(), "reason": reason,
                               "gate": st.gate})
            st.repeat_count += 1
            st.attempt += 1
            st.feedback = reason
            st.gate, st.decision, st.observation, st.submitted = None, None, None, {}
            locked = bool(st.contract and Contract(**st.contract).locked)
            st.status = READY_TO_GENERATE if (meta.lock_first and locked) else NEW
            st.outcome = None
            return
        if outcome == PIVOT_BACK:
            target = pivot_target or meta.pivot_target
            st.prior_pivots += 1
            st.outcome = PIVOT_BACK
            start, end = STEP_IDS.index(target), STEP_IDS.index(meta.step_id)
            for sid in STEP_IDS[start:end + 1]:
                s = run.steps[sid]
                s.history.append({"event": "pivot_reset", "from_step": meta.step_id, "attempt": s.attempt,
                                  "at": utc_now(), "reason": reason, "gate": s.gate, "outcome": s.outcome})
                if s.contract:
                    old = Contract(**s.contract)
                    if old.status != "INVALIDATED":
                        s.contract_history.append(old.model_copy(update={"status": "INVALIDATED"}).model_dump())
                s.status = NEW
                s.attempt += 1
                s.repeat_count = 0
                s.contract = None   # a new hypothesis version needs a fresh threshold lock
                s.gate, s.decision, s.observation, s.submitted = None, None, None, {}
                s.feedback = f"Pivot back from {meta.step_id}: {reason}"
                s.outcome = None
            run.current_step = target
            log.append(agent="orchestrator", action="pivot_back", action_type="PIVOT", phase=meta.phase,
                       step=meta.step_id, description=f"Pivoted back from {meta.step_id} to {target}. Reason: {reason}",
                       approved_by="founder", approval_channel=channel, pivot_target=target, gate_outcome=PIVOT_BACK,
                       outcome="pivot_back")
            return
        if outcome == STOP:
            st.status, st.outcome = DONE, STOP
            run.status = "STOPPED"
            run.status_reason = f"Stopped at step {meta.step_id}: {reason or 'recommended STOP accepted'}"
            log.append(agent="orchestrator", action="stop_venture", action_type="STOP", phase=meta.phase,
                       step=meta.step_id, description=run.status_reason, approved_by="founder",
                       approval_channel=channel, gate_outcome=STOP, outcome="stop")
            return
        raise FounderActionError(f"Unknown outcome {outcome}")

    def _final_decision(self, run: Run, meta, st: StepState, action: dict, channel: str) -> None:
        memo_rec = str(st.output.get("recommendation") or "").upper() or None
        chosen = str(action.get("final_decision") or (memo_rec if action["kind"] == "approve" else "")).upper()
        if chosen not in FINAL_DECISIONS:
            raise FounderActionError("Record PERSEVERE, PIVOT or STOP as the final decision.")
        reason = (action.get("reason") or "").strip()
        log = self.log(run.run_id)
        self._approval_record(run, meta, st, "approved", channel, reason)
        if memo_rec and chosen != memo_rec:
            if not reason:
                raise FounderActionError("Your decision differs from the memo's recommendation: give a reason.")
            log.append(agent="founder", action="final_decision", action_type="FOUNDER_OVERRIDE", phase=6, step="6.3",
                       description=f"Founder decided {chosen}; memo recommended {memo_rec}. Reason: {reason}",
                       approved_by="founder", approval_status="APPROVED", approval_channel=channel,
                       override={"original_recommendation": memo_rec, "chosen": chosen, "reason": reason})
        else:
            log.append(agent="founder", action="final_decision", action_type="FOUNDER_APPROVAL", phase=6, step="6.3",
                       description=f"Founder recorded the final decision: {chosen}" + (f". {reason}" if reason else ""),
                       approved_by="founder", approval_status="APPROVED", approval_channel=channel)
        run.final_decision = {"decision": chosen, "memo_recommendation": memo_rec, "reason": reason, "at": utc_now()}
        st.decision = {"kind": action["kind"], "chosen": chosen, "recommended": memo_rec, "reason": reason,
                       "channel": channel, "at": utc_now(), "override": bool(memo_rec and chosen != memo_rec)}
        st.status, st.outcome = DONE, GO
        run.history.append({"at": utc_now(), "step": "6.3", "outcome": f"FINAL:{chosen}", "reason": reason})
        run.pending = None
        if chosen == "STOP":
            run.status = "STOPPED"
            run.status_reason = f"Founder's final decision: STOP. {reason}".strip()
            log.append(agent="orchestrator", action="stop_venture", action_type="STOP", phase=6, step="6.3",
                       description=run.status_reason, approved_by="founder", approval_channel=channel, outcome="stop")
        else:
            run.status = "COMPLETED"

    # ------------------------------------------------------------------ phase-exit review
    def _open_phase_review(self, run: Run, phase: int) -> None:
        ctx = self._ctx(run, STEPS_BY_ID[steps_in_phase(phase)[-1].step_id], None)
        steps = [{"step": s.step_id, "name": s.name, "outcome": run.steps[s.step_id].outcome,
                  "overridden": run.steps[s.step_id].overridden, "summary": run.steps[s.step_id].summary[:400]}
                 for s in steps_in_phase(phase)]
        summary = gatekeeper.summarize_phase(ctx, phase, PHASE_NAMES[phase], steps)
        run.phase_reviews[str(phase)] = {"phase": phase, "summary": summary, "steps": steps, "opened_at": utc_now()}
        run.pending = {"kind": "phase_review", "phase": phase,
                       "prompt": f"End of phase {phase} ({PHASE_NAMES[phase]}). Answer the three questions before moving on.",
                       "summary": summary,
                       "questions": ["Do these deliverables match what you need? (Yes / Partly / No)",
                                     "Is anything unclear, missing or wrong?",
                                     "Rate your confidence to proceed, 1-5."]}

    def _phase_review(self, run: Run, action: dict, channel: str) -> None:
        if not run.pending or run.pending.get("kind") != "phase_review":
            raise FounderActionError("No phase-exit review is open.")
        phase = int(run.pending["phase"])
        match = str(action.get("match") or "").strip().capitalize()
        if match not in ("Yes", "Partly", "No"):
            raise FounderActionError("Answer the first question with Yes, Partly or No.")
        try:
            confidence = int(action.get("confidence"))
        except (TypeError, ValueError):
            raise FounderActionError("Rate your confidence from 1 to 5.") from None
        if not 1 <= confidence <= 5:
            raise FounderActionError("Rate your confidence from 1 to 5.")
        issues = (action.get("issues") or "").strip()
        last_meta = steps_in_phase(phase)[-1]
        ctx = self._ctx(run, last_meta, None)
        rubric = rubric_scorer.score_input(ctx, f"match={match}; confidence={confidence}; issues={issues}",
                                           kind=f"phase {phase} exit review answers") if issues else None
        review = run.phase_reviews.setdefault(str(phase), {"phase": phase})
        review.update({"match": match, "issues": issues, "confidence": confidence, "rubric": rubric,
                       "answered_at": utc_now(), "channel": channel})
        log = self.log(run.run_id)
        log.append(agent="founder", action="phase_exit_review", action_type="FOUNDER_APPROVAL", phase=phase,
                   step=last_meta.step_id, description=(f"Phase {phase} exit review: deliverables match = {match}, "
                                                        f"confidence {confidence}/5. Issues: {issues or 'none'}"),
                   approved_by="founder", approval_status="APPROVED" if (match == "Yes" and confidence > 2) else "REJECTED",
                   approval_channel=channel)
        run.pending = None
        if match in ("Partly", "No") or confidence <= 2:
            target = action.get("repeat_step") or last_meta.step_id
            meta = STEPS_BY_ID[target]
            if meta.phase != phase:
                raise FounderActionError("The step to repeat must belong to the phase under review.")
            st = run.steps[target]
            if st.repeat_count >= REPEAT_LIMIT:
                raise FounderActionError(f"Step {target} already used its {REPEAT_LIMIT} repeats; choose another step.")
            # Reopen the step and repeat it with the founder's issues as feedback.
            st.status = DONE
            run.current_step = target
            st.decision = {"kind": "phase_review", "chosen": REPEAT, "reason": issues, "channel": channel,
                           "at": utc_now(), "override": False}
            self._apply_outcome(run, meta, st, REPEAT, None, issues or f"Phase review: {match}, confidence {confidence}",
                                channel)
            return
        next_phase_steps = steps_in_phase(phase + 1)
        if next_phase_steps:
            run.current_step = next_phase_steps[0].step_id

    # ------------------------------------------------------------------ free-text requests (guardrails)
    def request(self, run_id: str, text: str, channel: str = "web") -> dict[str, Any]:
        with self.lock(run_id):
            run = self.store.load(run_id)
            violations = guardrails.check_request(text)
            meta = STEPS_BY_ID.get(run.current_step)
            if violations:
                message = guardrails.refusal_message(violations)
                self.log(run_id).append(agent="guardrails", action="refuse_request", action_type="ANALYZE_DATA",
                                        phase=meta.phase if meta else 0, step=run.current_step,
                                        description=f"Refused a founder request: {', '.join(v.rule for v in violations)}",
                                        approved_by=None, result={"request": text[:300],
                                                                  "violations": [v.as_dict() for v in violations]})
                run.messages.append({"role": "founder", "at": utc_now(), "text": text})
                run.messages.append({"role": "system", "at": utc_now(), "refused": True, "text": message})
                self.store.save(run)
                return {"refused": True, "message": message, "violations": [v.as_dict() for v in violations]}
            run.messages.append({"role": "founder", "at": utc_now(), "text": text})
            reply = ("Noted. To apply this to the current deliverable, reject it with this feedback; "
                     "the step is then repeated with your change (repeat limit 2).")
            run.messages.append({"role": "system", "at": utc_now(), "text": reply})
            self.store.save(run)
            return {"refused": False, "message": reply}

    # ------------------------------------------------------------------ rendering
    def _render_deliverable(self, run: Run, meta, st: StepState, out: StepOutput, claims, ledger: EvidenceLedger) -> str:
        lines = [f"# {meta.step_id} {meta.name}: {out.title}", "",
                 f"`{self.status_line(run)}`", "",
                 f"Venture: **{run.title}** | Run `{run.run_id}` | Attempt {st.attempt} | Generated {utc_now()}", ""]
        if out.summary:
            lines += [f"**What I'm doing now:** {out.summary}", ""]
        if st.feedback:
            lines += [f"> Changes requested for this attempt: {st.feedback}", ""]
        lines += [out.markdown.strip(), ""]
        if claims:
            lines += ["## Claims and their evidence", ""]
            lines += [f"- {ledger.render_claim(c)}" for c in claims]
            lines.append("")
        cited = sorted({i for c in claims for i in c.evidence_ids})
        if cited:
            lines += ["## Evidence cited", "", ledger.table_markdown(cited), ""]
        if st.claim_problems:
            lines += ["## Claim check", "", "The evidence check changed these claims before publication:", ""]
            lines += [f"- {p}" for p in st.claim_problems]
            lines.append("")
        if st.guardrail_flags:
            lines += ["## Guardrail flags (must be fixed before approval)", ""]
            lines += [f"- {f['message']} (found: '{f['match']}')" for f in st.guardrail_flags]
            lines.append("")
        if out.questions:
            lines += ["## What I need from you", ""]
            lines += [f"{i}. {q}" for i, q in enumerate(out.questions[:3], start=1)]
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _criterion_line(c) -> str:
        unit = f" {c.unit}" if c.unit else ""
        return f"{c.label} ({c.key}) {c.op} {c.target:g}{unit}"

    def _gate_headline(self, meta, gate: GateResult) -> str:
        if gate.status == "PASSED":
            return f"GATE PASSED: step {meta.step_id} {meta.name}. Recommendation: GO."
        if gate.status in ("NOT_EVALUABLE",):
            return (f"GATE NOT EVALUABLE: step {meta.step_id} {meta.name} ({gate.measurement_state}). "
                    "No outcome until valid data arrives.")
        if gate.status == "PENDING_APPROVAL":
            return f"GATE PENDING: step {meta.step_id} {meta.name} waits for founder approval."
        failed = [c for c in gate.criteria if c.passed is False]
        nums = "; ".join(f"{c.key} {c.actual:g}/{c.target:g} ({format_pct(c.pct_of_target)})" for c in failed if c.actual is not None)
        target = f" -> {gate.pivot_target}" if gate.outcome == PIVOT_BACK and gate.pivot_target else ""
        alt = f" or {gate.alternative}" if gate.alternative else ""
        word = "PARTIAL" if gate.status == "PARTIAL" else "FAILED"
        return f"GATE {word}: {nums}. Recommendation: {gate.outcome}{target}{alt}."

    def _gate_report(self, run: Run, meta, st: StepState, gate: GateResult, contract: Contract | None,
                     explanation: dict, observation: Observation | None, log_ids: list[str]) -> str:
        if contract:
            locked_on = (contract.locked_at or "")[:10] or "not locked"
            thresholds = "; ".join(self._criterion_line(c) for c in contract.criteria)
            thresholds += f" (locked on {locked_on} by {contract.locked_by or 'nobody'}, v{contract.version}"
            thresholds += f", window {contract.window_days} days)" if contract.window_days else ")"
        else:
            thresholds = "Founder approval of the deliverable (no numeric threshold)"
        if gate.criteria:
            src = ""
            if observation is not None:
                src = observation.notes or ", ".join(observation.sources[:3])
            actual = "; ".join(f"{c.key} = {'n/a' if c.actual is None else f'{c.actual:g}'}"
                               f"{'' if c.passed is None else (' (pass)' if c.passed else ' (fail)')}" for c in gate.criteria)
            actual += f" (source: {src})" if src else ""
        else:
            actual = "Deliverable produced; waiting for the founder's decision"
        if gate.status == "PASSED":
            status = "PASSED"
        elif gate.status in ("FAILED", "PARTIAL"):
            status = f"{gate.status} ({format_pct(gate.pct_of_target)} of target)"
        else:
            status = gate.status
        if gate.outcome:
            outcome = gate.outcome + (f" -> {gate.pivot_target}" if gate.outcome == PIVOT_BACK and gate.pivot_target else "")
            if gate.alternative:
                outcome += f" (alternative: {gate.alternative})"
        else:
            outcome = "none yet (not evaluable)" if gate.status == "NOT_EVALUABLE" else "GO once approved"
        question = self._decision_prompt(meta, st)
        lines = [self._gate_headline(meta, gate), "", "```", "=== GATE REPORT ===",
                 f"Phase / Step: {meta.step_id} {meta.name} (Phase {meta.phase}: {meta.phase_name})",
                 f"Gate type(s): {' + '.join(meta.gate_types)}",
                 f"Pre-set threshold(s): {thresholds}",
                 f"Actual result(s): {actual}",
                 f"Status: {status}",
                 f"Outcome: {outcome}",
                 f"Reasoning: {explanation.get('reasoning', '')}",
                 f"What would change my mind: {explanation.get('change_my_mind', '') or 'n/a'}",
                 f"Founder decision required: yes - {question}",
                 f"Log ID(s): {', '.join(log_ids) or 'pending'}",
                 "===================", "```", ""]
        if observation is not None and observation.details:
            lines += ["## Measurement details", ""]
            for key, value in observation.details.items():
                if key in ("missing",) and not value:
                    continue
                lines.append(f"- **{key}**: {value}")
            lines.append("")
        if gate.forced_by_repeat_limit:
            lines += [f"Repeat limit ({REPEAT_LIMIT}) reached: REPEAT is no longer available for this step.", ""]
        return "\n".join(lines)
