"""Phase 5 Launch: store page (5.1, gate A), launch posts (5.2, gate A) and mocked delivery (5.3, gate T + E).

Nothing here takes money or contacts anyone. The store page is published to
the MOCKED local site after founder approval; it shows a proposed future
price and creates no-charge mock orders only. Launch posts are drafts the
founder posts from their own account; approval puts them in the local outbox.
5.3 runs the sale-to-cash test suite on fixture data (excluded from analytics)
and, separately, reads the real first-party store events for the demand side.
"""
from __future__ import annotations

import re
import shutil
from typing import Any

from agents import launch_marketer
from agents.base import as_float
from evidence import Claim, Evidence
from gates import INVALID_DATA, READY, WAITING_FOR_DATA, Contract, Criterion, wilson_interval
from logbook import utc_now
from phases.base import DataField, Observation, StepHandler, StepOutput
from phases.validate import (as_count, beacon_script, compact, criterion_target, eligible_events, esc, faq_html, iso,
                             md_cell, page_html, pct1, window_info)
from store import slugify

STORE_LABEL = "MOCKED store: no payment is taken. Requesting access creates a no-charge mock order."
STORE_CTA = "Request access (no charge)"
ORDER_CONSENT = ("I agree that the founder may email me about this access request and this product. "
                 "No payment is taken and no card details are asked for.")
POLICY_NOTE = "Policies are drafts, not legal advice, and must be reviewed by a qualified lawyer before real use."
POST_HEADER = "DRAFT for the founder to post from their own account"
LAUNCH_WINDOW_DAYS = 14


def product_identity(ctx) -> tuple[str, str]:
    name = (ctx.prior("5.1").get("product_name") or ctx.prior("2.1").get("concept_name") or ctx.concept().get("name")
            or ctx.run.title)
    return name, slugify(name, max_len=40)


def founder_identity(ctx) -> str:
    """The founder's real background, from the brief's why_you (the only identity posts may speak from)."""
    return str((ctx.brief or {}).get("why_you") or "").strip()


# ------------------------------------------------------------------------------- impersonation check (posts)
_STOP = {"with", "from", "that", "this", "their", "they", "them", "have", "more", "than", "into", "over", "under",
         "about", "who", "whose", "which", "small", "large", "many", "most", "some", "other", "people", "users",
         "teams", "team", "owners", "fixture", "segment", "based", "early", "stage", "active", "clients", "client"}
_IDENTITY_CLAIM = re.compile(
    r"\b(?:i['’]?m|i\s+am|i['’]?ve\s+been|i\s+have\s+been|i\s+work\s+as|i\s+was|as)\s+(?:also\s+)?"
    r"(?:a|an|one\s+of\s+the)\s+((?:[a-z][\w-]*\s+){0,3}[a-z][\w-]*)", re.I)
_GENERIC_CLAIM = re.compile(r"\b(?:as\s+a\s+fellow|fellow\s+[a-z][\w-]*|like\s+(?:many\s+of\s+)?you,?\s+i\b|"
                            r"one\s+of\s+you\b|i['’]?m\s+one\s+of\s+you)", re.I)
_FREQUENCY_CLAIM = re.compile(
    r"\b(?:comes?\s+up|happens?|i\s+(?:keep\s+)?see(?:ing)?\s+(?:this|it))\b[^.!?\n]{0,40}?"
    r"\b(?:all\s+the\s+time|constantly|often|a\s+lot|every\s+(?:day|week|month)|daily|weekly|regularly|"
    r"again\s+and\s+again)\b", re.I)
_EVIDENCE_ID = re.compile(r"\bE-\d{3,}\b")


def _words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z][a-z-]{2,}", (text or "").lower()):
        out.add(w)
        out.add(w[:-1] if w.endswith("s") else w)
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def identity_violations(text: str, segment: str, why_you: str) -> list[dict[str, str]]:
    """Sentences that claim the founder belongs to the customer segment (or claim a problem's frequency without an
    evidence id), when the brief's why_you does not say so. Deterministic: no model involved."""
    seg = {w for w in _words(segment) if len(w) >= 4 and w not in _STOP}
    mine = _words(why_you)
    found: list[dict[str, str]] = []
    for sentence in _sentences(text):
        reason = ""
        first_person = re.search(r"\b(?:i|i['’]m|my|me|myself)\b", sentence, re.I)
        for match in _IDENTITY_CLAIM.finditer(sentence):
            if match.group(0).lower().startswith("as") and not first_person:
                continue   # "built as a tool for designers" describes the product, not the founder
            phrase = re.split(r"\b(?:for|who|with|that|to|and|in|on|at|of|like)\b", match.group(1), 1, flags=re.I)[0]
            claimed = {w for w in _words(phrase) if w in seg}
            if claimed and not claimed <= mine:
                reason = f"claims the founder is one of the customers ('{match.group(0)}')"
                break
        if not reason:
            generic = _GENERIC_CLAIM.search(sentence)
            if generic:
                claimed = {w for w in _words(generic.group(0)) if w in seg}
                if not claimed or not claimed <= mine:
                    reason = f"claims shared identity with the audience ('{generic.group(0)}')"
        if not reason and _FREQUENCY_CLAIM.search(sentence) and not _EVIDENCE_ID.search(sentence):
            reason = "claims how often the problem comes up without a sourced evidence id"
        if reason:
            found.append({"sentence": sentence, "reason": reason})
    return found


def drop_sentences(text: str, sentences: list[str]) -> str:
    for sentence in sentences:
        text = text.replace(sentence, "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def recommended_package(pricing: dict[str, Any]) -> dict[str, Any] | None:
    packages = [p for p in (pricing.get("packages") or []) if isinstance(p, dict)]
    rec = pricing.get("recommended_package_id")
    chosen = next((p for p in packages if rec is not None and str(p.get("id")) == str(rec)), None)
    return chosen or (packages[0] if packages else None)


# ---------------------------------------------------------------------------------------------- 5.1 Store page
class StorePage(StepHandler):
    def generate(self, ctx) -> StepOutput:
        rid = ctx.run_id
        canvas = ctx.prior("2.1")
        pricing = ctx.prior("4.1")
        package = recommended_package(pricing)
        price = as_float(package.get("price"), None) if package else None
        currency = str((package or {}).get("currency") or pricing.get("currency") or "").strip()
        billing = str((package or {}).get("billing") or "").strip()
        package_id = str((package or {}).get("id") or "default").strip()[:60]
        name = canvas.get("concept_name") or ctx.concept().get("name") or ctx.run.title
        product_id = slugify(name, max_len=40)
        price_text = self.price_text(price, currency, billing)

        payload = {
            "product_name": name, "concept": ctx.concept(), "uvp": canvas.get("uvp"), "segment": canvas.get("segment"),
            "problem": canvas.get("problem"),
            "founder_identity": founder_identity(ctx) or "not stated in the brief",
            "mvp_scope": compact(ctx.prior("3.1"), 2000), "build": compact(ctx.prior("3.2"), 1500),
            "docs": compact(ctx.prior("3.3"), 1500),
            "price_shown_by_code": price_text,
            "fixed_by_code": {"label": STORE_LABEL, "cta": STORE_CTA, "policies": "links to draft terms, privacy, refund"},
            "feedback": ctx.feedback,
        }
        copy = launch_marketer.store_page(ctx, payload)
        faq = list(copy["faq"])
        if not any("pay" in f["question"].lower() or "charge" in f["question"].lower() for f in faq):
            faq.append({"question": "Will I be charged?",
                        "answer": "No. This store takes no payment. Requesting access creates a no-charge mock order "
                                  "and the founder follows up by email."})
        copy["faq"] = faq[:6]
        page, visible = self.render(rid, name, product_id, package_id, price_text, copy)
        questions = list(copy["questions"])
        if price is None:
            questions.insert(0, "Step 4.1 has no recommended package with a price: the page says the price is not set. "
                                "Do you want to set one in 4.1 first?")
        claims = []
        if price is not None:
            claims.append(Claim(text=(f"Proposed future price for package '{(package or {}).get('name') or package_id}': "
                                      f"{price:,.2f} {currency}".rstrip() + (f" ({billing})" if billing else "")),
                                label="ASSUMPTION", basis="recommended package from step 4.1; no payment has validated it"))
        data = {"product_name": name, "product_id": product_id, "package_id": package_id, "price": price,
                "currency": currency, "billing": billing, "price_label": "Proposed future price",
                "store_path": f"/site/{rid}/store.html", "order_action": f"/p/{rid}/order",
                "copy": copy, "outward": [{"kind": "publish", "item_id": "store-page", "file": "store.html",
                                           "when": "on_approve", "target_name": "store.html"}]}
        markdown = self._markdown(rid, name, product_id, package_id, price_text, copy)
        summary = copy["summary"] or ("Wrote the store page with a proposed future price and a no-charge access "
                                      "request; approving it publishes the page to the MOCKED local site only.")
        return StepOutput(title=str(name), markdown=markdown, data=data, files={"store.html": page},
                          claims=claims, summary=summary, questions=questions[:3], marketing_text=visible)

    @staticmethod
    def price_text(price: float | None, currency: str, billing: str) -> str:
        if price is None:
            return "Proposed future price: not set yet"
        unit = f" {currency}" if currency else ""
        period = f" ({billing})" if billing else ""
        return f"Proposed future price: {price:,.2f}{unit}{period}. Not charged here."

    @staticmethod
    def render(rid: str, name: str, product_id: str, package_id: str, price_text: str,
               copy: dict[str, Any]) -> tuple[str, str]:
        headline = copy.get("tagline") or copy["outcome"]
        not_included = (f"<p><strong>Not included yet:</strong> {esc(copy['not_included'])}</p>"
                        if copy.get("not_included") else "")
        demo = copy.get("demo_description") or ""
        policies = "".join(f'<li><a href="/site/{esc(rid)}/{f}.html">{label} (draft)</a></li>'
                           for f, label in (("terms", "Terms"), ("privacy", "Privacy policy"), ("refund", "Refund policy")))
        body = f"""<header>
<p class="eyebrow">{esc(name)}</p>
<h1>{esc(headline)}</h1>
</header>
<p class="notice"><strong>{esc(STORE_LABEL)}</strong></p>
<section aria-labelledby="who-h"><h2 id="who-h">Who it is for</h2><p>{esc(copy['who_it_serves'])}</p></section>
<section aria-labelledby="outcome-h"><h2 id="outcome-h">The outcome</h2><p>{esc(copy['outcome'])}</p></section>
<section aria-labelledby="now-h"><h2 id="now-h">What is available now</h2><p>{esc(copy['available_now'])}</p>{not_included}</section>
{f'<section aria-labelledby="demo-h"><h2 id="demo-h">Demo</h2><p>{esc(demo)}</p></section>' if demo else ''}
<section aria-labelledby="price-h"><h2 id="price-h">Price</h2><p>{esc(price_text)}</p></section>
<section aria-labelledby="request-h">
<h2 id="request-h">{esc(STORE_CTA)}</h2>
<p class="notice"><strong>{esc(STORE_LABEL)}</strong></p>
<form id="order-form" method="post" action="/p/{esc(rid)}/order">
<input type="hidden" name="product_id" value="{esc(product_id)}">
<input type="hidden" name="package_id" value="{esc(package_id)}">
<input type="hidden" id="source" name="source" value="">
<input type="hidden" id="visitor_id" name="visitor_id" value="">
<label for="email">Email address (required)</label>
<input id="email" name="email" type="email" required autocomplete="email">
<div class="consent"><input id="consent" name="consent" type="checkbox" value="yes" required>
<label for="consent">{esc(ORDER_CONSENT)}</label></div>
<button type="submit">{esc(STORE_CTA)}</button>
</form>
</section>
{faq_html(copy['faq'])}
<section aria-labelledby="policies-h"><h2 id="policies-h">Policies</h2><ul>{policies}</ul><p>{esc(POLICY_NOTE)}</p></section>"""
        script = beacon_script(f"/p/{rid}/event", "store", cta_form_id="order-form")
        page = page_html(title=f"{name}: request access", banner=STORE_LABEL, body=body, script=script,
                         footer=esc("Served from the local MOCKED site by Venture Validator. No payment is taken."))
        visible = "\n".join([STORE_LABEL, name, headline, copy["who_it_serves"], copy["outcome"], copy["available_now"],
                             copy.get("not_included", ""), demo, price_text, STORE_CTA, ORDER_CONSENT, POLICY_NOTE,
                             *[f"{f['question']}\n{f['answer']}" for f in copy["faq"]]])
        return page, visible

    @staticmethod
    def _markdown(rid, name, product_id, package_id, price_text, copy) -> str:
        lines = ["## Store page", "", f"**{STORE_LABEL}**", "",
                 "| Section | Copy |", "|---|---|",
                 f"| Product | {md_cell(name)} (`{product_id}`, package `{package_id}`) |",
                 f"| Headline | {md_cell(copy.get('tagline') or copy['outcome'])} |",
                 f"| Who it is for | {md_cell(copy['who_it_serves'], 600)} |",
                 f"| The outcome | {md_cell(copy['outcome'], 600)} |",
                 f"| Available now | {md_cell(copy['available_now'], 700)} |",
                 f"| Not included yet | {md_cell(copy.get('not_included'), 500)} |",
                 f"| Demo | {md_cell(copy.get('demo_description'), 700)} |",
                 f"| Price | {md_cell(price_text)} (from step 4.1; labelled as a proposed future price) |",
                 f"| Call to action | {STORE_CTA}: creates a no-charge mock order via `/p/{rid}/order` |",
                 f"| Policies | `/site/{rid}/terms.html`, `privacy.html`, `refund.html` (drafts; lawyer review required) |",
                 "", "### FAQ", ""]
        lines += [f"- **{f['question']}** {f['answer']}" for f in copy["faq"]]
        lines += ["", "## Publishing (MOCKED)", "",
                  f"- Approving this step publishes `store.html` to the local MOCKED site at `/site/{rid}/store.html`. "
                  "Nothing is posted publicly and no payment provider is connected.",
                  "- The page is self-contained (inline CSS and script, no external resources). It sends a `page_view` "
                  "on load and a `cta_click` when the request form is submitted; the server records an `order_request`.",
                  "- Launch-readiness checks before sharing: the MOCKED label is visible before the form and repeated "
                  "next to it; the form requires an email and consent; policy links resolve once 4.2 drafts are "
                  "published; the page works on a phone-width screen.", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- 5.2 Launch posts
class LaunchPosts(StepHandler):
    def generate(self, ctx) -> StepOutput:
        rid = ctx.run_id
        canvas = ctx.prior("2.1")
        store = ctx.prior("5.1")
        name, product_id = product_identity(ctx)
        channels = [c for c in (canvas.get("channels") or []) if isinstance(c, dict) and c.get("id")]
        if not channels and not ctx.feedback:
            return StepOutput(
                title=str(name),
                markdown=("## Launch posts\n\nThe Lean Canvas (2.1) names no channels, so no post was drafted. "
                          "Reject this step with the 2-3 channels you want to launch in (for example a community, "
                          "a newsletter or a professional group) and the drafts will be written for them.\n"),
                data={"posts": [], "schedule": [], "outward": []},
                summary="No channels from the Lean Canvas: waiting for the founder to name the launch channels.",
                questions=["Which 2-3 channels will you post in? Reject this step with their names as feedback."])
        store_link = f"/site/{rid}/store.html"
        identity = founder_identity(ctx)
        segment_text = " ".join(str(x or "") for x in (canvas.get("segment"), (ctx.brief or {}).get("customer")))
        payload = {
            "product_name": name, "uvp": canvas.get("uvp"), "segment": canvas.get("segment"),
            "problem": canvas.get("problem"),
            "founder_identity": identity or "not stated in the brief: do not describe the founder's background",
            "store_page": {k: (store.get("copy") or {}).get(k) for k in ("who_it_serves", "outcome", "available_now",
                                                                       "not_included")},
            "price_label": StorePage.price_text(as_float(store.get("price"), None), str(store.get("currency") or ""),
                                                str(store.get("billing") or "")),
            "channels": [{"id": c["id"], "name": c.get("name"), "audience_rule": c.get("audience_rule"),
                          "url": c.get("url")} for c in channels],
            "launch_window_days": LAUNCH_WINDOW_DAYS,
            "fixed_by_code": {"owner": "the founder posts from their own account",
                              "link": "added by code with a per-channel utm_source",
                              "store_label": STORE_LABEL},
            "feedback": ctx.feedback,
        }
        reply = launch_marketer.launch_posts(ctx, payload)
        posts = self._match(channels, reply["posts"])
        posts, identity_notes = self._enforce_identity(ctx, payload, channels, posts, segment_text, identity)
        files, outward, texts, schedule = {}, [], [], []
        for post in posts:
            cid = post["channel_id"]
            post["link"] = f"{store_link}?utm_source={cid}"
            post["file"] = f"post_{cid}.md"
            content = self.post_file(post)
            files[post["file"]] = content
            texts.append(content)
            outward.append({"kind": "send", "item_id": f"post-{cid}", "file": post["file"], "when": "on_approve"})
            schedule.append({"day": post["day"], "channel_id": cid, "channel": post["channel_name"],
                             "format": post["format"], "timing": post["timing"], "owner": "founder", "file": post["file"]})
        schedule.sort(key=lambda s: (s["day"] or 99, s["channel_id"]))
        missing = [c["id"] for c in channels if c["id"] not in {p["channel_id"] for p in posts}]
        questions = list(reply["questions"])
        if missing:
            questions.insert(0, f"No draft came back for: {', '.join(missing)}. Reject with feedback to get them, or "
                                "approve without them.")
        data = {"product_id": product_id, "posts": posts, "schedule": schedule, "outward": outward,
                "missing_channels": missing, "identity_check": identity_notes}
        markdown = self._markdown(posts, schedule, missing, identity_notes)
        summary = reply["summary"] or (f"Drafted {len(posts)} launch post(s), one per channel, for you to post from "
                                       "your own account; approving puts them in the local outbox only.")
        return StepOutput(title=str(name), markdown=markdown, data=data, files=files, summary=summary,
                          questions=questions[:3], marketing_text="\n\n".join(texts))

    def _enforce_identity(self, ctx, payload, channels, posts, segment_text: str,
                          identity: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Reject posts that speak as a customer instead of as the founder: regenerate once with feedback, then drop
        any sentence that still fails and note it."""
        bad = {p["channel_id"]: identity_violations(p["text"], segment_text, identity) for p in posts}
        bad = {cid: v for cid, v in bad.items() if v}
        notes: list[str] = []
        if not bad:
            return posts, notes
        problems = "; ".join(f"[{cid}] \"{v['sentence'][:160]}\": {v['reason']}" for cid, vs in bad.items() for v in vs)
        retry_payload = {**payload, "feedback": (
            f"{payload.get('feedback') or ''}\nIDENTITY CHECK FAILED. Speak only as the founder, whose background "
            f"is: {identity or 'not stated'}. Do not claim to be a member of the audience, do not say 'as a fellow' "
            f"or 'like you, I', and do not claim how often the problem comes up. Rewrite: {problems}").strip()}
        try:
            retry = self._match(channels, launch_marketer.launch_posts(ctx, retry_payload)["posts"])
        except Exception:  # noqa: BLE001 - a failed retry falls back to dropping the offending sentences
            retry = []
        retry_by_id = {p["channel_id"]: p for p in retry}
        out = []
        for post in posts:
            cid = post["channel_id"]
            if cid not in bad:
                out.append(post)
                continue
            candidate = retry_by_id.get(cid)
            if candidate and not identity_violations(candidate["text"], segment_text, identity):
                out.append(candidate)
                notes.append(f"{cid}: regenerated once because the first draft spoke as a customer or claimed an "
                             "unsourced frequency.")
                continue
            source = candidate or post
            still = identity_violations(source["text"], segment_text, identity)
            source = {**source, "text": drop_sentences(source["text"], [v["sentence"] for v in still])}
            notes += [f"{cid}: removed \"{v['sentence'][:160]}\" ({v['reason']})." for v in still]
            if source["text"]:
                out.append(source)
            else:
                notes.append(f"{cid}: nothing was left after removing those sentences, so no draft is offered.")
        return out, notes

    @staticmethod
    def _match(channels: list[dict[str, Any]], raw_posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if channels:
            by_slug: dict[str, dict[str, Any]] = {}
            for post in raw_posts:
                by_slug.setdefault(slugify(post["channel_id"], max_len=30), post)
            for c in channels:
                post = by_slug.get(c["id"]) or by_slug.get(slugify(c.get("name") or "", max_len=30))
                if post:
                    out.append({**post, "channel_id": c["id"], "channel_name": c.get("name") or c["id"]})
            return out
        seen: set[str] = set()   # channels named by the founder in feedback
        for post in raw_posts[:6]:
            cid = slugify(post["channel_id"], max_len=30)
            if cid not in seen:
                seen.add(cid)
                out.append({**post, "channel_id": cid, "channel_name": post.get("channel_name") or post["channel_id"]})
        return out

    @staticmethod
    def post_file(post: dict[str, Any]) -> str:
        when = f"Day {post['day']} of the {LAUNCH_WINDOW_DAYS}-day launch window" if post["day"] else "Founder's choice"
        if post.get("timing"):
            when += f"; {post['timing']}"
        lines = [f"# {POST_HEADER}", "",
                 f"- Channel: {post['channel_name']} (`{post['channel_id']}`)",
                 f"- Format: {post['format']}",
                 "- Owner: the founder, posting from their own account. Venture Validator posts nothing: sending is "
                 "MOCKED and approval only places this draft in the local outbox.",
                 f"- Timing: {when}",
                 f"- Link: `{post['link']}` (local MOCKED store page; when you host the page publicly, use its public "
                 f"address and keep `?utm_source={post['channel_id']}` so visits are attributed to this channel)",
                 "", "---", "", post["text"].strip(), "", post["link"], "", "---", ""]
        if post.get("follow_up"):
            lines += [f"Follow-up: {post['follow_up']}", ""]
        lines.append("Edit freely before posting. Do not add reviews, ratings, user numbers or deadlines that are not "
                     "real.")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _markdown(posts, schedule, missing, identity_notes=None) -> str:
        lines = ["## Launch schedule", "",
                 "Each post is a draft for the founder to post from their own account. Approve the step (optionally "
                 "only some posts) to place them in the local outbox; nothing is posted by the system (MOCKED).", "",
                 "| Day | Channel | Format | Timing | Owner | Draft |", "|---|---|---|---|---|---|"]
        for s in schedule:
            lines.append(f"| {s['day'] or 'founder decides'} | {md_cell(s['channel'])} | {md_cell(s['format'])} | "
                         f"{md_cell(s['timing'])} | founder | `{s['file']}` |")
        for post in posts:
            lines += ["", f"## {post['channel_name']} (`{post['channel_id']}`)", "",
                      f"Tracked link: `{post['link']}`", "", "```text", post["text"].strip(), "```"]
        if missing:
            lines += ["", f"_No draft for: {', '.join(missing)}._"]
        lines += ["", "## Identity check", "",
                  "Every draft speaks only as the founder (background from the brief's why_you). Code rejects "
                  "sentences that claim the founder is one of the customers or claim how often the problem comes up "
                  "without a sourced evidence id."]
        lines += [f"- {n}" for n in (identity_notes or [])] or ["- All drafts passed on the first try."]
        lines += ["", "No testimonials, ratings or user numbers appear in these drafts: none exist yet.", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- 5.3 Mocked delivery
MOCKED_PARTS = [
    "Payment: none. There is no payment provider, no card or bank field and no charge; the CTA creates a no-charge "
    "mock order record.",
    "Order: a local mock order record with an idempotency key, stored in the run folder.",
    "Delivery: an access link or download grant written locally (MOCKED); no external system is called.",
    "Confirmation email: written to the local outbox (MOCKED); nothing is sent.",
    "Refunds: there is nothing to refund; the test only checks that revoking a mock order removes access.",
    "Test data: the delivery test suite runs on FIXTURE orders in a separate folder that analytics never reads.",
]
STORE_EVENTS = [
    ("page_view", "store page loads", "visitor_id", "eligible store visitor"),
    ("cta_click", "the access-request form is submitted (browser)", "visitor_id", "buy intent"),
    ("order_request", "the server records the no-charge request", "email_hash", "buy intent (same person as the click, "
     "not added twice)"),
]


def store_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    visitors, clicks, order_vids, orders = set(), set(), set(), set()
    for event in events:
        if event.get("page") not in (None, "store"):
            continue
        kind = event.get("type")
        if kind == "page_view" and event.get("visitor_id"):
            visitors.add(str(event["visitor_id"]))
        elif kind == "cta_click" and event.get("visitor_id"):
            clicks.add(str(event["visitor_id"]))
        elif kind == "order_request":
            if event.get("visitor_id"):
                order_vids.add(str(event["visitor_id"]))
            if event.get("email_hash"):
                orders.add(str(event["email_hash"]))
    # A request normally follows a click from the same browser, so the two are not added together:
    # the larger of (unique clicking browsers) and (unique requesting emails) is used.
    browsers = clicks | order_vids
    return {"visitors": len(visitors), "cta_clicks": len(clicks), "order_requests": len(orders),
            "buy_intents": max(len(browsers), len(orders))}


class MockedDelivery(StepHandler):
    def generate(self, ctx) -> StepOutput:
        store = ctx.prior("5.1")
        name, product_id = product_identity(ctx)
        product_id = store.get("product_id") or product_id
        rid = ctx.run_id
        lines = ["## Purchase-to-delivery flow (MOCKED)", "",
                 "No real money changes hands and no payment provider is involved. The flow below is what the local "
                 "app does when someone requests access on the store page.", "",
                 "```mermaid", "sequenceDiagram",
                 "  participant V as Visitor",
                 "  participant S as Store page (local MOCKED site)",
                 "  participant A as Local app",
                 "  participant O as Mock order records",
                 "  participant D as Delivery (MOCKED)",
                 "  participant M as Outbox (MOCKED email)",
                 "  V->>S: opens store page (page_view)",
                 "  V->>S: submits access request (cta_click)",
                 f"  S->>A: POST /p/{rid}/order (email, consent, product_id, package_id)",
                 "  A->>O: create no-charge mock order (idempotency key)",
                 "  O-->>A: existing order if the key was seen before",
                 "  A->>D: grant access once per order",
                 "  D->>M: write confirmation email to the local outbox (not sent)",
                 "  A-->>V: confirmation page repeating the no-charge label",
                 "```", "",
                 "## Event definitions", "",
                 "| Event | Recorded when | Dedupe key | Counts as |", "|---|---|---|---|"]
        lines += [f"| `{e}` | {when} | `{key}` | {counts} |" for e, when, key, counts in STORE_EVENTS]
        lines += ["", "Events flagged `internal` (founder, team, tests), fixture and bot-flagged events, and events "
                      "outside the locked window are excluded. Buy-intent rate = buy intents / eligible store visitors, "
                      "with a 95% Wilson interval.", "",
                  "## What is MOCKED", ""]
        lines += [f"- {m}" for m in MOCKED_PARTS]
        lines += ["", "## Gate T + E (thresholds locked before the launch window)", "",
                  "- T: 100% of end-to-end delivery tests pass, covering the happy path and at least 3 failure cases "
                  "(duplicate order, failed email, invalid product). The suite runs automatically once the thresholds "
                  "are locked; its log is saved as `payment_test_log.md`.",
                  f"- E: over the {LAUNCH_WINDOW_DAYS}-day launch window, at least 500 eligible store visitors and a "
                  "buy-intent rate of at least 3%.",
                  "- Routing: failing tests -> REPEAT (fix and re-run); too few visitors -> 2.1 (channels); "
                  "visitors but low intent -> 4.1 (price) or 2.2 (positioning).", ""]
        return StepOutput(title=str(name), markdown="\n".join(lines),
                          data={"product_id": product_id, "package_id": store.get("package_id"),
                                "price": store.get("price"), "currency": store.get("currency"),
                                "mocked": MOCKED_PARTS, "events": [e[0] for e in STORE_EVENTS]},
                          summary="Explained the mocked purchase-to-delivery flow; the delivery tests run when you lock "
                                  "the thresholds, and demand is read from the store page's own events.")

    def default_contract(self, ctx) -> Contract:
        return Contract(
            step_id=ctx.step_id,
            decision="Does the mocked delivery work end to end, and does the launch show real buy intent?",
            hypothesis=("Delivery passes every end-to-end test, and at least 3% of at least 500 eligible store visitors "
                        f"request access within {LAUNCH_WINDOW_DAYS} days."),
            criteria=[
                Criterion(key="delivery_tests_pass_rate", label="End-to-end delivery tests passing", target=1.0,
                          kind="hard", help="Share of delivery tests that pass (FIXTURE data)"),
                Criterion(key="failure_cases_tested", label="Failure cases tested", target=3, kind="hard",
                          unit="cases", help="Duplicate order, failed email, invalid product, ..."),
                Criterion(key="store_visitors", label="Eligible store visitors", target=500, kind="floor",
                          unit="visitors", help="Unique non-internal visitor IDs with a store page view in the window"),
                Criterion(key="buy_intent_rate", label="Mock buy-intent rate", target=0.03, kind="proportion",
                          help="Unique buy intents (CTA clicks / no-charge requests) / eligible store visitors"),
            ],
            window_days=LAUNCH_WINDOW_DAYS,
            pivot_target="4.1",
            notes=("Technical and demand criteria are separate: test fixtures never count as visitors or intents. "
                   "Exclusions: internal/test traffic, fixture and bot-flagged events, duplicates (visitor ID / email "
                   "hash), events outside the window. Too few visitors routes to 2.1 (channels); visitors without buy "
                   "intent routes to 4.1 (price), or 2.2 (positioning) by founder choice."),
        )

    # -- automatic collection
    def run_suite(self, ctx) -> tuple[dict[str, float | None], dict[str, Any], str]:
        store = ctx.prior("5.1")
        _name, fallback_id = product_identity(ctx)
        product_id = store.get("product_id") or fallback_id
        price = as_float(store.get("price"), None)
        currency = str(store.get("currency") or "").strip()
        work = ctx.run_path() / "commerce_test"
        observed: dict[str, float | None] = {"delivery_tests_pass_rate": None, "failure_cases_tested": None}
        details: dict[str, Any] = {"test_data": "FIXTURE orders in commerce_test/ (excluded from analytics)",
                                   "test_price": (f"{price:g} {currency}".strip() if price is not None
                                                  else "0 (FIXTURE amount: no price set in 5.1)")}
        try:
            import reconcile  # written by the sale-to-cash part; imported lazily
        except ImportError as exc:
            return observed, details, f"Delivery test suite unavailable ({exc}); test criteria have no value."
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True, exist_ok=True)
        try:
            result = reconcile.run_delivery_test_suite(work, product_id=product_id,
                                                       price=price if price is not None else 0.0,
                                                       currency=currency or "XXX")
        except Exception as exc:  # noqa: BLE001 - a crashing suite is reported, never turned into a pass
            return observed, details, f"Delivery test suite crashed: {type(exc).__name__}: {str(exc)[:200]}"
        tests = [t for t in (result.get("tests") or []) if isinstance(t, dict)]
        passed = sum(1 for t in tests if t.get("passed") is True)
        rate = round(passed / len(tests), 6) if tests else None
        failures = as_count(result.get("failure_cases_tested"))
        observed = {"delivery_tests_pass_rate": rate,
                    "failure_cases_tested": float(failures) if failures is not None else None}
        details.update({"tests_passed": f"{passed}/{len(tests)}",
                        "failed_tests": [t.get("name") for t in tests if t.get("passed") is not True],
                        "critical_failures": [t.get("name") for t in tests if t.get("critical") and t.get("passed") is not True],
                        "failure_cases_tested": failures})
        reported = as_float(result.get("pass_rate"), None)
        if reported is not None and rate is not None and abs(reported - rate) > 1e-6:
            details["pass_rate_note"] = f"suite reported {reported:g}; recomputed from the test list as {rate:g}"
        log_md = str(result.get("log_markdown") or "")
        if log_md:
            rel = ctx.store.write_artifact(ctx.run_id, "5.3", ctx.attempt, "payment_test_log.md", log_md)
            ctx.run.steps["5.3"].artifacts["payment_test_log.md"] = rel
            details["test_log"] = rel
        return observed, details, f"Delivery tests: {passed}/{len(tests)} passed; {failures} failure cases tested."

    def collect(self, ctx, contract: Contract) -> Observation:
        t_observed, t_details, t_note = self.run_suite(ctx)
        window = window_info(contract)
        events, excluded = eligible_events(ctx.store.read_events(ctx.run_id), window)
        counts = store_counts(events)
        obs = self._demand(ctx, contract, window, counts["visitors"], counts["buy_intents"], "local first-party events",
                           extra={"cta_clicks": counts["cta_clicks"], "order_requests": counts["order_requests"],
                                  "excluded_events": excluded})
        obs.observed.update(t_observed)
        obs.details = {**t_details, **obs.details}
        obs.notes = f"{t_note} {obs.notes}"
        if any(v is None for v in t_observed.values()) and obs.measurement_state == READY:
            obs.measurement_state = WAITING_FOR_DATA
        return obs

    def data_fields(self) -> list[DataField]:
        return [
            DataField("store_visitors", "Eligible store visitors (external analytics)", type="integer", required=False,
                      help="Only if the store page ran somewhere the local analytics cannot see. Leave both blank to "
                           "re-run the delivery tests and re-read the local events."),
            DataField("buy_intents", "Unique buy intents (external analytics)", type="integer", required=False,
                      help="Unique people who requested access or clicked the request button, excluding you and tests."),
            DataField("analytics_source", "Where these numbers come from", type="text", required=False),
        ]

    def observe(self, ctx, contract: Contract, data: dict[str, Any]) -> Observation:
        raw_v, raw_i = data.get("store_visitors"), data.get("buy_intents")
        if raw_v in (None, "") and raw_i in (None, ""):
            return self.collect(ctx, contract)
        visitors, intents = as_count(raw_v), as_count(raw_i)
        window = window_info(contract)
        if visitors is None or intents is None or intents > visitors:
            return Observation(observed={"store_visitors": None, "buy_intent_rate": None},
                               measurement_state=INVALID_DATA,
                               details={"source": "founder_data", "submitted": {"store_visitors": raw_v, "buy_intents": raw_i}},
                               notes="Founder data rejected: submit both numbers as whole counts, with buy intents not "
                                     "exceeding visitors.")
        source = str(data.get("analytics_source") or "").strip() or "analytics tool not named"
        row = ctx.ledger.add(Evidence(
            provenance="FOUNDER_REPORTED", source_type="founder_data",
            title=f"Store-page launch results reported by the founder ({source})", value=float(intents),
            unit="buy intents", denominator=float(visitors), observed_at=utc_now(),
            excerpt=f"{intents} buy intents from {visitors} store visitors, reported for window {window['text']}",
            method="founder-submitted external analytics"))
        # Test criteria stay None here: the orchestrator keeps the automatic test values already collected.
        obs = self._demand(ctx, contract, window, visitors, intents, f"founder_data ({source})", record=False)
        obs.evidence_ids = [row.evidence_id]
        return obs

    @staticmethod
    def _demand(ctx, contract, window, visitors: int, intents: int, source: str, *, extra: dict | None = None,
                record: bool = True) -> Observation:
        low, high = wilson_interval(intents, visitors)
        rate = round(intents / visitors, 6) if visitors else None
        details: dict[str, Any] = {"demand_source": source, "window": window["text"],
                                   "days_remaining": window["days_remaining"], "eligible_store_visitors": visitors,
                                   "buy_intents": intents,
                                   "buy_intent_rate": pct1(rate) if rate is not None else "n/a (no visitors)",
                                   "buy_intent_rate_95ci_wilson": (f"{pct1(low)} to {pct1(high)}"
                                                                   if low is not None else "n/a"),
                                   **(extra or {})}
        state = READY
        notes = f"Demand ({source}): {intents} buy intents / {visitors} eligible store visitors."
        if not window["closed"]:
            state = WAITING_FOR_DATA
            notes += (f" Launch window still open: {window['days_remaining']} days left (ends {iso(window['end'])}); "
                      "demand values are partial.")
        if intents > visitors:
            state = INVALID_DATA
            notes += " More buy intents than visitors: page-view events were lost, so the rate cannot be trusted."
        evidence_ids = []
        if record and state == READY:
            row = ctx.ledger.add(Evidence(
                provenance="DIRECT_OBSERVATION", source_type="local_page_analytics",
                title="Store-page launch: first-party analytics", value=float(intents), unit="buy intents",
                denominator=float(visitors), observed_at=utc_now(),
                excerpt=f"{intents} unique buy intents from {visitors} eligible store visitors, window {window['text']}",
                method="unique visitor_id page views; unique CTA clicks / no-charge requests; internal/bot/fixture "
                       "excluded"))
            evidence_ids.append(row.evidence_id)
        floor = criterion_target(contract, "store_visitors", 500)
        target = criterion_target(contract, "buy_intent_rate", 0.03)
        pivot = "2.1" if visitors < floor else ("4.1" if rate is not None and rate < target else None)
        return Observation(observed={"store_visitors": float(visitors), "buy_intent_rate": rate},
                           measurement_state=state, evidence_ids=evidence_ids, details=details, notes=notes,
                           pivot_target=pivot)
