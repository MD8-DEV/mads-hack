"""Pricing analyst agent (step 4.1): packages and the three price anchors.

The model proposes packages, the economics inputs (variable cost per customer
and a target margin, each labelled with a basis) and a customer-value
estimate. It never computes the floor, the sample bills or any comparison:
phases/commercial.py does that arithmetic. Comparable prices come only from
evidence rows the step hands over; the model may cite their IDs, nothing else.
"""
from __future__ import annotations

import re
from typing import Any

from agents.base import StepContext, as_list, call_agent

BILLING_PERIODS = ("month", "year", "one-time")
VALUE_LABELS = ("ESTIMATE", "ASSUMPTION", "FOUNDER_REPORTED", "SOURCED", "UNKNOWN")


def to_number(value: Any) -> float | None:
    """Lenient number parser: accepts 19, "19", "$19", "EGP 1,200", "19.5/mo"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def norm_billing(value: Any, default: str = "month") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if re.search(r"one[- ]?(time|off)|once|lifetime|single|per purchase|perpetual", text):
        return "one-time"
    if re.search(r"year|annual|/yr|\byr\b", text):
        return "year"
    if re.search(r"month|/mo\b|\bmo\b", text):
        return "month"
    return default


def norm_margin(value: Any) -> float | None:
    """A margin as a fraction in [0, 0.95]; 70 or "70%" become 0.7."""
    number = to_number(value)
    if number is None:
        return None
    if number > 1:
        number = number / 100.0
    if number < 0 or number > 0.95:
        return None
    return round(number, 4)


def _label(value: Any, default: str) -> str:
    text = str(value or "").strip().upper()
    return text if text in VALUE_LABELS else default


def _strs(value: Any, limit: int = 6) -> list[str]:
    return [str(x).strip() for x in as_list(value) if str(x).strip()][:limit]


def _usage(raw: Any) -> dict[str, float | None]:
    raw = raw if isinstance(raw, dict) else {}
    return {level: to_number(raw.get(level)) for level in ("low", "typical", "high")}


def validate_pricing_options(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    packages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(p for p in as_list(data.get("packages")) if isinstance(p, dict)):
        price = to_number(raw.get("price"))
        if price is None or price < 0:
            continue
        pid = re.sub(r"[^a-z0-9_-]+", "-", str(raw.get("id") or raw.get("name") or f"p{index + 1}").lower()).strip("-")
        pid = pid or f"p{index + 1}"
        if pid in seen:
            pid = f"{pid}-{index + 1}"
        seen.add(pid)
        packages.append({
            "id": pid,
            "name": str(raw.get("name") or pid).strip()[:60],
            "price": round(price, 2),
            "billing": norm_billing(raw.get("billing")),
            "price_metric": str(raw.get("price_metric") or "per account").strip()[:60],
            "metered": bool(raw.get("metered")),
            "usage_unit": str(raw.get("usage_unit") or "").strip()[:60],
            "usage_examples": _usage(raw.get("usage_examples")),
            "includes": _strs(raw.get("includes"), 8),
            "upgrade_trigger": str(raw.get("upgrade_trigger") or "").strip()[:240],
            "likely_objections": _strs(raw.get("likely_objections"), 5),
            "cost_to_serve_note": str(raw.get("cost_to_serve_note") or "").strip()[:240],
        })
        if len(packages) == 3:
            break
    if not packages:
        raise ValueError("'packages' must hold 2-3 objects, each with a numeric 'price'")

    econ = data.get("economics") if isinstance(data.get("economics"), dict) else {}
    variable_cost = to_number(econ.get("variable_cost_per_customer"))
    economics = {
        "variable_cost_per_customer": None if variable_cost is None or variable_cost < 0 else round(variable_cost, 4),
        "period": norm_billing(econ.get("period"), default=packages[0]["billing"]),
        "variable_cost_label": _label(econ.get("variable_cost_label"), "ESTIMATE"),
        "variable_cost_basis": str(econ.get("variable_cost_basis") or "").strip()[:400],
        "target_margin": norm_margin(econ.get("target_margin")),
        "target_margin_label": _label(econ.get("target_margin_label"), "ASSUMPTION"),
        "target_margin_basis": str(econ.get("target_margin_basis") or "").strip()[:400],
        "high_usage_note": str(econ.get("high_usage_note") or "").strip()[:400],
    }
    value = data.get("customer_value") if isinstance(data.get("customer_value"), dict) else {}
    estimate = to_number(value.get("estimate"))
    customer_value = {
        "estimate": None if estimate is None or estimate < 0 else round(estimate, 2),
        "period": norm_billing(value.get("period"), default=economics["period"]),
        "label": _label(value.get("label"), "ESTIMATE"),
        "basis": str(value.get("basis") or "").strip()[:500],
        "evidence_ids": _strs(value.get("evidence_ids"), 10),
    }
    outside = data.get("outside_option") if isinstance(data.get("outside_option"), dict) else {}
    outside_option = {
        "summary": str(outside.get("summary") or "").strip()[:600],
        "workaround": str(outside.get("workaround") or "").strip()[:400],
        "evidence_ids": _strs(outside.get("evidence_ids"), 12),
    }
    ids = [p["id"] for p in packages]
    recommended = str(data.get("recommended_package_id") or "").strip().lower()
    if recommended not in ids:
        recommended = ids[min(1, len(ids) - 1)]
    claims = []
    for raw in as_list(data.get("claims")):
        if isinstance(raw, dict) and str(raw.get("text") or "").strip():
            claims.append({"text": str(raw["text"]).strip()[:400], "label": _label(raw.get("label"), "ASSUMPTION"),
                           "evidence_ids": _strs(raw.get("evidence_ids"), 8),
                           "basis": str(raw.get("basis") or "").strip()[:300]})
    return {
        "packages": packages,
        "recommended_package_id": recommended,
        "economics": economics,
        "customer_value": customer_value,
        "outside_option": outside_option,
        "rationale": str(data.get("rationale") or "").strip()[:1200],
        "bundle_description": str(data.get("bundle_description") or "").strip()[:400],
        "page_headline": str(data.get("page_headline") or "").strip()[:120],
        "claims": claims[:8],
        "questions": _strs(data.get("questions"), 3),
    }


def pricing_options(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    """2-3 packages plus the economics and value anchors (labelled; arithmetic is done by the caller)."""
    return call_agent(ctx, role="pricing_analyst", task="pricing_options", payload=payload, tier="main",
                      max_tokens=3500, validate=validate_pricing_options,
                      description="Pricing analyst proposed packages and the three price anchors (prospective prices)")
