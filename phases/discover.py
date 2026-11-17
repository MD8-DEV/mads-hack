"""Phase 1 Discover: sharpen the idea, score alternatives, define the market, interview customers.

Handlers call role agents for drafts and do every count, total, rate and
interval here in Python. Numbers that cannot be measured stay None, so the
gate waits for data instead of passing on a guess.
"""
from __future__ import annotations

import json
import re
from typing import Any

from agents import interviewer, market_analyst, strategist
from agents.base import as_float, as_list
from evidence import CLAIM_LABELS, Claim
from gates import INSUFFICIENT_DATA, INVALID_DATA, READY, WAITING_FOR_DATA, Contract, Criterion, wilson_interval
from llm import LLMError
from phases.base import DataField, Observation, StepHandler, StepOutput

# ---------------------------------------------------------------------------------------------- helpers
NONE_WORDS = ("", "none", "no", "n/a", "na", "nothing", "null", "unknown", "-", "no evidence", "none yet")
URL_RE = re.compile(r"https?://[^\s<>\"'|,]+")
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _cell(value: Any, limit: int = 220) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "/").replace("\n", " ").strip()[:limit] or "-"


def _clip(value: Any, limit: int = 400) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().rstrip(".;")[:limit]


def _valid_ids(ctx, ids: Any) -> list[str]:
    return [i for i in dict.fromkeys(str(x).strip() for x in as_list(ids)) if i and ctx.ledger.get(i)]


def _label(value: Any, default: str = "ASSUMPTION") -> str:
    label = str(value or "").strip().upper()
    return label if label in CLAIM_LABELS else default


def _fmt(value: float | None, unit: str = "") -> str:
    if value is None:
        return "unknown"
    if unit in ("share", "rate"):
        return f"{value:.1%}"
    text = f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{text} {unit}".strip()


CONCEPT_KEYS = ("id", "name", "statement", "segment", "changed_assumption", "first_user", "smallest_test")


def _concept(ctx) -> dict[str, Any]:
    """The selected concept without its scorecard details (keeps model payloads small)."""
    concept = ctx.concept()
    return {k: concept.get(k) for k in CONCEPT_KEYS if concept.get(k)}


def _brief_evidence(ctx) -> list[str]:
    """Record what the founder reported in the brief as a FOUNDER_REPORTED row (once)."""
    text = str(ctx.brief.get("evidence") or "").strip()
    if text.lower() in NONE_WORDS or len(text) < 8:
        return []
    row = ctx.ledger.add({"provenance": "FOUNDER_REPORTED", "source_type": "founder_brief", "url": None,
                          "title": "Founder brief: existing evidence", "excerpt": text,
                          "method": "founder intake brief", "independence_group": "founder-brief",
                          "limitations": "Reported by the founder; not independently verified."})
    return [row.evidence_id]


def _numbers_in(text: str) -> list[float]:
    out = []
    for raw in NUMBER_RE.findall(text or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _value_in_evidence(ctx, value: float, ids: list[str]) -> bool:
    """True when a cited row carries this number (as its value or in its text), within 1%."""
    targets = [value, value * 100] if 0 < value <= 1 else [value]
    for evidence_id in ids:
        row = ctx.ledger.get(evidence_id)
        if row is None:
            continue
        candidates = ([row.value] if row.value is not None else []) + _numbers_in(f"{row.title} {row.excerpt}")
        for candidate in candidates:
            for target in targets:
                if abs(candidate - target) <= 0.01 * max(1.0, abs(target)):
                    return True
    return False


# ============================================================================================== 1.1
class SharpenIdea(StepHandler):
    """1.1: problem hypothesis, buying roles, 3-5 alternative concepts, status-quo baseline (gate A)."""

    def generate(self, ctx) -> StepOutput:
        brief = ctx.brief
        founder_ids = _brief_evidence(ctx)
        previous = ctx.prior("1.1") if (ctx.feedback or ctx.attempt) else {}
        payload = {
            "brief": {k: brief.get(k) for k in ("idea", "customer", "why_you", "jurisdiction", "budget", "time",
                                                "evidence", "values", "notes") if brief.get(k)},
            "title": ctx.run.title,
            "founder_evidence_ids": founder_ids,
            "previous_version": ({k: previous.get(k) for k in ("problem_statement", "segment", "alternatives")}
                                 if previous else None),
            "feedback": ctx.feedback,
        }
        reply = strategist.sharpen_idea(ctx, payload)

        segment = _clip(reply.get("segment"), 200)
        problem = _clip(reply.get("problem"), 300)
        situation = _clip(reply.get("situation"), 300) or "UNKNOWN situation (ask the founder)"
        workaround = _clip(reply.get("workaround"), 300) or "use an UNKNOWN workaround (ask the founder)"
        cost_raw = reply.get("cost_of_problem")
        cost = cost_raw if isinstance(cost_raw, dict) else {"text": cost_raw}
        cost_text = _clip(cost.get("text"), 300)
        cost_ids = _valid_ids(ctx, cost.get("evidence_ids"))
        cost_label = _label(cost.get("label"))
        if not cost_text:
            cost_text, cost_label = "an UNKNOWN amount of time or money", "UNKNOWN"
        if cost_label in ("SOURCED", "FOUNDER_REPORTED") and not cost_ids:
            cost_label = "ASSUMPTION"
        cost_basis = _clip(cost.get("basis"), 300) or ("stated in the founder brief" if cost_ids else
                                                       "no data yet; to be measured in interviews (1.4)")
        cost_of_problem = {"text": cost_text, "label": cost_label, "basis": cost_basis, "evidence_ids": cost_ids}
        statement = (f"{segment} struggle with {problem} when {situation}; today they {workaround}, "
                     f"which costs them {cost_text}.")

        roles_raw = reply.get("buying_roles") if isinstance(reply.get("buying_roles"), dict) else {}
        buying_roles = {r: _clip(roles_raw.get(r), 160) or "unknown" for r in ("user", "payer", "approver")}

        alternatives = []
        for index, alt in enumerate(reply.get("alternatives", [])[:5], start=1):
            alternatives.append({
                "id": f"A{index}",
                "name": _clip(alt.get("name"), 100) or f"Alternative {index}",
                "statement": _clip(alt.get("statement"), 400),
                "segment": _clip(alt.get("segment"), 200) or segment,
                "changed_assumption": _clip(alt.get("changed_assumption"), 200) or "not stated",
                "first_user": _clip(alt.get("first_user"), 200) or "not stated",
                "smallest_test": _clip(alt.get("smallest_test"), 300) or "not stated",
            })
        status_quo = _clip(reply.get("status_quo"), 400) or f"Do nothing: {segment} keep their current workaround."
        title = _clip(reply.get("title"), 100) or ctx.run.title

        questions = [_clip(q, 300) for q in as_list(reply.get("questions")) if _clip(q)][:3]
        if not any(re.search(r"\blast time\b|\blatest\b|\bmost recent\b", q, re.I) for q in questions):
            questions = [f"Walk me through the last time {segment} hit this problem: what triggered it, who did "
                         "what, and what did it cost?"] + questions
        questions = questions[:3]

        original = {"id": "C0", "name": title, "statement": statement, "segment": segment,
                    "changed_assumption": "original idea", "first_user": buying_roles["user"],
                    "smallest_test": "customer interviews (Step 1.4)"}

        md = [
            "## Problem statement (HYPOTHESIS)", "",
            f"> {statement}", "",
            "This is a hypothesis built from the brief. Steps 1.3 and 1.4 test it against public evidence and "
            "customer interviews.", "",
            "| Part | Value |", "|---|---|",
            f"| Segment | {_cell(segment)} |", f"| Problem | {_cell(problem)} |",
            f"| Situation / trigger | {_cell(situation)} |", f"| Current workaround | {_cell(workaround)} |",
            f"| Cost of the problem | {_cell(cost_text)} `{cost_label}` ({_cell(cost_basis, 160)}) |", "",
            "## Buying roles", "", "| Role | Who |", "|---|---|",
            *[f"| {r.capitalize()} | {_cell(v)} |" for r, v in buying_roles.items()], "",
            "## Concept cards", "",
            "Each alternative changes one assumption of the original idea.", "",
            "| ID | Concept | Statement | Changed assumption | First user | Smallest test |",
            "|---|---|---|---|---|---|",
            *[f"| {c['id']} | {_cell(c['name'], 80)} | {_cell(c['statement'])} | {_cell(c['changed_assumption'])} | "
              f"{_cell(c['first_user'])} | {_cell(c['smallest_test'])} |" for c in [original] + alternatives], "",
            "## Status-quo baseline", "", status_quo, "",
        ]
        if founder_ids:
            md += ["## Evidence the founder reported", "",
                   f"Recorded as `FOUNDER_REPORTED` ({', '.join(founder_ids)}); not independently verified.", ""]

        claims = [Claim(text=f"Problem hypothesis: {statement}", label="ASSUMPTION",
                        basis="framed from the founder brief; not yet tested (Steps 1.3-1.4 test it)"),
                  Claim(text=f"Cost of the problem: {cost_text}", label=cost_label, evidence_ids=cost_ids,
                        basis=cost_basis)]
        if founder_ids:
            claims.append(Claim(text="The founder reported existing evidence in the brief", label="FOUNDER_REPORTED",
                                evidence_ids=founder_ids))
        data = {"title": title, "problem_statement": statement, "statement_label": "HYPOTHESIS",
                "segment": segment, "problem": problem, "situation": situation, "workaround": workaround,
                "cost_of_problem": cost_of_problem, "buying_roles": buying_roles, "alternatives": alternatives,
                "status_quo": status_quo, "original": original}
        return StepOutput(title=title, markdown="\n".join(md), data=data, claims=claims, questions=questions,
                          summary=(f"Framed the idea as a testable problem hypothesis for {segment} and drafted "
                                   f"{len(alternatives)} alternative concepts for scoring in Step 1.2."))


# ============================================================================================== 1.2
FACTORS: list[tuple[str, str, int]] = [
    ("severity", "Problem severity", 3), ("frequency", "Frequency", 2), ("willingness_to_pay", "Willingness to pay", 3),
    ("reachability", "Reachability", 2), ("founder_fit", "Founder fit", 2), ("competition_gap", "Competition gap", 1),
    ("speed_to_mvp", "Speed to MVP", 1),
]
WEIGHTS = {key: weight for key, _, weight in FACTORS}
MAX_TOTAL = 5 * sum(WEIGHTS.values())  # 70
FACTOR_ANCHORS = {
    "severity": "1 = inconvenience ... 5 = material loss",
    "frequency": "1 = rare ... 5 = every workflow or purchase cycle",
    "willingness_to_pay": "1 = unknown ... 5 = evidenced use of a relevant budget",
    "reachability": "1 = untested list ... 5 = demonstrated repeatable channel",
    "founder_fit": "1 = missing prerequisites ... 5 = demonstrated access or capability (time and budget included)",
    "competition_gap": "1 = adequate substitutes ... 5 = repeatable unmet need",
    "speed_to_mvp": "1 = months with dependencies ... 5 = manual test in days",
}


def _clamp_score(value: Any, default: int) -> int:
    number = as_float(value)
    if number is None:
        return default
    return int(max(1, min(5, round(number))))


def parse_factor(raw: Any, valid_ids=None) -> dict[str, Any]:
    """Normalize one factor score. Unknown scores use 3 and are flagged; ranges stay within 1-5."""
    if not isinstance(raw, dict):
        raw = {"base": raw}
    base_raw = raw.get("base", raw.get("score"))
    unknown = bool(raw.get("unknown")) or base_raw is None or str(base_raw).strip().lower() in NONE_WORDS
    base = 3 if unknown else _clamp_score(base_raw, 3)
    low = _clamp_score(raw.get("low"), 1 if unknown else base)
    high = _clamp_score(raw.get("high"), 5 if unknown else base)
    low, high = min(low, base), max(high, base)
    ids = valid_ids(raw.get("evidence_ids")) if valid_ids else []
    basis = _clip(raw.get("basis"), 240)
    if not basis:
        basis = "unknown: no basis given" if unknown else "ASSUMPTION: no basis given"
    if not ids and not unknown and not basis.upper().startswith(("ASSUMPTION", "UNKNOWN")):
        basis = f"ASSUMPTION: {basis}"
    return {"base": base, "low": low, "high": high, "unknown": unknown, "basis": basis, "evidence_ids": ids}


def compute_scorecard(concepts: list[dict[str, Any]], scored: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Weighted totals, ranks, blockers and the sensitivity check, all in code.

    concepts: [{id, name, ...}]; scored: id -> {"scores": {factor: parsed}, "blockers": [...]}.
    """
    rows = []
    for index, concept in enumerate(concepts):
        entry = scored.get(concept["id"]) or {}
        scores = {key: entry.get("scores", {}).get(key) or parse_factor({"unknown": True}) for key in WEIGHTS}
        total = sum(WEIGHTS[k] * scores[k]["base"] for k in WEIGHTS)
        low = sum(WEIGHTS[k] * scores[k]["low"] for k in WEIGHTS)
        high = sum(WEIGHTS[k] * scores[k]["high"] for k in WEIGHTS)
        rows.append({**concept, "scores": scores, "weighted_total": total, "low_total": low, "high_total": high,
                     "blockers": list(entry.get("blockers") or []),
                     "unknown_factors": [k for k in WEIGHTS if scores[k]["unknown"]], "_order": index})
    rows.sort(key=lambda r: (-r["weighted_total"], len(r["unknown_factors"]), r["_order"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row.pop("_order", None)
    eligible = [r for r in rows if not r["blockers"]]
    recommended = eligible[0] if eligible else None
    sensitivity: dict[str, Any] = {"stable": True, "flips": [], "compared_with": [], "message": ""}
    if recommended:
        for other in eligible[1:]:
            sensitivity["compared_with"].append(other["id"])
            for key, weight in WEIGHTS.items():
                mine, theirs = recommended["scores"][key], other["scores"][key]
                if (mine["unknown"] or mine["low"] < mine["base"]) and mine["base"] > 1 and \
                        recommended["weighted_total"] - weight <= other["weighted_total"]:
                    sensitivity["flips"].append({"concept": recommended["id"], "factor": key, "move": -1,
                                                 "against": other["id"]})
                if (theirs["unknown"] or theirs["high"] > theirs["base"]) and theirs["base"] < 5 and \
                        other["weighted_total"] + weight >= recommended["weighted_total"]:
                    sensitivity["flips"].append({"concept": other["id"], "factor": key, "move": +1,
                                                 "against": recommended["id"]})
        sensitivity["stable"] = not sensitivity["flips"]
        if sensitivity["stable"]:
            sensitivity["message"] = ("The top rank holds if any single uncertain factor moves by one point within "
                                      "its plausible range.")
        else:
            moves = "; ".join(f"{f['concept']} {f['factor']} {'+1' if f['move'] > 0 else '-1'} vs {f['against']}"
                              for f in sensitivity["flips"][:6])
            sensitivity["message"] = ("The top rank is fragile: it can tie or swap if one uncertain factor moves "
                                      f"one point ({moves}). Run the cheapest test that tells these concepts apart "
                                      "before investing.")
    else:
        sensitivity["message"] = "Every concept has a hard blocker, so none can be recommended."
    return {"concepts": rows, "recommended_id": recommended["id"] if recommended else None,
            "sensitivity": sensitivity}


class ScoreAlternatives(StepHandler):
    """1.2: weighted scorecard with ranges, blockers and rank sensitivity (gate A)."""

    def generate(self, ctx) -> StepOutput:
        sharpened = ctx.prior("1.1")
        original = sharpened.get("original") or {"id": "C0", "name": sharpened.get("title") or ctx.run.title,
                                                 "statement": sharpened.get("problem_statement")
                                                 or ctx.brief.get("idea", ""),
                                                 "segment": sharpened.get("segment") or ctx.brief.get("customer", "")}
        concepts = [{k: original.get(k) for k in ("id", "name", "statement", "segment", "changed_assumption")}]
        for alt in sharpened.get("alternatives") or []:
            concepts.append({k: alt.get(k) for k in ("id", "name", "statement", "segment", "changed_assumption",
                                                     "first_user", "smallest_test")})
        payload = {
            "concepts": concepts,
            "factors": [{"key": k, "name": n, "weight": w, "anchors": FACTOR_ANCHORS[k]} for k, n, w in FACTORS],
            "founder": {k: ctx.brief.get(k) for k in ("why_you", "budget", "time", "jurisdiction", "evidence")},
            "evidence": ctx.evidence_digest(limit=30),
            "feedback": ctx.feedback,
        }
        reply = strategist.score_concepts(ctx, payload)
        valid = lambda ids: _valid_ids(ctx, ids)  # noqa: E731
        scored: dict[str, dict[str, Any]] = {}
        for item in reply.get("concepts", []):
            cid = str(item.get("id"))
            raw_scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
            blockers = [_clip(b, 200) for b in as_list(item.get("blockers"))
                        if _clip(b) and _clip(b).lower() not in NONE_WORDS]
            scored[cid] = {"scores": {k: parse_factor(raw_scores[k], valid) for k in WEIGHTS if k in raw_scores},
                           "blockers": blockers}
        card = compute_scorecard(concepts, scored)
        rows, rec_id = card["concepts"], card["recommended_id"]
        rec = next((r for r in rows if r["id"] == rec_id), None)

        def cell(score: dict[str, Any]) -> str:
            text = f"{score['base']}" + ("?" if score["unknown"] else "")
            return text + (f" ({score['low']}-{score['high']})" if score["low"] != score["high"] else "")

        md = ["## Weighted scorecard", "",
              f"Scores 1-5 per factor (low-high range in brackets; `?` = unknown, scored 3). Weights fixed in code; "
              f"maximum {MAX_TOTAL}. Totals, ranks and the sensitivity check are computed in code.", "",
              "| Rank | ID | Concept | " + " | ".join(f"{n} x{w}" for _, n, w in FACTORS) +
              f" | Total /{MAX_TOTAL} | Range | Blockers |",
              "|---|---|---|" + "---|" * len(FACTORS) + "---|---|---|"]
        for r in rows:
            md.append(f"| {r['rank']} | {r['id']} | {_cell(r['name'], 60)} | " +
                      " | ".join(cell(r["scores"][k]) for k in WEIGHTS) +
                      f" | **{r['weighted_total']}** | {r['low_total']}-{r['high_total']} | "
                      f"{_cell('; '.join(r['blockers']) or 'none', 120)} |")
        md += ["", "## Recommendation", ""]
        if rec:
            md.append(f"**{rec['id']} {rec['name']}** ranks highest without a hard blocker "
                      f"({rec['weighted_total']}/{MAX_TOTAL}, plausible range {rec['low_total']}-{rec['high_total']})."
                      + ("" if rec["id"] == "C0" else " This is not the original idea."))
        else:
            md.append("No concept can be recommended: every concept has a hard blocker. Reject this step with "
                      "feedback, or pivot back to 1.1.")
        md += ["", f"**Sensitivity:** {card['sensitivity']['message']}", "",
               "You may pick a different concept; a lower-ranked choice needs a reason, which is logged.", "",
               "## Basis per factor", ""]
        for r in rows:
            md.append(f"**{r['id']} {_cell(r['name'], 80)}**" +
                      (f" (unknown: {', '.join(r['unknown_factors'])})" if r["unknown_factors"] else ""))
            for key, name, _ in FACTORS:
                s = r["scores"][key]
                refs = f" [{', '.join(s['evidence_ids'])}]" if s["evidence_ids"] else ""
                md.append(f"- {name}: {cell(s)} - {_cell(s['basis'], 240)}{refs}")
            md.append("")

        claims = [Claim(text=f"{r['id']} {r['name']} scores {r['weighted_total']}/{MAX_TOTAL} "
                             f"(range {r['low_total']}-{r['high_total']})", label="ESTIMATE",
                        basis="weighted sum of model-assessed 1-5 factor scores; weights fixed in code; unknown "
                              "factors scored 3") for r in rows]
        for r in rows:
            for key, name, _ in FACTORS:
                s = r["scores"][key]
                if s["evidence_ids"]:
                    claims.append(Claim(text=f"{r['id']} {name} {s['base']}/5: {s['basis']}", label="SOURCED",
                                        evidence_ids=s["evidence_ids"]))
        data = {"concepts": rows, "recommended_id": rec_id, "sensitivity": card["sensitivity"],
                "weights": WEIGHTS, "max_total": MAX_TOTAL}
        questions = []
        if not card["sensitivity"]["stable"]:
            questions.append("The ranking is sensitive to one uncertain factor: do you have evidence on it, or should "
                             "the cheapest discriminating test come first?")
        summary = (f"Scored {len(rows)} concepts; recommended {rec_id} ({rec['weighted_total']}/{MAX_TOTAL})."
                   if rec else f"Scored {len(rows)} concepts; none can be recommended (hard blockers).")
        return StepOutput(title="Concept scorecard", markdown="\n".join(md), data=data, claims=claims,
                          questions=questions, summary=summary)


# ============================================================================================== 1.3
INPUT_NAMES = ("eligible_units", "annual_spend", "serviceability_filter", "reachable_units", "response_rate",
               "close_rate")
SHARE_INPUTS = ("serviceability_filter", "response_rate", "close_rate")
SCENARIOS = ("low", "base", "high")


def _input_name(raw: Any) -> str:
    name = re.sub(r"[^a-z_]", "", str(raw or "").strip().lower().replace(" ", "_"))
    if name.startswith(("filter", "serviceab", "sam_filter")):
        return "serviceability_filter"
    return name


def _share(value: float | None) -> float | None:
    if value is None:
        return None
    if 1 < value <= 100:
        value = value / 100
    return value if 0 <= value <= 1 else None


def parse_market_inputs(ctx, raw: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize the model's market inputs and check every SOURCED label against the cited evidence."""
    if isinstance(raw, dict):
        items = []
        for key, value in raw.items():
            if isinstance(value, list):
                items += [{"name": key, **v} for v in value if isinstance(v, dict)]
            elif isinstance(value, dict):
                items.append({"name": key, **value})
    else:
        items = [i for i in as_list(raw) if isinstance(i, dict)]
    out, notes = [], []
    for item in items:
        name = _input_name(item.get("name"))
        if name not in INPUT_NAMES:
            continue
        values = {s: as_float(item.get("value" if s == "base" else s)) for s in SCENARIOS}
        if values["base"] is None:
            values["base"] = as_float(item.get("base"))
        if name in SHARE_INPUTS:
            values = {s: _share(v) for s, v in values.items()}
        elif any(v is not None and v < 0 for v in values.values()):
            values = {s: None for s in SCENARIOS}
        ids = _valid_ids(ctx, item.get("evidence_ids"))
        label = _label(item.get("label"))
        basis = _clip(item.get("basis"), 300)
        if values["base"] is None:
            label = "UNKNOWN"
        elif label == "SOURCED" and not (ids and _value_in_evidence(ctx, values["base"], ids)):
            notes.append(f"{name}: labelled SOURCED but the number is not in the cited evidence; relabelled ESTIMATE")
            label, basis = "ESTIMATE", (basis + " (number not found in cited evidence)").strip()
        elif label == "FOUNDER_REPORTED" and not ids:
            label = "ASSUMPTION"
        if label in ("ESTIMATE", "ASSUMPTION") and not basis:
            basis = "no basis given"
        out.append({"name": name, "description": _clip(item.get("description") or item.get("filter"), 160),
                    "low": values["low"], "value": values["base"], "high": values["high"],
                    "unit": _clip(item.get("unit"), 60), "label": label, "evidence_ids": ids, "basis": basis})
    return out, notes


def compute_market(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    """TAM = eligible_units x annual_spend; SAM = TAM x product(filters); SOM = reachable x response x close x spend.

    SOM units are bounded by SAM units. A figure with a missing input stays None (UNKNOWN).
    """
    def pick(item: dict[str, Any] | None, scenario: str) -> float | None:
        if item is None:
            return None
        value = item.get("value" if scenario == "base" else scenario)
        return item.get("value") if value is None else value

    first = {n: next((i for i in inputs if i["name"] == n), None) for n in INPUT_NAMES}
    filters = [i for i in inputs if i["name"] == "serviceability_filter"]
    known_filters = [f for f in filters if f.get("value") is not None]
    notes = []
    if not filters:
        notes.append("No serviceability filter was given: SAM equals TAM (an upper bound).")
    elif len(known_filters) < len(filters):
        notes.append("Filters with unknown values were left out of SAM, so SAM is an upper bound.")
    results: dict[str, dict[str, Any]] = {k: {} for k in ("tam", "sam_units", "sam", "som_units", "som")}
    for s in SCENARIOS:
        units, spend = pick(first["eligible_units"], s), pick(first["annual_spend"], s)
        product = 1.0
        for f in known_filters:
            product *= pick(f, s)
        tam = units * spend if units is not None and spend is not None else None
        sam_units = units * product if units is not None else None
        sam = tam * product if tam is not None else None
        reach, resp, close = (pick(first["reachable_units"], s), pick(first["response_rate"], s),
                              pick(first["close_rate"], s))
        som_units = reach * resp * close if None not in (reach, resp, close) else None
        if som_units is not None and sam_units is not None and som_units > sam_units:
            som_units = sam_units
            if "SOM was capped at SAM units." not in notes:
                notes.append("SOM was capped at SAM units.")
        som = som_units * spend if som_units is not None and spend is not None else None
        for key, value in (("tam", tam), ("sam_units", sam_units), ("sam", sam), ("som_units", som_units),
                           ("som", som)):
            results[key][s] = round(value, 2) if value is not None else None
    assumption_inputs = sorted({i["name"] for i in inputs if i["label"] in ("ASSUMPTION", "UNKNOWN")})
    formulas = {"tam": "eligible_units x annual_spend",
                "sam_units": "eligible_units x product(serviceability filters)",
                "sam": "TAM x product(serviceability filters)",
                "som_units": "min(reachable_units x response_rate x close_rate, SAM units)",
                "som": "SOM units x annual_spend"}
    for key, value in results.items():
        value["formula"] = formulas[key]
        value["label"] = "UNKNOWN" if value.get("base") is None else "ESTIMATE"
    return {"results": results, "notes": notes, "assumption_inputs": assumption_inputs}


def _price_supported(ctx, price: str, ids: list[str]) -> bool:
    numbers = _numbers_in(price)
    if not numbers or not ids:
        return False
    text = " ".join(f"{r.title} {r.excerpt}" for r in (ctx.ledger.get(i) for i in ids) if r)
    found = _numbers_in(text)
    return all(any(abs(n - f) < 1e-9 for f in found) for n in numbers)


def _research_dict(result: Any) -> dict[str, Any]:
    return {"queries": list(getattr(result, "queries", []) or []),
            "evidence_ids": list(getattr(result, "evidence_ids", []) or []),
            "sources": list(getattr(result, "sources", []) or []),
            "stats": dict(getattr(result, "stats", {}) or {}),
            "coverage_notes": list(getattr(result, "coverage_notes", []) or [])}


class DefineMarket(StepHandler):
    """1.3: desk research, ICP, bottom-up market model, competitor and channel map (gate A + E).

    Thresholds are locked before research runs (steps.py: lock_first=True).
    """

    def default_contract(self, ctx) -> Contract:
        concept = ctx.concept()
        return Contract(
            step_id="1.3",
            decision=f"Is there enough public evidence of the problem, and a reachable community, to justify "
                     f"customer interviews for '{concept.get('name') or ctx.run.title}'?",
            hypothesis=f"{concept.get('segment') or 'The segment'} discuss this problem publicly and gather in at "
                       "least one sizeable community the founder can reach.",
            criteria=[
                Criterion(key="independent_discussions", target=5, unit="discussions", kind="scalable",
                          label="Independent public discussions of the problem in the last 24 months",
                          help="Hacker News, Reddit and Stack Exchange threads labelled relevant; a story and its "
                               "comments count once."),
                Criterion(key="largest_community_members", target=1000, unit="members", kind="scalable",
                          label="Members of the largest verified community where the segment gathers "
                                "(published audience, not eligible reach)",
                          help="Subreddit subscribers or Stack Exchange registered users, as published."),
            ],
            pivot_target="1.1",
            notes="Desk research uses free public sources only. 'No results' is a coverage gap, not proof of "
                  "absent demand; missing measurements wait for founder data with source URLs.")

    def generate(self, ctx) -> StepOutput:
        concept = _concept(ctx)
        brief = ctx.brief
        name = concept.get("name") or ctx.run.title
        segment = concept.get("segment") or brief.get("customer", "")
        problem = concept.get("statement") or brief.get("idea", "")
        try:
            from agents.researcher import run_desk_research
            research = _research_dict(run_desk_research(ctx, topic=name, segment=segment, problem=problem,
                                                        extra_queries=None))
        except Exception as exc:  # noqa: BLE001 - research problems are coverage gaps, not crashes
            if isinstance(exc, LLMError):
                note = f"desk research stopped: no model answered ({str(exc)[:160]})"
            else:
                note = f"desk research failed ({type(exc).__name__}: {str(exc)[:160]})"
            research = _research_dict(None)
            research["coverage_notes"].append(note)
        stats = research["stats"]

        previous = ctx.prior("1.3") if (ctx.feedback or ctx.attempt) else {}
        payload = {
            "brief": {k: brief.get(k) for k in ("idea", "customer", "jurisdiction", "budget", "time", "evidence")
                      if brief.get(k)},
            "concept": concept,
            "research": {"queries": research["queries"], "coverage_notes": research["coverage_notes"],
                         **{k: stats.get(k) for k in ("independent_discussions", "discussions_by_source",
                                                      "communities", "largest_community_members",
                                                      "competitor_candidates", "github_repos", "wikipedia_pageviews",
                                                      "world_bank") if k in stats}},
            "evidence": self._digest(ctx, research),
            "previous_version": ({k: previous.get(k) for k in ("icp", "market_model", "competitors", "channels")}
                                 if previous else None),
            "feedback": ctx.feedback,
        }
        reply = market_analyst.build_market_model(ctx, payload)

        inputs, input_notes = parse_market_inputs(ctx, reply.get("market_inputs"))
        market = compute_market(inputs)
        currency = _clip(reply.get("currency"), 10) or "USD"
        icp_raw = reply.get("icp") or {}
        icp = {"description": _clip(icp_raw.get("description"), 500),
               "inclusion": [_clip(x, 200) for x in as_list(icp_raw.get("inclusion")) if _clip(x)][:8],
               "exclusion": [_clip(x, 200) for x in as_list(icp_raw.get("exclusion")) if _clip(x)][:8],
               "purchasing_unit": _clip(icp_raw.get("purchasing_unit"), 80) or "unknown"}
        competitors, comp_notes = self._competitors(ctx, reply.get("competitors"), stats)
        channels = self._channels(ctx, reply.get("channels"), stats)
        market_model = {"horizon": _clip(reply.get("horizon"), 40) or "12 months", "currency": currency,
                        "purchasing_unit": icp["purchasing_unit"], "inputs": inputs, **market,
                        "notes": market["notes"] + input_notes + comp_notes}
        gap = _clip(reply.get("largest_coverage_gap"), 600) or "not stated"

        claims = self._claims(ctx, stats, market_model, reply.get("claims"))
        md = self._markdown(research, stats, icp, _clip(reply.get("primary_segment"), 300) or segment, market_model,
                            competitors, channels, gap)
        data = {"research": research, "market_model": market_model, "competitors": competitors,
                "channels": channels, "icp": icp, "primary_segment": _clip(reply.get("primary_segment"), 300) or segment,
                "largest_coverage_gap": gap}
        found = stats.get("independent_discussions")
        summary = ("Ran free desk research and built the market model. " +
                   (f"Found {found} independent relevant discussion(s) in 24 months"
                    if found is not None else "Public discussions could not be counted") +
                   (f"; largest verified community {stats['largest_community_members']:,} members."
                    if stats.get("largest_community_members") is not None else "; no verified community size."))
        questions = []
        if found is None or stats.get("largest_community_members") is None:
            questions.append("Some gate data could not be measured from public sources. Do you know discussion "
                             "threads or a community where this segment gathers? Submit them with their URLs.")
        return StepOutput(title=f"Market definition: {name}", markdown=md, data=data, claims=claims,
                          sources=research["sources"][:50], summary=summary, questions=questions)

    # --- generation helpers
    @staticmethod
    def _digest(ctx, research: dict[str, Any], limit: int = 60) -> list[dict[str, Any]]:
        stats = research["stats"]
        priority = list(stats.get("relevant_evidence_ids") or [])
        priority += [c.get("evidence_id") for c in stats.get("communities") or []]
        priority += [c.get("evidence_id") for c in stats.get("competitor_candidates") or []]
        priority += [r.get("evidence_id") for r in (stats.get("wikipedia_pageviews") or []) +
                     (stats.get("world_bank") or [])]
        priority += [r.get("evidence_id") for r in stats.get("github_repos") or [] if r.get("relevant")]
        priority += [r.evidence_id for r in ctx.ledger.all() if r.provenance == "FOUNDER_REPORTED"]
        rows = []
        for evidence_id in dict.fromkeys(i for i in priority if i):
            row = ctx.ledger.get(evidence_id)
            if row is None:
                continue
            rows.append({"id": row.evidence_id, "provenance": row.provenance, "source": row.source_type,
                         "url": row.url, "title": row.title[:140], "excerpt": row.excerpt[:280], "value": row.value,
                         "unit": row.unit, "observed_at": row.observed_at})
            if len(rows) >= limit:
                break
        return rows

    @staticmethod
    def _known_urls(ctx, stats: dict[str, Any]) -> set[str]:
        urls = set(ctx.ledger.urls())
        urls.update(c.get("url") for c in stats.get("communities") or [] if c.get("url"))
        urls.update(c.get("url") for c in stats.get("competitor_candidates") or [] if c.get("url"))
        return urls

    def _competitors(self, ctx, raw: Any, stats: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        known = self._known_urls(ctx, stats)
        out, notes, seen = [], [], set()
        for item in [i for i in as_list(raw) if isinstance(i, dict)][:6]:
            name = _clip(item.get("name"), 100)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            ids = _valid_ids(ctx, as_list(item.get("evidence_ids")) + as_list(item.get("price_evidence_ids")))
            url = str(item.get("url") or "").strip() or None
            if url and url not in known:
                notes.append(f"{name}: URL not found in collected evidence; removed")
                url = None
            if not url and ids:
                url = next((ctx.ledger.get(i).url for i in ids if ctx.ledger.get(i).url), None)
            kind = str(item.get("type") or "").strip().lower()
            is_status_quo = kind == "status_quo" or re.search(r"do nothing|status quo|inaction|no tool", name, re.I)
            price = _clip(item.get("price"), 80) or "unknown"
            if is_status_quo:
                price = "n/a (no purchase)"
            elif price.lower() not in ("unknown", "n/a", "quote required") and not _price_supported(ctx, price, ids):
                notes.append(f"{name}: price '{price}' not found in cited evidence; shown as unknown")
                price = "unknown"
            out.append({"name": name, "type": "status_quo" if is_status_quo else (kind or "direct"), "url": url,
                        "price": price, "evidence_ids": ids, "notes": _clip(item.get("notes"), 300),
                        "label": "SOURCED" if ids else "ASSUMPTION"})
        for cand in stats.get("competitor_candidates") or []:
            if len([c for c in out if c["type"] != "status_quo"]) >= 4:
                break
            if cand.get("name", "").lower() in seen:
                continue
            seen.add(cand["name"].lower())
            out.append({"name": cand["name"], "type": "direct", "url": cand.get("url"), "price": "unknown",
                        "evidence_ids": _valid_ids(ctx, [cand.get("evidence_id")]),
                        "notes": "found in desk research", "label": "SOURCED"})
        if not any(c["type"] == "status_quo" for c in out):
            out.append({"name": "Do nothing / keep the current workaround", "type": "status_quo", "url": None,
                        "price": "n/a (no purchase)", "evidence_ids": [], "label": "ASSUMPTION",
                        "notes": "Baseline: the cost of the problem keeps falling on the segment."})
        status_quo = [c for c in out if c["type"] == "status_quo"][:1]
        others = [c for c in out if c["type"] != "status_quo"][:4]
        return others + status_quo, notes

    def _channels(self, ctx, raw: Any, stats: dict[str, Any]) -> list[dict[str, Any]]:
        known = self._known_urls(ctx, stats)
        members_by_id = {c.get("evidence_id"): c for c in stats.get("communities") or [] if c.get("verified")}
        out, seen = [], set()
        for item in [i for i in as_list(raw) if isinstance(i, dict)][:6]:
            name = _clip(item.get("name"), 120)
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            ids = _valid_ids(ctx, item.get("evidence_ids"))
            url = str(item.get("url") or "").strip() or None
            if url and url not in known:
                url = None
            audience = next((members_by_id[i]["members"] for i in ids if i in members_by_id), None)
            out.append({"name": name, "url": url, "evidence_ids": ids, "published_audience": audience,
                        "eligible_reach": "unknown (published audience is not eligible reach)",
                        "note": _clip(item.get("note"), 300), "label": "SOURCED" if ids else "ASSUMPTION"})
        for community in members_by_id.values():
            if community["name"].lower() not in seen:
                seen.add(community["name"].lower())
                out.append({"name": community["name"], "url": community["url"],
                            "evidence_ids": [community["evidence_id"]], "published_audience": community["members"],
                            "eligible_reach": "unknown (published audience is not eligible reach)",
                            "note": "verified community from desk research", "label": "SOURCED"})
        return out

    @staticmethod
    def _claims(ctx, stats: dict[str, Any], market_model: dict[str, Any], raw_claims: Any) -> list[Claim]:
        claims: list[Claim] = []
        found = stats.get("independent_discussions")
        relevant = _valid_ids(ctx, stats.get("relevant_evidence_ids"))
        if found:
            claims.append(Claim(text=f"{found} independent public discussion(s) of the problem in the last "
                                     f"{stats.get('window_months', 24)} months (counted by thread)",
                                label="SOURCED", evidence_ids=relevant[:12]))
        elif found == 0:
            claims.append(Claim(text="No relevant public discussion was found in the sources that answered",
                                label="UNKNOWN", basis="coverage of free public sources, not evidence of absent "
                                                       "demand"))
        largest = stats.get("largest_community")
        if largest and _valid_ids(ctx, [largest.get("evidence_id")]):
            claims.append(Claim(text=f"{largest['name']} publishes {largest['members']:,} members (published "
                                     "audience, not eligible reach)", label="SOURCED",
                                evidence_ids=[largest["evidence_id"]]))
        results = market_model["results"]
        unit = market_model["currency"]
        for key, title in (("tam", "TAM"), ("sam", "SAM"), ("som", "SOM")):
            value = results[key]
            if value.get("base") is not None:
                claims.append(Claim(text=f"{title} {_fmt(value['base'], unit)} per year (range "
                                         f"{_fmt(value.get('low'), unit)} - {_fmt(value.get('high'), unit)})",
                                    label="ESTIMATE", basis=f"{value['formula']}; inputs labelled ASSUMPTION/UNKNOWN: "
                                    f"{', '.join(market_model['assumption_inputs']) or 'none'}"))
        for raw in as_list(raw_claims)[:8]:
            if isinstance(raw, dict) and _clip(raw.get("text")):
                claims.append(Claim(text=_clip(raw.get("text"), 300), label=_label(raw.get("label")),
                                    evidence_ids=[str(i) for i in as_list(raw.get("evidence_ids"))],
                                    basis=_clip(raw.get("basis"), 300)))
        return claims

    @staticmethod
    def _markdown(research, stats, icp, primary_segment, market_model, competitors, channels, gap) -> str:
        found = stats.get("independent_discussions")
        largest = stats.get("largest_community")
        md = ["## Gate evidence (computed from collected rows)", "",
              "| Criterion | Measured | Basis |", "|---|---|---|",
              f"| Independent public discussions, last {stats.get('window_months', 24)} months | "
              f"{'not measured' if found is None else found} | "
              f"{_cell(', '.join(f'{k}: {v}' for k, v in (stats.get('discussions_by_source') or {}).items()) or '-')} |",
              f"| Largest verified community (published audience) | "
              f"{'not measured' if not largest else f'{largest['members']:,}'} | "
              f"{_cell(largest['name'] + ' ' + largest['url']) if largest else '-'} |", ""]
        if research["queries"]:
            md += ["**Queries:** " + "; ".join(f"`{q}`" for q in research["queries"]), ""]
        status = stats.get("sources_status") or {}
        if status:
            md += ["| Source | Status |", "|---|---|", *[f"| {s} | {v} |" for s, v in status.items()], ""]
        if research["coverage_notes"]:
            md += ["**Coverage notes** (a gap in coverage is not evidence of absent demand):", "",
                   *[f"- {_cell(n, 300)}" for n in research["coverage_notes"]], ""]
        md += ["## Ideal customer profile", "", f"**Primary segment:** {primary_segment}", "",
               icp["description"] or "_No description given._", "",
               f"- Purchasing unit: {icp['purchasing_unit']}",
               *[f"- Include: {x}" for x in icp["inclusion"]], *[f"- Exclude: {x}" for x in icp["exclusion"]], "",
               f"## Market model ({market_model['horizon']}, {market_model['currency']})", "",
               "| Input | Low | Base | High | Unit | Label | Basis / evidence |", "|---|---|---|---|---|---|---|"]
        for item in market_model["inputs"]:
            unit = "share" if item["name"] in SHARE_INPUTS else ""
            name = item["name"] + (f" ({item['description']})" if item.get("description") else "")
            refs = (" [" + ", ".join(item["evidence_ids"]) + "]") if item["evidence_ids"] else ""
            md.append(f"| {_cell(name, 80)} | {_fmt(item['low'], unit)} | {_fmt(item['value'], unit)} | "
                      f"{_fmt(item['high'], unit)} | {_cell(item['unit'], 40)} | `{item['label']}` | "
                      f"{_cell(item['basis'], 200)}{refs} |")
        if not market_model["inputs"]:
            md.append("| (no inputs given) | | | | | `UNKNOWN` | |")
        md += ["", "| Figure | Low | Base | High | Formula | Label |", "|---|---|---|---|---|---|"]
        currency = market_model["currency"]
        for key, title, unit in (("tam", "TAM", currency), ("sam_units", "SAM units", "units"),
                                 ("sam", "SAM", currency), ("som_units", "SOM units", "units"),
                                 ("som", "SOM", currency)):
            r = market_model["results"][key]
            md.append(f"| {title} | {_fmt(r.get('low'), unit)} | {_fmt(r.get('base'), unit)} | "
                      f"{_fmt(r.get('high'), unit)} | {r['formula']} | `{r['label']}` |")
        if market_model["notes"]:
            md += ["", *[f"- {_cell(n, 300)}" for n in market_model["notes"]]]
        md += ["", "## Competitors and substitutes", "",
               "| Option | Type | Price (only as shown in evidence) | Link | Evidence | Notes |",
               "|---|---|---|---|---|---|"]
        for c in competitors:
            md.append(f"| {_cell(c['name'], 80)} | {c['type']} | {_cell(c['price'], 60)} | "
                      f"{c['url'] or '-'} | {', '.join(c['evidence_ids']) or '`ASSUMPTION`'} | "
                      f"{_cell(c['notes'], 200)} |")
        md += ["", "## Channels", "",
               "| Channel | Link | Published audience | Eligible reach | Evidence | Note |", "|---|---|---|---|---|---|"]
        for ch in channels:
            audience = f"{ch['published_audience']:,}" if ch["published_audience"] is not None else "unknown"
            md.append(f"| {_cell(ch['name'], 80)} | {ch['url'] or '-'} | {audience} | {ch['eligible_reach']} | "
                      f"{', '.join(ch['evidence_ids']) or '`ASSUMPTION`'} | {_cell(ch['note'], 200)} |")
        if not channels:
            md.append("| (none identified) | | | | | |")
        md += ["", "## Largest coverage gap", "", gap, ""]
        return "\n".join(md)

    # --- gate data
    def collect(self, ctx, contract: Contract) -> Observation:
        state = ctx.run.steps.get("1.3")
        output = dict(state.output) if state and state.output else {}
        research = output.get("research") or {}
        stats = research.get("stats") or {}
        notes = list(research.get("coverage_notes") or [])
        values = {"independent_discussions": stats.get("independent_discussions"),
                  "largest_community_members": stats.get("largest_community_members")}
        observed = {c.key: (float(values[c.key]) if values.get(c.key) is not None else None)
                    for c in contract.criteria}
        evidence_ids = _valid_ids(ctx, list(stats.get("relevant_evidence_ids") or []) +
                                  [(stats.get("largest_community") or {}).get("evidence_id")])
        sources = [u for u in (ctx.ledger.get(i).url for i in evidence_ids) if u]
        missing = [k for k, v in observed.items() if v is None]
        details = {
            "independent_discussions": {"value": values["independent_discussions"],
                                        "by_source": stats.get("discussions_by_source") or {},
                                        "window_months": stats.get("window_months", 24),
                                        "method": "rows labelled relevant by the model, counted once per thread "
                                                  "(independence group) in code"},
            "largest_community_members": {"value": values["largest_community_members"],
                                          "community": stats.get("largest_community"),
                                          "note": "published audience, not eligible reach"},
            "coverage_notes": notes, "missing": missing,
        }
        if not stats:
            state_name = WAITING_FOR_DATA
            text = "No desk-research statistics (research disabled or unavailable): submit counts with source URLs."
        elif missing:
            state_name = WAITING_FOR_DATA
            text = f"Desk research could not measure: {', '.join(missing)}. Submit them with source URLs."
        else:
            state_name = READY
            text = (f"Desk research: {len(evidence_ids)} evidence rows from free public sources "
                    f"({', '.join(sorted((stats.get('sources_status') or {}).keys()))}).")
        return Observation(observed=observed, measurement_state=state_name, sources=sources[:40],
                           evidence_ids=evidence_ids, details=details, notes=text)

    def data_fields(self) -> list[DataField]:
        return [
            DataField(key="discussion_urls", label="Public discussions of the problem (last 24 months), one URL "
                      "per line", type="text", required=False,
                      help="Each unique URL counts once; links already found by desk research are not counted twice."),
            DataField(key="largest_community_members", label="Members of the largest community where the segment "
                      "gathers (as published)", type="integer", required=False),
            DataField(key="largest_community_url", label="URL of that community (required with the member count)",
                      type="text", required=False),
        ]

    def observe(self, ctx, contract: Contract, data: dict[str, Any]) -> Observation:
        state = ctx.run.steps.get("1.3")
        stats = ((state.output or {}).get("research") or {}).get("stats") or {} if state else {}
        observed: dict[str, float | None] = {c.key: None for c in contract.criteria}
        evidence_ids, sources, notes = [], [], []
        urls = list(dict.fromkeys(u.rstrip(".)") for u in URL_RE.findall(str(data.get("discussion_urls") or ""))))
        if urls:
            research_urls = {ctx.ledger.get(i).url for i in _valid_ids(ctx, stats.get("relevant_evidence_ids"))}
            new_urls = [u for u in urls if u not in research_urls]
            for url in new_urls:
                row = ctx.ledger.add({"provenance": "FOUNDER_REPORTED", "source_type": "founder_data", "url": url,
                                      "title": "Founder-reported public discussion of the problem",
                                      "excerpt": f"Submitted by the founder for step 1.3: {url}",
                                      "independence_group": f"founder-url:{url}",
                                      "method": "founder-submitted link", "limitations": "Relevance judged by "
                                      "the founder; not checked by the system."})
                evidence_ids.append(row.evidence_id)
                sources.append(url)
            base = stats.get("independent_discussions") or 0
            observed["independent_discussions"] = float(base + len(new_urls))
            notes.append(f"discussions: {base} from desk research + {len(new_urls)} founder-submitted URL(s)")
        members = as_float(data.get("largest_community_members"))
        community_url = next(iter(URL_RE.findall(str(data.get("largest_community_url") or ""))), None)
        if members is not None and members >= 0 and community_url:
            row = ctx.ledger.add({"provenance": "FOUNDER_REPORTED", "source_type": "founder_data", "url": community_url,
                                  "title": "Founder-reported community size", "value": members, "unit": "members",
                                  "excerpt": f"Founder reports {members:,.0f} published members at {community_url}",
                                  "independence_group": f"founder-community:{community_url}",
                                  "method": "founder-submitted count with URL",
                                  "limitations": "Published audience, not eligible reach; not verified by the system."})
            evidence_ids.append(row.evidence_id)
            sources.append(community_url)
            observed["largest_community_members"] = float(max(members, stats.get("largest_community_members") or 0))
        elif members is not None:
            notes.append("community size ignored: it needs the community URL")
        observed = {k: v for k, v in observed.items() if k in {c.key for c in contract.criteria}}
        missing = [k for k, v in observed.items() if v is None]
        state_name = READY if not missing else (WAITING_FOR_DATA if len(missing) == len(observed)
                                                else INSUFFICIENT_DATA)
        return Observation(observed=observed, measurement_state=state_name, sources=sources,
                           evidence_ids=evidence_ids,
                           details={"source": "founder_data", "missing": missing, "notes": notes},
                           notes="Founder-reported data with source URLs" + (f"; {'; '.join(notes)}" if notes else ""))


# ============================================================================================== 1.4
BANNED_QUESTION_PATTERNS = [
    r"\bwould you\b", r"\bwill you\b", r"\bwould it\b", r"\bwould that\b", r"\bdo you think\b", r"\bimagine\b",
    r"\bcould you see yourself\b", r"\bhow much would\b", r"\bif (there was|there were|we built|i built|you had)\b",
    r"\b(our|my) (product|app|tool|solution|platform|service|idea)\b", r"\bdo you like\b",
    r"\bwhat do you think (of|about)\b", r"\bwould .{0,30}\bpay\b",
]
CORE_QUESTIONS = [
    ("Tell me about the last time this happened.", "anchor on a specific recent incident"),
    ("What did you do about it?", "the current workaround"),
    ("What have you already spent on this, in time or money?", "evidence of real cost or budget"),
    ("What triggered it?", "the moment the job starts"),
    ("Why did you pick that option over the alternatives?", "switching criteria"),
    ("Who else had to agree?", "buying roles"),
    ("What happened when you left it alone?", "cost of inaction"),
]
NOTE_FIELDS = ["participant_id", "interview_date", "recruited_via", "relationship_to_founder", "role", "organization",
               "last_incident_date", "problem_mention", "quote", "behaviour_observed", "workaround_or_spend",
               "current_spend", "pain_1_to_5", "commitment_offered", "commitment_completed",
               "compliment_or_hypothetical", "notes"]
PROBLEM_MENTIONS = ("unprompted", "specific_example", "prompted_only", "hypothetical", "none")
COUNTS_AS_PROBLEM = ("unprompted", "specific_example")


def mom_test_violations(question: str) -> list[str]:
    return [p for p in BANNED_QUESTION_PATTERNS if re.search(p, question or "", re.I)]


def _yes(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in ("yes", "y", "true", "1", "completed", "done"):
        return True
    if text in ("no", "n", "false", "0", "none", "offered", "not completed"):
        return False
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


class CustomerInterviews(StepHandler):
    """1.4: Mom Test kit; founder submits interview results; code computes rates and intervals (gate E)."""

    def generate(self, ctx) -> StepOutput:
        concept = _concept(ctx)
        market = ctx.prior("1.3")
        payload = {"concept": concept, "segment": concept.get("segment") or ctx.brief.get("customer"),
                   "brief": {k: ctx.brief.get(k) for k in ("idea", "customer", "why_you", "jurisdiction")
                             if ctx.brief.get(k)},
                   "icp": market.get("icp"),
                   "channels": [{k: c.get(k) for k in ("name", "url", "published_audience")}
                                for c in market.get("channels") or []],
                   "feedback": ctx.feedback}
        reply = interviewer.prepare_kit(ctx, payload)
        script = reply.get("script") or {}

        questions, removed = [], []
        for item in script.get("questions", []):
            q = _clip(item.get("q") if isinstance(item, dict) else item, 300)
            purpose = _clip(item.get("purpose"), 200) if isinstance(item, dict) else ""
            if not q:
                continue
            if mom_test_violations(q):
                removed.append(q)
                continue
            questions.append({"q": q if q.endswith("?") or q.endswith(".") else q + "?", "purpose": purpose})
        present = " ".join(_normalize(q["q"]) for q in questions)
        must = CORE_QUESTIONS[:3]
        for q, purpose in must:
            key = {"Tell me about the last time this happened.": "last time",
                   "What did you do about it?": "do about it",
                   "What have you already spent on this, in time or money?": "spent"}[q]
            if key not in present:
                questions.append({"q": q, "purpose": purpose})
        for q, purpose in CORE_QUESTIONS[3:]:
            if len(questions) >= 7:
                break
            if _normalize(q)[:20] not in present:
                questions.append({"q": q, "purpose": purpose})

        screener = [{"question": _clip(s.get("question"), 200), "qualifies_if": _clip(s.get("qualifies_if"), 200)}
                    for s in as_list(reply.get("screener")) if isinstance(s, dict) and _clip(s.get("question"))][:5]
        if not screener:
            screener = [{"question": "What is your role, and how often do you handle this kind of work?",
                         "qualifies_if": "the role matches the segment"},
                        {"question": "When did this last come up for you?", "qualifies_if": "within the last 3 months"}]
        known_urls = {c.get("url") for c in market.get("channels") or [] if c.get("url")}
        plan = []
        for item in as_list(reply.get("recruiting_plan")):
            if not isinstance(item, dict) or not _clip(item.get("source")):
                continue
            url = item.get("url") if item.get("url") in known_urls else None
            plan.append({"source": _clip(item.get("source"), 160), "url": url,
                         "approach": _clip(item.get("approach"), 300),
                         "target_count": int(as_float(item.get("target_count"), 0) or 0)})
        for channel in market.get("channels") or []:
            if len(plan) >= 2:
                break
            if channel.get("name") and channel["name"] not in {p["source"] for p in plan}:
                plan.append({"source": channel["name"], "url": channel.get("url"),
                             "approach": "Post or message following the community's rules; say it is research.",
                             "target_count": 5})
        for source, approach in (("Founder's own network (warm introductions)",
                                  "Ask contacts for introductions; record each participant's relationship to you."),
                                 ("Referrals from interviewees", "End each interview by asking for one introduction; "
                                                                 "track who referred whom.")):
            if len(plan) >= 2:
                break
            plan.append({"source": source, "url": None, "approach": approach, "target_count": 5})
        message = str(reply.get("recruiting_message") or "").strip()[:1500]
        commitments = [_clip(c, 200) for c in as_list(reply.get("commitment_asks")) if _clip(c)][:4] or [
            "An introduction to a colleague who handles the same work",
            "A screen-share of their current workaround (sensitive details hidden)"]

        files = {"interview_note_template.csv": ",".join(NOTE_FIELDS) + "\n"}
        outward = []
        if message:
            files["recruiting_message.md"] = (
                "# Recruiting message (DRAFT)\n\n"
                "MOCKED: approving this only places the draft in the local outbox. Nothing is sent. "
                "The founder sends it from their own account, under their own name, if they choose.\n\n---\n\n"
                + message + "\n")
            outward.append({"kind": "send", "item_id": "recruiting-message", "file": "recruiting_message.md",
                            "when": "before_collect", "target_name": "recruiting_message.md"})

        md = ["## Interview script (Mom Test)", "",
              "Past behaviour only: no pitching, no hypotheticals, no \"would you\".", "",
              f"**Opening:** {_clip(script.get('opening'), 600) or 'Explain this is research, not a sale, and ask permission to take notes.'}", "",
              "| # | Question | Purpose |", "|---|---|---|",
              *[f"| {i} | {_cell(q['q'], 300)} | {_cell(q['purpose'], 160)} |" for i, q in enumerate(questions, 1)], "",
              f"**Closing:** {_clip(script.get('closing'), 600) or 'Ask for a concrete next step and record whether it is completed.'}", ""]
        if removed:
            md += ["Questions removed by the Mom Test check (they pitch or ask about the future):", "",
                   *[f"- ~~{_cell(q, 200)}~~" for q in removed], ""]
        md += ["## Screener", "", "| Question | Qualifies if |", "|---|---|",
               *[f"| {_cell(s['question'])} | {_cell(s['qualifies_if'])} |" for s in screener], "",
               "## Recruiting plan", "", "| Source | Link | Approach | Target |", "|---|---|---|---|",
               *[f"| {_cell(p['source'], 100)} | {p['url'] or '-'} | {_cell(p['approach'])} | {p['target_count']} |"
                 for p in plan], "",
               "Track for every person: invited, eligible, completed, source, relationship to you. Include people "
               "who use the strongest substitute and people who did nothing.", "",
               "## Commitments to ask for", "", *[f"- {c}" for c in commitments], "",
               "Record offered and completed commitments separately; only completed ones count.", "",
               "## Note template", "",
               "One row per interview (`interview_note_template.csv`). `problem_mention` is one of "
               f"{', '.join(PROBLEM_MENTIONS)}.", "",
               "| Field | |", "|---|---|", *[f"| {f} | |" for f in NOTE_FIELDS], ""]
        if message:
            md += ["## Recruiting message (DRAFT, MOCKED send)", "",
                   "Approving it at the threshold lock only places it in the local outbox; nothing is sent.", "",
                   *[f"> {line}" for line in message.splitlines()], ""]
        md += ["## How results are judged", "",
               "Submit counts, or the notes as JSON using the template fields. Code computes every rate with a "
               "Wilson 95% interval and discounts compliments and hypothetical answers.", ""]
        data = {"script": {"opening": script.get("opening"), "questions": questions, "closing": script.get("closing")},
                "removed_questions": removed, "screener": screener, "recruiting_plan": plan,
                "commitment_asks": commitments, "note_template": NOTE_FIELDS, "outward": outward}
        return StepOutput(title="Customer interview kit", markdown="\n".join(md), data=data, files=files,
                          marketing_text=message,
                          summary=f"Prepared a Mom Test kit with {len(questions)} questions and {len(plan)} "
                                  "recruiting sources; waiting for interview results.",
                          claims=[Claim(text="Interview results are not in yet; the problem remains a hypothesis",
                                        label="UNKNOWN", basis="no interviews submitted")])

    def default_contract(self, ctx) -> Contract:
        return Contract(
            step_id="1.4",
            decision="Does the segment show real, costly pain in past behaviour, strong enough to design the business?",
            hypothesis=f"{ctx.concept().get('segment') or 'The segment'} describe the problem unprompted, already "
                       "spend on workarounds, and complete small commitments.",
            criteria=[
                Criterion(key="interviews_completed", target=10, unit="interviews", kind="floor",
                          label="Interviews completed with screened members of the segment"),
                Criterion(key="problem_unprompted_rate", target=0.6, unit="share", kind="proportion",
                          label="Share who describe the problem unprompted or with a specific recent example"),
                Criterion(key="workaround_or_spend_rate", target=0.3, unit="share", kind="proportion",
                          label="Share who already tried a workaround or spent time or money on it"),
                Criterion(key="commitments", target=3, unit="commitments", kind="scalable",
                          label="Completed commitments (intro made, artifact shared, follow-up held)"),
            ],
            pivot_target="1.1",
            notes="Fail with clean evidence of low pain: pivot back to 1.1, or STOP if no segment shows pain. "
                  "Biased recruiting or weak observation: repeat 1.4 within the repeat limit.")

    def collect(self, ctx, contract: Contract) -> Observation | None:
        return None

    def data_fields(self) -> list[DataField]:
        return [
            DataField(key="interviews_completed", label="Interviews completed", type="integer", required=False),
            DataField(key="described_problem_unprompted_or_specific", label="How many described the problem "
                      "unprompted or with a specific recent example", type="integer", required=False),
            DataField(key="tried_workaround_or_spent", label="How many already tried a workaround or spent time or "
                      "money on it", type="integer", required=False),
            DataField(key="commitments", label="Completed commitments (not just offered)", type="integer",
                      required=False),
            DataField(key="interview_notes_json", label="Interview notes (optional, JSON list using the template "
                      "fields)", type="json", required=False,
                      help="Example shape: [{\"participant_id\": \"P1\", \"problem_mention\": \"specific_example\", "
                           "\"quote\": \"...\", \"workaround_or_spend\": \"yes\", \"commitment_completed\": \"no\"}]. "
                           "If given, counts are computed from the notes."),
        ]

    # --- founder data
    def _code_notes(self, ctx, notes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """Structured fields first; free text classified by the model only with verified quotes."""
        coded, flags, pending = [], [], []
        for index, note in enumerate(notes):
            text = " ".join(str(note.get(k) or "") for k in ("quote", "behaviour_observed", "notes", "text",
                                                             "current_spend")).strip()
            mention = str(note.get("problem_mention") or "").strip().lower()
            entry = {"index": index, "participant_id": str(note.get("participant_id") or f"P{index + 1}"),
                     "organization": str(note.get("organization") or "").strip(),
                     "problem_mention": mention if mention in PROBLEM_MENTIONS else None,
                     "workaround_or_spend": _yes(note.get("workaround_or_spend")),
                     "commitment_completed": _yes(note.get("commitment_completed")),
                     "commitment_offered": _yes(note.get("commitment_offered")),
                     "compliment_or_hypothetical": _yes(note.get("compliment_or_hypothetical")),
                     "text": text, "coded_by": "founder"}
            coded.append(entry)
            needs = [k for k in ("problem_mention", "workaround_or_spend", "commitment_completed") if entry[k] is None]
            if needs and text:
                pending.append(entry)
        if pending:
            try:
                reply = interviewer.code_notes(ctx, [{"index": e["index"], "text": e["text"][:1500]} for e in pending])
            except LLMError:
                reply = {"notes": []}
                flags.append("note coding model unavailable: uncoded fields were not counted")
            by_index = {e["index"]: e for e in pending}
            for item in reply.get("notes", []):
                if not isinstance(item, dict):
                    continue
                entry = by_index.get(int(as_float(item.get("index"), -1)))
                if entry is None:
                    continue
                quotes = item.get("quotes") if isinstance(item.get("quotes"), dict) else {}
                haystack = _normalize(entry["text"])

                def supported(field: str) -> bool:
                    quote = _normalize(str(quotes.get(field) or ""))
                    return bool(quote) and quote in haystack

                if entry["problem_mention"] is None:
                    mention = str(item.get("problem_mention") or "").strip().lower()
                    if mention in COUNTS_AS_PROBLEM and not supported("problem_mention"):
                        flags.append(f"{entry['participant_id']}: problem label not backed by a quote; not counted")
                        mention = None
                    entry["problem_mention"] = mention if mention in PROBLEM_MENTIONS else None
                for field in ("workaround_or_spend", "commitment_completed", "commitment_offered",
                              "compliment_or_hypothetical"):
                    if entry[field] is None:
                        value = _yes(item.get(field))
                        if value and not supported(field):
                            flags.append(f"{entry['participant_id']}: {field} not backed by a quote; not counted")
                            value = None
                        entry[field] = value
                entry["coded_by"] = "model (quotes verified in code)"
        uncoded = [e["participant_id"] for e in coded
                   if None in (e["problem_mention"], e["workaround_or_spend"], e["commitment_completed"])]
        if uncoded:
            flags.append(f"{len(uncoded)} note(s) have fields that could not be coded ({', '.join(uncoded[:8])}); "
                         "those fields count as not met")
        return coded, flags

    def observe(self, ctx, contract: Contract, data: dict[str, Any]) -> Observation:
        details: dict[str, Any] = {"source": "founder_data"}
        red_flags: list[str] = []
        evidence_ids: list[str] = []
        notes_raw = data.get("interview_notes_json")
        notes: list[dict[str, Any]] = []
        if isinstance(notes_raw, str) and notes_raw.strip():
            try:
                notes_raw = json.loads(notes_raw)
            except ValueError:
                red_flags.append("interview notes JSON could not be parsed; used the submitted counts")
                notes_raw = None
        if isinstance(notes_raw, dict):
            notes_raw = notes_raw.get("notes") or notes_raw.get("interviews")
        if isinstance(notes_raw, list):
            notes = [n for n in notes_raw if isinstance(n, dict)]

        invalid: list[str] = []
        if notes:
            unique: dict[str, dict[str, Any]] = {}
            for index, note in enumerate(notes):
                unique.setdefault(str(note.get("participant_id") or f"P{index + 1}"), note)
            if len(unique) < len(notes):
                red_flags.append(f"{len(notes) - len(unique)} duplicate participant id(s) counted once")
            notes = list(unique.values())
            coded, flags = self._code_notes(ctx, notes)
            red_flags += flags
            n = len(coded)
            problem = sum(1 for e in coded if e["problem_mention"] in COUNTS_AS_PROBLEM)
            workaround = sum(1 for e in coded if e["workaround_or_spend"])
            commitments = sum(1 for e in coded if e["commitment_completed"])
            offered = sum(1 for e in coded if e["commitment_offered"] or e["commitment_completed"])
            compliments = sum(1 for e in coded if e["compliment_or_hypothetical"])
            hypothetical = sum(1 for e in coded if e["problem_mention"] == "hypothetical")
            orgs = {e["organization"].lower() for e in coded if e["organization"]}
            details.update({"method": "counted from interview notes", "offered_commitments": offered,
                            "compliment_or_hypothetical_notes": compliments, "hypothetical_problem_mentions": hypothetical,
                            "unique_organizations": len(orgs) or None,
                            "coding": [{k: e[k] for k in ("participant_id", "problem_mention", "workaround_or_spend",
                                                         "commitment_completed", "coded_by")} for e in coded]})
            if compliments:
                red_flags.append(f"{compliments} note(s) mainly record compliments or future-tense promises "
                                 "(discounted)")
            if hypothetical:
                red_flags.append(f"{hypothetical} participant(s) only talked hypothetically (not counted)")
            if offered > commitments:
                red_flags.append(f"{offered - commitments} commitment(s) offered but not completed (not counted)")
            for note, entry in zip(notes, coded):
                excerpt = str(note.get("quote") or note.get("behaviour_observed") or entry["text"] or "")[:600]
                row = ctx.ledger.add({
                    "provenance": "PARTICIPANT_REPORTED", "source_type": "interview_note", "url": None,
                    "title": f"Interview {entry['participant_id']}" + (f" ({note.get('role')})" if note.get("role") else ""),
                    "excerpt": excerpt, "observed_at": str(note.get("interview_date") or "") or None,
                    "independence_group": f"interview:{entry['organization'].lower() or entry['participant_id']}",
                    "method": "founder-submitted interview note (Mom Test template)",
                    "limitations": "Reported by the participant and recorded by the founder; not verified."})
                evidence_ids.append(row.evidence_id)
            submitted_n = as_float(data.get("interviews_completed"))
            if submitted_n is not None and int(submitted_n) != n:
                red_flags.append(f"submitted interview count ({int(submitted_n)}) differs from the notes ({n}); "
                                 "the notes were used")
        else:
            def count(key: str) -> int | None:
                value = as_float(data.get(key))
                if value is None:
                    return None
                if value < 0 or value != int(value):
                    invalid.append(f"{key} must be a whole number of 0 or more")
                    return None
                return int(value)

            n = count("interviews_completed")
            problem = count("described_problem_unprompted_or_specific")
            workaround = count("tried_workaround_or_spent")
            commitments = count("commitments")
            for key, value in (("described_problem_unprompted_or_specific", problem),
                               ("tried_workaround_or_spent", workaround)):
                if n is not None and value is not None and value > n:
                    invalid.append(f"{key} ({value}) is larger than interviews_completed ({n})")
            details["method"] = "founder-reported counts"
            if n is not None:
                red_flags.append("counts were submitted without notes, so quotes and coding cannot be audited")
                row = ctx.ledger.add({
                    "provenance": "FOUNDER_REPORTED", "source_type": "founder_data", "url": None,
                    "title": "Founder-reported interview counts", "value": float(n), "unit": "interviews",
                    "excerpt": (f"interviews={n}; problem unprompted/specific={problem}; workaround or spend="
                                f"{workaround}; completed commitments={commitments}"),
                    "method": "founder-submitted counts", "independence_group": f"founder-interview-counts:{ctx.run.run_id}",
                    "limitations": "Counts without notes; coding not auditable."})
                evidence_ids.append(row.evidence_id)

        if n is not None and n < 5:
            red_flags.append(f"sample size under 5 (n={n})")
        rates: dict[str, Any] = {}
        for key, successes in (("problem_unprompted_rate", problem), ("workaround_or_spend_rate", workaround)):
            if n and successes is not None and not invalid:
                low, high = wilson_interval(successes, n)
                rates[key] = {"successes": successes, "n": n, "rate": round(successes / n, 4),
                              "wilson95": [low, high]}
            else:
                rates[key] = None
        values = {"interviews_completed": n, "commitments": commitments,
                  "problem_unprompted_rate": rates["problem_unprompted_rate"]["rate"]
                  if rates["problem_unprompted_rate"] else None,
                  "workaround_or_spend_rate": rates["workaround_or_spend_rate"]["rate"]
                  if rates["workaround_or_spend_rate"] else None}
        if invalid:
            observed = {c.key: None for c in contract.criteria}
            state_name = INVALID_DATA
        else:
            observed = {c.key: (float(values[c.key]) if values.get(c.key) is not None else None)
                        for c in contract.criteria}
            missing = [k for k, v in observed.items() if v is None]
            state_name = READY if not missing else (WAITING_FOR_DATA if len(missing) == len(observed)
                                                    else INSUFFICIENT_DATA)
            details["missing"] = missing
        details.update({"rates": rates, "red_flags": red_flags, "invalid": invalid})
        summary = (f"n={n}; problem {problem}/{n}, workaround/spend {workaround}/{n}, completed commitments "
                   f"{commitments}" if n else "no interview count")
        return Observation(observed=observed, measurement_state=state_name, evidence_ids=evidence_ids,
                           details=details, notes=f"Founder-reported interview data ({details['method']}): {summary}"
                           + (f". Invalid: {'; '.join(invalid)}" if invalid else ""))
