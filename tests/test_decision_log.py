"""Decision-log format: required keys and types, append-only, approved_by values."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import ROOT
from logbook import REQUIRED_KEYS, DecisionLog, validate_entries


def test_entries_have_required_keys_and_types(tmp_path):
    log = DecisionLog(tmp_path / "log.json", run_id="r1")
    entry = log.append(agent="researcher", action="find_opportunities", action_type="RESEARCH", phase=1, step="1.3",
                       sources=["https://example.org/a", "not-a-url", "https://example.org/a"], model="stub/model",
                       cost=0)
    for key in REQUIRED_KEYS:
        assert key in entry
    assert entry["sources"] == ["https://example.org/a"]  # only URLs, deduplicated
    assert entry["cost"] == 0 and entry["approved_by"] is None
    gate = log.append(agent="gate_engine", action="landing_page_gate_e", action_type="GATE_DECISION", model=None)
    assert gate["model"] is None and gate["sources"] == []
    assert not validate_entries(log.entries)


def test_log_is_append_only(tmp_path):
    path = tmp_path / "log.json"
    log = DecisionLog(path, run_id="r1")
    first = log.append(agent="a", action="one", action_type="ANALYZE_DATA")
    log.append(agent="b", action="two", action_type="ANALYZE_DATA")
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert [e["action"] for e in stored] == ["one", "two"]
    assert stored[0] == first
    reopened = DecisionLog(path, run_id="r1")
    reopened.append(agent="c", action="three", action_type="ANALYZE_DATA")
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert [e["action"] for e in stored] == ["one", "two", "three"] and stored[0] == first
    assert len({e["log_id"] for e in stored}) == 3


def test_approved_by_and_action_type_are_validated(tmp_path):
    log = DecisionLog(tmp_path / "log.json")
    with pytest.raises(ValueError):
        log.append(agent="x", action="y", action_type="ANALYZE_DATA", approved_by="the agent")
    with pytest.raises(ValueError):
        log.append(agent="x", action="y", action_type="SOMETHING_ELSE")
    ok = log.append(agent="founder", action="approve_gate", action_type="FOUNDER_APPROVAL", approved_by="founder")
    assert ok["approved_by"] == "founder"


def test_validate_entries_reports_problems():
    bad = [{"timestamp": "t", "agent": "a", "action": 3, "sources": "x", "model": 1, "cost": "0",
            "approved_by": "someone"}, {"agent": "a"}]
    problems = validate_entries(bad)
    joined = " ".join(problems)
    for text in ("action must be a string", "sources must be a list", "model must be a string",
                 "cost must be a number", "approved_by must be", "missing timestamp"):
        assert text in joined


def test_committed_decision_log_is_valid():
    path = Path(ROOT) / "decision_log.json"
    if not path.exists():
        pytest.skip("no decision_log.json committed yet")
    entries = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(entries, list) and entries
    assert validate_entries(entries) == []
