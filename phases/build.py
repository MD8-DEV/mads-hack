"""Phase 3: Build.

3.1 MvpScope         (gate A)    smallest product that delivers the value proposition, with
                                 machine-checkable acceptance criteria
3.2 BuildAndTest     (gate T)    the builder writes the product; agents/qa.py tests it with
                                 deterministic checks (thresholds locked by system policy)
3.3 UserTestAndDocs  (gate E+A)  user docs written from the actual build, a usability-test plan
                                 for >= 5 target users; the founder reports the sessions

Products are small digital products a model can build in one pass: a
self-contained static web tool (product/index.html, inline CSS/JS, no network
requests, data in localStorage) and/or a markdown template kit.
"""
from __future__ import annotations

import json
import re
from typing import Any

from agents import builder, doc_writer, product_manager, qa
from agents.base import StepContext, as_float, as_list
from evidence import Claim, Evidence
from gates import INSUFFICIENT_DATA, INVALID_DATA, READY, WAITING_FOR_DATA, Contract, Criterion, wilson_interval
from logbook import utc_now
from phases.base import DataField, Observation, StepHandler, StepOutput

PARTICIPANTS_MIN = 5
UNASSISTED_TARGET = 0.8
PREVIOUS_FILES_LIMIT = 60_000      # characters of the previous build passed back to the builder on a repeat
DOC_FILES = ("docs/quick-start.md", "docs/faq.md", "docs/how-to.md", "docs/limitations.md")
SUPPORT_PLACEHOLDER = "[support contact: the founder adds this before sharing the docs]"

CHECK_TYPE_HELP = {
    "file_exists": "the file exists and is not empty (value ignored)",
    "contains": "case-insensitive substring of the file (value = the text)",
    "regex": "Python regular expression searched with IGNORECASE and MULTILINE (value = the pattern)",
    "html_element": "an element matching ONE compound selector exists, e.g. button#export, input[type=date], "
                    "form.add-item, table (no spaces or combinators)",
    "no_external_requests": "the page makes no network requests (value ignored)",
}

BUILD_REQUIREMENTS = [
    "Return product/index.html and product/README.md; a template kit may add product/templates/<name>.md files. "
    "Nothing else; at most 10 files; under 200 KB in total.",
    "product/index.html is a complete HTML5 document: <!DOCTYPE html>, <html lang=...>, <meta charset>, a viewport "
    "meta tag and a <title>; CSS in one inline <style>, JavaScript in one inline <script>.",
    "No network requests of any kind: no CDNs, web fonts, remote images, analytics, iframes, fetch, XMLHttpRequest, "
    "WebSocket or beacons. Use system fonts and inline SVG or CSS.",
    "Data stays in this browser: localStorage under one namespaced key; offer export (download a file built with a "
    "Blob) and a clear-all action that asks for confirmation.",
    "No accounts, logins, passwords, payments, checkout, card or bank fields, email or phone fields, upgrade prompts "
    "or locked features.",
    "No testimonials, ratings, user counts, countdown timers, urgency or promises of income or results.",
    "No placeholder text: no lorem ipsum, TODO or FIXME. Use realistic, clearly labelled example data if needed.",
    "Forms: handle submit in JavaScript with preventDefault, validate input, show inline errors, and render user "
    "text with textContent (never innerHTML with user input).",
    "Accessibility: a visible <label> for every field, keyboard-usable controls, readable contrast.",
    "product/README.md has '## Usage', '## Data and privacy' and '## Limitations' sections.",
    "Meet every acceptance criterion literally: the ids, classes, elements and texts its check looks for.",
]

_LEADING_WORDS = re.compile(r"\b(click|tap|press|button|menu|tab|field|scroll|select the|type into)\b", re.I)
_UI_LABEL = re.compile(r"\*\*([^*\n]{2,60})\*\*")   # the doc writer puts UI names in bold


# ------------------------------------------------------------------ helpers
def _trim(value: Any, limit: int = 2500) -> Any:
    """Keep payloads small: return the value, or its JSON text cut to `limit` characters."""
    if not value:
        return value
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else text[:limit] + " ...(truncated)"


def _cell(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value if value is not None else "").split())
    return (text[:limit] + ("..." if len(text) > limit else "")).replace("|", "/") or "-"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _demote(markdown: str) -> str:
    """Push headings down two levels so an embedded preview sits under the deliverable's own sections."""
    return re.sub(r"^(#{1,4}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", markdown, flags=re.M)


def _known_evidence(ctx: StepContext) -> tuple[set[str], dict[str, str]]:
    rows = ctx.ledger.all()   # FIXTURE rows are excluded: they never count as evidence
    return {r.evidence_id for r in rows}, {r.evidence_id: r.provenance for r in rows}


def _product_files(ctx: StepContext) -> dict[str, str]:
    """The files built in step 3.2 (latest attempt), read from the run's artifacts."""
    state = ctx.run.steps.get("3.2")
    files: dict[str, str] = {}
    if not state:
        return files
    for name, rel in sorted(state.artifacts.items()):
        if name.startswith("product/"):
            try:
                files[name] = ctx.store.read_artifact(ctx.run_id, rel)
            except OSError:
                continue
    return files


def _check_text(check: dict[str, Any]) -> str:
    value = check.get("value") or ""
    return f"`{check.get('type')}` on `{check.get('file')}`" + (f": `{_cell(value, 80)}`" if value else "")


# ------------------------------------------------------------------ 3.1 MVP scope
class MvpScope(StepHandler):
    def generate(self, ctx: StepContext) -> StepOutput:
        brief = ctx.brief
        payload = {
            "concept": ctx.concept(),
            "founder_constraints": {k: brief.get(k) for k in ("customer", "budget", "time", "jurisdiction")
                                    if brief.get(k)},
            "lean_canvas": _trim(ctx.prior("2.1"), 4000),
            "demand_test": _trim(ctx.prior("2.2"), 1500),
            "interviews": _trim(ctx.prior("1.4"), 1500),
            "evidence": ctx.evidence_digest(30),
            "product_kinds": {"web_tool": "one self-contained page product/index.html (inline CSS/JS, localStorage)",
                              "template_kit": "markdown templates under product/templates/ plus product/index.html "
                                              "as the kit's index page",
                              "web_tool_and_templates": "both"},
            "check_types": CHECK_TYPE_HELP,
            "files_the_build_will_have": [qa.INDEX, qa.README, "product/templates/<name>.md (template kits only)"],
            "limits": {"max_must_haves": product_manager.MAX_MUST_HAVES,
                       "max_acceptance_criteria": product_manager.MAX_ACCEPTANCE},
            "previous_scope": _trim(ctx.prior("3.1"), 3000) if ctx.attempt > 0 else None,
            "feedback": ctx.feedback,
        }
        raw = product_manager.mvp_scope(ctx, payload)
        known, provenance = _known_evidence(ctx)
        scope, notes = product_manager.normalize_scope(raw, known, provenance)

        claims = []
        for must in scope["must_haves"]:
            claims.append(Claim(text=f"{must['id']} {must['feature']} is a must-have: "
                                     f"{must['user_value'] or 'needed for the core flow'}",
                                label=must["label"], evidence_ids=must["evidence_ids"], basis=must["basis"]))
        baseline = scope["baseline"]
        claims.append(Claim(text=f"Baseline for the current alternative: {baseline['baseline_measure']}",
                            label=baseline["label"], evidence_ids=baseline["evidence_ids"],
                            basis="founder or source data" if baseline["evidence_ids"] else
                            "no baseline measured yet; measure it in the 3.3 sessions"))
        cited = sorted({i for c in claims for i in c.evidence_ids})
        questions = [str(q)[:300] for q in as_list(raw.get("questions")) if str(q).strip()][:3]
        summary = (f"Scoped '{scope['product_name']}' to {len(scope['must_haves'])} must-have(s) with "
                   f"{len(scope['acceptance_criteria'])} machine-checkable acceptance criteria "
                   f"(delivery mode: {scope['delivery_mode']['mode']}).")
        return StepOutput(title=scope["product_name"], markdown=self._render(scope), data=scope,
                          claims=claims, sources=ctx.ledger.urls(cited), summary=summary, questions=questions)

    @staticmethod
    def _render(scope: dict[str, Any]) -> str:
        pm, fve, mode = scope["process_map"], scope["first_value_event"], scope["delivery_mode"]
        lines = [f"## {scope['product_name']}", ""]
        if scope["uvp"]:
            lines += [f"**Value proposition:** {scope['uvp']}", ""]
        lines += [f"**Product format:** {scope['product_kind'].replace('_', ' ')} "
                  f"(`{qa.INDEX}` + `{qa.README}`; self-contained, no network requests, data in the browser)", "",
                  f"**Delivery mode:** {mode['mode'].replace('_', ' ')}. {mode['rationale']}", ""]
        if mode["alternatives_considered"]:
            lines += [f"Alternatives considered: {mode['alternatives_considered']}", ""]
        lines += ["## Process map", "", "| Trigger | Input | Action | Output | Outcome |", "|---|---|---|---|---|",
                  "| " + " | ".join(_cell(pm[k]) for k in product_manager.PROCESS_KEYS) + " |", "",
                  "## First-value event", "", f"- **Event:** {fve['event'] or 'not defined'}",
                  f"- **How it is observed:** {fve['how_observed'] or 'not defined'}", ""]
        b = scope["baseline"]
        lines += ["## Baseline and minimum useful improvement", "",
                  f"- Current alternative: {b['current_alternative'] or 'not stated'}",
                  f"- Baseline: {b['baseline_measure']} `{b['label']}`" +
                  (f" ({', '.join(b['evidence_ids'])})" if b["evidence_ids"] else ""),
                  f"- Minimum useful improvement: {b['minimum_useful_improvement'] or 'not stated'} `ASSUMPTION`", ""]
        lines += [f"## Must-haves ({len(scope['must_haves'])} of at most {product_manager.MAX_MUST_HAVES})", "",
                  "| ID | Feature | Why it is needed | Evidence | Label |", "|---|---|---|---|---|"]
        for m in scope["must_haves"]:
            lines.append(f"| {m['id']} | {_cell(m['feature'])} | {_cell(m['user_value'])} | "
                         f"{', '.join(m['evidence_ids']) or '-'} | {m['label']}"
                         + (f" ({_cell(m['basis'], 120)})" if m["label"] == "ASSUMPTION" else "") + " |")
        lines += ["", "## Acceptance criteria (checked by code in step 3.2)", "",
                  "| ID | Feature | Criterion | Critical | Check |", "|---|---|---|---|---|"]
        for c in scope["acceptance_criteria"]:
            lines.append(f"| {c['id']} | {c['feature'] or '-'} | {_cell(c['description'])} | "
                         f"{'yes' if c['critical'] else 'no'} | {_check_text(c['check'])} |")
        lines += ["", "## Won't build (this version)", ""]
        if scope["wont_build"]:
            lines += ["| Feature | Reason |", "|---|---|"]
            lines += [f"| {_cell(w['feature'])} | {_cell(w['reason'])} |" for w in scope["wont_build"]]
        else:
            lines.append("_Nothing listed._")
        ce = scope["ceilings"]
        hours = "not set" if ce["build_hours"] is None else f"{ce['build_hours']:g} hours"
        budget = "not set" if ce["budget_usd"] is None else f"${ce['budget_usd']:g}"
        lines += ["", "## Ceilings (plan, for the founder to confirm)", "",
                  f"- Time: {hours} `ASSUMPTION`", f"- Budget: {budget} `ASSUMPTION`"]
        if ce["basis"]:
            lines.append(f"- Basis: {ce['basis']}")
        if scope["risks"]:
            lines += ["", "## Where this MVP cannot deliver the promise", ""] + [f"- {r}" for r in scope["risks"]]
        if scope["notes"]:
            lines += ["", "## Scope rules applied by code", ""] + [f"- {n}" for n in scope["notes"]]
        return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ 3.2 Build and test
class BuildAndTest(StepHandler):
    def generate(self, ctx: StepContext) -> StepOutput:
        scope = ctx.prior("3.1")
        if not scope.get("acceptance_criteria"):
            raise ValueError("Step 3.1 has no MVP scope with acceptance criteria yet; complete 3.1 first.")
        acceptance = scope["acceptance_criteria"]
        previous_failures, previous_files = self._previous_attempt(ctx)
        payload = {
            "product": {k: scope.get(k) for k in ("product_name", "product_kind", "uvp", "process_map",
                                                  "first_value_event")},
            "must_haves": [{k: m.get(k) for k in ("id", "feature", "user_value")} for m in scope.get("must_haves", [])],
            "acceptance_criteria": acceptance,
            "check_types": CHECK_TYPE_HELP,
            "wont_build": scope.get("wont_build", []),
            "requirements": BUILD_REQUIREMENTS,
            "previous_failures": previous_failures,
            "previous_files": previous_files,
            "feedback": ctx.feedback,
        }
        reply = builder.build_product(ctx, payload)
        files = reply["files"]
        tests = qa.run_checks(files, acceptance)
        review = qa.review_build(ctx, files, acceptance, tests)
        m = qa.metrics(tests, review["bugs"])
        failures = qa.failures_for_builder(tests, review["bugs"])
        ctx.log.append(agent="qa", action="run_acceptance_tests", action_type="RUN_TESTS", phase=ctx.phase,
                       step=ctx.step_id, model=None, cost=0, approved_by=None,
                       description=(f"Deterministic QA on build attempt {ctx.attempt}: {m['critical_passed']}/"
                                    f"{m['critical_total']} critical checks passed, {m['acceptance_met']}/"
                                    f"{m['acceptance_total']} acceptance criteria met"),
                       result={k: m[k] for k in ("critical_pass_rate", "acceptance_met_rate", "open_critical_high_bugs",
                                                 "tests_passed", "tests_total")})
        evidence = ctx.ledger.add(Evidence(
            provenance="DIRECT_OBSERVATION", source_type="qa_test_run",
            title=(f"Build test run, step 3.2 attempt {ctx.attempt}: {m['critical_passed']}/{m['critical_total']} "
                   f"critical checks passed; {m['acceptance_met']}/{m['acceptance_total']} acceptance criteria met"),
            excerpt="; ".join(f"{t['id']} {'PASS' if t['passed'] else 'FAIL'}" for t in tests),
            value=m["critical_pass_rate"], unit="share of critical checks passed", denominator=m["critical_total"],
            observed_at=utc_now(), method="deterministic checks in agents/qa.py on the built files",
            limitations="Static checks of the files; they do not observe real users."))
        observed = {"critical_pass_rate": m["critical_pass_rate"], "acceptance_met_rate": m["acceptance_met_rate"],
                    "open_critical_high_bugs": float(m["open_critical_high_bugs"])}
        state = READY if all(v is not None for v in observed.values()) else INSUFFICIENT_DATA
        observation = Observation(
            observed=observed, measurement_state=state, evidence_ids=[evidence.evidence_id],
            details={"tests": [f"{t['id']} {'PASS' if t['passed'] else 'FAIL'}"
                               f"{' (critical)' if t['critical'] else ''}"
                               f"{'' if t['passed'] else ': ' + t['detail'][:120]}" for t in tests],
                     "attempt": ctx.attempt,
                     "model_review": review.get("note") or f"{len(review['bugs'])} bug(s) reported ({qa.MODEL_REVIEW})"},
            notes=(f"Deterministic QA run, attempt {ctx.attempt}: {m['critical_passed']}/{m['critical_total']} critical "
                   f"checks, {m['acceptance_met']}/{m['acceptance_total']} acceptance criteria, "
                   f"{m['open_critical_high_bugs']} open critical/high bug(s) ({qa.MODEL_REVIEW})"))

        size = sum(len(c.encode("utf-8")) for c in files.values())
        product_name = reply.get("product_name") or scope.get("product_name") or "MVP"
        data = {"product_name": product_name, "product_kind": scope.get("product_kind", "web_tool"),
                "product_files": sorted(files), "size_bytes": size, "metrics": m, "failed_tests": failures,
                "model_review": {"available": review.get("available", False), "note": review.get("note", ""),
                                 "bugs": review["bugs"]},
                "build_notes": reply.get("notes", ""), "dropped_paths": reply.get("dropped_paths", [])}
        report = self._test_report(ctx, product_name, tests, review, m)
        out_files = dict(files)
        out_files["test_report.md"] = report
        out_files["test_results.json"] = json.dumps({"attempt": ctx.attempt, "metrics": m, "tests": tests,
                                                     "model_review": review["bugs"]}, indent=2, ensure_ascii=False)
        passed_all = not [t for t in tests if t["critical"] and not t["passed"]] and m["acceptance_met_rate"] == 1.0 \
            and m["open_critical_high_bugs"] == 0
        summary = (f"Built {len(files)} file(s) for '{product_name}' and ran {m['tests_total']} checks: "
                   f"{m['critical_passed']}/{m['critical_total']} critical passed, {m['acceptance_met']}/"
                   f"{m['acceptance_total']} acceptance criteria met." +
                   ("" if passed_all else f" {len(failures)} failure(s) to fix."))
        claim = Claim(text=(f"Attempt {ctx.attempt}: {m['critical_passed']}/{m['critical_total']} critical checks passed, "
                            f"{m['acceptance_met']}/{m['acceptance_total']} acceptance criteria met, "
                            f"{m['open_critical_high_bugs']} open critical/high {qa.MODEL_REVIEW} bug(s)."),
                      label="SOURCED", evidence_ids=[evidence.evidence_id], basis="deterministic test run")
        return StepOutput(title=f"{product_name} (attempt {ctx.attempt})",
                          markdown=self._render(product_name, files, tests, review, m, failures, reply, passed_all),
                          data=data, files=out_files, claims=[claim], summary=summary, observation=observation)

    @staticmethod
    def _previous_attempt(ctx: StepContext) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """On a repeat: the failures of the last attempt and (if small) its files, so the builder fixes them."""
        if ctx.attempt <= 0:
            return [], {}
        failures = list(ctx.prior("3.2").get("failed_tests") or [])
        files = _product_files(ctx)
        if sum(len(c) for c in files.values()) > PREVIOUS_FILES_LIMIT:
            files = {}
        return failures, files

    @staticmethod
    def _tests_table(tests: list[dict[str, Any]]) -> list[str]:
        lines = ["| ID | Description | Critical | Result | Detail |", "|---|---|---|---|---|"]
        for t in tests:
            lines.append(f"| {t['id']} | {_cell(t['description'], 120)} | {'yes' if t['critical'] else 'no'} | "
                         f"{'PASS' if t['passed'] else 'FAIL'} | {_cell(t['detail'], 160)} |")
        return lines

    @staticmethod
    def _bugs_table(bugs: list[dict[str, Any]]) -> list[str]:
        lines = ["| ID | Bug | Severity | Reproduction | Counts toward the gate |", "|---|---|---|---|---|"]
        for b in bugs:
            lines.append(f"| {b['id']} | {_cell(b['title'], 100)} | {b['severity']} | {_cell(b['reproduction'], 140)} | "
                         f"{'yes' if b.get('counts') else 'no (not critical/high with a concrete reproduction)'} |")
        return lines

    def _metrics_lines(self, m: dict[str, Any]) -> list[str]:
        return ["| Metric | Result | Locked threshold |", "|---|---|---|",
                f"| Critical checks passed | {m['critical_passed']}/{m['critical_total']} "
                f"({_pct(m['critical_pass_rate'])}) | 100% |",
                f"| Acceptance criteria met | {m['acceptance_met']}/{m['acceptance_total']} "
                f"({_pct(m['acceptance_met_rate'])}) | 100% |",
                f"| Open critical/high bugs ({qa.MODEL_REVIEW}) | {m['open_critical_high_bugs']} | 0 |"]

    def _render(self, name: str, files: dict[str, str], tests: list[dict[str, Any]], review: dict[str, Any],
                m: dict[str, Any], failures: list[dict[str, Any]], reply: dict[str, Any], passed_all: bool) -> str:
        if passed_all:
            head = (f"**ALL CHECKS REQUIRED BY GATE T PASS:** {m['critical_passed']}/{m['critical_total']} critical, "
                    f"{m['acceptance_met']}/{m['acceptance_total']} acceptance criteria, 0 open critical/high bugs.")
        else:
            head = (f"**TESTS FAILING:** {m['critical_passed']}/{m['critical_total']} critical checks passed "
                    f"({_pct(m['critical_pass_rate'])}), {m['acceptance_met']}/{m['acceptance_total']} acceptance "
                    f"criteria met, {m['open_critical_high_bugs']} open critical/high bug(s).")
        lines = [head, "", "## Gate T metrics (thresholds fixed by system policy)", ""] + self._metrics_lines(m)
        if failures:
            lines += ["", "## Failures to fix", ""]
            lines += [f"- **{f['id']}** {f['description']}: {f['detail']}" for f in failures]
        lines += ["", "## Test results (deterministic, agents/qa.py)", ""] + self._tests_table(tests)
        lines += ["", f"## Model review ({qa.MODEL_REVIEW})", ""]
        if review.get("note"):
            lines.append(review["note"])
        elif review["bugs"]:
            lines += ["A model read the files and reported these bugs. Only critical/high bugs with a concrete "
                      "reproduction count toward the gate; deterministic checks stay authoritative.", ""]
            lines += self._bugs_table(review["bugs"])
        else:
            lines.append("No bugs reported.")
        lines += ["", "## Built files", "", "| File | Size |", "|---|---|"]
        lines += [f"| `{n}` | {len(c.encode('utf-8'))} bytes |" for n, c in sorted(files.items())]
        lines += ["", f"Open `{qa.INDEX}` from this step's artifacts in a browser to try it. It makes no network "
                      "requests and keeps its data in that browser only."]
        if reply.get("dropped_paths"):
            lines += ["", f"Files outside `product/` were dropped: {', '.join(reply['dropped_paths'])}"]
        if reply.get("notes"):
            lines += ["", "## Builder notes", "", reply["notes"]]
        return "\n".join(lines) + "\n"

    def _test_report(self, ctx: StepContext, name: str, tests: list[dict[str, Any]], review: dict[str, Any],
                     m: dict[str, Any]) -> str:
        lines = [f"# Test report: {name}", "", f"Step 3.2, attempt {ctx.attempt}, run `{ctx.run_id}`, {utc_now()}", "",
                 "Deterministic checks run by code (agents/qa.py). No test is skipped.", ""]
        lines += self._metrics_lines(m) + ["", "## Tests", ""] + self._tests_table(tests)
        lines += ["", f"## Model review ({qa.MODEL_REVIEW})", ""]
        lines += [review["note"]] if review.get("note") else (self._bugs_table(review["bugs"]) if review["bugs"]
                                                              else ["No bugs reported."])
        return "\n".join(lines) + "\n"

    def default_contract(self, ctx: StepContext) -> Contract:
        return Contract(
            step_id="3.2", decision="Ship the build to user testing (3.3), fix it (repeat), or rescope (3.1)",
            hypothesis="The build meets every acceptance criterion from 3.1 and passes every critical check.",
            criteria=[
                Criterion(key="critical_pass_rate", label="Critical checks passed", op=">=", target=1.0,
                          unit="share", kind="hard"),
                Criterion(key="acceptance_met_rate", label="Acceptance criteria met", op=">=", target=1.0,
                          unit="share", kind="hard"),
                Criterion(key="open_critical_high_bugs", label="Open critical/high bugs", op="<=", target=0,
                          unit="bugs", kind="hard"),
            ],
            pivot_target="3.1", notes="Test-gate policy: 100% critical checks, every acceptance criterion, no open "
                                      "critical/high bugs. Failing tests are fixed and re-run, never skipped.")

    def collect(self, ctx: StepContext, contract: Contract) -> Observation | None:
        return None   # the test run happens during generate(); without it there is nothing to observe


# ------------------------------------------------------------------ 3.3 User test and docs
class UserTestAndDocs(StepHandler):
    def generate(self, ctx: StepContext) -> StepOutput:
        files = _product_files(ctx)
        index = files.get(qa.INDEX, "")
        if not index.strip():
            raise ValueError("Step 3.2 has no built product/index.html; complete 3.2 first.")
        scope, build = ctx.prior("3.1"), ctx.prior("3.2")
        inventory = qa.ui_inventory(index)
        concept = ctx.concept()
        non_critical = [f for f in build.get("failed_tests") or [] if not f.get("critical")]
        payload = {
            "product": {"name": build.get("product_name") or scope.get("product_name"), "uvp": scope.get("uvp"),
                        "first_value_event": scope.get("first_value_event"),
                        "must_haves": [{k: m.get(k) for k in ("id", "feature", "user_value")}
                                       for m in scope.get("must_haves", [])],
                        "wont_build": scope.get("wont_build", [])},
            "built_files": {name: (content if len(content) <= 30000 else content[:30000] + "\n...(truncated)")
                            for name, content in files.items()},
            "ui_inventory": inventory,
            "build_test_summary": {"metrics": build.get("metrics"), "open_non_critical_issues": non_critical},
            "target_users": concept.get("segment") or ctx.brief.get("customer"),
            "waitlist_step_2_2": _trim(ctx.prior("2.2"), 1200),
            "participants_target": PARTICIPANTS_MIN,
            "support_contact_placeholder": SUPPORT_PLACEHOLDER,
            "feedback": ctx.feedback,
        }
        docs = doc_writer.user_docs(ctx, payload)
        name = payload["product"]["name"] or "the product"
        limitations = self._limitations(docs, scope, non_critical, inventory)
        label_warnings = self._label_warnings(docs, qa.searchable_text(index))
        goal_warnings = [f"{t['id']}: goal may lead the participant ('{m.group(0)}'): {t['neutral_goal']}"
                         for t in docs["usability_test"]["tasks"] if (m := _LEADING_WORDS.search(t["neutral_goal"]))]
        invite = self._invite(docs, name)
        out_files = {
            "docs/quick-start.md": self._quick_start(docs, name, inventory),
            "docs/faq.md": self._faq(docs, name),
            "docs/how-to.md": self._how_to(docs, name),
            "docs/limitations.md": self._limitations_md(limitations, name),
            "usability_test_plan.md": self._plan(docs, name, scope, goal_warnings),
            "usability_session_template.csv": ("participant_id,task_id,phase,completed,time_to_first_value_seconds,"
                                               "assistance_given,critical_failure,errors_observed,friction_notes,"
                                               "verbatim_quote_with_consent\n"),
            "usability_invite.md": invite,
        }
        outward = [{"kind": "send", "item_id": "usability-invite", "file": "usability_invite.md",
                    "when": "before_collect", "target_name": "usability-invite.md"}]
        marketing = "\n\n".join(out_files[n] for n in (*DOC_FILES, "usability_invite.md"))
        warnings = label_warnings + goal_warnings
        questions = []
        if SUPPORT_PLACEHOLDER in out_files["docs/faq.md"]:
            questions.append("Which support contact should the docs show (an address or page you control)?")
        questions.append(f"Can you reach at least {PARTICIPANTS_MIN} target users from the waitlist for "
                         "20-30 minute sessions within the test window?")
        data = {"product_name": name, "docs": list(DOC_FILES), "usability_plan": "usability_test_plan.md",
                "participants_target": PARTICIPANTS_MIN, "tasks": docs["usability_test"]["tasks"],
                "limitations": limitations, "doc_warnings": warnings, "outward": outward}
        summary = (f"Wrote quick-start, FAQ, {len(docs['how_to'])} how-to guide(s) and {len(limitations)} known "
                   f"limitation(s) from the actual 3.2 build, plus a usability-test plan for >= {PARTICIPANTS_MIN} "
                   "target users. No sessions have run yet.")
        return StepOutput(title=f"{name}: docs and usability-test plan",
                          markdown=self._render(docs, name, limitations, warnings, out_files), data=data,
                          files=out_files, summary=summary, questions=questions[:3], marketing_text=marketing)

    # --- deterministic additions and checks
    @staticmethod
    def _limitations(docs: dict[str, Any], scope: dict[str, Any], non_critical: list[dict[str, Any]],
                     inventory: dict[str, Any]) -> list[str]:
        items = list(docs["limitations"])
        if inventory.get("uses_local_storage"):
            items.append("Your data is saved only in this browser on this device (localStorage). It does not sync "
                         "between devices, and clearing browser data deletes it: export regularly.")
        items += [f"Not included in this version: {w['feature']}" for w in scope.get("wont_build", [])]
        items += [f"Open issue from build tests ({f['id']}): {f['description']} ({f['detail']})" for f in non_critical]
        out: list[str] = []
        for item in items:
            if item and item.lower() not in {o.lower() for o in out}:
                out.append(item)
        return out[:25]

    @staticmethod
    def _label_warnings(docs: dict[str, Any], product_text: str) -> list[str]:
        """UI labels the docs mention in bold or quotes that do not appear anywhere in the built product."""
        haystack = product_text.lower()
        texts = list(docs["quick_start"]["steps"]) + [s for h in docs["how_to"] for s in h["steps"]]
        missing: list[str] = []
        for text in texts:
            for match in _UI_LABEL.finditer(text):
                label = match.group(1).strip()
                if label and label.lower() not in haystack and label not in missing:
                    missing.append(label)
        return [f"The docs mention '{label}', which does not appear in the built product." for label in missing]

    # --- rendering
    @staticmethod
    def _quick_start(docs: dict[str, Any], name: str, inventory: dict[str, Any]) -> str:
        q = docs["quick_start"]
        lines = [f"# Quick start: {name}", ""]
        if q["intro"]:
            lines += [q["intro"], ""]
        lines += ["## Steps", ""] + [f"{i}. {s}" for i, s in enumerate(q["steps"], start=1)]
        if q["first_value"]:
            lines += ["", "## Your first result", "", q["first_value"]]
        lines += ["", "## Where your data lives", ""]
        if inventory.get("uses_local_storage"):
            lines.append("Everything you enter is saved only in this browser on this device. Nothing is sent "
                         "anywhere. Clearing your browser data deletes it.")
        else:
            lines.append("The tool makes no network requests: nothing you enter leaves your device.")
        lines += ["", "More: [How-to guides](how-to.md) | [FAQ](faq.md) | [Known limitations](limitations.md)"]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _faq(docs: dict[str, Any], name: str) -> str:
        lines = [f"# FAQ: {name}", ""]
        for item in docs["faq"]:
            lines += [f"### {item['q']}", "", item["a"] or "-", ""]
        if not docs["faq"]:
            lines += ["_No questions yet. Add the ones users ask during the usability sessions._", ""]
        lines += ["## How to get help", "", docs["help"] or f"Contact the founder: {SUPPORT_PLACEHOLDER}"]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _how_to(docs: dict[str, Any], name: str) -> str:
        lines = [f"# How-to guides: {name}", ""]
        for flow in docs["how_to"]:
            lines += [f"## {flow['flow']}", ""]
            if flow["goal"]:
                lines += [flow["goal"], ""]
            lines += [f"{i}. {s}" for i, s in enumerate(flow["steps"], start=1)]
            if flow["result"]:
                lines += ["", f"**Result:** {flow['result']}"]
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _limitations_md(limitations: list[str], name: str) -> str:
        lines = [f"# Known limitations: {name}", ""]
        lines += [f"- {item}" for item in limitations] or ["- None recorded yet."]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _invite(docs: dict[str, Any], name: str) -> str:
        invite = docs["invite"]
        subject = invite["subject"] or f"Would you try {name} for 20 minutes?"
        body = invite["body"] or (
            "Hi [first name],\n\nYou joined the waitlist for " + name + ". I am testing an early version and would "
            "value 20-30 minutes of your time while you try one task with it. I will watch how it works for you, not "
            "test you. Nothing is sold during the session.\n\nWould one of these times work: [times]?\n\n[Founder name]")
        return ("DRAFT for the founder to review and send from their own account. MOCKED: this system never sends it.\n\n"
                f"Subject: {subject}\n\n{body}\n")

    @staticmethod
    def _plan(docs: dict[str, Any], name: str, scope: dict[str, Any], goal_warnings: list[str]) -> str:
        test = docs["usability_test"]
        rec = test["recruiting"]
        fve = (scope.get("first_value_event") or {}).get("event") or "the core task"
        lines = [f"# Usability test plan: {name}", "",
                 "Status: plan only. No sessions have run. Results come only from sessions the founder actually runs.",
                 "", "## Locked criteria (proposed; locked with the founder before any session)", "",
                 f"- At least {PARTICIPANTS_MIN} target users take part (sample floor).",
                 f"- At least {UNASSISTED_TARGET:.0%} complete the core task ({fve}) in the silent phase, without help.",
                 "- No critical failures.", "",
                 "This is a small formative round: report it as 'k of n completed unassisted', with its limits.", "",
                 f"## Who to recruit (at least {PARTICIPANTS_MIN})", "",
                 f"- From the waitlist (step 2.2): {rec['from_waitlist'] or 'invite waitlist sign-ups who match the screening criteria.'}",
                 f"- Second route: {rec['other_route'] or 'not specified'}"]
        if rec["screening"]:
            lines += ["- Screening criteria:"] + [f"  - {s}" for s in rec["screening"]]
        lines += ["- Consent: ask before recording anything. Notes use a participant ID (P1, P2, ...), never names or "
                  "contact details.", "",
                  "## Session protocol", "",
                  f"1. Setup: open `{qa.INDEX}` from the step 3.2 build in a fresh browser profile (empty data).",
                  "2. Silent phase: read the neutral goal aloud, then do not help, hint or point. Note where the "
                  "participant hesitates. Stop at the time limit or when they give up.",
                  "3. Assisted phase: only after the silent phase. Record every hint. A task finished after a hint "
                  "counts as assisted, not unassisted.",
                  "4. Debrief: ask what they expected to happen and what they did the last time they had this job "
                  "(past behaviour, not 'would you...').", "",
                  "## Tasks", "", "| ID | Neutral goal (read aloud) | Success criterion | Realistic data | Time limit | Core |",
                  "|---|---|---|---|---|---|"]
        for t in test["tasks"]:
            lines.append(f"| {t['id']} | {_cell(t['neutral_goal'])} | {_cell(t['success_criterion'])} | "
                         f"{_cell(t['realistic_data'])} | {t['max_minutes']:g} min | {'yes' if t['core'] else 'no'} |")
        lines += ["", "## What to record (per participant and task; template: usability_session_template.csv)", "",
                  "- Completed in the silent phase without help (yes/no)",
                  "- Time to first value (seconds)",
                  "- Assistance given (what hint, when)",
                  "- Critical failure (yes/no, what happened)",
                  "- Errors and recurring friction",
                  "- Why a failure happened and what the participant would have used instead",
                  "- Verbatim quotes only with consent; never paraphrase a quote as if it were verbatim", "",
                  "## Critical failure definition", "",
                  test["critical_failure_definition"] or ("The participant cannot reach the first-value event, loses "
                                                          "or corrupts their data, or is misled into a wrong result."),
                  ""]
        if test["moderator_notes"]:
            lines += ["## Moderator notes", ""] + [f"- {n}" for n in test["moderator_notes"]] + [""]
        lines += ["## How results enter the gate", "",
                  "Submit: participants, completed_unassisted (core task, silent phase), critical_failures and session "
                  "notes. Code computes the completion rate and its Wilson 95% interval; the locked thresholds decide "
                  "the outcome."]
        if goal_warnings:
            lines += ["", "## Check these task goals", ""] + [f"- {w}" for w in goal_warnings]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render(docs: dict[str, Any], name: str, limitations: list[str], warnings: list[str],
                files: dict[str, str]) -> str:
        lines = ["## User docs (written from the actual 3.2 build)", "", "| File | What it covers |", "|---|---|",
                 "| `docs/quick-start.md` | First steps to the first result |",
                 "| `docs/faq.md` | Questions and answers, how to get help |",
                 f"| `docs/how-to.md` | {len(docs['how_to'])} core flow(s): "
                 f"{_cell(', '.join(h['flow'] for h in docs['how_to']), 150)} |",
                 f"| `docs/limitations.md` | {len(limitations)} known limitation(s) |", "",
                 "## Quick start preview", "", _demote(files["docs/quick-start.md"].split("\n", 2)[-1].strip()), ""]
        if warnings:
            lines += ["## Doc checks (fix before approving)", ""] + [f"- {w}" for w in warnings] + [""]
        lines += ["## Usability test", "",
                  f"Plan: `usability_test_plan.md` ({len(docs['usability_test']['tasks'])} task(s), at least "
                  f"{PARTICIPANTS_MIN} target users, silent then assisted phase). Record sessions with "
                  "`usability_session_template.csv`.", "",
                  "**Invitation (MOCKED send):** `usability_invite.md` is a draft for you to send from your own "
                  "account. Approving it when you lock the thresholds only writes it to the local outbox; nothing is "
                  "sent.", "",
                  "## Next", "",
                  "1. Lock the thresholds (and approve the invitation draft if you want it in the outbox).",
                  f"2. Run the sessions with at least {PARTICIPANTS_MIN} target users.",
                  "3. Submit what you observed. With no sessions, the gate stays WAITING_FOR_DATA."]
        return "\n".join(lines) + "\n"

    # --- evidence gate
    def default_contract(self, ctx: StepContext) -> Contract:
        fve = (ctx.prior("3.1").get("first_value_event") or {}).get("event") or "the core task"
        return Contract(
            step_id="3.3", decision="Accept the docs and move to Phase 4, fix the build (3.2), or rethink the solution (2.1)",
            hypothesis=(f"At least {UNASSISTED_TARGET:.0%} of at least {PARTICIPANTS_MIN} target users reach the "
                        f"first-value event ({fve}) without help, with no critical failures."),
            criteria=[
                Criterion(key="participants", label="Target users tested", op=">=", target=PARTICIPANTS_MIN,
                          unit="users", kind="floor"),
                Criterion(key="unassisted_completion_rate", label="Completed the core task without help", op=">=",
                          target=UNASSISTED_TARGET, unit="share", kind="proportion"),
                Criterion(key="critical_failures", label="Critical failures observed", op="<=", target=0,
                          unit="failures", kind="hard"),
            ],
            window_days=14, pivot_target="2.1",
            notes="Formative usability round. Completion counts only the silent (unassisted) phase.")

    def collect(self, ctx: StepContext, contract: Contract) -> Observation | None:
        return None   # only the founder can observe the sessions

    def data_fields(self) -> list[DataField]:
        return [
            DataField("participants", "Target users who took part", type="integer",
                      help="Count only people who match the target segment."),
            DataField("completed_unassisted", "Completed the core task without help", type="integer",
                      help="Silent phase only; a task finished after a hint counts as assisted."),
            DataField("critical_failures", "Critical failures observed", type="integer",
                      help="Could not reach the first result, lost or corrupted data, or was misled."),
            DataField("session_notes", "Session notes", type="text", required=False,
                      help="What happened, why failures occurred, friction. Participant IDs only, no names."),
        ]

    def observe(self, ctx: StepContext, contract: Contract, data: dict[str, Any]) -> Observation:
        notes_text = str(data.get("session_notes") or "").strip()
        values: dict[str, int] = {}
        problems: list[str] = []
        for key in ("participants", "completed_unassisted", "critical_failures"):
            raw = data.get(key)
            if raw in (None, ""):
                continue
            number = as_float(raw)
            if number is None or number < 0 or number != int(number):
                problems.append(f"{key} must be a whole number of at least 0 (got {raw!r})")
                continue
            values[key] = int(number)
        n, k, failures = values.get("participants"), values.get("completed_unassisted"), values.get("critical_failures")
        if n is not None and k is not None and k > n:
            problems.append(f"completed_unassisted ({k}) cannot exceed participants ({n})")
        if n is not None and failures is not None and failures > 0 and n == 0:
            problems.append("critical failures were reported with 0 participants")
        keys = [c.key for c in contract.criteria]
        if problems:
            return Observation(observed={key: None for key in keys}, measurement_state=INVALID_DATA,
                               details={"source": "founder_data", "problems": problems},
                               notes="Invalid founder data: " + "; ".join(problems))
        if n == 0:
            return Observation(observed={key: None for key in keys}, measurement_state=WAITING_FOR_DATA,
                               details={"source": "founder_data", "missing": keys},
                               notes="No sessions run yet (0 participants): the gate waits for real sessions.")
        rate = round(k / n, 4) if (n and k is not None) else None
        low, high = wilson_interval(k, n) if rate is not None else (None, None)
        computed = {"participants": None if n is None else float(n), "unassisted_completion_rate": rate,
                    "critical_failures": None if failures is None else float(failures)}
        observed = {key: computed.get(key) for key in keys}
        missing = [key for key, value in observed.items() if value is None]
        state = READY if not missing else (WAITING_FOR_DATA if len(missing) == len(keys) else INSUFFICIENT_DATA)
        evidence_ids: list[str] = []
        if rate is not None:
            row = ctx.ledger.add(Evidence(
                provenance="FOUNDER_REPORTED", source_type="founder_data",
                title=(f"Usability test (step 3.3): {k} of {n} target users completed the core task unassisted"
                       + (f"; {failures} critical failure(s)" if failures is not None else "")),
                excerpt=notes_text[:600], value=rate, unit="share completed unassisted", denominator=float(n),
                observed_at=utc_now(), method="moderated sessions run by the founder (silent, then assisted phase)",
                population=str(ctx.concept().get("segment") or ""),
                limitations="Small formative sample, reported by the founder; not observed by the system."))
            evidence_ids.append(row.evidence_id)
        pivot = None
        rate_target = next((c.target for c in contract.criteria if c.key == "unassisted_completion_rate"), UNASSISTED_TARGET)
        if failures and rate is not None and rate >= rate_target:
            pivot = "3.2"   # users reach the value but something breaks: an execution flaw, fix the build
        summary = (f"Founder-reported usability sessions: {k} of {n} completed unassisted ({_pct(rate)}; Wilson 95% "
                   f"interval {_pct(low)}-{_pct(high)}); {failures} critical failure(s)." if rate is not None
                   else "Founder-reported usability data is incomplete.")
        return Observation(
            observed=observed, measurement_state=state, evidence_ids=evidence_ids,
            details={"source": "founder_data", "participants": n, "completed_unassisted": k,
                     "critical_failures": failures, "wilson_95": [low, high] if rate is not None else None,
                     "sample_note": "Formative round: report as 'k of n'; the interval shows how uncertain it is.",
                     "session_notes": notes_text[:500], "missing": missing},
            notes=summary, pivot_target=pivot)
