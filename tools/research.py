"""Free, no-key public sources for desk research.

Each search function returns a SourceResult: evidence rows (dicts for
evidence.Evidence, provenance SOURCE_FACT), the API URLs consulted, and an
error note when the source failed. Nothing here raises on network problems:
a failed or blocked source is recorded as a coverage gap, never as "no demand".

Sources: Hacker News (Algolia), Reddit public JSON (often blocked), Stack
Exchange, GitHub repository search, Wikipedia search and pageviews, World Bank.
Responses are cached on disk for 24 hours, keyed by the full request URL.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

USER_AGENT = "venture-validator-research/0.1 (open-source prototype)"
WINDOW_MONTHS = 24
CACHE_TTL_SECONDS = 24 * 3600
EXCERPT_LIMIT = 600
AVG_MONTH_SECONDS = 30.4375 * 86400
DISCUSSION_SOURCES = ("hacker_news", "reddit", "stackexchange")

HN_SEARCH = "https://hn.algolia.com/api/v1/search"
HN_ITEM = "https://news.ycombinator.com/item?id={id}"
REDDIT_SEARCH = "https://www.reddit.com/search.json"
REDDIT_ABOUT = "https://www.reddit.com/r/{name}/about.json"
SE_SEARCH = "https://api.stackexchange.com/2.3/search/advanced"
SE_INFO = "https://api.stackexchange.com/2.3/info"
GITHUB_SEARCH = "https://api.github.com/search/repositories"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_PAGE = "https://en.wikipedia.org/wiki/{title}"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
             "{article}/monthly/{start}/{end}")
WORLD_BANK = "https://api.worldbank.org/v2/country/{iso2}/indicator/{code}"
WORLD_BANK_INDICATORS = {"SP.POP.TOTL": "people", "IT.NET.USER.ZS": "% of population"}

# Stack Exchange sites that do not live under <site>.stackexchange.com
SE_DOMAINS = {"stackoverflow": "stackoverflow.com", "superuser": "superuser.com", "serverfault": "serverfault.com",
              "askubuntu": "askubuntu.com", "mathoverflow": "mathoverflow.net"}

SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")
SE_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,40}$")
ISO2_RE = re.compile(r"^[A-Z]{2}$")


@dataclass
class SourceResult:
    source: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)          # API URLs consulted
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------- helpers
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean_text(text: Any) -> str:
    """Strip HTML tags and entities and collapse whitespace."""
    if not text:
        return ""
    cleaned = html.unescape(_TAG.sub(" ", str(text)))
    return _SPACE.sub(" ", cleaned).strip()


def iso_from_epoch(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def window_start(now: float, months: int = WINDOW_MONTHS) -> int:
    """Start of the look-back window, floored to the day so cache keys stay stable within a day."""
    since = now - months * AVG_MONTH_SECONDS
    return int(since // 86400 * 86400)


def within_window(observed_at: str | None, now: float, months: int = WINDOW_MONTHS) -> bool:
    parsed = parse_iso(observed_at)
    if parsed is None:
        return False
    return parsed.timestamp() >= window_start(now, months)


def se_site_url(site: str) -> str:
    return f"https://{SE_DOMAINS.get(site, f'{site}.stackexchange.com')}"


def _row(source_type: str, *, url: str | None, title: str, text: str, query: str, method: str, group: str,
         observed_at: str | None = None, value: float | None = None, unit: str = "",
         limitations: str = "", population: str = "") -> dict[str, Any]:
    return {"provenance": "SOURCE_FACT", "source_type": source_type, "url": url, "title": clean_text(title)[:300],
            "excerpt": clean_text(text)[:EXCERPT_LIMIT], "value": value, "unit": unit, "observed_at": observed_at,
            "query": query, "method": method, "independence_group": group, "limitations": limitations,
            "population": population}


# ---------------------------------------------------------------------------------------------- client
class ResearchClient:
    """httpx client with a 24h on-disk cache, a generic User-Agent and no retries.

    A source that answers 403/429, a non-JSON page, a server error or a network
    error is marked unavailable for the rest of this session (no endless retries).
    A Stack Exchange "backoff" field is obeyed by skipping that source until it expires.
    """

    def __init__(self, *, timeout: float = 20.0, cache_dir: Path | str | None = None,
                 transport: httpx.BaseTransport | None = None, now: Callable[[], float] | None = None,
                 cache_ttl: float = CACHE_TTL_SECONDS):
        self._client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True,
                                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.now = now or time.time
        self.cache_ttl = cache_ttl
        self.unavailable: dict[str, str] = {}
        self.backoff_until: dict[str, float] = {}
        self.http_calls = 0
        self.cache_hits = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ResearchClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # --- cache
    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ".json")

    def _read_cache(self, url: str) -> tuple[bool, Any]:
        path = self._cache_path(url)
        if path is None or not path.exists():
            return False, None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False, None
        if entry.get("url") != url or self.now() - float(entry.get("fetched_at") or 0) > self.cache_ttl:
            return False, None
        return True, entry.get("data")

    def _write_cache(self, url: str, data: Any) -> None:
        path = self._cache_path(url)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"url": url, "fetched_at": self.now(), "data": data}), encoding="utf-8")
        except OSError:
            pass  # a cache write failure must never stop research

    # --- requests
    def get_json(self, source: str, url: str, params: dict[str, Any] | None = None) -> tuple[Any, str | None, str]:
        """Return (data, error, full_url). Never raises."""
        try:
            full = str(httpx.URL(url, params=params)) if params else url
        except Exception as exc:  # noqa: BLE001
            return None, f"{source}: invalid request ({type(exc).__name__})", url
        hit, cached = self._read_cache(full)
        if hit:
            self.cache_hits += 1
            return cached, None, full
        if source in self.unavailable:
            return None, f"{source} unavailable ({self.unavailable[source]}); call skipped", full
        until = self.backoff_until.get(source)
        if until and self.now() < until:
            return None, f"{source} asked clients to back off; call skipped", full
        self.http_calls += 1
        try:
            resp = self._client.get(full)
        except Exception as exc:  # noqa: BLE001 - network errors are coverage gaps, never crashes
            self.unavailable[source] = type(exc).__name__
            return None, f"{source} request failed ({type(exc).__name__})", full
        if resp.status_code in (403, 429):
            self.unavailable[source] = f"HTTP {resp.status_code}"
            return None, f"{source} unavailable (HTTP {resp.status_code}: blocked or rate-limited)", full
        if resp.status_code == 404:
            return None, f"{source} returned HTTP 404 (not found)", full
        if resp.status_code >= 400:
            self.unavailable[source] = f"HTTP {resp.status_code}"
            return None, f"{source} returned HTTP {resp.status_code}", full
        try:
            data = resp.json()
        except ValueError:
            self.unavailable[source] = "non-JSON response"
            return None, f"{source} returned a non-JSON page (likely blocked)", full
        if isinstance(data, dict) and data.get("backoff"):
            try:
                self.backoff_until[source] = self.now() + float(data["backoff"])
            except (TypeError, ValueError):
                pass
        self._write_cache(full, data)
        return data, None, full


# ---------------------------------------------------------------------------------------------- sources
def search_hacker_news(client: ResearchClient, query: str, *, kind: str = "story", limit: int = 10,
                       window_months: int = WINDOW_MONTHS) -> SourceResult:
    kind = "comment" if kind == "comment" else "story"
    result = SourceResult("hacker_news")
    params = {"query": query, "tags": kind, "hitsPerPage": limit,
              "numericFilters": f"created_at_i>{window_start(client.now(), window_months)}"}
    data, error, full = client.get_json("hacker_news", HN_SEARCH, params)
    result.urls.append(full)
    if error or not isinstance(data, dict):
        result.error = error or "hacker_news: unexpected response"
        return result
    method = f"Hacker News Algolia search ({kind}s, last {window_months} months)"
    for hit in data.get("hits") or []:
        object_id = hit.get("objectID")
        if not object_id:
            continue
        if kind == "story":
            title = hit.get("title") or ""
            text = hit.get("story_text") or title
            group = f"hn:{object_id}"
        else:
            title = f"Comment on: {hit.get('story_title') or 'HN story'}"
            text = hit.get("comment_text") or ""
            group = f"hn:{hit.get('story_id') or object_id}"
        result.rows.append(_row(
            "hacker_news", url=HN_ITEM.format(id=object_id), title=title, text=text, query=query, method=method,
            group=group, observed_at=hit.get("created_at") or iso_from_epoch(hit.get("created_at_i")),
            limitations="Keyword match on a developer/founder-heavy forum; relevance is checked separately; "
                        "a story and its comments count once."))
    return result


def search_reddit(client: ResearchClient, query: str, *, limit: int = 15) -> SourceResult:
    result = SourceResult("reddit")
    params = {"q": query, "sort": "relevance", "t": "year", "limit": limit, "raw_json": 1}
    data, error, full = client.get_json("reddit", REDDIT_SEARCH, params)
    result.urls.append(full)
    if error or not isinstance(data, dict):
        result.error = error or "reddit: unexpected response"
        return result
    subreddits: dict[str, int] = {}
    for child in ((data.get("data") or {}).get("children") or []):
        post = child.get("data") or {}
        post_id, permalink = post.get("id"), post.get("permalink")
        if not post_id or not permalink:
            continue
        sub = post.get("subreddit") or ""
        if sub:
            subreddits[sub] = subreddits.get(sub, 0) + 1
        result.rows.append(_row(
            "reddit", url=f"https://www.reddit.com{permalink}", title=f"r/{sub}: {post.get('title') or ''}",
            text=post.get("selftext") or post.get("title") or "", query=query,
            method="Reddit public search JSON (posts, last 12 months)", group=f"reddit:{post_id}",
            observed_at=iso_from_epoch(post.get("created_utc")),
            limitations="Reddit search relevance is keyword-based; relevance is checked separately."))
    result.meta["subreddits"] = subreddits
    return result


def reddit_subreddit(client: ResearchClient, name: str) -> SourceResult:
    result = SourceResult("reddit")
    name = (name or "").strip().removeprefix("r/").removeprefix("/r/")
    if not SUBREDDIT_RE.match(name):
        result.error = f"reddit: invalid subreddit name {name!r}"
        return result
    data, error, full = client.get_json("reddit", REDDIT_ABOUT.format(name=name))
    result.urls.append(full)
    about = (data or {}).get("data") if isinstance(data, dict) else None
    if error or not isinstance(about, dict):
        result.error = error or f"reddit: no community data for r/{name}"
        return result
    members = about.get("subscribers")
    if not isinstance(members, (int, float)):
        result.error = f"reddit: subscriber count not published for r/{name}"
        return result
    display = about.get("display_name") or name
    url = f"https://www.reddit.com/r/{display}/"
    result.rows.append(_row(
        "reddit", url=url, title=f"r/{display} community", value=float(members), unit="subscribers",
        text=about.get("public_description") or about.get("title") or "", query=name,
        method="Reddit public about.json (subscriber count)", group=f"reddit-community:{display.lower()}",
        limitations="Published audience (subscribers), not eligible reach; includes inactive accounts."))
    result.meta["community"] = {"name": f"r/{display}", "url": url, "members": int(members), "source": "reddit"}
    return result


def search_stackexchange(client: ResearchClient, query: str, site: str, *, limit: int = 10,
                         window_months: int = WINDOW_MONTHS) -> SourceResult:
    result = SourceResult("stackexchange")
    if not SE_SITE_RE.match(site or ""):
        result.error = f"stackexchange: invalid site {site!r}"
        return result
    params = {"q": query, "site": site, "order": "desc", "sort": "relevance", "pagesize": limit,
              "fromdate": window_start(client.now(), window_months), "filter": "withbody"}
    data, error, full = client.get_json("stackexchange", SE_SEARCH, params)
    result.urls.append(full)
    if error or not isinstance(data, dict):
        result.error = error or "stackexchange: unexpected response"
        return result
    if data.get("error_id"):
        result.error = f"stackexchange error {data.get('error_name')}: {data.get('error_message')}"
        return result
    for item in data.get("items") or []:
        question_id, link = item.get("question_id"), item.get("link")
        if not question_id or not link:
            continue
        tags = ", ".join(item.get("tags") or [])
        result.rows.append(_row(
            "stackexchange", url=link, title=item.get("title") or "", text=item.get("body") or item.get("title") or "",
            query=query, method=f"Stack Exchange search on {site} (questions, last {window_months} months)",
            group=f"stackexchange:{site}:{question_id}", observed_at=iso_from_epoch(item.get("creation_date")),
            limitations=f"Tags: {tags}. Keyword match; relevance is checked separately."))
    return result


def stackexchange_site(client: ResearchClient, site: str) -> SourceResult:
    result = SourceResult("stackexchange")
    if not SE_SITE_RE.match(site or ""):
        result.error = f"stackexchange: invalid site {site!r}"
        return result
    data, error, full = client.get_json("stackexchange", SE_INFO, {"site": site})
    result.urls.append(full)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    if error or not items:
        result.error = error or f"stackexchange: no site info for {site}"
        return result
    info = items[0]
    members = info.get("total_users")
    if not isinstance(members, (int, float)):
        result.error = f"stackexchange: user count not published for {site}"
        return result
    url = se_site_url(site)
    result.rows.append(_row(
        "stackexchange", url=url, title=f"{site} Stack Exchange site statistics", value=float(members),
        unit="registered users", query=site, method="Stack Exchange API /info (site statistics)",
        text=(f"{site} Stack Exchange: {int(members)} registered users, {info.get('total_questions')} questions, "
              f"{info.get('total_answers')} answers (API {full})"),
        group=f"stackexchange-community:{site}",
        limitations="Published audience (registered users), not eligible reach; includes inactive accounts."))
    result.meta["community"] = {"name": f"{site} Stack Exchange", "url": url, "members": int(members),
                                "source": "stackexchange"}
    return result


def search_github(client: ResearchClient, query: str, *, limit: int = 10) -> SourceResult:
    result = SourceResult("github")
    data, error, full = client.get_json("github", GITHUB_SEARCH,
                                        {"q": query, "sort": "stars", "order": "desc", "per_page": limit})
    result.urls.append(full)
    if error or not isinstance(data, dict):
        result.error = error or "github: unexpected response"
        return result
    for repo in data.get("items") or []:
        name, url = repo.get("full_name"), repo.get("html_url")
        if not name or not url:
            continue
        stars = repo.get("stargazers_count")
        result.rows.append(_row(
            "github", url=url, title=name, text=repo.get("description") or name, query=query,
            method="GitHub repository search (sorted by stars, unauthenticated)", group=f"github:{name.lower()}",
            observed_at=repo.get("pushed_at"), value=float(stars) if isinstance(stars, (int, float)) else None,
            unit="stars", limitations="Stars measure developer interest, not customer demand or revenue."))
    return result


def search_wikipedia(client: ResearchClient, query: str, *, limit: int = 3) -> SourceResult:
    """Find candidate Wikipedia articles (titles only; no evidence rows)."""
    result = SourceResult("wikipedia")
    data, error, full = client.get_json("wikipedia", WIKI_API, {"action": "query", "list": "search",
                                                               "srsearch": query, "format": "json",
                                                               "srlimit": limit})
    result.urls.append(full)
    if error or not isinstance(data, dict):
        result.error = error or "wikipedia: unexpected response"
        return result
    result.meta["articles"] = [h.get("title") for h in ((data.get("query") or {}).get("search") or [])
                               if h.get("title")]
    return result


def _add_months(day: datetime, months: int) -> datetime:
    index = day.year * 12 + (day.month - 1) + months
    return day.replace(year=index // 12, month=index % 12 + 1, day=1)


def wikipedia_pageviews(client: ResearchClient, article: str, *, months: int = 12) -> SourceResult:
    result = SourceResult("wikipedia")
    now = datetime.fromtimestamp(client.now(), tz=timezone.utc)
    end = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).replace(day=1)
    start = _add_months(end, -(months - 1))
    slug = quote((article or "").replace(" ", "_"), safe="")
    if not slug:
        result.error = "wikipedia: no article"
        return result
    url = PAGEVIEWS.format(article=slug, start=start.strftime("%Y%m%d00"), end=end.strftime("%Y%m%d00"))
    data, error, full = client.get_json("wikipedia", url)
    result.urls.append(full)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    if error or not items:
        result.error = error or f"wikipedia: no pageview data for {article}"
        return result
    views = [i.get("views") for i in items if isinstance(i.get("views"), (int, float))]
    if not views:
        result.error = f"wikipedia: no pageview data for {article}"
        return result
    avg = round(sum(views) / len(views), 1)
    page = WIKI_PAGE.format(title=slug)
    result.rows.append(_row(
        "wikipedia", url=full, title=f"Wikipedia pageviews: {article}", value=avg, unit="views/month (average)",
        text=(f"Average {avg:,.0f} monthly user pageviews of the English Wikipedia article '{article}' ({page}) "
              f"over {len(views)} months, {start:%Y-%m} to {end:%Y-%m}."),
        query=article, method="Wikimedia REST pageviews API (user agents, all access)", group=f"wikipedia:{slug}",
        observed_at=end.strftime("%Y-%m-%dT00:00:00Z"),
        limitations="Topic interest worldwide, not demand for a product or a count of buyers."))
    result.meta["pageviews"] = {"article": article, "monthly_avg": avg, "url": full, "months": len(views)}
    return result


def world_bank(client: ResearchClient, iso2: str, code: str) -> SourceResult:
    result = SourceResult("world_bank")
    iso2 = (iso2 or "").upper()
    if not ISO2_RE.match(iso2) or code not in WORLD_BANK_INDICATORS:
        result.error = f"world_bank: invalid request ({iso2!r}, {code!r})"
        return result
    data, error, full = client.get_json("world_bank", WORLD_BANK.format(iso2=iso2, code=code),
                                        {"format": "json", "mrnev": 1})
    result.urls.append(full)
    if error or not isinstance(data, list) or len(data) < 2 or not data[1]:
        result.error = error or f"world_bank: no data for {code} in {iso2}"
        return result
    point = data[1][0] or {}
    value = point.get("value")
    if not isinstance(value, (int, float)):
        result.error = f"world_bank: no value for {code} in {iso2}"
        return result
    name = (point.get("indicator") or {}).get("value") or code
    country = (point.get("country") or {}).get("value") or iso2
    year = str(point.get("date") or "")
    result.rows.append(_row(
        "world_bank", url=full, title=f"{name}, {country} ({year})", value=float(value),
        unit=WORLD_BANK_INDICATORS[code], text=f"World Bank indicator {code} for {country}: {value} in {year}.",
        query=f"{iso2}:{code}", method="World Bank Indicators API (most recent non-empty value)",
        group=f"worldbank:{iso2}:{code}", observed_at=f"{year}-12-31T00:00:00Z" if year.isdigit() else None,
        limitations="Country-wide figure; not a count of the target segment.", population=country))
    result.meta["indicator"] = {"indicator": code, "name": name, "country": country, "value": value, "year": year,
                                "url": full}
    return result
