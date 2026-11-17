"""Founder web app (FastAPI + Jinja2, server-rendered, minimal JS, no CDNs).

Dashboard: start a venture, follow the run, answer whatever the pipeline is
waiting for (lock thresholds, submit data, approve/reject/decide, phase-exit
review), read every artifact, the decision log and the evidence ledger.

Local public pages: the MOCKED site (/site/...) serves only files the founder
approved for publishing; /p/... records first-party events (page views, CTA
clicks, waitlist sign-ups with hashed emails) and runs the MOCKED order flow:
no payment is ever taken, no provider is contacted, no card data exists.

Run: uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import markdown as md_lib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import checkout
import delivery
import payments
import reconcile as reconcile_mod
import webhooks
from commerce import CommerceError, CommerceStore, email_hash, valid_email
from config import ROOT
from gates import GateError
from orchestrator import FounderActionError, Orchestrator
from steps import PHASE_NAMES, STEP_IDS, STEPS, STEPS_BY_ID, get_handler, steps_in_phase

log = logging.getLogger("venture_validator.web")

app = FastAPI(title="Venture Validator", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))

MAX_BODY = 256 * 1024          # bytes for any request body
MAX_EVENT_BODY = 4 * 1024      # bytes for one analytics event
MAX_FIELD = 5000               # characters kept per form field
MAX_ARTIFACT_CHARS = 300_000   # characters shown per artifact
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
EVENT_TYPES = ("page_view", "cta_click")
EVENT_FIELDS = ("source", "visitor_id", "variant", "cta", "package_id", "product_id", "plan", "referrer_type")
BRIEF_FIELDS = ("title", "idea", "customer", "why_you", "jurisdiction", "budget", "time", "evidence", "values")
TRUTHY = ("on", "1", "true", "yes")
MOCKED_ITEMS = [
    ("Checkout and payments", "Order requests and settlement records are simulated. No money moves, no payment "
                              "provider is contacted and no card or bank data is collected."),
    ("Delivery emails", "Confirmation emails go to a local outbox and are not sent."),
    ("Publishing", "Approved pages are written to a local mock site (/site/...), not the internet."),
    ("Posts and messages", "Approved posts go to a local outbox for the founder to send manually."),
    ("Refunds and payouts", "Bookkeeping records only; nothing is paid back or paid out."),
]

# ---------------------------------------------------------------------------------------------- orchestrator
ORCH: Orchestrator | None = None
ADVANCE_MODE = "thread"   # "thread" (default), "sync" (tests: advance inline), "off" (never advance)
_ADV_GUARD = threading.Lock()
_ADV_RUNNING: set[str] = set()
_ADV_AGAIN: set[str] = set()
_EVENT_LOCK = threading.Lock()


def get_orchestrator() -> Orchestrator:
    global ORCH
    if ORCH is None:
        ORCH = Orchestrator()
    return ORCH


def is_advancing(run_id: str) -> bool:
    with _ADV_GUARD:
        return run_id in _ADV_RUNNING


def schedule_advance(orch: Orchestrator, run_id: str) -> None:
    """Advance a run in one daemon thread per run; a request during a run queues one more pass."""
    if ADVANCE_MODE == "off":
        return
    if ADVANCE_MODE == "sync":
        orch.advance(run_id)
        return
    with _ADV_GUARD:
        if run_id in _ADV_RUNNING:
            _ADV_AGAIN.add(run_id)
            return
        _ADV_RUNNING.add(run_id)

    def work() -> None:
        while True:
            try:
                orch.advance(run_id)
            except Exception:  # noqa: BLE001 - the orchestrator already surfaces errors as a retry prompt
                log.exception("advance failed for %s", run_id)
            with _ADV_GUARD:
                if run_id in _ADV_AGAIN:
                    _ADV_AGAIN.discard(run_id)
                    continue
                _ADV_RUNNING.discard(run_id)
                return

    threading.Thread(target=work, name=f"advance-{run_id}", daemon=True).start()


# ---------------------------------------------------------------------------------------------- rendering helpers
class _ScrubLinks(Treeprocessor):
    SAFE = ("http", "https", "mailto", "")

    def run(self, root):  # noqa: D401 - markdown API
        for element in root.iter():
            for attr in ("href", "src"):
                value = element.get(attr)
                if value is not None and urlparse(value.strip()).scheme.lower() not in self.SAFE:
                    element.set(attr, "#")
            if element.tag == "a" and element.get("href", "").startswith(("http://", "https://")):
                element.set("rel", "noopener noreferrer")
        return None


class _NoRawHtml(Extension):
    """Raw HTML in model-written markdown is shown as text, and only safe link schemes survive."""

    def extendMarkdown(self, md):  # noqa: N802 - markdown API
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_ScrubLinks(md), "vv_scrub_links", 0)


def render_markdown(text: str | None) -> Markup:
    html = md_lib.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists", _NoRawHtml()])
    return Markup(html)  # noqa: S704 - raw HTML disabled above; output is built by the markdown library


def safe_url(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text.startswith(("http://", "https://")) else None


templates.env.filters["markdown"] = render_markdown
templates.env.filters["safe_url"] = safe_url
templates.env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, ensure_ascii=False, default=str)
templates.env.globals["PHASE_NAMES"] = PHASE_NAMES
templates.env.globals["MOCKED_ITEMS"] = MOCKED_ITEMS


def page(request: Request, name: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def public_page(request: Request, *, title: str, message: str, status_code: int = 200, **extra: Any) -> HTMLResponse:
    return page(request, "page.html", {"title": title, "message": message, **extra}, status_code)


# ---------------------------------------------------------------------------------------------- validation
def check_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id or "") or ".." in run_id:
        raise HTTPException(status_code=404, detail="Unknown run")
    return run_id


def load_run(orch: Orchestrator, run_id: str):
    check_run_id(run_id)
    if not orch.store.exists(run_id):
        raise HTTPException(status_code=404, detail="Unknown run")
    return orch.store.load(run_id)


def check_step(step_id: str):
    meta = STEPS_BY_ID.get(step_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Unknown step")
    return meta


def inside(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


async def read_form(request: Request):
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="Request too large")
    return await request.form(max_files=0, max_fields=400)


def field(form, key: str, limit: int = MAX_FIELD) -> str:
    value = form.get(key)
    return value.strip()[:limit] if isinstance(value, str) else ""


def is_internal(request: Request) -> bool:
    return request.cookies.get("vv_founder") == "1" or request.query_params.get("internal") == "1"


def clean_text(value: Any, limit: int = 80) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or "")).strip()
    return text[:limit]


# ---------------------------------------------------------------------------------------------- middleware
@app.middleware("http")
async def limits_and_headers(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_BODY):
        return PlainTextResponse("Request too large", status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    path = request.url.path
    if (not path.startswith(("/p/", "/site/", "/static/"))
            and response.headers.get("content-type", "").startswith("text/html")):
        # The founder's own browser: their visits to the local pages count as internal traffic.
        response.set_cookie("vv_founder", "1", max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/p/") and "json" in request.headers.get("content-type", ""):
        return JSONResponse({"ok": False, "error": str(exc.detail)}, status_code=exc.status_code)
    return public_page(request, title=f"Error {exc.status_code}", message=str(exc.detail),
                       status_code=exc.status_code)


# ---------------------------------------------------------------------------------------------- dashboard
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    orch = get_orchestrator()
    runs = await run_in_threadpool(orch.store.list)
    rows = [{"run": r, "status_line": orch.status_line(r), "pending": (r.pending or {}).get("kind")} for r in runs]
    models = orch.settings.describe_models()
    return page(request, "index.html", {"rows": rows, "models": models,
                                        "has_models": bool(models.get("main") or models.get("fast")),
                                        "error": clean_text(request.query_params.get("error"), 500)})


@app.post("/runs")
async def create_run(request: Request):
    orch = get_orchestrator()
    form = await read_form(request)
    brief = {key: field(form, key) for key in BRIEF_FIELDS if field(form, key)}
    if not brief.get("idea"):
        return RedirectResponse("/?error=" + quote("Describe the idea to start a venture."), status_code=303)
    run = await run_in_threadpool(orch.create_run, brief, title=brief.get("title") or None)
    await run_in_threadpool(schedule_advance, orch, run.run_id)
    return RedirectResponse(f"/runs/{run.run_id}", status_code=303)


def timeline(run) -> list[dict[str, Any]]:
    rows = []
    for meta in STEPS:
        st = run.steps.get(meta.step_id)
        rows.append({"meta": meta, "status": st.status if st else "NEW", "outcome": st.outcome if st else None,
                     "overridden": bool(st and st.overridden), "attempt": st.attempt if st else 0,
                     "current": run.current_step == meta.step_id})
    return rows


def read_artifact(orch: Orchestrator, run_id: str, rel: str) -> str | None:
    path = orch.store.artifact_path(run_id, rel)
    if not inside(orch.store.path(run_id), path) or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")[:MAX_ARTIFACT_CHARS]


def decision_context(orch: Orchestrator, run, step_id: str) -> dict[str, Any]:
    meta = STEPS_BY_ID[step_id]
    st = run.steps[step_id]
    gate_md = read_artifact(orch, run.run_id, st.artifacts["gate_report.md"]) if st.artifacts.get("gate_report.md") else None
    deliverable_md = (read_artifact(orch, run.run_id, st.artifacts["deliverable.md"])
                      if st.artifacts.get("deliverable.md") else None)
    outward = [o for o in (st.output.get("outward") or []) if o.get("when", "on_approve") == "on_approve"]
    earlier = [s for s in STEPS if STEP_IDS.index(s.step_id) < STEP_IDS.index(step_id)]
    fields = []
    if meta.has_evidence_gate and not (st.gate or {}).get("outcome"):
        try:
            fields = [asdict(f) for f in get_handler(meta).data_fields()]
        except Exception:  # noqa: BLE001 - a missing handler only hides the optional data form
            fields = []
    return {"meta": meta, "st": st, "gate_md": gate_md, "deliverable_md": deliverable_md,
            "concepts": st.output.get("concepts") or [] if step_id == "1.2" else [],
            "recommended_id": st.output.get("recommended_id"),
            "ack": st.output.get("requires_acknowledgment"), "outward": outward,
            "outward_default_checked": step_id != "5.2", "earlier": earlier, "data_fields": fields,
            "memo_recommendation": st.output.get("recommendation") if step_id == "6.3" else None}


def site_files(orch: Orchestrator, run_id: str) -> list[str]:
    folder = orch.store.path(run_id) / "site"
    return sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.exists() else []


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    if run.status == "ACTIVE" and not run.pending and not is_advancing(run_id) and ADVANCE_MODE == "thread":
        schedule_advance(orch, run_id)  # resume after a restart
    pending = run.pending or {}
    ctx: dict[str, Any] = {
        "run": run, "status_line": orch.status_line(run), "pending": pending, "timeline": timeline(run),
        "advancing": is_advancing(run_id),
        "refresh": run.status == "ACTIVE" and not run.pending,
        "error": clean_text(request.query_params.get("error"), 600),
        "notice": clean_text(request.query_params.get("notice"), 600),
        "site_files": site_files(orch, run_id),
        "brief_fields": BRIEF_FIELDS,
        "messages": run.messages[-12:],
    }
    kind = pending.get("kind")
    if kind == "decision" and pending.get("step") in run.steps:
        ctx["d"] = decision_context(orch, run, pending["step"])
    if kind in ("lock_thresholds", "submit_data") and pending.get("step") in STEPS_BY_ID:
        ctx["pmeta"] = STEPS_BY_ID[pending["step"]]
        st = run.steps[pending["step"]]
        if st.artifacts.get("deliverable.md"):
            ctx["pending_deliverable"] = read_artifact(orch, run_id, st.artifacts["deliverable.md"])
    if kind == "phase_review":
        ctx["review_steps"] = steps_in_phase(int(pending.get("phase") or 1))
    return page(request, "run.html", ctx)


def _number(value: str, key: str, integer: bool = False) -> float | int:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        raise FounderActionError(f"'{key}' must be a number.") from None
    if not math.isfinite(number):
        raise FounderActionError(f"'{key}' must be a finite number.")
    return int(number) if integer and number.is_integer() else number


def build_action(form, run) -> dict[str, Any]:
    """Map a submitted form to an orchestrator action. Raises FounderActionError on bad input."""
    kind = field(form, "kind")
    action: dict[str, Any] = {"channel": "web"}
    step = field(form, "step", 10)
    if step:
        action["step"] = step
    reason = field(form, "reason")
    if reason:
        action["reason"] = reason
    pending = run.pending or {}

    if kind == "lock_thresholds":
        targets = {}
        for key, value in form.multi_items():
            if key.startswith("targets.") and isinstance(value, str) and value.strip():
                targets[key[len("targets."):]] = float(_number(value.strip(), key[len("targets."):]))
        action.update(kind="lock_thresholds", targets=targets,
                      approve_outward=field(form, "approve_outward").lower() in TRUTHY)
    elif kind == "submit_data":
        fields = {f.get("key"): f for f in (pending.get("fields") or [])}
        if not fields and step in STEPS_BY_ID:
            try:
                fields = {f.key: asdict(f) for f in get_handler(STEPS_BY_ID[step]).data_fields()}
            except Exception:  # noqa: BLE001
                fields = {}
        data: dict[str, Any] = {}
        for key, value in form.multi_items():
            if not key.startswith("data.") or not isinstance(value, str) or not value.strip():
                continue
            name, value = key[len("data."):], value.strip()[:MAX_FIELD * 4]
            ftype = (fields.get(name) or {}).get("type", "text")
            if ftype in ("number", "integer"):
                data[name] = _number(value, name, integer=ftype == "integer")
            elif ftype == "json":
                try:
                    data[name] = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise FounderActionError(f"'{name}' must be valid JSON ({exc.msg}).") from None
            else:
                data[name] = value
        if not data:
            raise FounderActionError("Enter at least one measured value, or skip the gate with a reason.")
        action.update(kind="submit_data", data=data)
    elif kind == "skip_gate":
        if not reason:
            raise FounderActionError("Skipping a gate needs a reason; it is logged as FOUNDER_OVERRIDE.")
        action.update(kind="decide", outcome="GO")
    elif kind == "stop":
        if not reason:
            raise FounderActionError("Stopping needs a reason.")
        action.update(kind="decide", outcome="STOP")
    elif kind == "approve":
        action["kind"] = "approve"
        if field(form, "concept_id"):
            action["concept_id"] = field(form, "concept_id", 80)
        if field(form, "acknowledge").lower() in TRUTHY:
            action["acknowledge"] = True
        if field(form, "outward_present") == "1":
            action["outward_ids"] = [v for v in form.getlist("outward_ids") if isinstance(v, str)][:50]
    elif kind == "select_concept":
        action.update(kind="select_concept", concept_id=field(form, "concept_id", 80))
        if field(form, "acknowledge").lower() in TRUTHY:
            action["acknowledge"] = True
    elif kind == "reject":
        action["kind"] = "reject"  # the orchestrator requires specific feedback in "reason"
    elif kind == "decide":
        outcome = field(form, "outcome", 20).upper()
        if not reason:
            raise FounderActionError("Choosing an outcome yourself needs a reason; it is logged.")
        action.update(kind="decide", outcome=outcome)
        if outcome == "PIVOT_BACK" and field(form, "pivot_target", 10):
            action["pivot_target"] = field(form, "pivot_target", 10)
        if field(form, "acknowledge").lower() in TRUTHY:
            action["acknowledge"] = True
        if field(form, "outward_present") == "1":
            action["outward_ids"] = [v for v in form.getlist("outward_ids") if isinstance(v, str)][:50]
    elif kind == "final_decision":
        action.update(kind="decide", final_decision=field(form, "final_decision", 20).upper())
    elif kind == "phase_review":
        action.update(kind="phase_review", match=field(form, "match", 10), issues=field(form, "issues"),
                      confidence=field(form, "confidence", 3))
        if field(form, "repeat_step", 10):
            action["repeat_step"] = field(form, "repeat_step", 10)
    elif kind == "clarify_brief":
        action.update(kind="clarify_brief", brief={k: field(form, f"brief.{k}") for k in BRIEF_FIELDS})
    elif kind == "retry":
        action["kind"] = "retry"
    else:
        raise FounderActionError(f"Unknown action {kind!r}.")
    return action


@app.post("/runs/{run_id}/act")
async def act(request: Request, run_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    form = await read_form(request)
    try:
        action = build_action(form, run)
        await run_in_threadpool(orch.act, run_id, action)
    except (FounderActionError, GateError, ValueError) as exc:
        return RedirectResponse(f"/runs/{run_id}?error=" + quote(str(exc)[:500]), status_code=303)
    await run_in_threadpool(schedule_advance, orch, run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.post("/runs/{run_id}/request")
async def founder_request(request: Request, run_id: str):
    orch = get_orchestrator()
    load_run(orch, run_id)
    form = await read_form(request)
    text = field(form, "text", 2000)
    if not text:
        return RedirectResponse(f"/runs/{run_id}?error=" + quote("Write a request first."), status_code=303)
    result = await run_in_threadpool(orch.request, run_id, text, "web")
    key = "error" if result.get("refused") else "notice"
    return RedirectResponse(f"/runs/{run_id}?{key}=" + quote(result.get("message", "")[:500]), status_code=303)


@app.get("/runs/{run_id}/steps/{step_id}", response_class=HTMLResponse)
async def step_page(request: Request, run_id: str, step_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    meta = check_step(step_id)
    st = run.steps[step_id]
    artifacts = []
    for name, rel in st.artifacts.items():
        text = read_artifact(orch, run_id, rel)
        if text is None:
            continue
        suffix = Path(name).suffix.lower()
        kind = {".md": "markdown", ".html": "html", ".htm": "html", ".json": "json"}.get(suffix, "text")
        if kind == "json":
            try:
                text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        artifacts.append({"name": name, "kind": kind, "text": text, "raw_url": f"/runs/{run_id}/files/{rel}"})
    history = []
    folder = orch.store.path(run_id) / "artifacts" / f"step{step_id.replace('.', '_')}"
    if folder.exists():
        for attempt_dir in sorted(folder.iterdir(), key=lambda p: (len(p.name), p.name)):
            if attempt_dir.is_dir():
                files = sorted(str(p.relative_to(orch.store.path(run_id))).replace("\\", "/")
                               for p in attempt_dir.rglob("*") if p.is_file())
                history.append({"attempt": attempt_dir.name, "files": files})
    return page(request, "step.html", {"run": run, "meta": meta, "st": st, "artifacts": artifacts,
                                       "history": history, "status_line": orch.status_line(run)})


@app.get("/runs/{run_id}/files/{rel:path}")
async def raw_file(run_id: str, rel: str):
    orch = get_orchestrator()
    load_run(orch, run_id)
    base = orch.store.path(run_id) / "artifacts"
    target = orch.store.path(run_id) / rel
    if not rel.startswith("artifacts/") or ".." in rel.split("/") or not inside(base, target) or not target.is_file():
        raise HTTPException(status_code=404, detail="Unknown file")
    suffix = target.suffix.lower()
    media = {".html": "text/html", ".htm": "text/html", ".json": "application/json", ".css": "text/css"}.get(
        suffix, "text/plain")
    headers = {"Content-Security-Policy": "sandbox", "Cache-Control": "no-store"}
    return Response(target.read_bytes(), media_type=f"{media}; charset=utf-8", headers=headers)


@app.get("/runs/{run_id}/log", response_class=HTMLResponse)
async def log_page(request: Request, run_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    book = orch.log(run_id)
    return page(request, "log.html", {"run": run, "entries": book.entries, "total_cost": book.total_cost(),
                                      "status_line": orch.status_line(run)})


@app.get("/runs/{run_id}/log.json")
async def log_json(run_id: str):
    orch = get_orchestrator()
    load_run(orch, run_id)
    return JSONResponse(orch.log(run_id).entries)


@app.get("/runs/{run_id}/evidence", response_class=HTMLResponse)
async def evidence_page(request: Request, run_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    rows = orch.ledger(run_id).all(include_fixtures=True)
    return page(request, "evidence.html", {"run": run, "rows": rows, "status_line": orch.status_line(run)})


def commerce_store(orch: Orchestrator, run_id: str) -> CommerceStore:
    return CommerceStore(orch.store.path(run_id) / "commerce.json", access_url_prefix=f"/p/{run_id}/access/")


@app.get("/runs/{run_id}/outbox", response_class=HTMLResponse)
async def outbox_page(request: Request, run_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    folder = orch.store.path(run_id) / "outbox"
    files = []
    if folder.exists():
        for path in sorted(folder.iterdir()):
            if path.is_file():
                files.append({"name": path.name, "text": path.read_text(encoding="utf-8", errors="replace")[:50_000]})
    cs = commerce_store(orch, run_id)
    emails, recon = [], None
    if cs.path.exists():
        emails = cs.outbox()
        recon = reconcile_mod.reconcile(cs)
    return page(request, "outbox.html", {"run": run, "files": files, "emails": emails, "recon": recon,
                                         "site_files": site_files(orch, run_id),
                                         "status_line": orch.status_line(run)})


# ---------------------------------------------------------------------------------------------- local MOCKED site
@app.get("/site/{run_id}/{filename}")
async def site_file(run_id: str, filename: str):
    orch = get_orchestrator()
    check_run_id(run_id)
    if not NAME_RE.match(filename or "") or ".." in filename or not orch.store.exists(run_id):
        raise HTTPException(status_code=404, detail="Not published")
    folder = orch.store.path(run_id) / "site"
    target = folder / filename
    if not inside(folder, target) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not published")
    suffix = target.suffix.lower()
    media = {".html": "text/html", ".htm": "text/html", ".css": "text/css", ".js": "text/javascript",
             ".json": "application/json", ".svg": "image/svg+xml", ".txt": "text/plain", ".md": "text/plain"}.get(
        suffix, "application/octet-stream")
    if media.startswith("text/") or media in ("application/json", "image/svg+xml"):
        media += "; charset=utf-8"
    return Response(target.read_bytes(), media_type=media, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------------------------- first-party events
def _append_event(orch: Orchestrator, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    with _EVENT_LOCK:
        return orch.store.append_event(run_id, event)


def _already_signed_up(orch: Orchestrator, run_id: str, hashed: str) -> bool:
    return any(e.get("type") == "waitlist_signup" and e.get("email_hash") == hashed
               for e in orch.store.read_events(run_id))


@app.post("/p/{run_id}/event")
async def record_event(request: Request, run_id: str):
    orch = get_orchestrator()
    load_run(orch, run_id)
    body = await request.body()
    if len(body) > MAX_EVENT_BODY:
        return JSONResponse({"ok": False, "error": "event too large"}, status_code=413)
    try:
        payload = json.loads(body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)
    if not isinstance(payload, dict) or payload.get("type") not in EVENT_TYPES:
        return JSONResponse({"ok": False, "error": f"type must be one of {', '.join(EVENT_TYPES)}"}, status_code=400)
    event = {"type": payload["type"], "page": clean_text(payload.get("page")) or "unknown",
             "internal": is_internal(request)}
    for key in EVENT_FIELDS:
        if payload.get(key) not in (None, ""):
            event[key] = clean_text(payload.get(key))
    stored = await run_in_threadpool(_append_event, orch, run_id, event)
    return JSONResponse({"ok": True, "event_id": stored["event_id"]})


@app.post("/p/{run_id}/waitlist", response_class=HTMLResponse)
async def waitlist(request: Request, run_id: str):
    orch = get_orchestrator()
    load_run(orch, run_id)
    form = await read_form(request)
    email = field(form, "email", 254)
    if not valid_email(email):
        return public_page(request, title="Check your email address",
                           message="That email address does not look valid. Go back and try again.", status_code=400)
    if field(form, "consent").lower() not in TRUTHY:
        return public_page(request, title="Consent needed",
                           message="Tick the consent box so we may email you about this research. Nothing is for sale.",
                           status_code=400)
    hashed = email_hash(email)
    if await run_in_threadpool(_already_signed_up, orch, run_id, hashed):
        return public_page(request, title="You're already on the research waitlist",
                           message="This email is already on the list; it is counted once. Nothing is for sale yet.")
    event = {"type": "waitlist_signup", "page": clean_text(field(form, "page")) or "landing", "email_hash": hashed,
             "role": clean_text(field(form, "role")), "source": clean_text(field(form, "source")),
             "internal": is_internal(request)}
    if field(form, "visitor_id"):
        event["visitor_id"] = clean_text(field(form, "visitor_id"))
    await run_in_threadpool(_append_event, orch, run_id, event)
    return public_page(request, title="Thank you",
                       message="You're on the research waitlist. Nothing is for sale yet.")


def _catalog(run) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    store_page = dict(run.steps["5.1"].output) if "5.1" in run.steps else {}
    pricing = dict(run.steps["4.1"].output) if "4.1" in run.steps else {}
    catalog: dict[str, dict[str, Any]] = {}
    product_id = str(store_page.get("product_id") or "").strip()
    if product_id:
        catalog[product_id] = {"price": store_page.get("price"),
                               "currency": store_page.get("currency") or pricing.get("currency")}
    packages = [p for p in (pricing.get("packages") or []) if isinstance(p, dict)]
    return catalog, packages


def _mock_order_flow(orch: Orchestrator, run, *, email: str, product_id: str, package_id: str, internal: bool,
                     source: str) -> dict[str, Any]:
    catalog, packages = _catalog(run)
    item = catalog.get(product_id)
    if item is None:
        raise checkout.InvalidProduct(f"Unknown product {product_id!r}.")
    price, currency = item.get("price"), item.get("currency")
    package = next((p for p in packages if str(p.get("id")) == package_id), None) if package_id else None
    if package is not None and package.get("price") is not None:
        price, currency = package.get("price"), package.get("currency") or currency
    if price is None or not currency:
        raise checkout.InvalidProduct("This product has no advertised price yet.")
    cs = commerce_store(orch, run.run_id)
    key = hashlib.sha256((email.strip().lower() + product_id).encode("utf-8")).hexdigest()
    order = checkout.create_order(cs, product_id=product_id, buyer_email=email, price=price, currency=currency,
                                  idempotency_key=key, catalog=catalog,
                                  metadata={"internal": internal, "package_id": package_id or None, "source": source})
    if not order["replayed"]:
        _append_event(orch, run.run_id, {"type": "order_request", "page": "store", "email_hash": email_hash(email),
                                         "product_id": product_id, "package_id": package_id or None,
                                         "internal": internal, "mocked": True})
    paid = payments.record_mock_payment(cs, order["order_id"], idempotency_key=f"pay:{order['order_id']}")
    webhooks.handle_event(cs, paid["event"])
    result = delivery.deliver(cs, order["order_id"], idempotency_key=f"deliver:{order['order_id']}")
    if not order["replayed"]:
        _append_event(orch, run.run_id, {"type": "mock_delivery", "page": "store", "product_id": product_id,
                                         "internal": internal, "mocked": True})
    return {"order": order, "delivery": result["delivery"], "access_url": result["access_url"],
            "email": result.get("email")}


@app.post("/p/{run_id}/order", response_class=HTMLResponse)
async def order(request: Request, run_id: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    form = await read_form(request)
    email = field(form, "email", 254)
    if not valid_email(email):
        return public_page(request, title="Check your email address", status_code=400, mocked=True,
                           message="That email address does not look valid. MOCKED: no payment was taken.")
    if field(form, "consent").lower() not in TRUTHY:
        return public_page(request, title="Consent needed", status_code=400, mocked=True,
                           message="Tick the consent box to continue. MOCKED: no payment was taken.")
    try:
        result = await run_in_threadpool(
            _mock_order_flow, orch, run, email=email, product_id=field(form, "product_id", 120),
            package_id=field(form, "package_id", 120), internal=is_internal(request),
            source=clean_text(field(form, "source")))
    except checkout.InvalidProduct as exc:
        return public_page(request, title="Product not available", status_code=400, mocked=True,
                           message=f"{exc} No order was recorded. MOCKED: no payment was taken.")
    except CommerceError as exc:
        return public_page(request, title="Order not possible", status_code=409, mocked=True,
                           message=f"{exc} MOCKED: no payment was taken.")
    return public_page(request, title="Order request received (MOCKED)", mocked=True,
                       message=("MOCKED: no payment was taken. This is a test of the delivery flow: nothing was "
                                "charged and no payment details were asked for."),
                       order=result["order"], access_url=result["access_url"], email_status=(result["email"] or {}).get("status"))


@app.get("/p/{run_id}/access/{token}", response_class=HTMLResponse)
async def access(request: Request, run_id: str, token: str):
    orch = get_orchestrator()
    run = load_run(orch, run_id)
    cs = commerce_store(orch, run_id)
    if not TOKEN_RE.match(token or "") or not cs.path.exists() or not delivery.has_access(cs, token):
        return public_page(request, title="No access", status_code=403, mocked=True,
                           message=("This access link is unknown, expired or was revoked (for example after a "
                                    "refund). MOCKED: no payment was taken."))
    st = run.steps.get("3.2")
    rel = None
    if st:
        rel = st.artifacts.get("product/index.html") or next(
            (r for n, r in st.artifacts.items() if n.startswith("product/") and n.endswith(".html")), None)
    product_html = read_artifact(orch, run_id, rel) if rel else None
    return public_page(request, title="Your product (MOCKED delivery)", mocked=True,
                       message="MOCKED: no payment was taken. Access was issued by the mocked delivery flow.",
                       product_html=product_html,
                       missing_product=product_html is None)


if __name__ == "__main__":  # pragma: no cover
    import os

    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
