"""Phase 6: Operate and learn.

6.1 Support       gate E: FAQ from the user docs, ticket categories, severities, honest templates, escalation.
                  Response-time statistics are computed in code from real tickets only.
6.2 Metrics       gate E: dashboard definitions; values observable from the local first-party events are
                  computed in code, everything else is "not observable yet" until the founder reports cohorts.
6.3 DecisionMemo  gate A: cross-phase gate table built in code, PERSEVERE allowed only when every evidence or
                  test gate in phases 1-5 passed without an override, unit economics computed in code.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from datetime import datetime, timezone
from typing import Any

import guardrails
from agents import memo_writer, metrics_analyst, support_lead
from agents.base import StepContext, as_list
from agents.memo_writer import PIVOT_TYPES, RECOMMENDATIONS, SCENARIOS
from agents.pricing_analyst import to_number
from evidence import Claim, Evidence
from gates import INSUFFICIENT_DATA, INVALID_DATA, WAITING_FOR_DATA, Contract, Criterion, wilson_interval
from phases.base import DataField, Observation, StepHandler, StepOutput
from phases.commercial import MOCK_NOTE, cell, measurement_state, money, prior_digest, to_int
from steps import STEPS, STEPS_BY_ID

# ---------------------------------------------------------------------------------------------- 6.1 support

REQUIRED_CATEGORIES: list[tuple[str, str, str]] = [
    ("onboarding", "Onboarding", "Getting started, first use and setup questions."),
    ("confusion", "Confusion", "The user does not understand how a feature or result works."),
    ("missing_feature", "Missing feature", "The user needs something the product does not do yet."),
    ("reliability", "Reliability", "Errors, crashes, slowness or lost work."),
    ("fulfillment", "Fulfillment", f"Access or delivery did not arrive or was wrong (delivery is {MOCK_NOTE} in this prototype)."),
    ("trust_privacy", "Trust and privacy", "Questions or concerns about data, security or who sees what."),
    ("offer_misunderstanding", "Offer misunderstanding",
     f"The user misread the offer, the proposed price or the no-charge ({MOCK_NOTE}) order."),
]
DEFAULT_SEVERITIES: list[dict[str, Any]] = [
    {"level": "critical", "definition": "Data exposure, the product is unusable for everyone, or a wrong delivery.",
     "first_response_target_hours": 4, "examples": []},
    {"level": "high", "definition": "A core flow is broken for some users and there is no workaround.",
     "first_response_target_hours": 24, "examples": []},
    {"level": "medium", "definition": "A problem with a workaround, or a confusing step.", "first_response_target_hours": 48,
     "examples": []},
    {"level": "low", "definition": "Questions, suggestions and cosmetic issues.", "first_response_target_hours": 72,
     "examples": []},
]
SEVERITIES = tuple(s["level"] for s in DEFAULT_SEVERITIES)
_PROMISE = re.compile(
    r"\b(guarantee\w*|we promise|i promise|promise (you|that)|will definitely|100% (fixed|sure|guaranteed)|"
    r"full refund|refund (your|the) (money|payment)|money[- ]back)\b", re.IGNORECASE)


def default_template(category_id: str, name: str) -> dict[str, str]:
    return {"id": f"{category_id}-default", "category": category_id, "title": f"{name}: first reply",
            "body": (f"Hi, thanks for writing in. I have logged this as a {name.lower()} question. To look into it, "
                     "could you tell me what you were trying to do, what happened instead, and when it happened? "
                     "I will reply in this thread as soon as I know more.\n[Your name]")}


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_tickets(raw: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse founder-submitted tickets. Returns (tickets, problems); drills/tests are kept but flagged."""
    if raw in (None, ""):
        return [], []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        raw = raw.get("tickets")
    if not isinstance(raw, list):
        raise ValueError("expected a JSON list of tickets")
    tickets, problems = [], []
    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            problems.append(f"ticket {index}: not an object")
            continue
        try:
            created = _parse_time(row.get("created_at"))
            first = _parse_time(row.get("first_response_at"))
            resolved = _parse_time(row.get("resolved_at"))
        except (TypeError, ValueError):
            problems.append(f"ticket {index}: a timestamp is not ISO 8601")
            continue
        if created is None:
            problems.append(f"ticket {index}: created_at is required")
            continue
        if (first and first < created) or (resolved and resolved < created):
            problems.append(f"ticket {index}: a response or resolution is earlier than created_at")
            continue
        severity = str(row.get("severity") or "").strip().lower()
        tickets.append({"index": index, "category": str(row.get("category") or "uncategorised").strip().lower(),
                        "severity": severity if severity in SEVERITIES else "unspecified",
                        "created_at": created, "first_response_at": first, "resolved_at": resolved,
                        "drill": bool(row.get("drill") or row.get("test") or row.get("fixture"))})
    return tickets, problems


def ticket_stats(tickets: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    """Counts, median and max first-response hours (calendar hours), and critical issues open over 72h."""
    real = [t for t in tickets if not t["drill"]]
    stats: dict[str, Any] = {"tickets_observed": len(real), "drills_excluded": len(tickets) - len(real),
                             "as_of": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"), "hours_basis": "calendar hours"}
    if not real:
        stats.update({"median_first_response_hours": None, "max_first_response_hours": None,
                      "critical_open_over_72h": None,
                      "note": "No real tickets: no observed response-time denominator."})
        return stats
    hours, unanswered = [], 0
    for t in real:
        end = t["first_response_at"] or as_of
        if t["first_response_at"] is None:
            unanswered += 1
        hours.append(max(0.0, (end - t["created_at"]).total_seconds() / 3600))
    critical_open = [t for t in real if t["severity"] == "critical"
                     and (t["resolved_at"] is None or t["resolved_at"] > as_of)
                     and (as_of - t["created_at"]).total_seconds() / 3600 > 72]
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for t in real:
        by_severity[t["severity"]] = by_severity.get(t["severity"], 0) + 1
        by_category[t["category"]] = by_category.get(t["category"], 0) + 1
    stats.update({
        "median_first_response_hours": round(statistics.median(hours), 2),
        "max_first_response_hours": round(max(hours), 2),
        "unanswered": unanswered,
        "critical_open_over_72h": len(critical_open),
        "by_severity": by_severity, "by_category": by_category,
    })
    if unanswered:
        stats["unanswered_note"] = (f"{unanswered} unanswered ticket(s) are counted at their current age, a lower bound "
                                    "on their real first-response time.")
    if len(real) < 10:
        stats["individual_response_hours"] = [round(h, 2) for h in hours]
        stats["low_volume_note"] = "Fewer than 10 tickets: read the individual ages, not the percentile."
    return stats


class Support(StepHandler):
    """6.1 Support: workflow and FAQ; gate E on real first-response times and open critical issues."""

    def generate(self, ctx: StepContext) -> StepOutput:
        payload = {
            "product": ctx.concept(),
            "user_docs": prior_digest(ctx, "3.3", ("docs", "quick_start", "faq", "how_to", "how_tos",
                                                   "known_limitations", "limitations"), 5000),
            "mvp_scope": prior_digest(ctx, "3.1", ("must_haves", "core_flows", "wont_build"), 1500),
            "policies": ctx.prior("4.2").get("policies"),
            "required_categories": [c[0] for c in REQUIRED_CATEGORIES],
            "required_severities": list(SEVERITIES),
            "feedback": ctx.feedback,
        }
        reply = support_lead.support_setup(ctx, payload)
        notes: list[str] = []

        categories = {c["id"]: c for c in reply["ticket_categories"] if c["id"]}
        for cid, name, description in REQUIRED_CATEGORIES:
            if cid not in categories:
                categories[cid] = {"id": cid, "name": name, "description": description, "examples": []}
                notes.append(f"Added the required category '{cid}'.")
        severities = {s["level"]: s for s in reply["severity_levels"] if s["level"] in SEVERITIES}
        for default in DEFAULT_SEVERITIES:
            if default["level"] not in severities:
                severities[default["level"]] = dict(default)
                notes.append(f"Added the default severity '{default['level']}'.")
            elif severities[default["level"]]["first_response_target_hours"] is None:
                severities[default["level"]]["first_response_target_hours"] = default["first_response_target_hours"]
        templates = []
        for template in reply["response_templates"]:
            if _PROMISE.search(template["body"]) or guardrails.check_marketing(template["body"]):
                name = categories.get(template["category"], {}).get("name") or template["category"] or "support"
                templates.append(default_template(template["category"] or "general", name))
                notes.append(f"Replaced template '{template['id']}': it made a promise or broke a copy rule.")
            else:
                templates.append(template)
        covered = {t["category"] for t in templates}
        for cid, name, _ in REQUIRED_CATEGORIES:
            if cid not in covered:
                templates.append(default_template(cid, name))
        faq = reply["faq"]
        if not faq:
            notes.append("No FAQ entries could be built from the user docs.")
        hours = reply["hours_policy"]

        lines = ["## FAQ / knowledge base (from the step 3.3 user docs)", ""]
        lines += [f"**{f['q']}**  \n{f['a']}  \n_Source: {f['source'] or 'TO VERIFY'}_\n" for f in faq] or ["_None yet._", ""]
        lines += ["## Ticket categories", "", "| Id | Category | Description | Examples |", "|---|---|---|---|"]
        lines += [f"| {c['id']} | {cell(c['name'])} | {cell(c['description'])} | {cell('; '.join(c['examples']))} |"
                  for c in categories.values()]
        lines += ["", "## Severity levels", "", "| Level | Definition | First-response target (hours) |", "|---|---|---|"]
        lines += [f"| {lvl} | {cell(severities[lvl]['definition'])} | {severities[lvl]['first_response_target_hours']:g} |"
                  for lvl in SEVERITIES]
        lines += ["", "## Response templates", ""]
        for t in templates:
            lines += [f"### {t['title'] or t['id']} (`{t['category']}`)", "", t["body"], ""]
        lines += ["## Escalation rules", ""] + [f"- {r}" for r in reply["escalation_rules"] or
                                                ["Any critical ticket goes to the founder immediately."]]
        basis = hours["basis"]
        lines += ["", "## Hours", "",
                  f"- Targets are set in **{basis} hours**" + (f" ({hours['business_hours']}, {hours['timezone']})"
                                                                if basis == "business" else "") + ".",
                  "- The gate measures first-response time in calendar hours from the ticket timestamps.", "",
                  "## How tickets are reported and measured", "",
                  "Submit tickets as a JSON list: `{category, severity, created_at, first_response_at, resolved_at}` "
                  "(ISO 8601 times; mark practice tickets with `\"drill\": true`). Code computes the count, the median "
                  "and maximum first-response hours and the critical issues open longer than 72 hours. Drills are "
                  "excluded from the gate. With zero real tickets there is no observed response time, so the gate "
                  "cannot be evaluated.", ""]
        if reply["docs_gaps"]:
            lines += ["## Gaps in the user docs", ""] + [f"- {g}" for g in reply["docs_gaps"]] + [""]
        if notes:
            lines += ["## Checks applied in code", ""] + [f"- {n}" for n in notes]
        data = {"faq": faq, "ticket_categories": list(categories.values()),
                "severity_levels": [severities[lvl] for lvl in SEVERITIES], "response_templates": templates,
                "escalation_rules": reply["escalation_rules"], "hours_policy": hours, "docs_gaps": reply["docs_gaps"],
                "notes": notes}
        marketing = "\n".join([f"{f['q']} {f['a']}" for f in faq] + [t["body"] for t in templates])
        return StepOutput(
            title="Support workflow, FAQ and response templates", markdown="\n".join(lines), data=data,
            summary=(f"Set up support with {len(faq)} FAQ entries, {len(categories)} ticket categories and "
                     f"{len(templates)} response templates. The gate needs real tickets with timestamps."),
            questions=reply["questions"], marketing_text=marketing)

    def default_contract(self, ctx: StepContext) -> Contract:
        return Contract(
            step_id="6.1", decision="Is support responsive enough to keep operating?",
            hypothesis="Real users get a first response within a day and no critical issue stays open beyond 72 hours.",
            criteria=[
                Criterion(key="tickets_observed", label="Real support tickets observed", op=">=", target=1,
                          unit="tickets", kind="floor"),
                Criterion(key="median_first_response_hours", label="Median first response (calendar hours)", op="<=",
                          target=24, unit="hours"),
                Criterion(key="critical_open_over_72h", label="Unresolved critical issues older than 72 hours",
                          op="<=", target=0, unit="issues", kind="hard"),
            ],
            window_days=14, pivot_target="3.2",
            notes="Drills are kept apart from real tickets and never count as response evidence.")

    def data_fields(self) -> list[DataField]:
        return [
            DataField("tickets_json", "Support tickets", type="json",
                      help='JSON list of {"category", "severity", "created_at", "first_response_at", "resolved_at"} '
                           '(ISO 8601). Add "drill": true for practice tickets. An empty list means no tickets yet.'),
            DataField("as_of", "Measured as of (ISO 8601, optional)", type="text", required=False,
                      help="Defaults to now (UTC)."),
        ]

    def observe(self, ctx: StepContext, contract: Contract, data: dict[str, Any]) -> Observation:
        observed: dict[str, float | None] = {c.key: None for c in contract.criteria}
        try:
            as_of = _parse_time(data.get("as_of")) or datetime.now(timezone.utc)
            tickets, problems = parse_tickets(data.get("tickets_json"))
        except (TypeError, ValueError) as exc:
            tickets, problems, as_of = [], [f"tickets could not be read: {exc}"], datetime.now(timezone.utc)
        if problems:
            return Observation(observed=observed, measurement_state=INVALID_DATA,
                               details={"source": "founder_data", "problems": problems},
                               notes="INVALID: " + "; ".join(problems[:5]))
        stats = ticket_stats(tickets, as_of)
        for key in ("tickets_observed", "median_first_response_hours", "critical_open_over_72h"):
            if key in observed and stats.get(key) is not None:
                observed[key] = float(stats[key])
        evidence_ids = []
        if stats["tickets_observed"]:
            ev = ctx.ledger.add(Evidence(
                provenance="FOUNDER_REPORTED", source_type="founder_data", title="Support tickets (founder-submitted)",
                excerpt=(f"{stats['tickets_observed']} real tickets; median first response "
                         f"{stats['median_first_response_hours']} h; {stats['critical_open_over_72h']} critical open > 72 h."),
                value=float(stats["tickets_observed"]), unit="tickets", method="statistics computed in code",
                observed_at=stats["as_of"]))
            evidence_ids.append(ev.evidence_id)
            state = measurement_state(contract, observed)
        else:
            # Zero tickets is no data, not a support failure: the gate stays not evaluable.
            state = INSUFFICIENT_DATA
        missing = [c.key for c in contract.criteria if observed.get(c.key) is None]
        details = {"source": "founder_data", **stats, "missing": missing}
        if not stats["tickets_observed"]:
            details["missing"] = []  # keep the step not evaluable even when values are merged from earlier data
        notes = (f"Founder-submitted tickets; {stats['tickets_observed']} real, {stats['drills_excluded']} drills excluded; "
                 "calendar hours")
        if not stats["tickets_observed"]:
            notes += "; no real tickets, so no observed response-time denominator"
        return Observation(observed=observed, measurement_state=state, evidence_ids=evidence_ids, details=details,
                           notes=notes)


# ---------------------------------------------------------------------------------------------- 6.2 metrics

REQUIRED_METRICS: dict[str, dict[str, str]] = {
    "qualified_acquisition": {"name": "Qualified acquisition", "question": "Are eligible people entering the funnel?",
                              "numerator": "Unique eligible visitors or accounts entering the funnel",
                              "denominator": "-", "window": "per source, per week",
                              "cohort_rule": "Exclude internal, test and research-recruit traffic"},
    "activation": {"name": "Activation", "question": "Do new users reach the first value event?",
                   "numerator": "Eligible new users who completed the value event within the activation window",
                   "denominator": "Eligible new users whose activation window is complete",
                   "window": "activation window after first entry", "cohort_rule": "Event-time cohorts; mature cohorts only"},
    "time_to_value": {"name": "Time to value", "question": "How long until users get value?",
                      "numerator": "Median time from first entry to the value event",
                      "denominator": "Activated users (show the unactivated share alongside)", "window": "per cohort",
                      "cohort_rule": "Event-time cohorts"},
    "retention_week1": {"name": "Week-1 retention", "question": "Do users come back in week 1?",
                        "numerator": "Cohort members repeating the value event in days 7-13",
                        "denominator": "Eligible cohort (state: activated users or all new users)", "window": "week 1",
                        "cohort_rule": "Only cohorts at least 14 days old"},
    "retention_week4": {"name": "Week-4 retention", "question": "Do users still use it after a month?",
                        "numerator": "Cohort members repeating the value event in days 28-34",
                        "denominator": "Eligible cohort (state: activated users or all new users)", "window": "week 4",
                        "cohort_rule": "Only cohorts at least 35 days old"},
    "quality": {"name": "Quality and fulfillment", "question": "Does the product do the job?",
                "numerator": "Successful jobs", "denominator": "Attempted jobs", "window": "per week",
                "cohort_rule": f"Includes {MOCK_NOTE} deliveries; list failure reasons"},
    "pricing_intent": {"name": "Pricing intent", "question": "Do people act at the displayed price?",
                       "numerator": f"Paid-plan clicks or {MOCK_NOTE} order requests",
                       "denominator": "Unique pricing or store page visitors", "window": "per offer and channel",
                       "cohort_rule": "No money changes hands: intent at a displayed price only"},
    "support_load": {"name": "Support load", "question": "How much support does each user need?",
                     "numerator": "Support tickets", "denominator": "Active users", "window": "per week",
                     "cohort_rule": "Real tickets only; drills excluded"},
    "attachment_survey": {"name": "Attachment survey (Sean Ellis)", "question": "Would users be very disappointed without it?",
                          "numerator": "Respondents answering 'very disappointed'",
                          "denominator": "Completed responses from users who experienced the core value",
                          "window": "one survey wave", "cohort_rule": "Invite only users past the value event; report invitations"},
    "forecast_commercial": {"name": "Forecast commercial metrics", "question": "Could the economics work?",
                            "numerator": "Scenario CAC, contribution, payback", "denominator": "-",
                            "window": "scenario", "cohort_rule": f"Unavailable as observed values: checkout is {MOCK_NOTE}"},
}
PAGE_VIEW_TYPES = {"page_view", "pageview", "view", "visit"}
SIGNUP_TYPES = {"signup", "sign_up", "sign-up", "waitlist_signup", "waitlist"}
ORDER_TYPES = {"mock_order", "mock_order_request", "order_request", "order", "buy", "buy_click", "mock_buy"}
PLAN_CLICK_TYPES = {"plan_click", "paid_plan_click", "choose_plan"}
INTERNAL_FLAGS = ("internal", "is_internal", "fixture", "test", "bot")


def _etype(event: dict[str, Any]) -> str:
    return str(event.get("type") or event.get("event") or event.get("name") or "").strip().lower()


def _visitor(event: dict[str, Any]) -> str | None:
    value = event.get("visitor_id") or event.get("visitor") or event.get("vid") or event.get("session_id")
    return str(value) if value else None


def _page(event: dict[str, Any]) -> str:
    page = str(event.get("page") or event.get("path") or "").strip().lower()
    if "store" in page:
        return "store"
    if "pricing" in page:
        return "pricing"
    if "landing" in page or page in ("", "/", "index", "index.html"):
        return "landing"
    return page


def observable_counts(events: list[dict[str, Any]]) -> dict[str, Any]:
    """What the local first-party events can show (internal, test and fixture traffic excluded)."""
    eligible = [e for e in events if isinstance(e, dict) and not any(e.get(flag) for flag in INTERNAL_FLAGS)]
    visitors: dict[str, set[str]] = {"landing": set(), "store": set(), "pricing": set()}
    views_without_id = 0
    signups: set[str] = set()
    signup_events = 0
    orders: set[str] = set()
    plan_clickers: set[str] = set()
    for position, e in enumerate(eligible):
        kind = _etype(e)
        who = _visitor(e)
        if kind in PAGE_VIEW_TYPES:
            page = _page(e)
            if page in visitors and who:
                visitors[page].add(who)
            elif not who:
                views_without_id += 1
        elif kind in SIGNUP_TYPES:
            signup_events += 1
            signups.add(str(e.get("email_hash") or who or e.get("event_id") or f"#{position}"))
        elif kind in ORDER_TYPES:
            orders.add(str(e.get("order_id") or e.get("event_id") or f"#{position}"))
        elif kind in PLAN_CLICK_TYPES and who:
            plan_clickers.add(who)
    return {"events_total": len(events), "events_excluded_internal_or_test": len(events) - len(eligible),
            "unique_landing_visitors": len(visitors["landing"]), "unique_store_visitors": len(visitors["store"]),
            "unique_pricing_visitors": len(visitors["pricing"]), "page_views_without_visitor_id": views_without_id,
            "waitlist_signups": len(signups), "signup_events": signup_events,
            "mock_order_requests": len(orders), "paid_plan_clickers": len(plan_clickers)}


NOT_OBSERVABLE = ["activation", "time_to_value", "retention_week1", "retention_week4", "quality", "support_load",
                  "attachment_survey", "forecast_commercial"]


def _rate(numerator: int | None, denominator: int | None) -> tuple[float | None, list[float | None]]:
    if numerator is None or denominator is None or denominator <= 0:
        return None, [None, None]
    low, high = wilson_interval(numerator, denominator)
    return round(numerator / denominator, 4), [low, high]


class Metrics(StepHandler):
    """6.2 Metrics: decision dashboard; gate E on activation, week-4 retention and the attachment survey."""

    def generate(self, ctx: StepContext) -> StepOutput:
        counts = observable_counts(ctx.store.read_events(ctx.run_id))
        payload = {
            "product": ctx.concept(),
            "lean_canvas_key_metrics": prior_digest(ctx, "2.1", ("key_metrics", "channels", "uvp"), 1200),
            "mvp_core_flows": prior_digest(ctx, "3.1", ("core_flows", "must_haves"), 1500),
            "required_metric_keys": list(REQUIRED_METRICS),
            "recorded_event_types": ["page_view (landing, pricing, store)", "waitlist signup",
                                     f"{MOCK_NOTE} order request", "paid-plan click"],
            "feedback": ctx.feedback,
        }
        reply = metrics_analyst.dashboard_spec(ctx, payload)
        notes: list[str] = []
        given = {m["key"]: m for m in reply["metrics"]}
        metrics = []
        for key, default in REQUIRED_METRICS.items():
            metric = {**default, "key": key, "data_source": "", **{k: v for k, v in given.get(key, {}).items() if v}}
            if key not in given:
                notes.append(f"Added the default definition for '{key}'.")
            if key == "forecast_commercial":
                metric["status"] = f"unavailable as an observed value ({MOCK_NOTE} checkout: no real payments)"
            elif key in ("qualified_acquisition", "pricing_intent"):
                metric["status"] = "partly observable from local events"
            else:
                metric["status"] = "not observable yet"
            metrics.append(metric)
        metrics += [m for k, m in given.items() if k not in REQUIRED_METRICS][:4]

        observable_rows = [
            ("Unique landing-page visitors", counts["unique_landing_visitors"]),
            ("Unique pricing-page visitors", counts["unique_pricing_visitors"]),
            ("Unique store-page visitors", counts["unique_store_visitors"]),
            ("Waitlist sign-ups", counts["waitlist_signups"]),
            (f"{MOCK_NOTE} order requests (no money changes hands)", counts["mock_order_requests"]),
            ("Visitors who clicked a paid plan", counts["paid_plan_clickers"]),
        ]
        lines = [f"Value event: **{reply['value_event'] or 'not defined yet'}**"
                 + (f"; activation window {reply['activation_window_days']} days." if reply["activation_window_days"] else "."),
                 "", "## Metric definitions", "",
                 "| Metric | Question | Numerator | Denominator | Window | Cohort rule | Status |",
                 "|---|---|---|---|---|---|---|"]
        lines += [f"| {cell(m['name'])} | {cell(m.get('question'))} | {cell(m.get('numerator'))} | {cell(m.get('denominator'))} "
                  f"| {cell(m.get('window'))} | {cell(m.get('cohort_rule'))} | {cell(m.get('status', 'definition only'))} |"
                  for m in metrics]
        lines += ["", "## Observable now (local first-party events, computed in code)", "",
                  "| Measure | Value |", "|---|---|"]
        lines += [f"| {label} | {value} |" for label, value in observable_rows]
        lines += ["", f"Events read: {counts['events_total']}; excluded as internal/test/fixture: "
                      f"{counts['events_excluded_internal_or_test']}; page views without a visitor id: "
                      f"{counts['page_views_without_visitor_id']}.", "",
                  "## Not observable yet", "",
                  "Activation, time to value, week-1 and week-4 retention, quality, support load and the attachment "
                  "survey need product-usage cohorts or survey answers the prototype does not record. Report them as "
                  "cohort counts; rates and intervals are computed in code. Forecast commercial metrics stay "
                  f"scenario-only because checkout is {MOCK_NOTE}.", ""]
        if reply["data_quality_checks"]:
            lines += ["## Data-quality checks", ""] + [f"- {c}" for c in reply["data_quality_checks"]] + [""]
        if reply["instrumentation_gaps"]:
            lines += ["## Instrumentation gaps", ""] + [f"- {g}" for g in reply["instrumentation_gaps"]] + [""]
        if notes:
            lines += ["## Checks applied in code", ""] + [f"- {n}" for n in notes]
        data = {"value_event": reply["value_event"], "activation_window_days": reply["activation_window_days"],
                "metrics": metrics, "observable_now": counts, "not_observable_yet": NOT_OBSERVABLE,
                "data_quality_checks": reply["data_quality_checks"], "instrumentation_gaps": reply["instrumentation_gaps"],
                "notes": notes}
        return StepOutput(
            title="Decision dashboard specification", markdown="\n".join(lines), data=data,
            summary=("Defined the decision-dashboard metrics and computed what the local events show. Activation, "
                     "retention and the attachment survey need founder-reported cohorts."),
            questions=reply["questions"])

    def default_contract(self, ctx: StepContext) -> Contract:
        return Contract(
            step_id="6.2", decision="Do users activate, stay and care enough to keep building?",
            hypothesis="A mature cohort activates, a fifth still use the product in week 4, and 40% would be very disappointed without it.",
            criteria=[
                Criterion(key="eligible_cohort", label="Eligible new users with a complete activation window",
                          op=">=", target=30, unit="users", kind="floor"),
                Criterion(key="activation_rate", label="Activation rate", op=">=", target=0.4, unit="share",
                          kind="proportion"),
                Criterion(key="week4_retention", label="Week-4 retention", op=">=", target=0.2, unit="share",
                          kind="proportion"),
                Criterion(key="very_disappointed_rate", label="Sean Ellis 'very disappointed' share", op=">=",
                          target=0.4, unit="share", kind="proportion"),
            ],
            window_days=35, pivot_target="3.1",
            notes="Week-4 retention needs cohorts at least 35 days old. Rates are computed in code from submitted counts.")

    def collect(self, ctx: StepContext, contract: Contract) -> Observation:
        counts = observable_counts(ctx.store.read_events(ctx.run_id))
        evidence_ids = []
        if counts["events_total"]:
            ev = ctx.ledger.add(Evidence(
                provenance="DIRECT_OBSERVATION", source_type="local_events",
                title="Local first-party events (landing, pricing, store pages)",
                excerpt=(f"{counts['unique_landing_visitors']} landing, {counts['unique_store_visitors']} store visitors; "
                         f"{counts['waitlist_signups']} sign-ups; {counts['mock_order_requests']} MOCKED order requests."),
                value=float(counts["unique_landing_visitors"]), unit="unique landing visitors",
                method="counted in code from events.json, internal/test traffic excluded"))
            evidence_ids.append(ev.evidence_id)
        return Observation(observed={c.key: None for c in contract.criteria}, measurement_state=WAITING_FOR_DATA,
                           evidence_ids=evidence_ids,
                           details={"observable_now": counts, "not_observable_yet": NOT_OBSERVABLE},
                           notes="Local events cannot show activation, retention or survey answers; founder cohort data needed")

    def data_fields(self) -> list[DataField]:
        return [
            DataField("eligible_cohort", "Eligible new users whose activation window is complete", type="integer"),
            DataField("activated_users", "Of those, users who reached the value event in the window", type="integer"),
            DataField("week4_cohort", "Users in cohorts at least 35 days old", type="integer", required=False),
            DataField("week4_retained", "Of those, users repeating the value event in week 4", type="integer",
                      required=False),
            DataField("retention_base", "Retention base", type="choice", required=False,
                      choices=["activated users", "all new users"]),
            DataField("survey_responses", "Completed Sean Ellis survey responses", type="integer", required=False),
            DataField("very_disappointed", "Responses answering 'very disappointed'", type="integer", required=False),
        ]

    def observe(self, ctx: StepContext, contract: Contract, data: dict[str, Any]) -> Observation:
        values = {k: to_int(data.get(k)) for k in ("eligible_cohort", "activated_users", "week4_cohort",
                                                   "week4_retained", "survey_responses", "very_disappointed")}
        problems = [f"{k} cannot be negative" for k, v in values.items() if v is not None and v < 0]
        for part, whole in (("activated_users", "eligible_cohort"), ("week4_retained", "week4_cohort"),
                            ("very_disappointed", "survey_responses")):
            if values[part] is not None and values[whole] is not None and values[part] > values[whole]:
                problems.append(f"{part} cannot exceed {whole}")
        observed: dict[str, float | None] = {c.key: None for c in contract.criteria}
        if problems:
            return Observation(observed=observed, measurement_state=INVALID_DATA,
                               details={"source": "founder_data", "problems": problems},
                               notes="INVALID: " + "; ".join(problems))
        activation, act_ci = _rate(values["activated_users"], values["eligible_cohort"])
        retention, ret_ci = _rate(values["week4_retained"], values["week4_cohort"])
        disappointed, sur_ci = _rate(values["very_disappointed"], values["survey_responses"])
        computed = {"eligible_cohort": None if values["eligible_cohort"] is None else float(values["eligible_cohort"]),
                    "activation_rate": activation, "week4_retention": retention,
                    "very_disappointed_rate": disappointed}
        for key in observed:
            observed[key] = computed.get(key)
        details: dict[str, Any] = {
            "source": "founder_data", "counts": values, "retention_base": data.get("retention_base") or "not stated",
            "wilson_95": {"activation_rate": act_ci, "week4_retention": ret_ci, "very_disappointed_rate": sur_ci},
            "observable_now": observable_counts(ctx.store.read_events(ctx.run_id)),
        }
        if values["survey_responses"] is not None and values["survey_responses"] < 30:
            details["survey_caveat"] = "Fewer than 30 survey responses: directional only."
        evidence_ids = []
        if any(v is not None for v in values.values()):
            ev = ctx.ledger.add(Evidence(
                provenance="FOUNDER_REPORTED", source_type="founder_data", title="Cohort metrics (founder-reported counts)",
                excerpt="; ".join(f"{k}={v}" for k, v in values.items() if v is not None),
                value=computed["eligible_cohort"], unit="eligible users", method="rates and Wilson intervals computed in code"))
            evidence_ids.append(ev.evidence_id)
        missing = [c.key for c in contract.criteria if observed.get(c.key) is None]
        details["missing"] = missing
        return Observation(observed=observed, measurement_state=measurement_state(contract, observed),
                           evidence_ids=evidence_ids, details=details,
                           notes="Founder-reported cohort counts; rates computed in code"
                                 + (f"; missing: {', '.join(missing)}" if missing else ""))


# ---------------------------------------------------------------------------------------------- 6.3 decision memo

PIVOT_TYPE_BY_STEP = {"1.1": "problem", "1.2": "problem", "1.3": "segment", "1.4": "problem", "2.1": "solution",
                      "2.2": "channel", "3.1": "solution", "3.2": "solution", "3.3": "solution", "4.1": "pricing",
                      "4.2": "pricing", "5.1": "channel", "5.2": "channel", "5.3": "pricing", "6.1": "solution",
                      "6.2": "solution"}
RETURN_STEP_BY_PIVOT = {"segment": "1.1", "problem": "1.1", "solution": "3.1", "channel": "2.1", "pricing": "4.1"}


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def build_gate_table(run) -> list[dict[str, Any]]:
    """One row per step before 6.3: gate types, locked thresholds, actual values, status, outcome, override."""
    rows = []
    for meta in STEPS:
        if meta.step_id == "6.3":
            continue
        st = run.steps.get(meta.step_id)
        if st is None:
            continue
        gate = st.gate or {}
        contract = st.contract or {}
        decision = st.decision or {}
        overridden = bool(st.overridden or decision.get("override"))
        criteria = contract.get("criteria") or []
        thresholds = [f"{c.get('key')} {c.get('op', '>=')} {_fmt(c.get('target'))}" for c in criteria]
        actual = {c.get("key"): c.get("actual") for c in gate.get("criteria") or []}
        if meta.has_evidence_gate:
            status = gate.get("status") or "NOT_RUN"
        elif st.outcome == "GO":
            status = "APPROVED"
        elif st.outcome:
            status = st.outcome
        else:
            status = "PENDING" if st.status != "NEW" else "NOT_RUN"
        rows.append({
            "step": meta.step_id, "name": meta.name, "phase": meta.phase, "gate_types": list(meta.gate_types),
            "evidence_gate": meta.has_evidence_gate, "thresholds": thresholds,
            "thresholds_locked": contract.get("status") == "LOCKED", "contract_version": contract.get("version"),
            "locked_on": (contract.get("locked_at") or "")[:10] or None,
            "actual": actual, "status": status, "recommended": gate.get("outcome"),
            "outcome": st.outcome or decision.get("chosen"), "overridden": overridden,
            "override_reason": decision.get("reason") if overridden else None,
            "evidence_passed": bool(gate.get("evidence_passed")),
        })
    return rows


def classify(row: dict[str, Any]) -> str:
    if row["status"] == "PASSED" and row["evidence_passed"] and not row["overridden"]:
        return "passed"
    if row["status"] == "PASSED":
        return "passed_overridden"
    if row["status"] in ("FAILED", "PARTIAL"):
        return "failed"
    return "not_evaluable"


def gate_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    evidence_rows = [r for r in rows if r["evidence_gate"]]
    kinds = [classify(r) for r in evidence_rows]
    return {"total": len(evidence_rows),
            "passed": sum(k in ("passed", "passed_overridden") for k in kinds),
            "passed_without_override": kinds.count("passed"),
            "failed": kinds.count("failed"),
            "not_evaluable": kinds.count("not_evaluable"),
            "overridden": sum(r["overridden"] for r in evidence_rows)}


def compute_unit_economics(scenario: dict[str, Any]) -> dict[str, Any]:
    """Contribution, CAC, payback and break-even from labelled inputs (all ESTIMATE)."""
    price, cost = scenario.get("net_price"), scenario.get("variable_cost")
    contribution = None if price is None or cost is None else round(price - cost, 4)
    cac, cac_source = scenario.get("cac"), "input" if scenario.get("cac") is not None else None
    total, customers = scenario.get("acquisition_cost_total"), scenario.get("customers_acquired")
    if cac is None and total is not None and customers:
        cac, cac_source = round(total / customers, 4), "acquisition_cost_total / customers_acquired"
    billing = scenario.get("billing") or "month"
    monthly = None
    if contribution is not None:
        monthly = contribution if billing == "month" else (contribution / 12 if billing == "year" else None)
    payback, payback_note = None, ""
    if cac is not None and monthly is not None:
        if monthly > 0:
            payback = round(cac / monthly, 2)
        else:
            payback_note = "never at these inputs (contribution is not positive)"
    elif billing == "one-time":
        payback_note = "not applicable to a one-time price"
    fixed = scenario.get("fixed_cost_per_month")
    per_month = monthly if billing != "one-time" else contribution
    break_even = None
    if fixed is not None and per_month is not None and per_month > 0:
        break_even = math.ceil(fixed / per_month)
    return {"unit_contribution": contribution, "monthly_unit_contribution": monthly, "cac": cac,
            "cac_source": cac_source, "simple_payback_months": payback, "payback_note": payback_note,
            "break_even_customers": break_even,
            "break_even_unit": "sales per month" if billing == "one-time" else "paying customers"}


class DecisionMemo(StepHandler):
    """6.3 Persevere-or-pivot memo (gate A: the founder records the final decision)."""

    def generate(self, ctx: StepContext) -> StepOutput:
        rows = build_gate_table(ctx.run)
        counts = gate_counts(rows)
        early = [r for r in rows if r["evidence_gate"] and r["phase"] <= 5]
        persevere_allowed = bool(early) and all(classify(r) == "passed" for r in early)
        allowed = list(RECOMMENDATIONS) if persevere_allowed else ["PIVOT", "STOP"]
        any_failed = any(classify(r) == "failed" for r in rows if r["evidence_gate"])
        pricing = ctx.prior("4.1")
        currency = pricing.get("currency") or "USD"
        summaries = {sid: st.summary[:300] for sid, st in ctx.run.steps.items() if st.summary and sid != "6.3"}
        sharpened = ctx.prior("1.1")
        payload = {
            "original_hypothesis": {"concept": ctx.concept(), "problem_statement": sharpened.get("problem_statement"),
                                    "brief_idea": ctx.brief.get("idea")},
            "gate_table": rows, "evidence_gate_counts": counts, "allowed_recommendations": allowed,
            "allowed_pivot_types": list(PIVOT_TYPES), "evidence_digest": ctx.evidence_digest(40),
            "deliverable_summaries": summaries,
            "pricing": {"currency": currency, "recommended_package_id": pricing.get("recommended_package_id"),
                        "packages": [{k: p.get(k) for k in ("id", "name", "price", "billing")}
                                     for p in as_list(pricing.get("packages")) if isinstance(p, dict)],
                        "economics_floor": pricing.get("economics_floor")},
            "feedback": ctx.feedback,
        }
        reply = memo_writer.decision_memo(ctx, payload)
        notes: list[str] = []

        recommendation = reply["recommendation"]
        replaced = None
        if recommendation not in allowed:
            new = "STOP" if any_failed else "PIVOT"
            reason = ("PERSEVERE is allowed only when every evidence or test gate in phases 1-5 passed without a "
                      "founder override" if recommendation == "PERSEVERE" else f"'{recommendation}' is not an allowed option")
            replaced = {"from": recommendation, "to": new, "reason": reason}
            notes.append(f"The model recommended {recommendation}; replaced with {new} ({reason}; "
                         f"{'an evidence gate FAILED' if any_failed else 'no evidence gate failed outright'}).")
            recommendation = new
        pivot_type = None
        if recommendation == "PIVOT":
            pivot_type = reply["pivot_type"] if reply["pivot_type"] in PIVOT_TYPES else None
            if pivot_type is None:
                first_gap = next((r for r in rows if r["evidence_gate"] and classify(r) != "passed"), None)
                pivot_type = PIVOT_TYPE_BY_STEP.get(first_gap["step"] if first_gap else "", "solution")
                notes.append(f"Pivot type set in code to '{pivot_type}' from the earliest unpassed evidence gate"
                             + (f" ({first_gap['step']})." if first_gap else "."))
        return_step = RETURN_STEP_BY_PIVOT.get(pivot_type) if pivot_type else None

        known = {ev.evidence_id for ev in ctx.ledger.all(include_fixtures=True)}
        unknown: set[str] = set()
        for group in ("supporting_evidence", "countervailing_evidence"):
            for point in reply[group]:
                unknown.update(i for i in point["evidence_ids"] if i not in known)
                point["evidence_ids"] = [i for i in point["evidence_ids"] if i in known]
        if unknown:
            notes.append(f"Removed citations of unknown evidence IDs: {', '.join(sorted(unknown))}.")

        econ = reply["unit_economics"]
        econ_currency = econ["currency"] or currency
        scenarios = {}
        for name in SCENARIOS:
            inputs = econ["scenarios"][name]
            scenarios[name] = {"inputs": inputs, "computed": compute_unit_economics(inputs)}

        experiments = list(reply["experiments"])
        for row in rows:
            if len(experiments) >= 3:
                break
            if row["evidence_gate"] and classify(row) != "passed":
                rule = "; ".join(row["thresholds"]) or "the locked thresholds"
                experiments.append({
                    "hypothesis": f"Step {row['step']} ({row['name']}) can meet its criteria with real data.",
                    "design": f"Re-run the step {row['step']} test under locked thresholds and submit the real results.",
                    "cost_time": "TO ESTIMATE with the founder", "data_source": "founder-submitted data or local events",
                    "owner": "founder", "decision_rule": f"GO only if {rule}; otherwise follow the gate outcome.",
                    "what_it_changes": "Turns an untested or failed assumption into evidence.", "added_by_code": "yes"})
        if len(experiments) < 3:
            notes.append(f"Only {len(experiments)} next experiment(s) could be grounded; define the rest with the founder.")

        overrides = [f"Step {r['step']} ({r['name']}): founder chose {r['outcome']} instead of "
                     f"{r['recommended'] or 'no outcome (not evaluable)'}. Reason: {r['override_reason'] or 'not given'}"
                     for r in rows if r["overridden"]]
        markdown = self._markdown(recommendation, pivot_type, return_step, reply, rows, counts, persevere_allowed,
                                  scenarios, econ, econ_currency, experiments, overrides, notes)
        claims = []
        for name in SCENARIOS:
            inputs = scenarios[name]["inputs"]
            for key in ("net_price", "variable_cost", "cac", "fixed_cost_per_month"):
                if inputs.get(key) is not None:
                    claims.append(Claim(text=f"{name} scenario {key.replace('_', ' ')}: {money(inputs[key], econ_currency)}",
                                        label="ESTIMATE", basis=inputs["basis"].get(key) or "no basis given"))
        for point in reply["supporting_evidence"] + reply["countervailing_evidence"]:
            if point["evidence_ids"]:
                claims.append(Claim(text=point["text"], label="SOURCED", evidence_ids=point["evidence_ids"]))
        data = {
            "recommendation": recommendation, "pivot_type": pivot_type, "return_step": return_step,
            "allowed_recommendations": allowed, "persevere_allowed": persevere_allowed,
            "recommendation_replaced": replaced, "gate_table": rows, "evidence_gate_counts": counts,
            "experiments": experiments, "unit_economics": {"currency": econ_currency, "scenarios": scenarios,
                                                           "label": "ESTIMATE", "mocked_commerce": True},
            "supporting_evidence": reply["supporting_evidence"], "countervailing_evidence": reply["countervailing_evidence"],
            "overrides": overrides, "notes": notes,
        }
        title = f"Recommendation: {recommendation}" + (f" ({pivot_type})" if pivot_type else "")
        return StepOutput(
            title=title, markdown=markdown, data=data, claims=claims,
            summary=(f"{title}. Evidence gates: {counts['passed_without_override']}/{counts['total']} passed without "
                     f"override, {counts['failed']} failed, {counts['not_evaluable']} not evaluable, "
                     f"{counts['overridden']} overridden. The founder records the final decision."),
            questions=reply["questions"])

    @staticmethod
    def _markdown(recommendation, pivot_type, return_step, reply, rows, counts, persevere_allowed, scenarios, econ,
                  currency, experiments, overrides, notes) -> str:
        head = f"## Recommendation: {recommendation}" + (f" (pivot type: {pivot_type}, return to step {return_step})"
                                                        if pivot_type else "")
        lines = [head, "", reply["headline"] or "", "",
                 f"Evidence and test gates: **{counts['passed_without_override']} of {counts['total']} passed without "
                 f"override**; {counts['failed']} failed; {counts['not_evaluable']} not evaluable; "
                 f"{counts['overridden']} overridden by the founder. Overrides and unevaluated gates count as untested.",
                 "", "PERSEVERE is " + ("allowed: every evidence gate in phases 1-5 passed without override."
                                        if persevere_allowed else
                                        "not allowed: not every evidence gate in phases 1-5 passed without override."),
                 "", "## Cross-phase gate table", "",
                 "| Step | Gate | Locked thresholds | Actual | Status | Outcome | Overridden |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            thresholds = "; ".join(r["thresholds"]) or ("founder approval" if not r["evidence_gate"] else "none")
            if r["thresholds"] and not r["thresholds_locked"]:
                thresholds += " (not locked)"
            actual = "; ".join(f"{k}={_fmt(v)}" for k, v in r["actual"].items()) or "-"
            lines.append(f"| {r['step']} {cell(r['name'])} | {'+'.join(r['gate_types'])} | {cell(thresholds)} | {cell(actual)} "
                         f"| {r['status']} | {r['outcome'] or '-'} | {'YES' if r['overridden'] else 'no'} |")
        lines += ["", "## Original hypothesis", "", reply["original_hypothesis"] or "_Not stated._", ""]
        for title, key in (("Strongest supporting evidence", "supporting_evidence"),
                           ("Strongest countervailing evidence", "countervailing_evidence")):
            lines += [f"## {title}", ""]
            points = reply[key]
            lines += [f"- {p['text']}" + (f" ({', '.join(p['evidence_ids'])})" if p["evidence_ids"] else "")
                      for p in points] or ["- _None given._"]
            lines.append("")
        for title, key in (("Proven", "proven"), ("Disproven", "disproven"), ("Assumptions that changed", "assumptions_changed"),
                           ("Unresolved", "unresolved")):
            if reply[key]:
                lines += [f"## {title}", ""] + [f"- {x}" for x in reply[key]] + [""]
        lines += ["## Overrides that affect interpretation", ""]
        lines += [f"- {o}" for o in overrides + reply["overrides_affecting_interpretation"]] or ["- None."]
        lines += ["", f"## Unit economics (ESTIMATE; no real sales: checkout is {MOCK_NOTE})", "",
                  "| Scenario | Net price | Variable cost | Unit contribution | CAC | Payback (months) | Fixed cost / month | Break-even |",
                  "|---|---|---|---|---|---|---|---|"]
        for name in SCENARIOS:
            i, c = scenarios[name]["inputs"], scenarios[name]["computed"]
            payback = _fmt(c["simple_payback_months"]) if c["simple_payback_months"] is not None else (c["payback_note"] or "n/a")
            be = f"{c['break_even_customers']} {c['break_even_unit']}" if c["break_even_customers"] is not None else "n/a"
            lines.append(f"| {name} | {money(i['net_price'], currency)} | {money(i['variable_cost'], currency)} "
                         f"| {money(c['unit_contribution'], currency)} | {money(c['cac'], currency)} | {payback} "
                         f"| {money(i['fixed_cost_per_month'], currency)} | {be} |")
        lines += ["", "Inputs are labelled estimates from the memo writer (bases listed under claims); unit contribution "
                      "= net price - variable cost, payback = CAC / monthly contribution and break-even = ceil(fixed "
                      "cost / contribution) are computed in code.", ""]
        if econ["main_sensitivity"]:
            lines += [f"Main sensitivity: {econ['main_sensitivity']}", ""]
        if econ["practical_constraint"]:
            lines += [f"Practical constraint: {econ['practical_constraint']}", ""]
        if reply["next_move"]:
            lines += ["## Next move", "", reply["next_move"], ""]
        lines += ["## Next 3 experiments", "",
                  "| # | Hypothesis | Design | Cost / time | Data source | Owner | Decision rule | What it changes |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {n} | {cell(e.get('hypothesis'))} | {cell(e.get('design'))} | {cell(e.get('cost_time'))} "
                  f"| {cell(e.get('data_source'))} | {cell(e.get('owner'))} | {cell(e.get('decision_rule'))} "
                  f"| {cell(e.get('what_it_changes'))} |" for n, e in enumerate(experiments, start=1)]
        if notes:
            lines += ["", "## Checks applied in code", ""] + [f"- {n}" for n in notes]
        lines += ["", "## Your decision", "",
                  "Record PERSEVERE, PIVOT or STOP. A decision that differs from this recommendation is logged as a "
                  "FOUNDER_OVERRIDE with your reason."]
        return "\n".join(lines)
