"""Market analyst agent: ICP, market inputs, competitor and channel map (1.3).

The model proposes inputs with labels and evidence IDs. Code checks every
citation, computes TAM/SAM/SOM, and keeps prices and URLs only when they
appear in collected evidence (phases/discover.py).
"""
from __future__ import annotations

from typing import Any

from agents.base import StepContext, call_agent

ROLE = "market_analyst"


def _validate_market(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    if not data.get("market_inputs") and not data.get("competitors"):
        raise ValueError("market_inputs and competitors are missing")
    if not isinstance(data.get("market_inputs"), (list, dict)):
        data["market_inputs"] = []
    if not isinstance(data.get("competitors"), list):
        data["competitors"] = []
    if not isinstance(data.get("channels"), list):
        data["channels"] = []
    if not isinstance(data.get("icp"), dict):
        data["icp"] = {"description": str(data.get("icp") or "")}
    return data


def build_market_model(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="build_market_model", payload=payload, tier="main", max_tokens=4000,
                      validate=_validate_market, description="Built the ICP, market inputs, competitor and "
                      "channel map from collected evidence")
