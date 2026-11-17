"""Phase 2 Validate: Lean Canvas (2.1, gate A) and landing-page demand test (2.2, gate E).

2.1 turns the Phase 1 evidence into a nine-box canvas where every box cites
evidence or is labelled, ranks the three riskiest assumptions and names the
channels that 2.2 and 5.2 use.

2.2 writes landing-page copy, renders a self-contained page (published to the
MOCKED local site only when the founder locks the thresholds and approves the
page), and counts first-party events after the lock: unique non-internal
visitors and unique sign-ups by email hash. Before the locked window ends the
measurement state is WAITING_FOR_DATA; no number is ever filled in by a model.

Helpers shared with phases/launch.py (window, events, HTML) live here; the
clock is `_now()` so tests can move time forward.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from agents import business_designer, growth_marketer
from agents.base import as_float
from evidence import Claim, Evidence
from gates import INVALID_DATA, READY, WAITING_FOR_DATA, Contract, Criterion, wilson_interval
from logbook import utc_now
from phases.base import DataField, Observation, StepHandler, StepOutput
from store import slugify

CTA_LANDING = "Join the research waitlist"
AVAILABILITY = ("Not built yet. Joining the waitlist means we may contact you for a short research conversation. "
                "There is nothing to buy on this page.")
LANDING_BANNER = "Prototype page served locally by Venture Validator. Publishing is MOCKED: nothing is posted publicly."
CONSENT_TEXT = ("I agree to be contacted by email about this research, including an invitation to a short research "
                "conversation. My email is used for nothing else and I can ask to be removed at any time.")
PRIVACY_NOTE = ("Your email address is stored only so the founder can contact you about this research. "
                "The role question is optional.")
DEFAULT_WINDOW_DAYS = 14


# ---------------------------------------------------------------------------------------------- clock and window
def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def window_info(contract: Contract) -> dict[str, Any]:
    """The locked measurement window: it starts when the thresholds were locked."""
    start = parse_ts(contract.locked_at)
    days = contract.window_days or DEFAULT_WINDOW_DAYS
    end = start + timedelta(days=days) if start else None
    now = _now()
    closed = bool(end and now >= end)
    remaining = round(max(0.0, (end - now).total_seconds() / 86400), 1) if end else None
    return {"start": start, "end": end, "closed": closed, "days_remaining": remaining, "window_days": days,
            "text": (f"{iso(start)} to {iso(end)} ({days} days)" if start else "window not started (thresholds not locked)")}


def eligible_events(events: list[dict[str, Any]], window: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Drop internal, fixture and bot events, and events outside the locked window."""
    kept: list[dict[str, Any]] = []
    excluded = {"internal": 0, "fixture_or_bot": 0, "outside_window": 0, "no_timestamp": 0}
    start, end = window.get("start"), window.get("end")
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("internal"):
            excluded["internal"] += 1
            continue
        if event.get("fixture") or event.get("bot"):
            excluded["fixture_or_bot"] += 1
            continue
        ts = parse_ts(event.get("timestamp"))
        if ts is None:
            excluded["no_timestamp"] += 1
            continue
        if (start and ts < start) or (end and ts > end):
            excluded["outside_window"] += 1
            continue
        kept.append(event)
    kept.sort(key=lambda e: str(e.get("timestamp")))
    return kept, excluded


def pct1(value: float | None) -> str:
    """A rate with one decimal (whole percents hide small rates and interval bounds)."""
    return "n/a" if value is None else f"{value:.1%}"


def as_count(value: Any) -> int | None:
    number = as_float(value, None)
    if number is None or number < 0 or number != int(number):
        return None
    return int(number)


def criterion_target(contract: Contract, key: str, default: float) -> float:
    return next((c.target for c in contract.criteria if c.key == key), default)


# ---------------------------------------------------------------------------------------------- text helpers
def esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def md_cell(text: Any, limit: int = 400) -> str:
    value = str(text if text not in (None, "") else "-").replace("|", "/").replace("\r", " ").replace("\n", " ")
    return value[:limit]


def compact(value: Any, limit: int = 2500) -> Any:
    """Keep model payloads small: drop bookkeeping keys and truncate when large."""
    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if k not in ("outward", "outward_results")}
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= limit else text[:limit] + " ...[truncated]"


def founder_brief_evidence_id(ctx) -> str | None:
    """The founder's intake brief as a FOUNDER_REPORTED evidence row (deduplicated by the ledger)."""
    parts = [f"{k}: {v}" for k, v in (ctx.brief or {}).items() if isinstance(v, str) and v.strip()]
    if not parts:
        return None
    row = ctx.ledger.add(Evidence(provenance="FOUNDER_REPORTED", source_type="founder_data", title="Founder brief (intake)",
                                  excerpt="; ".join(parts)[:600], observed_at=getattr(ctx.run, "created_at", None),
                                  method="founder intake form"))
    return row.evidence_id


def citable(ctx, ids: list[str]) -> list[str]:
    out = []
    for evidence_id in ids:
        row = ctx.ledger.get(evidence_id)
        if row is not None and row.provenance != "FIXTURE" and evidence_id not in out:
            out.append(evidence_id)
    return out


# ---------------------------------------------------------------------------------------------- HTML helpers
PAGE_CSS = """
:root{--bg:#ffffff;--fg:#1b1b1b;--muted:#4a4a4a;--accent:#1d4ed8;--accent-fg:#ffffff;--banner:#fff2c2;--banner-fg:#3b2c00;--line:#cfcfcf}
@media (prefers-color-scheme: dark){:root{--bg:#141414;--fg:#f1f1f1;--muted:#c9c9c9;--accent:#8db4ff;--accent-fg:#0b1a33;--banner:#3b2f00;--banner-fg:#fff2c2;--line:#3d3d3d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.banner{background:var(--banner);color:var(--banner-fg);padding:12px 16px;border-bottom:2px solid var(--banner-fg);font-weight:700}
main{max-width:720px;margin:0 auto;padding:24px 16px 40px}
h1{font-size:clamp(1.6rem,5vw,2.3rem);line-height:1.2;margin:.2em 0 .4em}
h2{font-size:1.2rem;margin:1.8em 0 .5em}
.eyebrow{margin:0;color:var(--muted);font-weight:600}
.lead{font-size:1.1rem;color:var(--muted)}
.notice{border-left:4px solid var(--accent);padding:8px 12px;margin:12px 0}
form{display:grid;gap:12px;border:1px solid var(--line);border-radius:10px;padding:16px}
label{font-weight:600}
input[type=email],input[type=text]{width:100%;padding:10px 12px;font:inherit;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
.consent{display:flex;gap:10px;align-items:flex-start}
.consent label{font-weight:400}
.consent input{width:20px;height:20px;margin-top:3px;flex:none}
button{font:inherit;font-weight:700;padding:12px 18px;border:0;border-radius:8px;background:var(--accent);color:var(--accent-fg);cursor:pointer}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
a{color:var(--accent)}
dt{font-weight:600;margin-top:12px}
dd{margin:4px 0 0}
footer{max-width:720px;margin:0 auto;padding:0 16px 32px;color:var(--muted);font-size:.92rem}
""".strip()


def beacon_script(event_url: str, page: str, *, cta_form_id: str | None = None) -> str:
    """Inline first-party analytics: a page_view on load (and a cta_click on submit). No third parties."""
    cta = ""
    if cta_form_id:
        cta = (f'  var form = document.getElementById({json.dumps(cta_form_id)});\n'
               '  if (form) { form.addEventListener("submit", function () {\n'
               f'    send({{type: "cta_click", page: {json.dumps(page)}, source: source, visitor_id: visitorId}});\n'
               '  }); }\n')
    script = (
        "(function () {\n"
        f"  var EVENT_URL = {json.dumps(event_url)};\n"
        "  var params = new URLSearchParams(window.location.search);\n"
        "  var source = params.get(\"utm_source\") || null;\n"
        "  var visitorId = null;\n"
        "  try { visitorId = window.localStorage.getItem(\"vv_visitor_id\"); } catch (err) { visitorId = null; }\n"
        "  if (!visitorId) {\n"
        "    visitorId = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID()\n"
        "      : \"v\" + Date.now().toString(36) + Math.random().toString(36).slice(2);\n"
        "    try { window.localStorage.setItem(\"vv_visitor_id\", visitorId); } catch (err) { /* private mode */ }\n"
        "  }\n"
        "  var sourceField = document.getElementById(\"source\");\n"
        "  if (sourceField && source) { sourceField.value = source; }\n"
        "  var visitorField = document.getElementById(\"visitor_id\");\n"
        "  if (visitorField) { visitorField.value = visitorId; }\n"
        "  function send(payload) {\n"
        "    try {\n"
        "      fetch(EVENT_URL, {method: \"POST\", headers: {\"Content-Type\": \"application/json\"},\n"
        "        body: JSON.stringify(payload), keepalive: true}).catch(function () {});\n"
        "    } catch (err) { /* analytics must never break the page */ }\n"
        "  }\n"
        f"  send({{type: \"page_view\", page: {json.dumps(page)}, source: source, visitor_id: visitorId}});\n"
        f"{cta}"
        "})();")
    return script.replace("</", "<\\/")


def page_html(*, title: str, banner: str, body: str, script: str, footer: str = "") -> str:
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"robots\" content=\"noindex\">\n"
            f"<title>{esc(title)}</title>\n<style>\n{PAGE_CSS}\n</style>\n</head>\n<body>\n"
            f"<div class=\"banner\" role=\"note\">{esc(banner)}</div>\n<main>\n{body}\n</main>\n"
            f"<footer>{footer}</footer>\n<script>\n{script}\n</script>\n</body>\n</html>\n")


def faq_html(faq: list[dict[str, str]]) -> str:
    items = "".join(f"<dt>{esc(f['question'])}</dt><dd>{esc(f['answer'])}</dd>" for f in faq)
    return f"<section aria-labelledby=\"faq-h\">\n<h2 id=\"faq-h\">Questions</h2>\n<dl>{items}</dl>\n</section>"


# ---------------------------------------------------------------------------------------------- 2.1 Lean Canvas
class LeanCanvas(StepHandler):
    def generate(self, ctx) -> StepOutput:
        brief_id = founder_brief_evidence_id(ctx)
        payload = {
            "concept": ctx.concept(),
            "founder_brief": {k: ctx.brief.get(k) for k in ("idea", "customer", "why_you", "jurisdiction", "budget",
                                                            "time", "evidence") if ctx.brief.get(k)},
            "founder_brief_evidence_id": brief_id,
            "phase1": {sid: compact(ctx.prior(sid)) for sid in ("1.1", "1.2", "1.3", "1.4") if ctx.prior(sid)},
            "evidence": ctx.evidence_digest(40),
            "feedback": ctx.feedback,
        }
        reply = business_designer.lean_canvas(ctx, payload)
        problems: list[str] = []

        canvas: dict[str, dict[str, Any]] = {}
        claims: list[Claim] = []
        for key, box in reply["boxes"].items():
            label, ids, basis = self._resolve(ctx, box["label"], box["evidence_ids"], box["basis"], brief_id, problems,
                                              box["title"])
            canvas[key] = {**box, "label": label, "evidence_ids": ids, "basis": basis}
            claims.append(Claim(text=f"{box['title']}: {box['content']}", label=label, evidence_ids=ids,
                                basis=basis or "model inference from the Phase 1 deliverables"))

        revenue = dict(reply["revenue_hypothesis"])
        label, ids, basis = self._resolve(ctx, revenue["label"], revenue["evidence_ids"], revenue["basis"], brief_id,
                                          problems, "Revenue hypothesis")
        revenue.update(label=label, evidence_ids=ids, basis=basis)
        revenue_text = revenue["statement"] or canvas["revenue_streams"]["content"]
        claims.append(Claim(text=f"Revenue hypothesis: {revenue_text}", label=label, evidence_ids=ids,
                            basis=basis or "hypothesis to be tested in 4.1 (pricing)"))

        channels = self._channels(ctx, reply["channels"], problems)
        questions = list(reply["questions"])
        if not channels:
            questions.insert(0, "No channel could be named from the evidence: which 2-3 places do your target customers "
                                "already gather (communities, newsletters, associations)?")
        if len(reply["riskiest_assumptions"]) < 3:
            problems.append(f"Only {len(reply['riskiest_assumptions'])} riskiest assumption(s) were given; three are expected.")

        concept = ctx.concept()
        data = {
            "canvas": canvas,
            "uvp": canvas["unique_value_proposition"]["content"],
            "problem": canvas["problem"]["content"],
            "segment": canvas["customer_segments"]["content"],
            "riskiest_assumptions": reply["riskiest_assumptions"],
            "channels": channels,
            "revenue_hypothesis": revenue,
            "missing_boxes": reply["missing_boxes"],
            "concept_name": concept.get("name") or ctx.run.title,
        }
        markdown = self._markdown(ctx, canvas, reply["riskiest_assumptions"], channels, revenue, problems)
        summary = reply["summary"] or ("Built the Lean Canvas from the Phase 1 deliverables, ranked the three riskiest "
                                       "assumptions and named the channels for the demand test.")
        return StepOutput(title=str(data["concept_name"]), markdown=markdown, data=data, claims=claims,
                          sources=ctx.ledger.urls(sorted({i for c in claims for i in c.evidence_ids})),
                          summary=summary, questions=questions[:3])

    @staticmethod
    def _resolve(ctx, label: str, ids: list[str], basis: str, brief_id: str | None, problems: list[str],
                 what: str) -> tuple[str, list[str], str]:
        known = citable(ctx, ids)
        unknown = [i for i in ids if i not in known]
        if unknown:
            problems.append(f"{what}: removed citations that are not in the evidence ledger: {', '.join(unknown)}.")
        if label == "SOURCED" and not known:
            problems.append(f"{what}: labelled SOURCED without a resolvable citation; relabelled ASSUMPTION.")
            return "ASSUMPTION", [], basis or "no resolvable evidence was cited"
        if label == "FOUNDER_REPORTED" and not known:
            if brief_id:
                return label, [brief_id], basis or "stated in the founder brief"
            return "ASSUMPTION", [], basis or "founder statement without a recorded source"
        if label in ("ASSUMPTION", "UNKNOWN") and not basis:
            basis = "no basis given"
        return label, known, basis

    @staticmethod
    def _channels(ctx, raw: list[dict[str, Any]], problems: list[str]) -> list[dict[str, Any]]:
        known_urls = set(ctx.ledger.urls())
        phase1_text = json.dumps([ctx.prior("1.3"), ctx.prior("1.4")], ensure_ascii=False, default=str)
        out: list[dict[str, Any]] = []
        used: set[str] = set()
        for item in raw[:6]:
            base = slugify(item.get("id") or item.get("name"), max_len=30) or "channel"
            channel_id, n = base, 2
            while channel_id in used:
                channel_id, n = f"{base}-{n}", n + 1
            used.add(channel_id)
            url = item.get("url")
            if url and url not in known_urls and url not in phase1_text:
                problems.append(f"Channel {item['name']}: URL {url} is not in the evidence, so it was removed.")
                url = None
            out.append({"id": channel_id, "name": item["name"], "url": url,
                        "audience_rule": item.get("audience_rule") or "",
                        "evidence_ids": citable(ctx, item.get("evidence_ids") or [])})
        return out

    @staticmethod
    def _markdown(ctx, canvas, assumptions, channels, revenue, problems) -> str:
        lines = ["## Lean Canvas", "",
                 "Every box cites evidence (`SOURCED`, `FOUNDER_REPORTED`) or is labelled `ASSUMPTION` / `UNKNOWN` "
                 "with its basis.", "",
                 "| Box | Content | Label | Evidence / basis |", "|---|---|---|---|"]
        for key, _title, _aliases in business_designer.BOXES:
            box = canvas[key]
            ref = ", ".join(box["evidence_ids"]) or box["basis"]
            lines.append(f"| {box['title']} | {md_cell(box['content'], 600)} | `{box['label']}` | {md_cell(ref, 300)} |")
        lines += ["", "## Three riskiest assumptions (ranked by loss if wrong)", "",
                  "Scores are the model's 1-5 judgement (`ASSUMPTION`); the ranking is computed from them.", "",
                  "| Rank | Assumption | Loss if wrong | Loss (1-5) | Uncertainty (1-5) | Test | Cost / time | Decision it blocks |",
                  "|---|---|---|---|---|---|---|---|"]
        for a in assumptions:
            lines.append(f"| {a['rank']} | {md_cell(a['assumption'])} | {md_cell(a['loss_if_wrong'])} | {a['loss_score']:g} | "
                         f"{a['uncertainty_score']:g} | {md_cell(a['test'])} | {md_cell(a['cost_to_test'])} | "
                         f"{md_cell(a['blocks_decision'])} |")
        lines += ["", "## Channels for the demand test (used by 2.2 and 5.2)", ""]
        if channels:
            lines += ["| ID | Channel | Audience rule | Link | Evidence |", "|---|---|---|---|---|"]
            for c in channels:
                link = f"[link]({c['url']})" if c["url"] else "not known from evidence"
                lines.append(f"| `{c['id']}` | {md_cell(c['name'])} | {md_cell(c['audience_rule'])} | {link} | "
                             f"{', '.join(c['evidence_ids']) or '`ASSUMPTION`'} |")
        else:
            lines.append("_No channel could be named from the evidence. The founder needs to name 2-3 channels._")
        lines += ["", "## Revenue stream hypothesis", "",
                  "| Who pays | Price unit | Billing period | Current substitute spend | Label |", "|---|---|---|---|---|",
                  f"| {md_cell(revenue['who_pays'])} | {md_cell(revenue['price_unit'])} | {md_cell(revenue['billing_period'])} | "
                  f"{md_cell(revenue['substitute_spend'])} | `{revenue['label']}` |", ""]
        if revenue["statement"]:
            lines += [revenue["statement"], ""]
        lines += ["The price itself is tested in 4.1 without taking any money.", ""]
        if problems:
            lines += ["## Citation and completeness checks", ""] + [f"- {p}" for p in problems] + [""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- 2.2 Landing-page test
EVENT_DICTIONARY = [
    {"event": "page_view", "sent_when": "the landing page loads (inline first-party script)",
     "fields": "type, page=landing, visitor_id (random ID kept in the browser), source (utm_source)",
     "counts_as": "eligible unique visitor", "dedupe_key": "visitor_id",
     "excluded": "internal (founder/team/test) traffic, fixture and bot-flagged events, events outside the window"},
    {"event": "waitlist_signup", "sent_when": "the form is submitted with an email and consent (server side)",
     "fields": "type, page=landing, email_hash (never the raw email), role (optional follow-up answer), source",
     "counts_as": "waitlist sign-up", "dedupe_key": "email_hash",
     "excluded": "internal traffic, duplicate emails (counted once), events outside the window"},
]


def landing_counts(events: list[dict[str, Any]]) -> dict[str, Any]:
    visitors: dict[str, str] = {}
    signups: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("page") not in (None, "landing"):
            continue
        if event.get("type") == "page_view" and event.get("visitor_id"):
            visitors.setdefault(str(event["visitor_id"]), str(event.get("source") or "direct"))
        elif event.get("type") == "waitlist_signup" and event.get("email_hash"):
            signups.setdefault(str(event["email_hash"]), {"source": str(event.get("source") or "direct"),
                                                         "role": bool(str(event.get("role") or "").strip())})
    by_source: dict[str, dict[str, int]] = {}
    for source in visitors.values():
        by_source.setdefault(source, {"visitors": 0, "signups": 0})["visitors"] += 1
    for item in signups.values():
        by_source.setdefault(item["source"], {"visitors": 0, "signups": 0})["signups"] += 1
    return {"visitors": len(visitors), "signups": len(signups),
            "follow_up_answered": sum(1 for s in signups.values() if s["role"]), "by_source": by_source}


class LandingPageTest(StepHandler):
    def generate(self, ctx) -> StepOutput:
        canvas = ctx.prior("2.1")
        concept = ctx.concept()
        product = canvas.get("concept_name") or concept.get("name") or ctx.run.title
        channels = [c for c in (canvas.get("channels") or []) if isinstance(c, dict) and c.get("id")]
        payload = {
            "product_name": product,
            "uvp": canvas.get("uvp") or concept.get("statement"),
            "problem": canvas.get("problem") or concept.get("statement"),
            "segment": canvas.get("segment") or concept.get("segment"),
            "riskiest_assumptions": (canvas.get("riskiest_assumptions") or [])[:3],
            "channels": [{"id": c["id"], "name": c.get("name"), "audience_rule": c.get("audience_rule")} for c in channels],
            "budget": ctx.brief.get("budget"), "founder_time": ctx.brief.get("time"),
            "fixed_by_code": {"cta": CTA_LANDING, "availability": AVAILABILITY, "social_proof": "none (nothing real yet)"},
            "feedback": ctx.feedback,
        }
        copy = growth_marketer.landing_page(ctx, payload)
        faq = list(copy["faq"])
        asked = " ".join(f["question"].lower() for f in faq)
        if "available" not in asked and "built" not in asked:
            faq.insert(0, {"question": "Can I use it today?", "answer": AVAILABILITY})
        if "pay" not in asked and "cost" not in asked and "charge" not in asked:
            faq.append({"question": "Does joining cost anything?",
                        "answer": "No. There is nothing to buy; the waitlist is for research conversations."})
        copy["faq"] = faq[:6]

        rid = ctx.run_id
        page, visible = self.render(rid, product, copy)
        traffic = self._traffic_plan(ctx, rid, channels, copy["channel_actions"])
        questions = list(copy["questions"])
        if not channels:
            questions.insert(0, "Step 2.1 named no channels: where will you send people to this page? "
                                "Name 2-3 places your target customers already gather.")
        outward = [{"kind": "publish", "item_id": "landing-page", "file": "landing.html", "when": "before_collect",
                    "target_name": "landing.html"}]
        data = {"product_name": product, "copy": {**copy, "cta": CTA_LANDING, "availability": AVAILABILITY},
                "headline": copy["headline"], "cta": CTA_LANDING, "traffic_plan": traffic,
                "event_dictionary": EVENT_DICTIONARY, "landing_path": f"/site/{rid}/landing.html",
                "form_action": f"/p/{rid}/waitlist", "event_endpoint": f"/p/{rid}/event", "outward": outward}
        markdown = self._markdown(ctx, rid, copy, traffic)
        summary = copy["summary"] or ("Wrote the landing page and tracking for a 14-day demand test; the page is "
                                      "published to the MOCKED local site only when you lock the thresholds.")
        return StepOutput(title=str(product), markdown=markdown, data=data,
                          files={"landing.html": page}, summary=summary, questions=questions[:3],
                          marketing_text=visible)

    # -- rendering
    @staticmethod
    def render(run_id: str, product: str, copy: dict[str, Any]) -> tuple[str, str]:
        benefits = "".join(f"<li>{esc(b)}</li>" for b in copy["benefits"])
        follow_up = copy.get("follow_up_question") or growth_marketer.DEFAULT_FOLLOW_UP
        body = f"""<header>
<p class="eyebrow">{esc(product)}</p>
<h1>{esc(copy['headline'])}</h1>
{f'<p class="lead">{esc(copy["subheadline"])}</p>' if copy.get('subheadline') else ''}
</header>
<section aria-labelledby="benefits-h">
<h2 id="benefits-h">What it is meant to do</h2>
<ul>{benefits}</ul>
</section>
<section aria-labelledby="availability-h">
<h2 id="availability-h">Availability</h2>
<p class="notice">{esc(AVAILABILITY)}</p>
</section>
<section aria-labelledby="join-h">
<h2 id="join-h">{esc(CTA_LANDING)}</h2>
<form id="waitlist-form" method="post" action="/p/{esc(run_id)}/waitlist">
<label for="email">Email address (required)</label>
<input id="email" name="email" type="email" required autocomplete="email">
<label for="role">{esc(follow_up)} (optional)</label>
<input id="role" name="role" type="text" maxlength="200">
<div class="consent"><input id="consent" name="consent" type="checkbox" value="yes" required>
<label for="consent">{esc(CONSENT_TEXT)}</label></div>
<input type="hidden" id="source" name="source" value="">
<input type="hidden" id="visitor_id" name="visitor_id" value="">
<input type="hidden" name="page" value="landing">
<button type="submit">{esc(CTA_LANDING)}</button>
</form>
</section>
{faq_html(copy['faq'])}"""
        script = beacon_script(f"/p/{run_id}/event", "landing")
        page = page_html(title=f"{product}: research waitlist", banner=LANDING_BANNER, body=body, script=script,
                         footer=esc(PRIVACY_NOTE))
        visible = "\n".join([LANDING_BANNER, product, copy["headline"], copy.get("subheadline", ""), *copy["benefits"],
                             AVAILABILITY, CTA_LANDING, follow_up, CONSENT_TEXT, PRIVACY_NOTE,
                             *[f"{f['question']}\n{f['answer']}" for f in copy["faq"]]])
        return page, visible

    @staticmethod
    def _traffic_plan(ctx, run_id: str, channels: list[dict[str, Any]], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {a["channel_id"]: a for a in actions}
        budget = str(ctx.brief.get("budget") or "not stated in the brief")
        rows = []
        for c in channels or [{"id": "direct", "name": "Direct link shared by the founder", "audience_rule": ""}]:
            action = by_id.get(c["id"], {})
            rows.append({"channel_id": c["id"], "channel": c.get("name") or c["id"],
                         "tracked_link": f"/site/{run_id}/landing.html?utm_source={c['id']}",
                         "action": action.get("action") or "Founder shares the tracked link with this audience.",
                         "message_angle": action.get("message_angle", ""), "founder_hours": action.get("founder_hours", ""),
                         "owner": "founder", "budget": budget, "duration_days": DEFAULT_WINDOW_DAYS})
        return rows

    @staticmethod
    def _markdown(ctx, run_id: str, copy: dict[str, Any], traffic: list[dict[str, Any]]) -> str:
        lines = ["## Landing-page copy", "",
                 f"- **Headline (unique value proposition):** {copy['headline']}"]
        if copy.get("subheadline"):
            lines.append(f"- **Subheadline:** {copy['subheadline']}")
        lines += [f"- **Benefit {i}:** {b}" for i, b in enumerate(copy["benefits"], start=1)]
        lines += [f"- **Single call to action:** {CTA_LANDING}",
                  f"- **Availability (shown on the page):** {AVAILABILITY}",
                  "- **Social proof:** none. Nothing real exists yet, so the page shows no testimonials, ratings, "
                  "user counts or countdowns.",
                  f"- **Follow-up question (optional field):** {copy['follow_up_question']}", "",
                  "### FAQ", ""]
        lines += [f"- **{f['question']}** {f['answer']}" for f in copy["faq"]]
        lines += ["", "## Page and publishing (MOCKED)", "",
                  f"- File: `landing.html` (self-contained: inline CSS and script, no external fonts, images or trackers).",
                  f"- Published only when you lock the thresholds and approve the page, to the local MOCKED site at "
                  f"`/site/{run_id}/landing.html`. Nothing is posted publicly.",
                  f"- Form posts to `/p/{run_id}/waitlist` (email required, consent required, role optional); "
                  f"page views post to `/p/{run_id}/event`.", "",
                  f"## Traffic plan ({DEFAULT_WINDOW_DAYS} days, owner: founder)", "",
                  f"Budget from the brief (`FOUNDER_REPORTED`): {md_cell(ctx.brief.get('budget') or 'not stated')}. "
                  "The system spends nothing; any paid promotion is the founder's own decision.", "",
                  "| Channel | Tracked link | Action | Message angle | Founder hours | Owner |", "|---|---|---|---|---|---|"]
        for row in traffic:
            lines.append(f"| {md_cell(row['channel'])} | `{row['tracked_link']}` | {md_cell(row['action'])} | "
                         f"{md_cell(row['message_angle'])} | {md_cell(row['founder_hours'])} | founder |")
        if copy.get("repeat_variable"):
            lines += ["", f"**The one variable to change if the result is a near miss (named in advance):** "
                          f"{copy['repeat_variable']}"]
        lines += ["", "## Event dictionary", "",
                  "| Event | Sent when | Fields | Counts as | Dedupe key | Excluded |", "|---|---|---|---|---|---|"]
        for e in EVENT_DICTIONARY:
            lines.append(f"| `{e['event']}` | {e['sent_when']} | {e['fields']} | {e['counts_as']} | `{e['dedupe_key']}` | "
                         f"{e['excluded']} |")
        lines += ["", "## Tracking requirements", "",
                  "- Visitors: unique `visitor_id` with a landing `page_view` inside the locked window.",
                  "- Sign-ups: unique `email_hash` with a landing `waitlist_signup` inside the window; the raw email is "
                  "never used in metrics.",
                  "- Source: `utm_source` from the tracked link (first touch per visitor); `direct` when absent.",
                  "- Exclusions: events flagged `internal` (founder, team and test visits), fixture and bot-flagged "
                  "events, events before the lock or after the window ends.",
                  "- Follow-up: share of sign-ups that answered the optional question (reported, not gated; "
                  "reference value 20%).",
                  "- If you send traffic to a copy of the page hosted elsewhere, submit the visitors and sign-ups from "
                  "that analytics tool with its name; they are logged as `FOUNDER_REPORTED`.", ""]
        return "\n".join(lines)

    # -- thresholds and measurement
    def default_contract(self, ctx) -> Contract:
        canvas = ctx.prior("2.1")
        segment = canvas.get("segment") or ctx.concept().get("segment") or "the target segment"
        return Contract(
            step_id=ctx.step_id,
            decision="Is there enough real demand to justify building the MVP (Phase 3)?",
            hypothesis=(f"At least 10% of at least 300 eligible unique visitors from {segment[:160]} join the research "
                        f"waitlist within {DEFAULT_WINDOW_DAYS} days of the page going live."),
            criteria=[
                Criterion(key="unique_visitors", label="Eligible unique visitors", target=300, kind="floor",
                          unit="visitors", help="Unique non-internal visitor IDs with a landing page view in the window"),
                Criterion(key="signup_rate", label="Visitor-to-waitlist sign-up rate", target=0.10, kind="proportion",
                          help="Unique sign-ups (by email hash) / eligible unique visitors"),
            ],
            window_days=DEFAULT_WINDOW_DAYS,
            pivot_target="1.4",
            notes=("Exclusions: internal/test traffic (events flagged internal), fixture and bot-flagged events, "
                   "duplicate emails (counted once by hash), repeat visits (counted once by visitor ID), events before "
                   "the lock or after the window. Uses the rate-with-floor default (>= 10% with >= 300 visitors) so "
                   "the denominator is explicit; the alternative (>= 100 sign-ups) is not used. Follow-up answer rate "
                   "is reported, not gated. A missed visitor floor routes to 2.1 (channels); a missed rate routes "
                   "to 1.4."),
        )

    def collect(self, ctx, contract: Contract) -> Observation:
        window = window_info(contract)
        events, excluded = eligible_events(ctx.store.read_events(ctx.run_id), window)
        counts = landing_counts(events)
        visitors, signups = counts["visitors"], counts["signups"]
        site_page = ctx.run_path() / "site" / "landing.html"
        published = site_page.exists()
        own_rel = ctx.run.steps[ctx.step_id].artifacts.get("landing.html")
        current = bool(published and own_rel and
                       site_page.read_text(encoding="utf-8") == ctx.store.read_artifact(ctx.run_id, own_rel))
        details = self._details(window, visitors, signups, counts, excluded, "local first-party events")
        details["published_to_mock_site"] = published
        details["published_page_matches_this_attempt"] = current
        state, notes = READY, f"Local first-party events: {signups} sign-ups / {visitors} eligible unique visitors."
        if published and not current:
            notes += (" The page on the MOCKED site is from an earlier attempt, so these visits may not reflect "
                      "this attempt's copy.")
        if not window["closed"]:
            state = WAITING_FOR_DATA
            notes += (f" Window still open: {window['days_remaining']} days left (ends {iso(window['end'])}); "
                      "partial values are not evaluated.")
        if not published and visitors == 0:
            state = WAITING_FOR_DATA
            notes += (" The landing page was not published to the MOCKED site, so no traffic could be observed; "
                      "submit visitors and sign-ups from the analytics of wherever you hosted it.")
        if signups > visitors:
            state = INVALID_DATA
            notes += " More sign-ups than visitors: page-view events were lost, so the rate cannot be trusted."
        evidence_ids = []
        if state == READY:
            row = ctx.ledger.add(Evidence(
                provenance="DIRECT_OBSERVATION", source_type="local_page_analytics",
                title="Landing-page demand test: first-party analytics", value=float(signups), unit="waitlist sign-ups",
                denominator=float(visitors), observed_at=utc_now(),
                excerpt=f"{signups} unique sign-ups from {visitors} eligible unique visitors, window {window['text']}",
                method="unique visitor_id page views and unique email_hash sign-ups, internal/bot/fixture excluded",
                limitations="Visitors who block scripts are not counted as visitors."))
            evidence_ids.append(row.evidence_id)
        floor = criterion_target(contract, "unique_visitors", 300)
        return Observation(observed={"unique_visitors": float(visitors),
                                     "signup_rate": round(signups / visitors, 6) if visitors else None},
                           measurement_state=state, evidence_ids=evidence_ids, details=details, notes=notes,
                           pivot_target="2.1" if visitors < floor else "1.4")

    def data_fields(self) -> list[DataField]:
        return [
            DataField("unique_visitors", "Eligible unique visitors (external analytics)", type="integer", required=False,
                      help="Only if the page ran somewhere the local analytics cannot see. Leave both numbers blank "
                           "to re-read the local first-party events."),
            DataField("signups", "Unique waitlist sign-ups (external analytics)", type="integer", required=False,
                      help="Deduplicated by email; excluding you, your team and test entries."),
            DataField("analytics_source", "Where these numbers come from", type="text", required=False,
                      help="For example the name of the analytics tool or form service."),
        ]

    def observe(self, ctx, contract: Contract, data: dict[str, Any]) -> Observation:
        raw_v, raw_s = data.get("unique_visitors"), data.get("signups")
        if raw_v in (None, "") and raw_s in (None, ""):
            return self.collect(ctx, contract)   # nothing typed in: refresh from the local events
        visitors, signups = as_count(raw_v), as_count(raw_s)
        window = window_info(contract)
        if visitors is None or signups is None or signups > visitors:
            return Observation(observed={"unique_visitors": float(visitors) if visitors is not None else None,
                                         "signup_rate": None}, measurement_state=INVALID_DATA,
                               details={"source": "founder_data", "submitted": {"unique_visitors": raw_v, "signups": raw_s}},
                               notes="Founder data rejected: submit both numbers as whole counts, with sign-ups not "
                                     "exceeding visitors.")
        source = str(data.get("analytics_source") or "").strip() or "analytics tool not named"
        row = ctx.ledger.add(Evidence(
            provenance="FOUNDER_REPORTED", source_type="founder_data",
            title=f"Landing-page results reported by the founder ({source})", value=float(signups),
            unit="waitlist sign-ups", denominator=float(visitors), observed_at=utc_now(),
            excerpt=f"{signups} sign-ups from {visitors} unique visitors, reported for window {window['text']}",
            method="founder-submitted external analytics"))
        details = self._details(window, visitors, signups, None, None, f"founder_data ({source})")
        state, notes = READY, f"Founder-reported ({source}): {signups} sign-ups / {visitors} unique visitors."
        if not window["closed"]:
            state = WAITING_FOR_DATA
            notes += (f" Submitted {window['days_remaining']} days before the locked window ends ({iso(window['end'])}); "
                      "the gate is evaluated on the full window. Submit again after it ends, or override with a reason.")
        floor = criterion_target(contract, "unique_visitors", 300)
        return Observation(observed={"unique_visitors": float(visitors),
                                     "signup_rate": round(signups / visitors, 6) if visitors else None},
                           measurement_state=state, evidence_ids=[row.evidence_id], details=details, notes=notes,
                           pivot_target="2.1" if visitors < floor else "1.4")

    @staticmethod
    def _details(window, visitors, signups, counts, excluded, source) -> dict[str, Any]:
        low, high = wilson_interval(signups, visitors)
        details: dict[str, Any] = {
            "source": source, "window": window["text"], "days_remaining": window["days_remaining"],
            "eligible_unique_visitors": visitors, "unique_signups": signups,
            "signup_rate": pct1(signups / visitors) if visitors else "n/a (no visitors)",
            "signup_rate_95ci_wilson": f"{pct1(low)} to {pct1(high)}" if low is not None else "n/a",
        }
        if counts is not None:
            answered = counts["follow_up_answered"]
            details["follow_up_answered"] = (f"{answered}/{signups} ({pct1(answered / signups)}; reference 20%, "
                                             "not gated)") if signups else "n/a"
            details["by_source"] = counts["by_source"]
        if excluded is not None:
            details["excluded_events"] = excluded
        return details
