"""Phase 4: Commercial setup. No payments of any kind.

4.1 Pricing       gate E + A: three price anchors, 2-3 packages, a Van Westendorp survey design and a
                  no-charge pricing-page click test (MOCKED: "Choose plan" -> "Coming soon: no payment is taken").
4.2 LegalDrafts   gate A: Terms, Privacy and Refund DRAFTS tailored to the data the prototype handles.

All arithmetic (economics floor, sample bills, Van Westendorp curves and intersections, click rate and
its Wilson interval) happens here in Python. Prices are prospective; nobody is asked for payment details.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

import markdown as md_lib

from agents import legal_drafter, pricing_analyst
from agents.base import StepContext, as_list
from agents.pricing_analyst import to_number
from evidence import Claim, Evidence
from gates import (INSUFFICIENT_DATA, INVALID_DATA, READY, WAITING_FOR_DATA, Contract, Criterion, check_criterion,
                   wilson_interval)
from phases.base import DataField, Observation, StepHandler, StepOutput

# ---------------------------------------------------------------------------------------------- shared helpers

MOCK_NOTE = "MOCKED"

_CURRENCY_BY_PLACE: list[tuple[str, str]] = [
    (r"united states|u\.s\.a?\.?|america\b|\busa\b", "USD"), (r"united kingdom|\bu\.?k\.?\b|england|scotland|wales|britain", "GBP"),
    (r"egypt", "EGP"), (r"canada", "CAD"), (r"australia", "AUD"), (r"new zealand", "NZD"), (r"india\b", "INR"),
    (r"nigeria", "NGN"), (r"kenya", "KES"), (r"ghana", "GHS"), (r"south africa", "ZAR"), (r"morocco", "MAD"),
    (r"united arab emirates|\buae\b|dubai|abu dhabi", "AED"), (r"saudi", "SAR"), (r"jordan", "JOD"),
    (r"pakistan", "PKR"), (r"bangladesh", "BDT"), (r"turkey|t[uü]rkiye", "TRY"), (r"brazil", "BRL"),
    (r"mexico", "MXN"), (r"japan", "JPY"), (r"singapore", "SGD"), (r"switzerland", "CHF"), (r"sweden", "SEK"),
    (r"norway", "NOK"), (r"denmark", "DKK"), (r"poland", "PLN"), (r"indonesia", "IDR"), (r"philippines", "PHP"),
    (r"germany|france|spain|italy|netherlands|ireland|belgium|austria|portugal|finland|greece|estonia|latvia|"
     r"lithuania|slovakia|slovenia|luxembourg|malta|cyprus|croatia|\beu\b|euro", "EUR"),
]


def currency_for(brief: dict[str, Any]) -> tuple[str, str]:
    """Currency from the brief: an explicit 3-letter code, else the jurisdiction, else USD (labelled)."""
    explicit = str(brief.get("currency") or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", explicit):
        return explicit, "currency given in the founder's brief"
    place = str(brief.get("jurisdiction") or "").strip()
    if re.search(r"\bUS\b", place):
        return "USD", f"from the jurisdiction in the brief ({place})"
    for pattern, code in _CURRENCY_BY_PLACE:
        if place and re.search(pattern, place, re.IGNORECASE):
            return code, f"from the jurisdiction in the brief ({place})"
    if place:
        return "USD", f"ASSUMPTION: no currency mapped for jurisdiction '{place}'; USD used until the founder confirms"
    return "USD", "ASSUMPTION: no jurisdiction in the brief; USD used until the founder confirms"


def measurement_state(contract: Contract, observed: dict[str, float | None]) -> str:
    """READY when every criterion has a value, or when a present floor value already misses its target
    (a missed floor fails the gate whatever the other values are). Otherwise data is missing."""
    present = [c for c in contract.criteria if observed.get(c.key) is not None]
    if len(present) == len(contract.criteria):
        return READY
    if any(c.kind == "floor" and check_criterion(c, observed[c.key]).passed is False for c in present):
        return READY
    return INSUFFICIENT_DATA if present else WAITING_FOR_DATA


def to_int(value: Any) -> int | None:
    number = to_number(value)
    if number is None:
        return None
    return int(round(number))


def money(value: float | None, currency: str = "") -> str:
    if value is None:
        return "unknown"
    text = f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return f"{text} {currency}".strip()


def cell(value: Any) -> str:
    return str(value if value not in (None, "") else "-").replace("|", "/").replace("\n", " ")


def prior_digest(ctx: StepContext, step_id: str, keys: tuple[str, ...], limit: int = 2000) -> dict[str, Any]:
    """A size-limited view of an earlier step's deliverable for a model payload."""
    data = ctx.prior(step_id)
    picked = {k: data[k] for k in keys if k in data}
    if not picked:
        picked = {k: v for k, v in data.items() if k not in ("outward", "outward_results")}
    state = ctx.run.steps.get(step_id)
    if state is not None and state.summary:
        picked["summary"] = state.summary
    text = json.dumps(picked, ensure_ascii=False, default=str)
    if len(text) > limit:
        return {"excerpt": text[:limit], "truncated": True}
    return picked


def html_page(title: str, body_html: str, *, banner: str, footer: str) -> str:
    """A small self-contained HTML page (inline CSS, no external requests)."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: #fafafa; color: #1d1d1f; line-height: 1.55; }}
  main {{ max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }}
  .banner {{ background: #fff4ce; border: 1px solid #d9b500; border-radius: 8px; padding: 12px 16px; font-weight: 600; margin-bottom: 24px; }}
  .plans {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
  .plan {{ background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 16px; }}
  .plan.recommended {{ border-color: #3b5bdb; }}
  .price {{ font-size: 1.6em; font-weight: 700; }}
  .muted {{ color: #555; font-size: 0.9em; }}
  button {{ font: inherit; padding: 8px 14px; border-radius: 6px; border: 1px solid #3b5bdb; background: #3b5bdb; color: #fff; cursor: pointer; }}
  .coming-soon {{ display: none; margin-top: 10px; padding: 8px; border-radius: 6px; background: #eef2ff; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
  footer {{ margin-top: 40px; color: #555; font-size: 0.85em; }}
</style>
</head>
<body>
<main>
<div class="banner">{html.escape(banner)}</div>
{body_html}
<footer>{html.escape(footer)}</footer>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------------------------- 4.1 pricing

VW_KEYS = ("too_cheap", "cheap", "expensive", "too_expensive")
VW_METHOD = (
    "Van Westendorp price sensitivity meter. Responses must satisfy too_cheap <= cheap <= expensive <= too_expensive "
    "(with too_cheap < too_expensive); other rows are excluded and counted. Curves are evaluated at every distinct "
    "answered price p: Too cheap(p) = share with too_cheap >= p; Cheap(p) = share with cheap >= p; "
    "Expensive(p) = share with expensive <= p; Too expensive(p) = share with too_expensive <= p; "
    "Not cheap = 1 - Cheap; Not expensive = 1 - Expensive. Intersections: PMC = Too cheap x Not cheap, "
    "OPP = Too cheap x Too expensive, IPP = Cheap x Expensive, PME = Not expensive x Too expensive, each found at "
    "the first grid price where the falling curve is no longer above the rising curve, by linear interpolation "
    "between the two neighbouring grid prices. Acceptable range = [PMC, PME]. Other published conventions "
    "intersect Too cheap with Expensive; results then differ slightly. A small sample is directional only, and the "
    "range describes stated price perception, not purchase demand.")


def parse_vw_responses(raw: Any) -> tuple[list[dict[str, float]], list[str]]:
    """Parse raw Van Westendorp rows. Raises ValueError when the payload itself is unreadable."""
    if raw in (None, "", []):
        return [], []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        raw = raw.get("responses")
    if not isinstance(raw, list):
        raise ValueError("expected a JSON list of {too_cheap, cheap, expensive, too_expensive} objects")
    valid: list[dict[str, float]] = []
    problems: list[str] = []
    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            problems.append(f"row {index}: not an object")
            continue
        values = [to_number(row.get(key)) for key in VW_KEYS]
        if any(v is None or v < 0 for v in values):
            problems.append(f"row {index}: a value is missing or negative")
            continue
        if not (values[0] <= values[1] <= values[2] <= values[3]) or values[0] >= values[3]:
            problems.append(f"row {index}: inconsistent order (needs too_cheap <= cheap <= expensive <= too_expensive)")
            continue
        valid.append(dict(zip(VW_KEYS, values)))
    return valid, problems


def _crossing(grid: list[float], falling: list[float], rising: list[float]) -> float | None:
    diffs = [f - r for f, r in zip(falling, rising)]
    for i, diff in enumerate(diffs):
        if diff <= 0:
            if i == 0:
                return grid[0] if diff == 0 else None
            if diff == 0:
                return grid[i]
            before = diffs[i - 1]
            return grid[i - 1] + (grid[i] - grid[i - 1]) * before / (before - diff)
    return None


def van_westendorp(responses: list[dict[str, float]]) -> dict[str, Any]:
    """Cumulative curves and the four intersections (see VW_METHOD)."""
    n = len(responses)
    result: dict[str, Any] = {"n": n, "pmc": None, "opp": None, "ipp": None, "pme": None, "grid_points": 0}
    if n == 0:
        return result
    grid = sorted({r[k] for r in responses for k in VW_KEYS})
    too_cheap = [sum(r["too_cheap"] >= p for r in responses) / n for p in grid]
    cheap = [sum(r["cheap"] >= p for r in responses) / n for p in grid]
    expensive = [sum(r["expensive"] <= p for r in responses) / n for p in grid]
    too_expensive = [sum(r["too_expensive"] <= p for r in responses) / n for p in grid]
    not_cheap = [1 - x for x in cheap]
    not_expensive = [1 - x for x in expensive]

    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 2)

    result.update({
        "pmc": rounded(_crossing(grid, too_cheap, not_cheap)),
        "opp": rounded(_crossing(grid, too_cheap, too_expensive)),
        "ipp": rounded(_crossing(grid, cheap, expensive)),
        "pme": rounded(_crossing(grid, not_expensive, too_expensive)),
        "grid_points": len(grid),
    })
    return result


def amount_in_period(amount: float | None, billing: str, period: str) -> float | None:
    """Convert an amount between month and year; one-time amounts only compare with one-time amounts."""
    if amount is None:
        return None
    if billing == period:
        return amount
    if billing == "year" and period == "month":
        return amount / 12
    if billing == "month" and period == "year":
        return amount * 12
    return None


def billing_phrase(billing: str) -> str:
    return {"month": "per month", "year": "per year", "one-time": "one-time"}.get(billing, billing)


def comparable_prices(ctx: StepContext) -> list[dict[str, Any]]:
    """Comparable prices only from step 1.3 competitors with resolvable evidence, or price/spend evidence rows."""
    known = {ev.evidence_id: ev for ev in ctx.ledger.all()}
    rows: list[dict[str, Any]] = []
    used: set[str] = set()
    for comp in as_list(ctx.prior("1.3").get("competitors")):
        if not isinstance(comp, dict) or not comp.get("name"):
            continue
        ids = [str(i) for i in as_list(comp.get("evidence_ids")) if str(i) in known]
        used.update(ids)
        price = str(comp.get("price") or "").strip()
        if price and re.search(r"quote|contact|sales|custom", price, re.IGNORECASE):
            price, status = "quote required", "quote_required"
        elif price and ids and to_number(price) is not None and not re.search(r"unknown|n/?a", price, re.IGNORECASE):
            status = "sourced"
        else:
            price, status = "unknown", "unknown"
        rows.append({"name": str(comp["name"])[:80], "url": comp.get("url"), "price": price, "status": status,
                     "evidence_ids": ids if status == "sourced" else ids[:3]})
    money_unit = re.compile(r"[$€£¥₹]|\b[A-Z]{3}\b")
    money_word = re.compile(r"price|spend|spent|cost|fee|per (month|year|seat|user)|/\s*(mo|month|yr|year)", re.IGNORECASE)
    for ev in ctx.ledger.all():
        if ev.evidence_id in used or ev.value is None:
            continue
        if money_unit.search(ev.unit or "") or money_word.search(ev.unit or ""):
            rows.append({"name": (ev.title or ev.excerpt or ev.evidence_id)[:80], "url": ev.url,
                         "price": f"{ev.value:g} {ev.unit}".strip(),
                         "status": "sourced" if ev.provenance == "SOURCE_FACT" else ev.provenance.lower(),
                         "evidence_ids": [ev.evidence_id]})
    return rows[:15]


def _sample_bills(package: dict[str, Any]) -> dict[str, float | None]:
    bills: dict[str, float | None] = {}
    for level in ("low", "typical", "high"):
        units = package["usage_examples"].get(level)
        if package["metered"]:
            bills[level] = None if units is None else round(package["price"] * units, 2)
        else:
            bills[level] = package["price"]
    return bills


def vw_questions(bundle: str, currency: str, billing: str) -> list[dict[str, str]]:
    unit = f"{currency} {billing_phrase(billing)}"
    return [
        {"key": "too_expensive", "text": f"At what price ({unit}) would {bundle} be so expensive that you would not consider buying it?"},
        {"key": "too_cheap", "text": f"At what price ({unit}) would {bundle} be so cheap that you would doubt its quality?"},
        {"key": "expensive", "text": f"At what price ({unit}) would {bundle} start to feel expensive: not out of the question, but you would have to think about it?"},
        {"key": "cheap", "text": f"At what price ({unit}) would {bundle} be a bargain: a great buy for the money?"},
    ]


def pricing_page_html(product: str, headline: str, packages: list[dict[str, Any]], recommended_id: str,
                      currency: str) -> str:
    cards = []
    for p in packages:
        includes = "".join(f"<li>{html.escape(item)}</li>" for item in p["includes"])
        metric = f" {html.escape(p['price_metric'])}" if p.get("price_metric") else ""
        cards.append(
            f'<div class="plan{" recommended" if p["id"] == recommended_id else ""}">'
            f'<h2>{html.escape(p["name"])}</h2>'
            f'<div class="muted">Proposed future price</div>'
            f'<div class="price">{html.escape(money(p["price"], currency))}</div>'
            f'<div class="muted">{html.escape(billing_phrase(p["billing"]))}{metric}</div>'
            f'<ul>{includes}</ul>'
            f'<button type="button" data-plan="{html.escape(p["id"])}" onclick="choosePlan(this)">Choose plan</button>'
            f'<div class="coming-soon" role="status">Coming soon: no payment is taken. ({MOCK_NOTE})</div>'
            f'</div>')
    body = (f"<h1>{html.escape(headline or product)}</h1>"
            f"<p>These are proposed future prices for {html.escape(product)}. This page only measures interest: "
            "choosing a plan does not take any payment and does not ask for any payment details.</p>"
            f'<div class="plans">{"".join(cards)}</div>'
            "<script>function choosePlan(btn){var box=btn.parentNode.querySelector('.coming-soon');"
            "if(box){box.style.display='block';}}</script>")
    return html_page(f"{product} pricing (proposed)", body,
                     banner=f"{MOCK_NOTE} pricing page for a no-charge click test. Prices are proposed future prices. "
                            "No payment is taken.",
                     footer=f"{MOCK_NOTE}: local prototype page. Nothing is sold here and no payment provider is connected.")


class Pricing(StepHandler):
    """4.1 Pricing: three anchors, 2-3 packages, a Van Westendorp survey and a no-charge click test."""

    def generate(self, ctx: StepContext) -> StepOutput:
        concept = ctx.concept()
        currency, currency_basis = currency_for(ctx.brief)
        comparables = comparable_prices(ctx)
        payload = {
            "product": concept,
            "brief": {k: ctx.brief.get(k) for k in ("idea", "customer", "jurisdiction", "budget", "evidence")},
            "currency": currency,
            "comparable_prices": comparables,
            "evidence_digest": ctx.evidence_digest(25),
            "interview_findings": prior_digest(ctx, "1.4", ("analysis", "findings", "spend", "summary_stats"), 1500),
            "lean_canvas": prior_digest(ctx, "2.1", ("revenue_streams", "cost_structure", "key_metrics", "channels",
                                                     "customer_segments", "uvp"), 1500),
            "mvp_scope": prior_digest(ctx, "3.1", ("must_haves", "core_flows", "wont_build"), 1200),
            "feedback": ctx.feedback,
        }
        reply = pricing_analyst.pricing_options(ctx, payload)
        notes: list[str] = []
        known_ids = {ev.evidence_id for ev in ctx.ledger.all(include_fixtures=True)}

        econ = reply["economics"]
        vc, margin = econ["variable_cost_per_customer"], econ["target_margin"]
        floor_value = round(vc / (1 - margin), 2) if vc is not None and margin is not None else None
        economics_floor = {
            "value": floor_value, "currency": currency, "period": econ["period"],
            "variable_cost_per_customer": vc, "target_margin": margin,
            "formula": "floor = variable_cost_per_customer / (1 - target_margin)",
            "variable_cost_label": econ["variable_cost_label"], "variable_cost_basis": econ["variable_cost_basis"],
            "target_margin_label": econ["target_margin_label"], "target_margin_basis": econ["target_margin_basis"],
            "high_usage_note": econ["high_usage_note"],
        }
        if floor_value is None:
            notes.append("Economics floor unknown: the model gave no usable variable cost or margin.")

        packages: list[dict[str, Any]] = []
        for p in reply["packages"]:
            bills = _sample_bills(p)
            typical = amount_in_period(bills.get("typical"), p["billing"], econ["period"])
            below = None if (floor_value is None or typical is None) else typical < floor_value
            packages.append({**p, "currency": currency, "sample_bills": bills, "below_economics_floor": below})
        recommended_id = reply["recommended_package_id"]
        recommended = next(p for p in packages if p["id"] == recommended_id)
        if recommended["below_economics_floor"]:
            notes.append(f"The recommended package's typical bill is below the economics floor "
                         f"({money(floor_value, currency)} {billing_phrase(econ['period'])}).")
        reference_price = recommended["sample_bills"].get("typical") or recommended["price"]

        outside = dict(reply["outside_option"])
        dropped = [i for i in outside["evidence_ids"] if i not in known_ids]
        outside["evidence_ids"] = [i for i in outside["evidence_ids"] if i in known_ids]
        value = dict(reply["customer_value"])
        dropped += [i for i in value["evidence_ids"] if i not in known_ids]
        value["evidence_ids"] = [i for i in value["evidence_ids"] if i in known_ids]
        if dropped:
            notes.append(f"Removed citations of unknown evidence IDs: {', '.join(sorted(set(dropped)))}.")
        if not any(c["status"] == "sourced" for c in comparables):
            notes.append("No sourced comparable price exists in the evidence ledger: the outside-option anchor rests "
                         "on the workaround description only.")

        bundle = reply["bundle_description"] or f"the {recommended['name']} package of {concept.get('name') or ctx.run.title}"
        questions_vw = vw_questions(bundle, currency, recommended["billing"])
        product_name = str(concept.get("name") or ctx.run.title)
        headline = reply["page_headline"] or f"{product_name}: proposed plans"
        page = pricing_page_html(product_name, headline, packages, recommended_id, currency)

        research_design = {
            "van_westendorp": {
                "bundle": bundle, "currency": currency, "billing": recommended["billing"],
                "reference_price": reference_price, "questions": questions_vw,
                "screening": "Ask only people in the target segment who own the problem; record role and how they "
                             "were recruited. Never ask for payment details.",
                "consistency_check": "too_cheap <= cheap <= expensive <= too_expensive; other rows are excluded and counted.",
                "sample_floor": 30, "method": VW_METHOD,
            },
            "click_test": {
                "page": "pricing.html", "mocked": True,
                "flow": "'Choose plan' -> 'Coming soon: no payment is taken' (MOCKED). No form, no payment details.",
                "metric": "paid_plan_click_rate = visitors who clicked 'Choose plan' on a paid plan / unique pricing-page visitors",
                "interval": "Wilson 95% interval computed in code",
            },
        }

        claims: list[Claim] = []
        if vc is not None:
            claims.append(Claim(text=f"Variable cost to serve one customer: {money(vc, currency)} {billing_phrase(econ['period'])}",
                                label=econ["variable_cost_label"], basis=econ["variable_cost_basis"]))
        if margin is not None:
            claims.append(Claim(text=f"Target contribution margin: {margin:.0%}", label=econ["target_margin_label"],
                                basis=econ["target_margin_basis"]))
        if floor_value is not None:
            claims.append(Claim(text=f"Economics floor: {money(floor_value, currency)} {billing_phrase(econ['period'])}",
                                label="ESTIMATE", basis=f"computed in code: {money(vc)} / (1 - {margin:g})"))
        for comp in comparables:
            if comp["status"] == "sourced":
                claims.append(Claim(text=f"Comparable price: {comp['name']} at {comp['price']}", label="SOURCED",
                                    evidence_ids=comp["evidence_ids"]))
        if value["estimate"] is not None:
            claims.append(Claim(text=f"Customer value estimate: {money(value['estimate'], currency)} {billing_phrase(value['period'])}",
                                label=value["label"], evidence_ids=value["evidence_ids"], basis=value["basis"]))
        claims += [Claim(**c) for c in reply["claims"]]

        contract_preview = self.default_contract(ctx)
        markdown = self._markdown(ctx, currency, currency_basis, economics_floor, comparables, outside, value,
                                  packages, recommended_id, research_design, reply["rationale"], notes,
                                  contract_preview)
        marketing = "\n".join([headline] + [f"{p['name']}: " + "; ".join(p["includes"]) for p in packages])

        questions = list(reply["questions"])
        if currency_basis.startswith("ASSUMPTION"):
            questions.insert(0, "Which currency and jurisdiction should prices use? (USD is a placeholder.)")
        data = {
            "packages": packages, "recommended_package_id": recommended_id, "currency": currency,
            "currency_basis": currency_basis, "billing": recommended["billing"], "economics_floor": economics_floor,
            "comparables": comparables, "outside_option": outside, "customer_value": value,
            "vw_reference_price": reference_price, "research_design": research_design,
            "rationale": reply["rationale"], "notes": notes, "prices_are_prospective": True, "mocked": ["click_test"],
            "outward": [{"kind": "publish", "item_id": "pricing-page", "file": "pricing.html",
                         "when": "before_collect", "target_name": "pricing.html"}],
        }
        return StepOutput(
            title=f"Pricing: {recommended['name']} at {money(recommended['price'], currency)} {billing_phrase(recommended['billing'])} (proposed)",
            markdown=markdown, data=data, files={"pricing.html": page}, claims=claims,
            sources=ctx.ledger.urls([i for c in comparables for i in c["evidence_ids"]]),
            summary=(f"Proposed {len(packages)} packages in {currency}; recommended {recommended['name']} at "
                     f"{money(recommended['price'], currency)} {billing_phrase(recommended['billing'])}. "
                     "The price is a hypothesis until the survey and the no-charge click test report back."),
            questions=questions[:3], marketing_text=marketing)

    def _markdown(self, ctx, currency, currency_basis, floor, comparables, outside, value, packages, recommended_id,
                  design, rationale, notes, contract) -> str:
        lines = ["All prices below are **proposed future prices**. No payment is taken, no payment provider is "
                 "connected and nobody is asked for card or bank details.", "",
                 f"Currency: **{currency}** ({currency_basis}).", ""]
        lines += ["## Anchor 1: economics floor", "",
                  "| Input | Value | Label | Basis |", "|---|---|---|---|",
                  f"| Variable cost per customer ({billing_phrase(floor['period'])}) | {money(floor['variable_cost_per_customer'], currency)} "
                  f"| {floor['variable_cost_label']} | {cell(floor['variable_cost_basis'])} |",
                  f"| Target contribution margin | {'unknown' if floor['target_margin'] is None else format(floor['target_margin'], '.0%')} "
                  f"| {floor['target_margin_label']} | {cell(floor['target_margin_basis'])} |",
                  f"| **Economics floor** | **{money(floor['value'], currency)}** | ESTIMATE | computed in code: {floor['formula']} |", ""]
        if floor["high_usage_note"]:
            lines += [f"High-usage case (ESTIMATE): {floor['high_usage_note']}", ""]
        lines += ["## Anchor 2: outside option (comparable prices from the evidence ledger only)", ""]
        if comparables:
            lines += ["| Alternative | Price | Status | Evidence |", "|---|---|---|---|"]
            lines += [f"| {cell(c['name'])} | {cell(c['price'])} | {c['status']} | {', '.join(c['evidence_ids']) or '-'} |"
                      for c in comparables]
        else:
            lines.append("_No comparable prices in the evidence ledger: price unknown; get quotes or public price pages._")
        lines.append("")
        if outside["summary"] or outside["workaround"]:
            refs = f" (evidence: {', '.join(outside['evidence_ids'])})" if outside["evidence_ids"] else " `ASSUMPTION`"
            lines += [f"{outside['summary']} {outside['workaround']}".strip() + refs, ""]
        lines += ["## Anchor 3: customer value", "",
                  f"- Estimate: {money(value['estimate'], currency)} {billing_phrase(value['period'])} `{value['label']}`"
                  + (f" (evidence: {', '.join(value['evidence_ids'])})" if value["evidence_ids"] else ""),
                  f"- Basis: {value['basis'] or 'not given'}", ""]
        lines += ["## Packages (proposed future prices)", "",
                  "| Package | Price | Billing | Price metric | Low / typical / high bill | vs economics floor | Upgrade trigger | Likely objections |",
                  "|---|---|---|---|---|---|---|---|"]
        for p in packages:
            bills = " / ".join(money(p["sample_bills"][k], currency) for k in ("low", "typical", "high"))
            versus = {True: "BELOW floor", False: "above floor", None: "not comparable"}[p["below_economics_floor"]]
            mark = " (recommended)" if p["id"] == recommended_id else ""
            lines.append(f"| {cell(p['name'])}{mark} | {money(p['price'], currency)} | {billing_phrase(p['billing'])} "
                         f"| {cell(p['price_metric'])}{' (metered)' if p['metered'] else ''} | {bills} | {versus} "
                         f"| {cell(p['upgrade_trigger'])} | {cell('; '.join(p['likely_objections']))} |")
        lines += ["", "Sample bills are computed in code from the price and the usage examples (price x units when "
                  "metered, otherwise the flat price).", ""]
        if rationale:
            lines += ["**Rationale:** " + rationale, ""]
        vw = design["van_westendorp"]
        lines += ["## Research design", "", "### Van Westendorp price survey", "",
                  f"Bundle shown: {vw['bundle']}. Same currency ({vw['currency']}) and billing period "
                  f"({billing_phrase(vw['billing'])}) in all four questions. The recommended price tested against "
                  f"the acceptable range is **{money(vw['reference_price'], currency)}** (typical bill).", ""]
        lines += [f"{i}. {q['text']} (`{q['key']}`)" for i, q in enumerate(vw["questions"], start=1)]
        lines += ["", f"- Screening: {vw['screening']}", f"- Consistency check: {vw['consistency_check']}",
                  f"- Sample floor: {vw['sample_floor']} valid responses.", f"- Method (computed in code): {vw['method']}", "",
                  f"### No-charge pricing-page click test ({MOCK_NOTE})", "",
                  f"- Page: `pricing.html` (published to the local {MOCK_NOTE} site only after you approve it when locking the thresholds).",
                  f"- Flow: {design['click_test']['flow']}",
                  f"- Metric: {design['click_test']['metric']}; {design['click_test']['interval']}.", ""]
        if contract is not None:
            lines += ["## Proposed thresholds (lock before collecting data)", "",
                      "| Criterion | Rule | Kind |", "|---|---|---|"]
            lines += [f"| {c.label} | {c.key} {c.op} {c.target:g} | {c.kind} |" for c in contract.criteria]
            lines.append("")
        if notes:
            lines += ["## Checks applied in code", ""] + [f"- {n}" for n in notes] + [""]
        return "\n".join(lines)

    def default_contract(self, ctx: StepContext) -> Contract:
        return Contract(
            step_id="4.1",
            decision="Keep the recommended price as the provisional launch price, or change the pricing model.",
            hypothesis="Target buyers find the recommended price acceptable and some choose a paid plan on a no-charge pricing page.",
            criteria=[
                Criterion(key="pricing_responses", label="Valid pricing survey responses", op=">=", target=30,
                          unit="responses", kind="floor"),
                Criterion(key="price_in_acceptable_range", label="Recommended price inside the Van Westendorp acceptable range (1 = inside PMC..PME, 0 = outside)",
                          op=">=", target=1, kind="hard"),
                Criterion(key="paid_plan_click_rate", label="Pricing-page visitors who click a paid plan",
                          op=">=", target=0.05, unit="share", kind="proportion"),
            ],
            window_days=14, pivot_target="2.1",
            notes="Prices are prospective. The click test is MOCKED: no payment is taken and no payment details are requested.")

    def data_fields(self) -> list[DataField]:
        return [
            DataField("van_westendorp_responses_json", "Van Westendorp responses", type="json", required=False,
                      help='JSON list like [{"too_cheap": 5, "cheap": 10, "expensive": 20, "too_expensive": 30}], '
                           "one object per respondent, same currency and billing period as the survey."),
            DataField("pricing_responses", "Pricing survey responses received", type="integer", required=False,
                      help="Only used when raw responses are not submitted; otherwise the valid raw rows are counted."),
            DataField("pricing_page_visitors", "Unique pricing-page visitors", type="integer", required=False),
            DataField("paid_plan_clicks", "Visitors who clicked 'Choose plan' on a paid plan", type="integer",
                      required=False),
        ]

    def observe(self, ctx: StepContext, contract: Contract, data: dict[str, Any]) -> Observation:
        out = ctx.prior("4.1")
        currency = out.get("currency") or ""
        billing = out.get("billing") or ""
        reference = to_number(out.get("vw_reference_price"))
        observed: dict[str, float | None] = {c.key: None for c in contract.criteria}
        details: dict[str, Any] = {"source": "founder_data", "currency": currency, "billing": billing,
                                   "recommended_price": reference}
        problems: list[str] = []
        evidence_ids: list[str] = []

        raw = data.get("van_westendorp_responses_json")
        valid: list[dict[str, float]] | None = None
        if raw not in (None, "", []):
            try:
                valid, row_problems = parse_vw_responses(raw)
            except (ValueError, TypeError) as exc:
                problems.append(f"Van Westendorp responses could not be read: {exc}")
            else:
                vw = van_westendorp(valid)
                in_range = None
                if vw["pmc"] is not None and vw["pme"] is not None and reference is not None:
                    in_range = 1.0 if vw["pmc"] <= reference <= vw["pme"] else 0.0
                observed["pricing_responses"] = float(len(valid))
                observed["price_in_acceptable_range"] = in_range
                details["van_westendorp"] = {
                    "valid_responses": len(valid), "excluded_responses": len(row_problems),
                    "exclusions": row_problems[:10], "PMC": vw["pmc"], "OPP": vw["opp"], "IPP": vw["ipp"],
                    "PME": vw["pme"], "acceptable_range": [vw["pmc"], vw["pme"]], "grid_points": vw["grid_points"],
                    "recommended_price_in_range": in_range, "method": VW_METHOD}
                if len(valid) < 30:
                    details["van_westendorp"]["caveat"] = "Fewer than 30 valid responses: directional only."
                ev = ctx.ledger.add(Evidence(
                    provenance="FOUNDER_REPORTED", source_type="founder_data",
                    title="Van Westendorp price survey (founder-submitted responses)",
                    excerpt=(f"{len(valid)} valid responses ({len(row_problems)} excluded). Acceptable range "
                             f"{vw['pmc']}-{vw['pme']} {currency} {billing_phrase(billing)}; recommended price {reference}."),
                    value=float(len(valid)), unit="valid responses", method="Van Westendorp PSM computed in code",
                    population="founder-recruited survey respondents"))
                evidence_ids.append(ev.evidence_id)
        reported = to_int(data.get("pricing_responses"))
        if reported is not None:
            if reported < 0:
                problems.append("pricing_responses cannot be negative")
            elif valid is None:
                observed["pricing_responses"] = float(reported)
            elif reported != len(valid):
                details["pricing_responses_note"] = (f"Founder reported {reported} responses; {len(valid)} valid raw "
                                                     "responses were counted instead.")

        visitors, clicks = to_int(data.get("pricing_page_visitors")), to_int(data.get("paid_plan_clicks"))
        if visitors is not None and clicks is not None:
            if visitors < 0 or clicks < 0 or clicks > visitors:
                problems.append("paid_plan_clicks must be between 0 and pricing_page_visitors")
            elif visitors == 0:
                details["click_test"] = {"visitors": 0, "clicks": clicks, "note": "no visitors: click rate undefined"}
            else:
                rate = round(clicks / visitors, 4)
                low, high = wilson_interval(clicks, visitors)
                observed["paid_plan_click_rate"] = rate
                details["click_test"] = {"visitors": visitors, "clicks": clicks, "click_rate": rate,
                                         "wilson_95": [low, high], "mocked": True}
                ev = ctx.ledger.add(Evidence(
                    provenance="FOUNDER_REPORTED", source_type="founder_data",
                    title="Pricing-page click test (MOCKED no-charge page, founder-reported counts)",
                    excerpt=f"{clicks}/{visitors} visitors clicked a paid plan ({rate:.1%}; Wilson 95% {low}-{high}).",
                    value=rate, unit="click rate", denominator=float(visitors),
                    method="clicks / unique visitors; Wilson interval computed in code"))
                evidence_ids.append(ev.evidence_id)
        elif (visitors is None) != (clicks is None):
            details["click_test"] = {"note": "both pricing_page_visitors and paid_plan_clicks are needed"}

        missing = [c.key for c in contract.criteria if observed.get(c.key) is None]
        if problems:
            details["problems"] = problems
            state = INVALID_DATA
        else:
            details["missing"] = missing
            state = measurement_state(contract, observed)
        notes = "Founder-reported pricing data; statistics computed in code"
        if problems:
            notes += "; INVALID: " + "; ".join(problems)
        elif missing:
            notes += f"; missing: {', '.join(missing)}"
        return Observation(observed=observed, measurement_state=state, evidence_ids=evidence_ids, details=details,
                           notes=notes)


# ---------------------------------------------------------------------------------------------- 4.2 legal drafts

BANNER = "DRAFT, not legal advice. Must be reviewed by a qualified lawyer before use."
ACKNOWLEDGMENT = "These are drafts, not legal advice; a qualified lawyer must review them before any real use."
COUNSEL = "TO CONFIRM WITH COUNSEL"

DEFAULT_DATA_INVENTORY: list[dict[str, str]] = [
    {"data": "Waitlist email address", "collected_when": "A visitor joins the waitlist on the landing page",
     "stored_as": "A one-way hash of the email, a consent flag and a timestamp (the plain email is not kept by the prototype)",
     "purpose": "Count real sign-ups and record consent", "recipients": "None (stored locally by the prototype)",
     "retention": f"Not set yet: founder to decide ({COUNSEL})"},
    {"data": "Page-view events", "collected_when": "A visitor opens the landing, pricing or store page",
     "stored_as": "Page name, timestamp and a random visitor id generated for the browser (not linked to a name or email)",
     "purpose": "Count unique visitors for the demand tests", "recipients": "None (stored locally by the prototype)",
     "retention": f"Not set yet: founder to decide ({COUNSEL})"},
    {"data": "Mock order requests (MOCKED)", "collected_when": "A visitor clicks Buy on the store page",
     "stored_as": "Order id, product id, timestamp and the random visitor id; no-charge, nothing is sold",
     "purpose": "Measure buy intent and test the MOCKED delivery flow", "recipients": "None (stored locally by the prototype)",
     "retention": f"Not set yet: founder to decide ({COUNSEL})"},
    {"data": "Payment data", "collected_when": "Never", "stored_as": "Not collected: no card, bank or payment details; no payment provider",
     "purpose": "-", "recipients": "-", "retention": "-"},
]

_COMPLIANCE_CLAIM = re.compile(
    r"\b(?:fully\s+|legally\s+)?compliant\b"
    r"|\bin\s+(?:full\s+)?compliance\s+with\b"
    r"|\b(?:we|this\s+(?:policy|document|service|product|site|website|app|draft)|our\s+\w+|the\s+(?:service|product|policy|platform|app))\s+(?:fully\s+)?compl(?:y|ies)\s+with\b"
    r"|\bmeets?\s+(?:all\s+)?(?:applicable\s+)?(?:legal|regulatory)\s+requirements\b"
    r"|\b(?:guarantee[sd]?|ensures?)\s+(?:full\s+)?(?:legal\s+)?compliance\b"
    r"|\blegally\s+(?:approved|vetted|cleared)\b"
    r"|\b(?:approved|reviewed|vetted)\s+by\s+(?:a\s+|our\s+)?(?:lawyer|counsel|attorney|legal\s+team)\b",
    re.IGNORECASE)
_REMOVED = f"[Removed by the drafting check: drafts never claim legal compliance. {COUNSEL}.]"
_NEGATION = re.compile(r"\b(no|not|never|nothing|none|neither|nor|without)\b", re.IGNORECASE)
_PAYMENT_TAKEN = re.compile(
    r"\b(card|bank|charged?|chargebacks?|billing details|payment (?:was|is|has been) (?:taken|processed|made)|"
    r"refunds? (?:will be|are|is) (?:issued|processed|paid)|refund (?:your|the) (?:payment|money|purchase price))\b",
    re.IGNORECASE)
_UNLISTED_DATA = re.compile(
    r"\b(credit card|card numbers?|payment (?:information|details|data)|bank (?:account|details)|google analytics|"
    r"facebook pixel|meta pixel|advertising (?:cookies|partners)|third[- ]party (?:analytics|trackers?)|"
    r"cookies?|ip address(?:es)?|location data|phone numbers?|date of birth)\b", re.IGNORECASE)


def _split_sentences(line: str) -> tuple[str, list[str]]:
    prefix = re.match(r"^(\s*(?:[-*+]|\d+\.|>|#+)?\s*)", line).group(1)
    return prefix, re.split(r"(?<=[.!?])\s+", line[len(prefix):])


def remove_compliance_claims(text: str) -> tuple[str, int]:
    """Replace every sentence that claims legal compliance; return the text and the number removed."""
    removed = 0
    out_lines = []
    for line in text.splitlines():
        if not _COMPLIANCE_CLAIM.search(line) or line.strip() == BANNER:
            out_lines.append(line)
            continue
        prefix, sentences = _split_sentences(line)
        kept = []
        for sentence in sentences:
            if _COMPLIANCE_CLAIM.search(sentence):
                removed += 1
                if not kept or kept[-1] != _REMOVED:
                    kept.append(_REMOVED)
            else:
                kept.append(sentence)
        out_lines.append(prefix + " ".join(kept))
    return "\n".join(out_lines), removed


def _strip_banner_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if "not legal advice" not in line.lower()).strip()


def finalize_doc(text: str, jurisdiction: str | None, notes: list[str], name: str) -> str:
    """Enforce the exact banner first, the jurisdiction line, and no compliance claims."""
    text, removed = remove_compliance_claims(text.strip())
    if removed:
        notes.append(f"{name}: removed {removed} statement(s) claiming legal compliance.")
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    first = lines[0].strip() if lines else ""
    if first == BANNER:
        lines.pop(0)
    elif "not legal advice" in first.lower():
        lines.pop(0)
        notes.append(f"{name}: draft banner normalised to the exact required wording.")
    elif any("not legal advice" in line.lower() for line in lines):
        notes.append(f"{name}: draft banner was not the first line; it was moved to the top with the exact wording.")
    else:
        notes.append(f"{name}: the model omitted the draft banner; it was added.")
    lines = [line for line in lines if "not legal advice" not in line.lower()]
    if jurisdiction:
        where = (f"> Jurisdiction (from the founder's brief): {jurisdiction}. Every statement about a specific law "
                 f"is {COUNSEL}.")
    else:
        where = f"> Jurisdiction: not provided. Every jurisdiction-specific clause is {COUNSEL}."
    body = "\n".join(lines).strip()
    return f"{BANNER}\n\n{where}\n\n{body}\n"


def _safe_sentences(text: str, pattern: re.Pattern[str]) -> tuple[str, int]:
    """Drop sentences matching pattern unless they are negated ("no card details are collected")."""
    dropped = 0
    out_lines = []
    for line in text.splitlines():
        if not pattern.search(line):
            out_lines.append(line)
            continue
        prefix, sentences = _split_sentences(line)
        kept = [s for s in sentences if not pattern.search(s) or _NEGATION.search(s)]
        dropped += len(sentences) - len(kept)
        if kept:
            out_lines.append(prefix + " ".join(kept))
    return "\n".join(out_lines).strip(), dropped


REFUND_TODAY = (
    f"## Today: no payments ({MOCK_NOTE})\n\n"
    "No payment is taken today. Any order placed through the prototype is a MOCKED, no-charge request that the "
    "prototype records to test delivery. No card, bank or other payment details are requested or stored, and no "
    "payment provider is connected. Because nothing is charged, there is nothing to refund.\n")
REFUND_FUTURE_HEADER = (
    "## If real payments are introduced later (CONDITIONAL)\n\n"
    "> CONDITIONAL: the terms in this section apply only if and when real payments are introduced, and only after a "
    "qualified lawyer has reviewed them. They do not apply today.\n")


def data_inventory(ctx: StepContext) -> list[dict[str, str]]:
    """What the prototype actually handles: from the build (3.2) when it reports one, else the default inventory."""
    reported = ctx.prior("3.2").get("data_inventory")
    if isinstance(reported, list) and reported and all(isinstance(r, dict) for r in reported):
        return [{k: str(v) for k, v in r.items()} for r in reported]
    return DEFAULT_DATA_INVENTORY


def inventory_markdown(inventory: list[dict[str, str]]) -> str:
    cols = ["data", "collected_when", "stored_as", "purpose", "recipients", "retention"]
    lines = ["| Data | Collected when | Stored as | Purpose | Recipients | Retention |", "|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(cell(row.get(c)) for c in cols) + " |" for row in inventory]
    return "\n".join(lines)


def policy_html(title: str, text: str) -> str:
    body = "\n".join(line for line in text.splitlines() if line.strip() != BANNER)
    # Escape raw HTML from the model before Markdown conversion so the page stays inert.
    body_html = md_lib.markdown(body.replace("<", "&lt;"), extensions=["tables"])
    return html_page(title, body_html, banner=BANNER,
                     footer=f"Local {MOCK_NOTE} site: this draft is published only to the prototype's local folder.")


class LegalDrafts(StepHandler):
    """4.2 Draft legal policies (gate A; approval also requires acknowledging that a lawyer must review them)."""

    def generate(self, ctx: StepContext) -> StepOutput:
        concept = ctx.concept()
        jurisdiction = str(ctx.brief.get("jurisdiction") or "").strip() or None
        pricing = ctx.prior("4.1")
        inventory = data_inventory(ctx)
        payload = {
            "product": concept,
            "jurisdiction": jurisdiction,
            "data_inventory": inventory,
            "pricing": {"packages": [{k: p.get(k) for k in ("name", "price", "currency", "billing")}
                                     for p in as_list(pricing.get("packages")) if isinstance(p, dict)],
                        "status": "prospective prices; no payment is taken; orders are MOCKED"},
            "support_contact": ctx.brief.get("contact") or ctx.brief.get("support_email") or None,
            "feedback": ctx.feedback,
        }
        reply = legal_drafter.policies(ctx, payload)
        notes: list[str] = []

        terms = finalize_doc(reply["terms"], jurisdiction, notes, "Terms")
        privacy_body = (reply["privacy"].rstrip() + "\n\n## Data the prototype handles today (from the build)\n\n"
                        + inventory_markdown(inventory) + "\n\nIf anything above contradicts this table, the table "
                        "describes the prototype as built: fix the text before use.\n")
        privacy = finalize_doc(privacy_body, jurisdiction, notes, "Privacy")

        current, dropped = _safe_sentences(_strip_banner_lines(reply["refund_current"]), _PAYMENT_TAKEN)
        if dropped:
            notes.append(f"Refund: dropped {dropped} sentence(s) that described payments or refunds of money as "
                         "happening today; the MOCKED no-payment description replaces them.")
        future = _strip_banner_lines(reply["refund_future_conditional"]) or (
            f"Not drafted yet. {COUNSEL} before any paid launch.")
        refund_body = ("# Refund Policy\n\n" + REFUND_TODAY + ("\n" + current + "\n" if current else "") + "\n"
                       + REFUND_FUTURE_HEADER + "\n" + future + "\n")
        refund = finalize_doc(refund_body, jurisdiction, notes, "Refund")

        discrepancies = list(reply["build_discrepancies"])
        for sentence_text in re.split(r"(?<=[.!?])\s+|\n", privacy):
            match = _UNLISTED_DATA.search(sentence_text)
            if match and not _NEGATION.search(sentence_text) and "|" not in sentence_text:
                discrepancies.append(f"Privacy draft mentions '{match.group(0)}', which the data inventory does not "
                                     "list: verify it in the build or remove it.")
        discrepancies = list(dict.fromkeys(discrepancies))[:10]

        checklist = [
            "Have a qualified lawyer review all three drafts before any real use.",
            "Confirm the jurisdiction, the buyer jurisdictions and the legal entity or founder role." if not jurisdiction
            else f"Confirm that {jurisdiction} is the governing jurisdiction and where buyers are located.",
            "Set retention and deletion periods for waitlist hashes, page-view events and mock orders.",
            "Add a real support and privacy contact address to every policy.",
            "Link the policies from the landing, pricing and store pages.",
            "Replace the MOCKED refund section with counsel-reviewed terms before any real payment is introduced.",
        ] + reply["implementation_checklist"]
        counsel = [
            "Which consumer-protection and data-protection rules apply to this product, founder and buyers?",
            "Is a hashed email with a consent flag enough to show valid consent for a waitlist here?",
            "What must change in these drafts before real payments or refunds are introduced?",
        ] + reply["counsel_questions"]
        checklist = list(dict.fromkeys(checklist))[:15]
        counsel = list(dict.fromkeys(counsel))[:12]

        files = {"terms.md": terms, "privacy.md": privacy, "refund.md": refund,
                 "terms.html": policy_html("Terms of Service (DRAFT)", terms),
                 "privacy.html": policy_html("Privacy Policy (DRAFT)", privacy),
                 "refund.html": policy_html("Refund Policy (DRAFT)", refund)}
        questions = list(reply["questions"])
        if not jurisdiction:
            questions.insert(0, "Which country (and state, if any) is your business based in, and where are your buyers?")
        markdown = self._markdown(jurisdiction, inventory, notes, checklist, counsel, discrepancies, terms, privacy,
                                  refund)
        data = {
            "requires_acknowledgment": ACKNOWLEDGMENT,
            "policies": {"terms": "terms.html", "privacy": "privacy.html", "refund": "refund.html"},
            "policies_markdown": {"terms": "terms.md", "privacy": "privacy.md", "refund": "refund.md"},
            "banner": BANNER, "jurisdiction": jurisdiction, "data_inventory": inventory,
            "implementation_checklist": checklist, "counsel_questions": counsel,
            "build_discrepancies": discrepancies, "enforcement_notes": notes, "mocked": ["refund workflow", "publishing"],
            "outward": [{"kind": "publish", "item_id": f"policy-{name}", "file": f"{name}.html", "when": "on_approve",
                         "target_name": f"{name}.html"} for name in ("terms", "privacy", "refund")],
        }
        claims = [Claim(text="The policy drafts describe the data inventory of the prototype as built", label="ASSUMPTION",
                        basis="inventory supplied by the build step or the default prototype inventory; verify against the code")]
        return StepOutput(
            title="Draft Terms, Privacy and Refund policies (not legal advice)", markdown=markdown, data=data,
            files=files, claims=claims,
            summary=("Drafted Terms, Privacy and Refund policies tailored to the prototype's data. They are drafts, "
                     "not legal advice: a qualified lawyer must review them before any real use."),
            questions=questions[:3])

    @staticmethod
    def _markdown(jurisdiction, inventory, notes, checklist, counsel, discrepancies, terms, privacy, refund) -> str:
        lines = [f"**{BANNER}**", "",
                 "Approving this step requires acknowledging that these are drafts and that a qualified lawyer must "
                 f"review them. Approval publishes the HTML versions to the local {MOCK_NOTE} site only.", "",
                 f"Jurisdiction: **{jurisdiction or 'not provided'}**"
                 + ("" if jurisdiction else f" (jurisdiction-specific clauses are marked {COUNSEL})"), "",
                 "| Document | Markdown | Page |", "|---|---|---|",
                 "| Terms of Service | terms.md | terms.html |", "| Privacy Policy | privacy.md | privacy.html |",
                 "| Refund Policy | refund.md | refund.html |", "",
                 "## Data the prototype handles", "", inventory_markdown(inventory), "",
                 "## Implementation checklist", ""] + [f"- [ ] {item}" for item in checklist]
        lines += ["", "## Questions for counsel", ""] + [f"{i}. {q}" for i, q in enumerate(counsel, start=1)]
        if discrepancies:
            lines += ["", "## Discrepancies between the build and the drafts", ""] + [f"- {d}" for d in discrepancies]
        if notes:
            lines += ["", "## Checks applied in code", ""] + [f"- {n}" for n in notes]
        def nested(text: str) -> str:  # keep the drafts' headings below this deliverable's own headings
            return re.sub(r"^(#+)", r"###\1", text, flags=re.MULTILINE)

        lines += ["", "## Full drafts", "", "### terms.md", "", nested(terms), "", "### privacy.md", "",
                  nested(privacy), "", "### refund.md", "", nested(refund)]
        return "\n".join(lines)
