"""Researcher agent: desk research over free public sources.

The model only plans search queries and labels which collected rows are
relevant. Every row comes from a real API response (tools/research.py) and
every count is computed here in Python from those rows. A source that fails
or is blocked becomes a coverage note; "no results" never means "no demand".
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from agents.base import StepContext, as_list, call_agent
from llm import LLMError
from tools import research as R

ROLE = "researcher"
CLASSIFY_BATCH = 25
MAX_CLASSIFY_ROWS = 100
MAX_SUBREDDITS = 3
LOG_SOURCE_LIMIT = 40

SOURCE_LABELS = {"hacker_news": "Hacker News (Algolia)", "reddit": "Reddit public JSON",
                 "stackexchange": "Stack Exchange", "github": "GitHub repository search",
                 "wikipedia": "Wikipedia search and pageviews", "world_bank": "World Bank indicators"}
SOURCE_ACTIONS = {"hacker_news": "search_hacker_news", "reddit": "search_reddit",
                  "stackexchange": "search_stackexchange", "github": "search_github",
                  "wikipedia": "search_wikipedia", "world_bank": "fetch_world_bank"}
FAMILIES = ("problem_queries", "workaround_queries", "alternative_queries", "pricing_queries")
DISCUSSION_FAMILIES = ("extra", "problem_queries", "workaround_queries")


@dataclass
class ResearchResult:
    queries: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    coverage_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------- query plan
def _clean_query(text: Any) -> str:
    query = re.sub(r"\s+", " ", str(text or "")).strip().strip('"').strip()
    return query[:80]


def _validate_plan(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    plan: dict[str, Any] = {}
    for family in FAMILIES:
        plan[family] = [q for q in (_clean_query(x) for x in as_list(data.get(family))) if q]
    if not any(plan[f] for f in FAMILIES):
        raise ValueError("no search queries in the reply")
    plan["subreddits"] = [s for s in (str(x or "").strip().removeprefix("r/") for x in as_list(data.get("subreddits")))
                          if R.SUBREDDIT_RE.match(s)][:MAX_SUBREDDITS]
    site = str(data.get("stackexchange_site") or "").strip().lower()
    plan["stackexchange_site"] = site if R.SE_SITE_RE.match(site) else None
    topic = _clean_query(data.get("wikipedia_topic"))
    plan["wikipedia_topic"] = topic or None
    iso2 = str(data.get("country_iso2") or "").strip().upper()
    plan["country_iso2"] = iso2 if R.ISO2_RE.match(iso2) else None
    return plan


def _fallback_plan(topic: str, segment: str, problem: str) -> dict[str, Any]:
    """Deterministic queries built from the founder's own words when the planner is unavailable."""
    words = lambda text, n: " ".join(re.findall(r"[A-Za-z0-9][\w\-']*", text or "")[:n])  # noqa: E731
    return {"problem_queries": [q for q in (words(problem, 6), words(f"{segment} {topic}", 5)) if q],
            "workaround_queries": [], "alternative_queries": [q for q in (words(topic, 4),) if q],
            "pricing_queries": [], "subreddits": [], "stackexchange_site": None,
            "wikipedia_topic": words(topic, 4) or None, "country_iso2": None}


def plan_queries(ctx: StepContext, *, topic: str, segment: str, problem: str,
                 max_queries: int) -> tuple[dict[str, Any], list[str]]:
    payload = {"topic": topic, "segment": segment, "problem": problem, "max_queries": max_queries,
               "jurisdiction": ctx.brief.get("jurisdiction") or None, "feedback": ctx.feedback}
    try:
        plan = call_agent(ctx, role=ROLE, task="plan_queries", payload=payload, tier="fast", max_tokens=900,
                          validate=_validate_plan, action_type="RESEARCH",
                          description="Planned desk-research query families")
        notes: list[str] = []
    except LLMError as exc:
        plan = _fallback_plan(topic, segment, problem)
        notes = [f"query planner unavailable ({str(exc)[:120]}); used queries built from the founder's own words"]
    if not ctx.brief.get("jurisdiction"):
        plan["country_iso2"] = None  # never guess a country the founder did not name
    return plan, notes


def _ordered_queries(plan: dict[str, Any], extra: list[str], max_queries: int) -> list[tuple[str, str]]:
    """Round-robin across query families so every family gets a slot; extra queries first."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def push(family: str, query: str) -> None:
        key = query.lower()
        if query and key not in seen and len(out) < max_queries:
            seen.add(key)
            out.append((family, query))

    for query in extra:
        push("extra", _clean_query(query))
    pools = {f: list(plan.get(f) or []) for f in FAMILIES}
    while len(out) < max_queries and any(pools.values()):
        for family in FAMILIES:
            if pools[family]:
                push(family, pools[family].pop(0))
    return out


# ---------------------------------------------------------------------------------------------- relevance
def _validate_relevance(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    if "relevant_ids" not in data:
        raise ValueError("missing relevant_ids")
    competitors = []
    for item in as_list(data.get("competitors")):
        if isinstance(item, dict) and item.get("id"):
            competitors.append({"id": str(item["id"]).strip(), "name": str(item.get("name") or "").strip()})
    return {"relevant_ids": [str(x).strip() for x in as_list(data.get("relevant_ids"))],
            "community_ids": [str(x).strip() for x in as_list(data.get("community_ids"))],
            "competitors": competitors}


def classify_relevance(ctx: StepContext, *, topic: str, segment: str, problem: str,
                       rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Ask the model which rows describe the problem for the segment. None if any batch failed."""
    merged: dict[str, Any] = {"relevant_ids": set(), "community_ids": set(), "competitors": []}
    for start in range(0, len(rows), CLASSIFY_BATCH):
        batch = rows[start:start + CLASSIFY_BATCH]
        payload = {"topic": topic, "segment": segment, "problem": problem, "rows": batch}
        try:
            reply = call_agent(ctx, role=ROLE, task="classify_relevance", payload=payload, tier="fast",
                               max_tokens=1500, validate=_validate_relevance, action_type="ANALYZE_DATA",
                               description=f"Labelled relevance of {len(batch)} collected research rows")
        except LLMError:
            return None
        allowed = {r["id"] for r in batch}
        merged["relevant_ids"].update(i for i in reply["relevant_ids"] if i in allowed)
        merged["community_ids"].update(i for i in reply["community_ids"] if i in allowed)
        merged["competitors"] += [c for c in reply["competitors"] if c["id"] in allowed]
    return merged


# ---------------------------------------------------------------------------------------------- main entry
def _empty_stats() -> dict[str, Any]:
    return {"window_months": R.WINDOW_MONTHS, "independent_discussions": None, "discussions_by_source": {},
            "relevant_evidence_ids": [], "communities": [], "largest_community_members": None,
            "largest_community": None, "competitor_candidates": [], "github_repos": [], "wikipedia_pageviews": [],
            "world_bank": [], "rows_collected": 0, "relevance_checked": False, "sources_status": {}}


def run_desk_research(ctx, *, topic: str, segment: str, problem: str, extra_queries: list[str] | None = None,
                      max_queries: int = 6) -> ResearchResult:
    if not ctx.settings.research_enabled:
        return ResearchResult(coverage_notes=["research disabled (offline)"])

    notes: list[str] = []
    plan, plan_notes = plan_queries(ctx, topic=topic, segment=segment, problem=problem, max_queries=max_queries)
    notes += plan_notes
    queries = _ordered_queries(plan, list(extra_queries or []), max(1, max_queries))
    discussion_q = [q for fam, q in queries if fam in DISCUSSION_FAMILIES]
    product_q = [q for fam, q in queries if fam not in DISCUSSION_FAMILIES]
    if not discussion_q and product_q:
        discussion_q = product_q[:1]

    collected: dict[str, list[R.SourceResult]] = {}

    def keep(res: R.SourceResult) -> R.SourceResult:
        collected.setdefault(res.source, []).append(res)
        return res

    site = plan.get("stackexchange_site")
    cache_dir = ctx.settings.data_dir / "cache" / "research"
    with R.ResearchClient(timeout=ctx.settings.research_timeout, cache_dir=cache_dir,
                          transport=ctx.extra.get("research_transport"), now=ctx.extra.get("research_now")) as client:
        seen_subs: dict[str, int] = {}
        for query in discussion_q:
            keep(R.search_hacker_news(client, query, kind="story"))
            keep(R.search_hacker_news(client, query, kind="comment"))
            res = keep(R.search_reddit(client, query))
            for name, count in (res.meta.get("subreddits") or {}).items():
                seen_subs[name] = seen_subs.get(name, 0) + count
            if site:
                keep(R.search_stackexchange(client, query, site))
        for query in product_q:
            keep(R.search_hacker_news(client, query, kind="story"))
            keep(R.search_github(client, query))
        subs = list(plan.get("subreddits") or [])
        for name, _ in sorted(seen_subs.items(), key=lambda kv: -kv[1]):
            if len(subs) >= MAX_SUBREDDITS:
                break
            if name.lower() not in {s.lower() for s in subs}:
                subs.append(name)
        for name in subs[:MAX_SUBREDDITS]:
            keep(R.reddit_subreddit(client, name))
        if site:
            keep(R.stackexchange_site(client, site))
        wiki_topic = plan.get("wikipedia_topic") or topic
        if wiki_topic:
            found = keep(R.search_wikipedia(client, wiki_topic))
            for article in (found.meta.get("articles") or [])[:1]:
                keep(R.wikipedia_pageviews(client, article))
        if plan.get("country_iso2"):
            for code in R.WORLD_BANK_INDICATORS:
                keep(R.world_bank(client, plan["country_iso2"], code))

    # --- store rows in the ledger and log one entry per source
    meta_by_id: dict[str, dict[str, Any]] = {}
    evidence_ids: list[str] = []
    source_urls: list[str] = []
    stats = _empty_stats()
    communities_raw: list[tuple[str, dict[str, Any]]] = []
    for source, results in collected.items():
        ids: list[str] = []
        errors = list(dict.fromkeys(r.error for r in results if r.error))
        ok_calls = sum(1 for r in results if not r.error)
        for res in results:
            for row in res.rows:
                ev = ctx.ledger.add(row)
                if ev.evidence_id not in meta_by_id:
                    kind = "discussion"
                    if row.get("unit") in ("subscribers", "registered users"):
                        kind = "community"
                    elif source == "github":
                        kind = "repo"
                    elif source in ("wikipedia", "world_bank"):
                        kind = "statistic"
                    meta_by_id[ev.evidence_id] = {"source": source, "kind": kind, "row": ev}
                    evidence_ids.append(ev.evidence_id)
                ids.append(ev.evidence_id)
                if ev.url and ev.url not in source_urls:
                    source_urls.append(ev.url)
            if res.meta.get("community"):
                rows_ids = [ctx.ledger.add(r).evidence_id for r in res.rows]
                if rows_ids:
                    communities_raw.append((rows_ids[0], res.meta["community"]))
        unique_ids = list(dict.fromkeys(ids))
        row_urls = list(dict.fromkeys(meta_by_id[i]["row"].url for i in unique_ids if meta_by_id[i]["row"].url))
        api_urls = list(dict.fromkeys(u for r in results for u in r.urls))
        status = "ok" if ok_calls else ("unavailable" if errors else "no calls")
        if ok_calls and errors:
            status = "partial"
        stats["sources_status"][source] = status
        ctx.log.append(agent="researcher", action=SOURCE_ACTIONS.get(source, f"search_{source}"),
                       action_type="RESEARCH", phase=ctx.phase, step=ctx.step_id,
                       description=(f"Searched {SOURCE_LABELS.get(source, source)}: {len(results)} request(s), "
                                    f"{len(unique_ids)} evidence row(s)" + (f"; issues: {'; '.join(errors)[:300]}"
                                                                            if errors else "")),
                       sources=(row_urls + api_urls)[:LOG_SOURCE_LIMIT], model=None, cost=0, approved_by=None,
                       result={"rows": len(unique_ids), "evidence_ids": unique_ids[:60], "errors": errors,
                               "status": status})
        if source == "reddit" and errors and not ok_calls:
            notes.append("reddit unavailable (blocked or rate-limited); Reddit discussions and subscriber counts "
                         "were not checked")
        elif errors:
            notes += [f"{SOURCE_LABELS.get(source, source)}: {e}" for e in errors[:3]]
        if ok_calls and not unique_ids and source not in ("wikipedia",):
            notes.append(f"{SOURCE_LABELS.get(source, source)} returned no results for these queries "
                         "(coverage gap, not evidence of absent demand)")

    stats["rows_collected"] = len(evidence_ids)
    now = (ctx.extra.get("research_now") or time.time)()

    # --- relevance check by the model (rows it may label: discussions, communities, repos)
    discussion_ids = [i for i in evidence_ids if meta_by_id[i]["kind"] == "discussion"
                      and R.within_window(meta_by_id[i]["row"].observed_at, now)]
    stale = [i for i in evidence_ids if meta_by_id[i]["kind"] == "discussion" and i not in discussion_ids]
    if stale:
        notes.append(f"{len(stale)} discussion row(s) were older than {R.WINDOW_MONTHS} months or undated "
                     "and were not counted")
    community_ids = [i for i in evidence_ids if meta_by_id[i]["kind"] == "community"]
    repo_ids = [i for i in evidence_ids if meta_by_id[i]["kind"] == "repo"]
    to_check = discussion_ids + community_ids + repo_ids
    truncated = len(to_check) > MAX_CLASSIFY_ROWS
    if truncated:
        keep_d = discussion_ids[:max(0, MAX_CLASSIFY_ROWS - len(community_ids) - min(len(repo_ids), 10))]
        to_check = keep_d + community_ids + repo_ids[:10]
        notes.append(f"only {len(keep_d)} of {len(discussion_ids)} discussion rows were checked for relevance; "
                     "the discussion count is a lower bound")
    rows_payload = []
    for evidence_id in to_check[:MAX_CLASSIFY_ROWS]:
        row = meta_by_id[evidence_id]["row"]
        rows_payload.append({"id": evidence_id, "source": row.source_type, "kind": meta_by_id[evidence_id]["kind"],
                             "title": row.title[:160], "excerpt": row.excerpt[:280], "observed_at": row.observed_at,
                             "value": row.value, "unit": row.unit})
    labels = {"relevant_ids": set(), "community_ids": set(), "competitors": []}
    relevance_ok = True
    if rows_payload:
        result = classify_relevance(ctx, topic=topic, segment=segment, problem=problem, rows=rows_payload)
        if result is None:
            relevance_ok = False
            notes.append("relevance check unavailable (model failed); no discussion or community was counted")
        else:
            labels = result
    stats["relevance_checked"] = relevance_ok and bool(rows_payload)

    # --- independent discussions (24 months, counted by independence group)
    discussion_sources_ok = any(stats["sources_status"].get(s) in ("ok", "partial") for s in R.DISCUSSION_SOURCES)
    relevant = [i for i in discussion_ids if i in labels["relevant_ids"]]
    stats["relevant_evidence_ids"] = relevant
    if relevance_ok and discussion_sources_ok:
        groups: dict[str, str] = {}
        for evidence_id in relevant:
            row = meta_by_id[evidence_id]["row"]
            groups.setdefault(row.independence_group or row.url or evidence_id, meta_by_id[evidence_id]["source"])
        by_source: dict[str, int] = {}
        for source in groups.values():
            by_source[source] = by_source.get(source, 0) + 1
        stats["independent_discussions"] = len(groups)
        stats["discussions_by_source"] = by_source
        stats["independence_groups"] = sorted(groups)
    elif not discussion_sources_ok:
        notes.append("no discussion source (Hacker News, Reddit, Stack Exchange) answered; discussions not counted")

    # --- communities (published audience, only those the relevance check confirmed)
    communities = []
    for evidence_id, info in communities_raw:
        verified = relevance_ok and evidence_id in labels["community_ids"]
        communities.append({**info, "evidence_id": evidence_id, "verified": verified})
    stats["communities"] = communities
    verified = [c for c in communities if c["verified"]]
    if verified:
        largest = max(verified, key=lambda c: c["members"])
        stats["largest_community_members"] = int(largest["members"])
        stats["largest_community"] = largest
    elif communities:
        notes.append("community sizes were found but none was confirmed as a place where the segment gathers")

    # --- competitor candidates and repos (only from collected rows)
    candidates, seen_names = [], set()
    for item in labels["competitors"]:
        meta = meta_by_id.get(item["id"])
        if not meta:
            continue
        row = meta["row"]
        name = item["name"]
        haystack = f"{row.title} {row.excerpt}".lower()
        if not name or name.lower() not in haystack:
            name = row.title[:80]
        if name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        candidates.append({"name": name, "url": row.url, "evidence_id": item["id"], "source": row.source_type})
    stats["competitor_candidates"] = candidates
    flagged = labels["relevant_ids"] | {c["evidence_id"] for c in candidates}
    stats["github_repos"] = [{"name": meta_by_id[i]["row"].title, "url": meta_by_id[i]["row"].url,
                              "stars": meta_by_id[i]["row"].value, "evidence_id": i, "relevant": i in flagged}
                             for i in repo_ids]
    for source, results in collected.items():
        for res in results:
            if res.meta.get("pageviews") and res.rows:
                stats["wikipedia_pageviews"].append({**res.meta["pageviews"],
                                                     "evidence_id": ctx.ledger.add(res.rows[0]).evidence_id})
            if res.meta.get("indicator") and res.rows:
                stats["world_bank"].append({**res.meta["indicator"],
                                            "evidence_id": ctx.ledger.add(res.rows[0]).evidence_id})

    return ResearchResult(queries=[q for _, q in queries], evidence_ids=evidence_ids, sources=source_urls,
                          stats=stats, coverage_notes=list(dict.fromkeys(notes)))
