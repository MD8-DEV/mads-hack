"""Desk research with STUBBED HTTP (httpx.MockTransport) and a STUBBED model. No network access.

All API responses below are FIXTURE data shaped like the real free APIs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from agents.base import StepContext
from agents.researcher import ResearchResult, run_desk_research
from config import Settings
from llm import FakeLLM, task_id_of
from steps import STEP_IDS, STEPS_BY_ID
from store import RunStore
from tests import stubs_discover
from tools import research as R

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc).timestamp()
RECENT = int(NOW - 30 * 86400)          # one month ago
OLD = int(NOW - 30 * 30 * 86400)        # about 30 months ago: outside the 24-month window


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------- FIXTURE API responses
def hn_response(tags: str) -> dict:
    if tags == "comment":
        return {"hits": [
            {"objectID": "5001", "story_id": 2002, "story_title": "Ask HN: tracking client feedback?",
             "comment_text": "FIXTURE: I lose <i>client feedback</i> in email threads every project.",
             "created_at": iso(RECENT), "created_at_i": RECENT},
            {"objectID": "5002", "story_id": 2002, "story_title": "Ask HN: tracking client feedback?",
             "comment_text": "FIXTURE: Same here, we copy comments into a spreadsheet.",
             "created_at": iso(RECENT), "created_at_i": RECENT},
            {"objectID": "5003", "story_id": 1001, "story_title": "Client feedback is scattered everywhere",
             "comment_text": "FIXTURE: this is my week every week.", "created_at": iso(RECENT),
             "created_at_i": RECENT},
        ]}
    return {"hits": [
        {"objectID": "1001", "title": "Client feedback is scattered everywhere",
         "story_text": "FIXTURE: freelance designers &amp; their clients send feedback in five places.",
         "created_at": iso(RECENT), "created_at_i": RECENT},
        {"objectID": "1002", "title": "Unrelated rocket launch thread", "story_text": "FIXTURE",
         "created_at": iso(RECENT), "created_at_i": RECENT},
        {"objectID": "1003", "title": "Old thread about client feedback", "story_text": "FIXTURE",
         "created_at": iso(OLD), "created_at_i": OLD},
    ]}


SE_SEARCH = {"items": [{"question_id": 3003, "link": "https://graphicdesign.stackexchange.com/questions/3003/x",
                        "title": "How do you organise client feedback rounds?", "tags": ["client-relations"],
                        "body": "<p>FIXTURE: clients comment by email and chat.</p>", "creation_date": RECENT}],
             "quota_max": 300, "quota_remaining": 290}
SE_INFO = {"items": [{"total_users": 12000, "total_questions": 30000, "total_answers": 50000}]}
GITHUB = {"items": [{"full_name": "fixture/feedback-board", "html_url": "https://github.com/fixture/feedback-board",
                     "description": "FIXTURE: collect client feedback on designs", "stargazers_count": 42,
                     "pushed_at": iso(RECENT)}]}
WIKI_SEARCH = {"query": {"search": [{"title": "Web design"}]}}
PAGEVIEWS = {"items": [{"views": 1000}, {"views": 2000}, {"views": 3000}]}


def world_bank_response(code: str) -> list:
    value = {"SP.POP.TOTL": 118365995, "IT.NET.USER.ZS": 74.6}[code]
    return [{"page": 1}, [{"indicator": {"id": code, "value": f"FIXTURE {code}"}, "country": {"value": "Egypt"},
                           "date": "2024", "value": value}]]


class FakeWeb:
    """STUBBED web: routes requests to FIXTURE responses and records every call."""

    def __init__(self, *, se_backoff: int | None = None, fail_hosts: tuple[str, ...] = ()):
        self.calls: list[httpx.URL] = []
        self.se_backoff = se_backoff
        self.fail_hosts = fail_hosts

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(url)
        assert "venture-validator-research" in request.headers["User-Agent"]
        if url.host in self.fail_hosts:
            raise httpx.ConnectError("FIXTURE: network down", request=request)
        if url.host == "hn.algolia.com":
            return httpx.Response(200, json=hn_response(url.params.get("tags")))
        if url.host == "www.reddit.com":
            return httpx.Response(403, text="<html>blocked</html>")
        if url.host == "api.stackexchange.com":
            if url.path.endswith("/info"):
                return httpx.Response(200, json=SE_INFO)
            body = dict(SE_SEARCH)
            if self.se_backoff:
                body["backoff"] = self.se_backoff
            return httpx.Response(200, json=body)
        if url.host == "api.github.com":
            return httpx.Response(200, json=GITHUB)
        if url.host == "en.wikipedia.org":
            return httpx.Response(200, json=WIKI_SEARCH)
        if url.host == "wikimedia.org":
            return httpx.Response(200, json=PAGEVIEWS)
        if url.host == "api.worldbank.org":
            return httpx.Response(200, json=world_bank_response(url.path.rstrip("/").split("/")[-1]))
        return httpx.Response(404, json={})

    def hosts(self) -> list[str]:
        return [u.host for u in self.calls]


def stub_model(messages, tier):
    task = task_id_of(messages)
    first_user = next(m["content"] for m in messages if m["role"] == "user")
    reply = stubs_discover.respond(task, first_user)
    return reply if reply is not None else {}


def make_ctx(tmp_path, *, web=None, responder=stub_model, enabled=True, brief=None):
    settings = Settings(data_dir=tmp_path, main_chain=[], fast_chain=[], request_timeout=5, daily_budget_usd=0,
                        research_enabled=enabled, research_timeout=5)
    store = RunStore(tmp_path / "runs")
    run = store.create(brief or {"idea": "Client feedback tracker", "customer": "freelance web designers",
                                 "jurisdiction": "Egypt"}, step_ids=STEP_IDS)
    llm = FakeLLM(responder)
    ctx = StepContext(run=run, meta=STEPS_BY_ID["1.3"], store=store, llm=llm, log=store.log(run.run_id),
                      ledger=store.ledger(run.run_id), approvals=store.approvals(run.run_id), settings=settings,
                      extra={"research_transport": httpx.MockTransport(web) if web else None,
                             "research_now": lambda: NOW})
    return ctx, llm


def research(ctx) -> ResearchResult:
    return run_desk_research(ctx, topic="Client feedback tracker", segment="freelance web designers",
                             problem="client feedback scattered across channels")


# ------------------------------------------------------------------------------------- tests
def test_collects_every_source_and_counts_by_independence_group(tmp_path):
    web = FakeWeb()
    ctx, _ = make_ctx(tmp_path, web=web)
    result = research(ctx)
    stats = result.stats

    # Story 1001 and its comment count once; two comments on story 2002 count once; one Stack Exchange question.
    assert stats["independent_discussions"] == 3
    assert stats["discussions_by_source"] == {"hacker_news": 2, "stackexchange": 1}
    assert stats["largest_community_members"] == 12000
    assert stats["largest_community"]["url"] == "https://graphicdesign.stackexchange.com"
    assert stats["window_months"] == 24
    assert stats["wikipedia_pageviews"][0]["monthly_avg"] == 2000.0
    assert {w["indicator"] for w in stats["world_bank"]} == {"SP.POP.TOTL", "IT.NET.USER.ZS"}
    assert stats["competitor_candidates"][0]["url"] == "https://github.com/fixture/feedback-board"

    # Reddit is blocked: one attempt, then skipped, and recorded as a coverage note.
    assert web.hosts().count("www.reddit.com") == 1
    assert any("reddit unavailable" in n for n in result.coverage_notes)
    assert any("older than 24 months" in n for n in result.coverage_notes)

    # Evidence rows are real SOURCE_FACT rows with URLs and short excerpts.
    rows = [ctx.ledger.get(i) for i in result.evidence_ids]
    assert rows and all(r.provenance == "SOURCE_FACT" and r.url and len(r.excerpt) <= 600 for r in rows)
    assert all("<" not in r.excerpt for r in rows)  # HTML stripped
    assert set(stats["relevant_evidence_ids"]) <= set(result.evidence_ids)

    # One RESEARCH log entry per source, without a model and at zero cost.
    entries = [e for e in ctx.log.entries if e["action_type"] == "RESEARCH" and e["model"] is None]
    assert sorted(e["action"] for e in entries) == sorted(
        ["search_hacker_news", "search_reddit", "search_stackexchange", "search_github", "search_wikipedia",
         "fetch_world_bank"])
    assert all(e["agent"] == "researcher" and e["cost"] == 0 and e["approved_by"] is None for e in entries)
    assert all(e["sources"] for e in entries)


def test_offline_flag_makes_no_calls(tmp_path):
    web = FakeWeb()
    ctx, llm = make_ctx(tmp_path, web=web, enabled=False)
    result = research(ctx)
    assert result.coverage_notes == ["research disabled (offline)"]
    assert result.stats == {} and result.evidence_ids == []
    assert web.calls == [] and llm.calls == []


def test_relevance_failure_counts_nothing(tmp_path):
    def broken_classifier(messages, tier):
        if task_id_of(messages) == "researcher.classify_relevance":
            return "not json at all"
        return stub_model(messages, tier)

    ctx, _ = make_ctx(tmp_path, web=FakeWeb(), responder=broken_classifier)
    result = research(ctx)
    assert result.stats["independent_discussions"] is None
    assert result.stats["largest_community_members"] is None
    assert any("relevance check unavailable" in n for n in result.coverage_notes)


def test_relevance_filter_ignores_unknown_ids(tmp_path):
    def sloppy_classifier(messages, tier):
        if task_id_of(messages) == "researcher.classify_relevance":
            return {"relevant_ids": ["E-900", "E-901"], "community_ids": ["E-950"], "competitors": []}
        return stub_model(messages, tier)

    ctx, _ = make_ctx(tmp_path, web=FakeWeb(), responder=sloppy_classifier)
    result = research(ctx)
    assert result.stats["independent_discussions"] == 0     # sources answered; nothing relevant was labelled
    assert result.stats["largest_community_members"] is None


def test_planner_failure_uses_founder_words(tmp_path):
    def no_planner(messages, tier):
        if task_id_of(messages) == "researcher.plan_queries":
            return "???"
        return stub_model(messages, tier)

    ctx, _ = make_ctx(tmp_path, web=FakeWeb(), responder=no_planner)
    result = research(ctx)
    assert result.queries and all(q for q in result.queries)
    assert any("query planner unavailable" in n for n in result.coverage_notes)
    assert result.stats["world_bank"] == []   # no country guessed without the planner


def test_no_country_without_jurisdiction(tmp_path):
    web = FakeWeb()
    ctx, _ = make_ctx(tmp_path, web=web, brief={"idea": "Client feedback tracker", "customer": "designers"})
    research(ctx)
    assert "api.worldbank.org" not in web.hosts()


def test_cache_reuses_responses_for_24_hours(tmp_path):
    web = FakeWeb()
    clock = {"now": NOW}
    with R.ResearchClient(cache_dir=tmp_path / "cache", transport=httpx.MockTransport(web),
                          now=lambda: clock["now"]) as client:
        first = R.search_github(client, "feedback tool")
        second = R.search_github(client, "feedback tool")
        assert len(web.calls) == 1 and client.cache_hits == 1
        assert first.rows == second.rows
        clock["now"] += 25 * 3600
        R.search_github(client, "feedback tool")
        assert len(web.calls) == 2
    cached = list((tmp_path / "cache").glob("*.json"))
    assert cached and json.loads(cached[0].read_text(encoding="utf-8"))["url"].startswith("https://api.github.com/")


def test_network_error_never_raises_and_is_not_retried(tmp_path):
    web = FakeWeb(fail_hosts=("hn.algolia.com",))
    with R.ResearchClient(transport=httpx.MockTransport(web), now=lambda: NOW) as client:
        first = R.search_hacker_news(client, "client feedback")
        second = R.search_hacker_news(client, "client feedback", kind="comment")
    assert first.rows == [] and "request failed" in first.error
    assert second.rows == [] and "unavailable" in second.error
    assert len(web.calls) == 1


def test_stackexchange_backoff_is_obeyed(tmp_path):
    web = FakeWeb(se_backoff=30)
    with R.ResearchClient(transport=httpx.MockTransport(web), now=lambda: NOW) as client:
        first = R.search_stackexchange(client, "client feedback", "graphicdesign")
        second = R.search_stackexchange(client, "feedback rounds", "graphicdesign")
    assert first.rows and first.error is None
    assert second.rows == [] and "back off" in second.error
    assert web.hosts().count("api.stackexchange.com") == 1


def test_all_discussion_sources_down_means_not_measured(tmp_path):
    web = FakeWeb(fail_hosts=("hn.algolia.com", "api.stackexchange.com"))
    ctx, _ = make_ctx(tmp_path, web=web)
    result = research(ctx)
    assert result.stats["independent_discussions"] is None
    assert any("no discussion source" in n for n in result.coverage_notes)


def test_rows_have_window_and_independence_metadata(tmp_path):
    web = FakeWeb()
    with R.ResearchClient(transport=httpx.MockTransport(web), now=lambda: NOW) as client:
        comments = R.search_hacker_news(client, "client feedback", kind="comment")
    groups = [r["independence_group"] for r in comments.rows]
    assert groups == ["hn:2002", "hn:2002", "hn:1001"]
    assert all(r["url"].startswith("https://news.ycombinator.com/item?id=") for r in comments.rows)
    since = int(web.calls[0].params["numericFilters"].split(">")[1])
    assert NOW - since > 23 * 30 * 86400
    assert R.within_window(iso(RECENT), NOW) and not R.within_window(iso(OLD), NOW)
