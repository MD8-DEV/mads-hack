"""Builder agent: writes the MVP files in one pass (step 3.2).

The product is a small, self-contained digital product: product/index.html
(inline CSS and JS, no network requests, data kept in the browser's
localStorage), product/README.md, and optionally markdown templates under
product/templates/. The model writes the files; agents/qa.py tests them.
"""
from __future__ import annotations

import re
from typing import Any

from agents import qa
from agents.base import StepContext, call_agent

ROLE = "builder"
MAX_FILE_CHARS = 400_000   # a single absurd file is rejected outright; the 200 KB cap is a QA test
_FENCE = re.compile(r"^\s*```[\w-]*\s*\n(.*?)\n?```\s*$", re.S)


def _unfence(content: str) -> str:
    match = _FENCE.match(content or "")
    return match.group(1) if match else (content or "")


def validate_build(data: Any) -> dict[str, Any]:
    """Accept {"files": {path: content}} or {"files": [{"path", "content"}]}; product/index.html is required."""
    if not isinstance(data, dict):
        raise ValueError("expected one JSON object with a 'files' map")
    raw = data.get("files")
    if isinstance(raw, list):
        raw = {str(f.get("path") or f.get("name") or ""): f.get("content") for f in raw if isinstance(f, dict)}
    if not isinstance(raw, dict) or not raw:
        raise ValueError("'files' must map file paths to file contents")
    files: dict[str, str] = {}
    dropped: list[str] = []
    for path, content in raw.items():
        name = str(path or "").strip().replace("\\", "/").lstrip("./")
        if name and not name.startswith("product/"):
            name = "product/" + name
        if not qa.is_product_path(name) or not isinstance(content, str):
            dropped.append(str(path))
            continue
        if len(content) > MAX_FILE_CHARS:
            raise ValueError(f"{name} is {len(content)} characters; keep the whole product under 200 KB")
        files[name] = _unfence(content)
    index = files.get(qa.INDEX, "")
    if "<" not in index or len(index.strip()) < 50:
        raise ValueError(f"'{qa.INDEX}' is missing or is not an HTML page")
    if len(files) > qa.MAX_FILES:
        keep = [qa.INDEX, qa.README] + [n for n in files if n not in (qa.INDEX, qa.README)]
        dropped += keep[qa.MAX_FILES:]
        files = {n: files[n] for n in keep[:qa.MAX_FILES] if n in files}
    return {"files": files, "product_name": str(data.get("product_name") or "")[:80],
            "notes": str(data.get("notes") or "")[:1500], "dropped_paths": dropped}


def build_product(ctx: StepContext, payload: dict[str, Any]) -> dict[str, Any]:
    return call_agent(ctx, role=ROLE, task="build_product", payload=payload, tier="main", max_tokens=16000,
                      validate=validate_build, description="Built the MVP files (product/index.html, product/README.md)")
