"""FIXTURE model replies for the Phase 1 (Discover) and researcher tasks. STUBBED model only, used in tests.

respond(task_id, user_text) returns a reply dict for tasks this part owns, else None.
Replies only cite evidence IDs that appear in the request, so they never invent references.
"""
from __future__ import annotations

import json
import re
from typing import Any


def _payload(user_text: str) -> dict[str, Any]:
    match = re.search(r"INPUT \(JSON\):\n(.*)\n\nReply with ONLY", user_text or "", re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except ValueError:
        return {}


def _plan(p: dict[str, Any]) -> dict[str, Any]:
    return {"problem_queries": ["client feedback scattered", "design revision chaos"],
            "workaround_queries": ["feedback spreadsheet freelance"],
            "alternative_queries": ["alternative to markup tool"],
            "pricing_queries": ["design feedback tool pricing"],
            "subreddits": ["freelance", "web_design"], "stackexchange_site": "graphicdesign",
            "wikipedia_topic": "Web design", "country_iso2": "EG"}


def _classify(p: dict[str, Any]) -> dict[str, Any]:
    rows = p.get("rows") or []
    relevant, communities, competitors = [], [], []
    for row in rows:
        text = f"{row.get('title', '')} {row.get('excerpt', '')}".lower()
        if "unrelated" in text:
            continue
        if row.get("kind") == "discussion":
            relevant.append(row["id"])
        elif row.get("kind") == "community":
            communities.append(row["id"])
        elif row.get("kind") == "repo":
            competitors.append({"id": row["id"], "name": row.get("title", "")})
    return {"relevant_ids": relevant, "community_ids": communities, "competitors": competitors}


def _sharpen(p: dict[str, Any]) -> dict[str, Any]:
    revised = " (revised)" if p.get("feedback") else ""
    ids = p.get("founder_evidence_ids") or []
    return {
        "title": "Client feedback tracker" + revised,
        "segment": "Freelance web designers with 3+ active clients",
        "problem": "client feedback scattered across email, chat and calls",
        "situation": "a project enters its revision rounds",
        "workaround": "copy comments into a spreadsheet by hand",
        "cost_of_problem": {"text": "hours of rework per project", "label": "FOUNDER_REPORTED" if ids else "ASSUMPTION",
                            "basis": "FIXTURE basis", "evidence_ids": ids},
        "buying_roles": {"user": "the designer", "payer": "the designer", "approver": "the designer"},
        "alternatives": [
            {"name": "Agency revision log", "statement": "Small agencies track revision requests per client",
             "segment": "Design agencies with 2-10 staff", "changed_assumption": "segment",
             "first_user": "agency project lead", "smallest_test": "5 agency interviews"},
            {"name": "Feedback template pack", "statement": "A template that structures client feedback",
             "segment": "Freelance web designers", "changed_assumption": "delivery mode (template)",
             "first_user": "solo designer", "smallest_test": "share a template in one community"},
            {"name": "Concierge feedback digest", "statement": "A weekly human-made digest of client feedback",
             "segment": "Freelance web designers", "changed_assumption": "delivery mode (concierge)",
             "first_user": "busy freelancer", "smallest_test": "run it by hand for 3 designers"},
        ],
        "status_quo": "Designers keep re-reading threads and miss some requests.",
        "questions": ["Walk me through the last time a client's feedback got lost. What did it cost?"],
    }


def _score(p: dict[str, Any]) -> dict[str, Any]:
    concepts = []
    for index, concept in enumerate(p.get("concepts") or []):
        cid = concept.get("id")
        base = 4 if cid == "A1" else 3
        scores = {key: {"base": base, "low": base - 1, "high": base + 1 if base < 5 else 5, "basis": "ASSUMPTION: FIXTURE",
                        "evidence_ids": []}
                  for key in ("severity", "frequency", "willingness_to_pay", "reachability", "founder_fit",
                              "competition_gap", "speed_to_mvp")}
        if cid == "C0":
            scores["frequency"] = {"base": None, "unknown": True, "basis": "no data (FIXTURE)", "evidence_ids": []}
        blockers = ["needs a partnership the founder does not have (FIXTURE)"] if cid == "A3" else []
        if cid == "A3":
            scores = {k: dict(v, base=5, low=5, high=5) for k, v in scores.items()}
        concepts.append({"id": cid, "scores": scores, "blockers": blockers})
    return {"concepts": concepts}


def _market(p: dict[str, Any]) -> dict[str, Any]:
    rows = p.get("evidence") or []
    community = next((r for r in rows if r.get("unit") in ("subscribers", "registered users", "members")), None)
    priced = next((r for r in rows if "$19" in (r.get("excerpt") or "")), None)
    channels = [{"name": "Community found in research", "url": community.get("url") if community else None,
                 "evidence_ids": [community["id"]] if community else [], "note": "ASSUMPTION: share eligible unknown"}]
    competitors = [
        {"name": "Priced tool", "type": "direct", "url": priced.get("url") if priced else None,
         "price": "$19/mo", "evidence_ids": [priced["id"]] if priced else [], "notes": "FIXTURE"},
        {"name": "Uncited tool", "type": "direct", "url": "https://fixture.invalid/not-collected", "price": "$49/mo",
         "evidence_ids": [], "notes": "FIXTURE: price and URL are not in evidence"},
        {"name": "Spreadsheets", "type": "substitute", "url": None, "price": "unknown", "evidence_ids": [],
         "notes": "FIXTURE"},
    ]
    return {
        "icp": {"description": "FIXTURE ICP", "inclusion": ["3+ active clients"], "exclusion": ["agencies"],
                "purchasing_unit": "designer"},
        "primary_segment": "Freelance web designers (FIXTURE)", "horizon": "12 months", "currency": "USD",
        "market_inputs": [
            {"name": "eligible_units", "value": 50000, "low": 20000, "high": 80000, "unit": "designers",
             "label": "SOURCED", "evidence_ids": [], "basis": "FIXTURE: labelled SOURCED without evidence"},
            {"name": "annual_spend", "value": 120, "low": 60, "high": 240, "unit": "USD", "label": "ASSUMPTION",
             "evidence_ids": [], "basis": "FIXTURE assumption"},
            {"name": "serviceability_filter", "description": "English-speaking", "value": 0.5, "label": "ASSUMPTION",
             "evidence_ids": [], "basis": "FIXTURE assumption"},
            {"name": "reachable_units", "value": 2000, "label": "ASSUMPTION", "evidence_ids": [],
             "basis": "FIXTURE assumption"},
            {"name": "response_rate", "value": 10, "label": "ASSUMPTION", "evidence_ids": [], "basis": "FIXTURE (percent)"},
            {"name": "close_rate", "value": 0.05, "label": "ASSUMPTION", "evidence_ids": [], "basis": "FIXTURE"},
        ],
        "competitors": competitors, "channels": channels,
        "largest_coverage_gap": "FIXTURE: no public data on how many designers pay for feedback tools.",
        "claims": [{"text": "FIXTURE claim citing a missing row", "label": "SOURCED", "evidence_ids": ["E-999"],
                    "basis": ""}],
    }


def _kit(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "script": {"opening": "I'm researching how designers handle client feedback. This is not a sales call.",
                   "questions": [{"q": "Tell me about the last time client feedback got lost.", "purpose": "incident"},
                                 {"q": "What did you do about it?", "purpose": "workaround"},
                                 {"q": "Would you pay $20 a month for a tool that fixes this?", "purpose": "pitch"},
                                 {"q": "What have you already spent on this?", "purpose": "spend"}],
                   "closing": "Could you introduce me to another designer who deals with this?"},
        "screener": [{"question": "How many active clients do you have?", "qualifies_if": "3 or more"}],
        "recruiting_plan": [{"source": "Community found in research", "url": "https://fixture.invalid/x",
                             "approach": "post in the weekly thread", "target_count": 6}],
        "recruiting_message": "Hi, I'm researching how freelance designers keep track of client feedback. "
                              "It's research, not a sales pitch. Could I ask you about your last project for 20 minutes?",
        "commitment_asks": ["An introduction to another designer"],
    }


def _code_notes(p: dict[str, Any]) -> dict[str, Any]:
    out = []
    for note in p.get("notes") or []:
        text = note.get("text") or ""
        low = text.lower()
        item = {"index": note.get("index"), "problem_mention": "none", "workaround_or_spend": False,
                "commitment_offered": False, "commitment_completed": False, "compliment_or_hypothetical": False,
                "quotes": {}}
        if "last week" in low:
            item["problem_mention"] = "specific_example"
            item["quotes"]["problem_mention"] = text[low.index("last week"):low.index("last week") + 9]
        if "spreadsheet" in low:
            item["workaround_or_spend"] = True
            item["quotes"]["workaround_or_spend"] = "spreadsheet"
        if "introduced me" in low:
            item["commitment_completed"] = True
            item["quotes"]["commitment_completed"] = "introduced me"
        if "fixture-bad-quote" in low:
            item["commitment_completed"] = True
            item["quotes"]["commitment_completed"] = "words that are not in the note"
        if "love it" in low:
            item["compliment_or_hypothetical"] = True
            item["quotes"]["compliment_or_hypothetical"] = "love it"
        out.append(item)
    return {"notes": out}


HANDLERS = {
    "researcher.plan_queries": _plan,
    "researcher.classify_relevance": _classify,
    "strategist.sharpen_idea": _sharpen,
    "strategist.score_concepts": _score,
    "market_analyst.build_market_model": _market,
    "interviewer.prepare_kit": _kit,
    "interviewer.code_notes": _code_notes,
}


def respond(task_id: str, user_text: str) -> dict | None:
    handler = HANDLERS.get(task_id)
    return handler(_payload(user_text)) if handler else None
