"""Run the guardrail evals in evals/trick_prompts.yaml and print a pass/fail table.

    python evals/run_evals.py [path/to/trick_prompts.yaml]

Exit code 1 when a case misses (a trick prompt is not refused, or a legitimate
request is refused). Cases marked xfail are known pattern gaps: they are shown
as XFAIL and do not fail the run; if one starts passing it is shown as XPASS.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

import guardrails  # noqa: E402

DEFAULT_PATH = Path(__file__).resolve().parent / "trick_prompts.yaml"
CHECKS = {"request": guardrails.check_request, "idea": guardrails.check_idea,
          "marketing": guardrails.check_marketing}


def load_cases(path: Path | str = DEFAULT_PATH) -> dict[str, list[dict[str, Any]]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {key: list(data.get(key) or []) for key in ("refuse", "allow", "by_design")}


def expected_rules(case: dict[str, Any]) -> list[str]:
    rule = case.get("rule")
    if rule is None:
        return []
    return [str(r) for r in rule] if isinstance(rule, list) else [str(rule)]


def evaluate_case(case: dict[str, Any], expect_refusal: bool) -> tuple[bool, list[str]]:
    """Return (passed, rules that fired)."""
    check = CHECKS[case.get("check", "request")]
    found = [v.rule for v in check(str(case["text"]))]
    if expect_refusal:
        wanted = expected_rules(case)
        passed = bool(found) and (not wanted or any(rule in found for rule in wanted))
    else:
        passed = not found
    return passed, found


def run(path: Path | str = DEFAULT_PATH, out=print) -> int:
    cases = load_cases(path)
    rows: list[tuple[str, str, str, str, str]] = []
    misses = 0
    for group, expect in (("refuse", True), ("allow", False)):
        for case in cases[group]:
            passed, found = evaluate_case(case, expect)
            if case.get("xfail"):
                status = "XPASS" if passed else "XFAIL"
            else:
                status = "PASS" if passed else "MISS"
                misses += 0 if passed else 1
            expected = ("refuse: " + "|".join(expected_rules(case))) if expect else "allow"
            rows.append((status, case.get("id", "?"), case.get("check", "request"), expected,
                         ", ".join(found) or "-"))
    for case in cases["by_design"]:
        rows.append(("DESIGN", case.get("id", "?"), "data", "gate cannot pass", case.get("handled_by", "")))

    widths = [max(len(str(r[i])) for r in rows + [("Status", "Case", "Check", "Expected", "Fired")])
              for i in range(5)]
    widths = [min(w, 72) for w in widths]
    header = ("Status", "Case", "Check", "Expected", "Fired / handled by")
    out(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    out("-+-".join("-" * w for w in widths))
    for row in rows:
        out(" | ".join(str(c)[:w].ljust(w) for c, w in zip(row, widths)))
    counts = {s: sum(1 for r in rows if r[0] == s) for s in ("PASS", "MISS", "XFAIL", "XPASS", "DESIGN")}
    out("")
    out(f"{counts['PASS']} passed, {counts['MISS']} missed, {counts['XFAIL']} known gaps (xfail), "
        f"{counts['XPASS']} unexpectedly passing, {counts['DESIGN']} handled by design")
    for case in cases["refuse"]:
        if case.get("xfail"):
            out(f"Known gap {case['id']}: {case['xfail']}")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH))
