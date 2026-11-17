"""STUBBED model replies (FIXTURE data) for the Phase 2 and Phase 5 agents.

respond(task_id, user_text) returns a FIXTURE reply for the tasks of
business_designer, growth_marketer and launch_marketer, and None for any
other task. Replies read the agent's INPUT JSON so they only cite evidence IDs
and channel IDs that the agent was actually given.
"""
from __future__ import annotations

import json
import re
from typing import Any

TASKS = ("business_designer.lean_canvas", "growth_marketer.landing_page", "launch_marketer.store_page",
         "launch_marketer.launch_posts")


def agent_input(user_text: str) -> dict[str, Any]:
    """The INPUT JSON block that agents.base.call_agent puts in the user message."""
    match = re.search(r"INPUT \(JSON\):\n(.*)\n\nReply with ONLY", user_text or "", re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _lean_canvas(data: dict[str, Any]) -> dict[str, Any]:
    brief_id = data.get("founder_brief_evidence_id")
    founder = {"label": "FOUNDER_REPORTED", "evidence_ids": [brief_id] if brief_id else [], "basis": "FIXTURE: founder brief"}

    def assume(basis: str) -> dict[str, Any]:
        return {"label": "ASSUMPTION", "evidence_ids": [], "basis": f"FIXTURE: {basis}"}

    return {
        "boxes": {
            "problem": {"content": "FIXTURE problem: clients send feedback across email and chat, so revisions get lost.", **founder},
            "customer_segments": {"content": "FIXTURE segment: solo freelance web designers with 3+ active clients.", **founder},
            "unique_value_proposition": {"content": "Collect every client comment in one place and finish revisions faster.",
                                         **assume("not yet tested with visitors")},
            "solution": {"content": "FIXTURE solution: a shared feedback link per project.", **assume("smallest delivery")},
            "channels": {"content": "FIXTURE channels: a design community and a freelancer newsletter.", **assume("reachability")},
            "revenue_streams": {"content": "FIXTURE revenue: monthly subscription paid by the designer.", **assume("to test in 4.1")},
            "cost_structure": {"content": "FIXTURE costs: founder time and free-tier hosting.", **founder},
            "key_metrics": {"content": "FIXTURE metrics: projects with feedback collected per week.", **assume("value event")},
            "unfair_advantage": {"content": "None yet.", **assume("no unique asset identified")},
        },
        "riskiest_assumptions": [
            {"assumption": "FIXTURE: designers will move clients to a new link", "loss_if_wrong": "No usage at all",
             "loss_score": 4, "uncertainty_score": 4, "test": "Landing-page test (2.2)", "cost_to_test": "14 days, 0 cash",
             "blocks_decision": "3.1 MVP scope"},
            {"assumption": "FIXTURE: the problem is frequent enough to pay for", "loss_if_wrong": "Cannot monetize",
             "loss_score": 5, "uncertainty_score": 3, "test": "Pricing test (4.1)", "cost_to_test": "1 week",
             "blocks_decision": "4.1 price"},
            {"assumption": "FIXTURE: the design community allows posts", "loss_if_wrong": "Low reach",
             "loss_score": 3, "uncertainty_score": 2, "test": "Ask the moderators", "cost_to_test": "1 hour",
             "blocks_decision": "2.2 traffic plan"},
        ],
        "channels": [
            {"id": "design-community", "name": "FIXTURE design community", "url": None,
             "audience_rule": "Members who say they freelance", "evidence_ids": []},
            {"id": "freelance-newsletter", "name": "FIXTURE freelancer newsletter", "url": None,
             "audience_rule": "Readers who click through from the issue", "evidence_ids": []},
        ],
        "revenue_hypothesis": {"who_pays": "the designer", "price_unit": "per designer", "billing_period": "monthly",
                               "substitute_spend": None, "statement": "FIXTURE: a monthly subscription per designer.",
                               "label": "ASSUMPTION", "evidence_ids": [], "basis": "FIXTURE: common for the category"},
        "summary": "FIXTURE: built the canvas from the stubbed Phase 1 outputs.",
        "questions": [],
    }


def _landing_page(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": "Every client comment in one place",
        "subheadline": "For freelance designers juggling feedback across email and chat.",
        "benefits": ["See all feedback for a project on one page", "Know which revisions are still open",
                     "Send clients one link instead of long email threads"],
        "follow_up_question": "How many active clients do you have?",
        "faq": [{"question": "What happens after I join?",
                 "answer": "The founder may email you to ask about how you handle client feedback today."},
                {"question": "Who is it for?", "answer": "Freelance web designers with several active clients."}],
        "channel_actions": [{"channel_id": c.get("id"), "action": "Share the tracked link once with a short note",
                             "message_angle": "Lost feedback", "founder_hours": "ESTIMATE: 1 h"}
                            for c in data.get("channels") or []],
        "repeat_variable": "The headline angle",
        "summary": "FIXTURE: landing copy for the research waitlist.",
        "questions": [],
    }


def _store_page(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "tagline": "Collect client feedback with one link",
        "who_it_serves": "Freelance web designers with several active clients; not agencies with their own tools.",
        "outcome": "All feedback for a project lands on one page you can work through.",
        "available_now": "An early version with one shared feedback page per project.",
        "not_included": "Integrations and team accounts.",
        "demo_description": "Create a project, share its link, and see a comment appear on the project page.",
        "faq": [{"question": "What happens after I request access?",
                 "answer": "The founder emails you an access link for the early version."}],
        "summary": "FIXTURE: store copy.",
        "questions": [],
    }


def _launch_posts(data: dict[str, Any]) -> dict[str, Any]:
    channels = data.get("channels") or [{"id": "founder-named-channel", "name": "Founder-named channel"}]
    return {
        "posts": [{"channel_id": c.get("id"), "channel_name": c.get("name"), "format": "community post",
                   "text": (f"FIXTURE draft for {c.get('name')}: I built an early tool that keeps client feedback "
                            "on one page. Requesting access costs nothing; I would love to hear how you handle "
                            "feedback today."),
                   "day": 1 + 3 * i, "timing": "weekday morning", "follow_up": "Reply to every comment within a day."}
                  for i, c in enumerate(channels)],
        "summary": "FIXTURE: launch drafts.",
        "questions": [],
    }


def respond(task_id: str, user_text: str) -> dict | None:
    if task_id not in TASKS:
        return None
    data = agent_input(user_text)
    return {"business_designer.lean_canvas": _lean_canvas, "growth_marketer.landing_page": _landing_page,
            "launch_marketer.store_page": _store_page, "launch_marketer.launch_posts": _launch_posts}[task_id](data)
