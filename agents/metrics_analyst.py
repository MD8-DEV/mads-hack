"""Metrics analyst agent (step 6.2): the decision-dashboard specification.

The model writes metric definitions (numerator, denominator, window, cohort
rule) tailored to the product's value event. It never reports a value: code
computes what the local first-party events can show and marks everything
else "not observable yet" (phases/operate.py).
"""
from __future__ import annotations

import re
from typing import Any

from agents.base import StepContext, as_float, as_list, call_agent


def _s(value: Any, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def validate_dashboard_spec(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply must be a JSON object")
    metrics = []
    for raw in as_list(data.get("metrics")):
        if not isinstance(raw, dict) or not (raw.get("key") or raw.get("name")):
            continue
        key = re.sub(r"[^a-z0-9_]+", "_", _s(raw.get("key") or raw.get("name"), 60).lower()).strip("_")
        metrics.append({"key": key, "name": _s(raw.get("name") or key, 80), "question": _s(raw.get("question")),
                        "numerator": _s(raw.get("numerator")), "denominator": _s(raw.get("denominator")),
                        "window": _s(raw.get("window"), 160), "cohort_rule": _s(raw.get("cohort_rule")),
                        "data_source": _s(raw.get("data_source"), 200)})
    if not metrics and not data.get("value_event"):
        raise ValueError("reply needs 'metrics' (a list of definitions) and 'value_event'")
    window = as_float(data.get("activation_window_days"))
    return {
        "value_event": _s(data.get("value_event"), 300),
        "activation_window_days": int(window) if window and window > 0 else None,
        "metrics": metrics[:14],
        "data_quality_checks": [_s(x, 300) for x in as_list(data.get("data_quality_checks")) if _s(x)][:10],
        "instrumentation_gaps": [_s(x, 300) for x in as_list(data.get("instrumentation_gaps")) if _s(x)][:10],
        "questions": [_s(x, 300) for x in as_list(data.get("questions")) if _s(x)][:3],
    }


def dashboard_spec(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Metric definitions for the decision dashboard (definitions only, never values)."""
    return call_agent(ctx, role="metrics_analyst", task="dashboard_spec", payload=payload, tier="fast",
                      max_tokens=3500, validate=validate_dashboard_spec,
                      description="Metrics analyst defined the decision-dashboard metrics (numerator, denominator, window, cohort)")
