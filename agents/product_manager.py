"""Product manager agent: scopes the smallest product that delivers the value proposition (step 3.1).

The model drafts the process map, first-value event, delivery mode, must-haves,
acceptance criteria, won't-build list and ceilings. Code then enforces the
rules the model may not bend:

* at most 5 must-haves (extra ones are cut, with a note);
* a must-have may cite only evidence IDs that exist in the ledger, otherwise
  it is labelled ASSUMPTION;
* features that would need payments, accounts or credentials move to the
  won't-build list (system policy);
* every acceptance criterion is machine-checkable against the built files:
  unknown check types, bad files, empty values, bad regexes and unsupported
  selectors are converted to a file_exists check on product/index.html, with a note.
"""
from __future__ import annotations

import re
from typing import Any

from agents import qa
from agents.base import StepContext, as_float, as_list, call_agent

ROLE = "product_manager"
MAX_MUST_HAVES = 5
MAX_ACCEPTANCE = 15
DELIVERY_MODES = ("concierge", "prototype", "working_product")
PRODUCT_KINDS = ("web_tool", "template_kit", "web_tool_and_templates")
PROCESS_KEYS = ("trigger", "input", "action", "output", "outcome")

# Features the system never builds into a product (payments, accounts, credentials).
POLICY_EXCLUDED = re.compile(
    r"\b(take|accept|process|collect|charge)\s+(card\s+)?payments?\b|\bcheckout\b|\bcredit[\s-]?cards?\b"
    r"|\bcard details\b|\b(stripe|paypal)\b|\blog[\s-]?ins?\b|\bsign[\s-]?in\b|\bsign[\s-]?ups?\b"
    r"|\b(user|customer) accounts?\b|\bpasswords?\b", re.I)
POLICY_REASON = "Out of scope by system policy: no payments, accounts or credential collection in the product."


def _text(value: Any, limit: int = 600) -> str:
    if isinstance(value, list):
        value = "; ".join(_text(v, limit) for v in value if v not in (None, ""))
    elif isinstance(value, dict):
        value = "; ".join(f"{k}: {_text(v, limit)}" for k, v in value.items() if v not in (None, ""))
    return " ".join(str(value or "").split())[:limit]


def _ids(value: Any) -> list[str]:
    out: list[str] = []
    for item in as_list(value):
        for found in re.findall(r"E-\d{3,}", str(item)):
            if found not in out:
                out.append(found)
    return out


def _bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "y", "1", "critical"):
            return True
        if lowered in ("false", "no", "n", "0"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _first(data: dict[str, Any], *keys: str) -> Any:
    """The first present, non-empty value (0 counts as a value)."""
    for key in keys:
        if data.get(key) not in (None, ""):
            return data[key]
    return None


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


# ------------------------------------------------------------------ model reply validation
def validate_scope(data: Any) -> dict[str, Any]:
    """Lenient shape check; raises ValueError only when the reply is unusable."""
    if not isinstance(data, dict):
        raise ValueError("expected one JSON object")
    musts = data.get("must_haves") or data.get("features") or []
    if isinstance(musts, dict):
        musts = [dict(v, id=k) if isinstance(v, dict) else {"id": k, "feature": v} for k, v in musts.items()]
    musts = [m if isinstance(m, dict) else {"feature": str(m)} for m in as_list(musts) if m]
    if not any(_text(m.get("feature") or m.get("name") or m.get("title")) for m in musts):
        raise ValueError("'must_haves' needs at least one feature with a name")
    criteria = [c for c in as_list(data.get("acceptance_criteria") or data.get("acceptance")) if isinstance(c, dict)]
    if not criteria:
        raise ValueError("'acceptance_criteria' needs at least one machine-checkable criterion")
    data["must_haves"] = musts
    data["acceptance_criteria"] = criteria
    return data


# ------------------------------------------------------------------ normalisation (code-enforced rules)
def normalize_check(raw: Any, criterion_id: str) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    check = dict(raw) if isinstance(raw, dict) else {}
    kind = _slug(check.get("type"))
    file_name = str(check.get("file") or qa.INDEX).strip().lstrip("./")
    value = check.get("value")
    value = "" if value is None else str(value)

    def fallback(reason: str) -> tuple[dict[str, Any], list[str]]:
        notes.append(f"{criterion_id}: {reason}; converted to a file_exists check on {qa.INDEX}.")
        return {"type": "file_exists", "file": qa.INDEX, "value": ""}, notes

    if kind not in qa.CHECK_TYPES:
        return fallback(f"unknown check type {check.get('type')!r}")
    if not qa.is_product_path(file_name):
        notes.append(f"{criterion_id}: file {file_name!r} is not a product file; checking {qa.INDEX} instead.")
        file_name = qa.INDEX
    if kind in ("html_element", "no_external_requests") and not file_name.endswith(".html"):
        notes.append(f"{criterion_id}: {kind} needs an HTML file; checking {qa.INDEX} instead of {file_name}.")
        file_name = qa.INDEX
    if kind == "file_exists":
        return {"type": kind, "file": file_name, "value": ""}, notes
    if kind == "no_external_requests":
        return {"type": kind, "file": file_name, "value": ""}, notes
    if not value.strip():
        return fallback(f"{kind} check has no value")
    if kind == "contains":
        return {"type": kind, "file": file_name, "value": value[:200]}, notes
    if kind == "regex":
        if len(value) > 300:
            return fallback("regex longer than 300 characters")
        try:
            re.compile(value)
        except re.error as exc:
            return fallback(f"invalid regex ({exc})")
        return {"type": kind, "file": file_name, "value": value}, notes
    # html_element: one compound selector; for "form#a button" keep the last compound.
    selector = value.strip()
    if qa.parse_selector(selector) is None:
        last = re.split(r"[\s>+~]+", selector)[-1] if selector else ""
        if last and qa.parse_selector(last) is not None:
            notes.append(f"{criterion_id}: selector {selector!r} simplified to {last!r} (one compound selector only).")
            selector = last
        else:
            return fallback(f"unsupported selector {value!r}")
    return {"type": kind, "file": file_name, "value": selector}, notes


def _resolve_feature(ref: str, ids: set[str], name_to_id: dict[str, str]) -> str:
    """Map an acceptance criterion's feature reference ("F2", "Export", "F2: Export") to a feature ID."""
    if ref in ids:
        return ref
    if _slug(ref) in name_to_id:
        return name_to_id[_slug(ref)]
    for token in re.findall(r"[A-Za-z]+\d+", ref):
        if token in ids:
            return token
    return ref


def normalize_scope(raw: dict[str, Any], known_ids: set[str],
                    provenance: dict[str, str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Apply the code-enforced scope rules. Returns (scope, notes)."""
    provenance = provenance or {}
    notes: list[str] = []

    # --- must-haves
    musts: list[dict[str, Any]] = []
    wont: list[dict[str, str]] = []
    for item in as_list(raw.get("wont_build") or raw.get("won't_build") or raw.get("exclusions")):
        if isinstance(item, dict):
            feature = _text(item.get("feature") or item.get("name") or item.get("item"), 200)
            reason = _text(item.get("reason") or item.get("why"), 300)
        else:
            feature, reason = _text(item, 200), ""
        if feature:
            wont.append({"feature": feature, "reason": reason or "Not needed to test the value proposition."})

    used_ids: set[str] = set()
    removed_ids: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    candidates = []
    for index, item in enumerate(raw.get("must_haves") or [], start=1):
        feature = _text(item.get("feature") or item.get("name") or item.get("title"), 200)
        if not feature:
            continue
        fid = _text(item.get("id"), 20) or f"F{index}"
        if fid in used_ids:
            fid = f"F{index}"
        used_ids.add(fid)
        value = _text(item.get("user_value") or item.get("why") or item.get("description"), 400)
        if POLICY_EXCLUDED.search(f"{feature} {value}"):
            wont.append({"feature": feature, "reason": POLICY_REASON})
            removed_ids[fid] = "moved to won't-build by system policy"
            name_to_id[_slug(feature)] = fid
            notes.append(f"{fid} '{feature}' moved to the won't-build list: {POLICY_REASON}")
            continue
        candidates.append((fid, feature, value, item))
    if len(candidates) > MAX_MUST_HAVES:
        cut = candidates[MAX_MUST_HAVES:]
        candidates = candidates[:MAX_MUST_HAVES]
        for fid, feature, _, _ in cut:
            removed_ids[fid] = "cut: more than 5 must-haves"
            name_to_id[_slug(feature)] = fid
            wont.append({"feature": feature, "reason": "Cut to keep at most 5 must-haves (deferred, not rejected)."})
        notes.append(f"The model proposed {len(candidates) + len(cut)} must-haves; kept the first {MAX_MUST_HAVES} "
                     f"and moved {', '.join(f for _, f, _, _ in cut)} to the won't-build list.")
    for fid, feature, value, item in candidates:
        cited = _ids(item.get("evidence_ids") or item.get("evidence"))
        valid = [i for i in cited if i in known_ids]
        if cited and len(valid) < len(cited):
            notes.append(f"{fid}: dropped unknown evidence IDs {[i for i in cited if i not in known_ids]}.")
        if valid:
            reported = all(provenance.get(i) in ("FOUNDER_REPORTED", "PARTICIPANT_REPORTED") for i in valid)
            label = "FOUNDER_REPORTED" if reported else "SOURCED"
            basis = _text(item.get("basis"), 300)
        else:
            label = "ASSUMPTION"
            basis = _text(item.get("basis"), 300) or "No evidence row supports this feature yet."
        name_to_id[_slug(feature)] = fid
        musts.append({"id": fid, "feature": feature, "user_value": value, "evidence_ids": valid, "label": label,
                      "basis": basis, "critical_path": _bool(item.get("critical_path"), True)})

    # --- acceptance criteria
    kept_ids = {m["id"] for m in musts}
    criteria: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw.get("acceptance_criteria") or [], start=1):
        cid = _text(item.get("id"), 20) or f"AC{index}"
        if cid in seen or cid.startswith("G"):   # G* ids are reserved for generic QA checks
            cid = f"AC{index}"
        seen.add(cid)
        feature_ref = _text(item.get("feature") or item.get("feature_id"), 200)
        feature_id = _resolve_feature(feature_ref, kept_ids | set(removed_ids), name_to_id)
        if feature_id in removed_ids:
            notes.append(f"{cid} dropped: its feature {feature_id} was {removed_ids[feature_id]}.")
            continue
        if feature_id and feature_id not in kept_ids:
            notes.append(f"{cid}: feature reference {feature_ref!r} matches no must-have; kept as a general criterion.")
        check, check_notes = normalize_check(item.get("check"), cid)
        notes += check_notes
        criteria.append({"id": cid, "feature": feature_id if feature_id in kept_ids else "",
                         "description": _text(item.get("description"), 300) or f"{check['type']} {check['value']}".strip(),
                         "critical": _bool(item.get("critical"), True), "check": check})
    if len(criteria) > MAX_ACCEPTANCE:
        notes.append(f"Kept the first {MAX_ACCEPTANCE} of {len(criteria)} acceptance criteria.")
        criteria = criteria[:MAX_ACCEPTANCE]
    if not criteria:
        criteria.append({"id": "AC1", "feature": musts[0]["id"] if musts else "",
                         "description": "The product page exists.", "critical": True,
                         "check": {"type": "file_exists", "file": qa.INDEX, "value": ""}})
        notes.append("No usable acceptance criterion remained; added a file_exists check. Ask for a rescope.")
    for must in musts:
        if not any(c["feature"] == must["id"] for c in criteria):
            notes.append(f"{must['id']} '{must['feature']}' has no machine-checkable acceptance criterion.")

    # --- the rest of the spec
    process = raw.get("process_map") if isinstance(raw.get("process_map"), dict) else {}
    process_map = {k: _text(process.get(k), 300) for k in PROCESS_KEYS}
    fve = raw.get("first_value_event")
    if isinstance(fve, dict):
        first_value = {"event": _text(fve.get("event") or fve.get("name"), 300),
                       "how_observed": _text(fve.get("how_observed") or fve.get("signal"), 300)}
    else:
        first_value = {"event": _text(fve, 300), "how_observed": ""}
    delivery = raw.get("delivery_mode") if isinstance(raw.get("delivery_mode"), dict) else {"mode": raw.get("delivery_mode")}
    mode = _slug(delivery.get("mode"))
    if mode not in DELIVERY_MODES:
        mode = {"working": "working_product", "product": "working_product", "manual": "concierge",
                "clickable_prototype": "prototype"}.get(mode, "prototype")
    kind = _slug(raw.get("product_kind"))
    if kind not in PRODUCT_KINDS:
        kind = "web_tool"
    baseline_raw = raw.get("baseline") if isinstance(raw.get("baseline"), dict) else {}
    baseline_ids = [i for i in _ids(baseline_raw.get("evidence_ids")) if i in known_ids]
    baseline_label = str(baseline_raw.get("label") or "").upper()
    measure = _text(baseline_raw.get("baseline_measure") or baseline_raw.get("measure"), 300)
    if baseline_ids:
        baseline_label = "FOUNDER_REPORTED" if all(
            provenance.get(i) in ("FOUNDER_REPORTED", "PARTICIPANT_REPORTED") for i in baseline_ids) else "SOURCED"
    elif not measure:
        baseline_label = "UNKNOWN"
    elif baseline_label not in ("ESTIMATE", "ASSUMPTION", "UNKNOWN"):
        baseline_label = "ASSUMPTION"
    ceilings_raw = raw.get("ceilings") if isinstance(raw.get("ceilings"), dict) else {}
    hours = as_float(_first(ceilings_raw, "build_hours", "time_hours"))
    budget = as_float(_first(ceilings_raw, "budget_usd", "budget"))
    scope = {
        "product_name": _text(raw.get("product_name") or raw.get("name"), 80) or "MVP",
        "product_kind": kind,
        "uvp": _text(raw.get("uvp") or raw.get("value_proposition"), 300),
        "process_map": process_map,
        "first_value_event": first_value,
        "delivery_mode": {"mode": mode, "rationale": _text(delivery.get("rationale"), 500),
                          "alternatives_considered": _text(delivery.get("alternatives_considered"), 500)},
        "baseline": {"current_alternative": _text(baseline_raw.get("current_alternative"), 300),
                     "baseline_measure": measure or "Not measured yet.", "label": baseline_label,
                     "evidence_ids": baseline_ids,
                     "minimum_useful_improvement": _text(baseline_raw.get("minimum_useful_improvement"), 300)},
        "must_haves": musts,
        "acceptance_criteria": criteria,
        "wont_build": wont,
        "ceilings": {"build_hours": hours if hours is not None and hours >= 0 else None,
                     "budget_usd": budget if budget is not None and budget >= 0 else None,
                     "basis": _text(ceilings_raw.get("basis"), 300)},
        "risks": [_text(r, 300) for r in as_list(raw.get("risks") or raw.get("cannot_deliver")) if _text(r)][:6],
        "notes": notes,
    }
    return scope, notes


def mvp_scope(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Ask the model for the MVP scope (validated shape; normalised by the caller)."""
    return call_agent(ctx, role=ROLE, task="mvp_scope", payload=payload, tier="main", max_tokens=4000,
                      validate=validate_scope, description="Scoped the MVP: process map, must-haves, acceptance criteria")
