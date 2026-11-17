"""Nothing goes out without the founder's approval of the exact content (approval.py)."""
from __future__ import annotations

import pytest

from approval import ApprovalBook, ApprovalRequired, outward_subject, perform_outward_action
from logbook import DecisionLog, validate_entries


@pytest.fixture()
def book_and_log(tmp_path):
    return ApprovalBook(tmp_path / "approvals.json", run_id="r1"), DecisionLog(tmp_path / "log.json", run_id="r1")


def _publish(book, log, content, calls):
    return perform_outward_action(book=book, log=log, kind="publish", item_id="landing", content=content,
                                  executor=lambda: calls.append(content) or {"mocked": True, "published_to": "local"},
                                  phase=2, step_id="2.2", agent="growth_marketer")


def test_blocked_without_approval(book_and_log):
    book, log = book_and_log
    calls: list[str] = []
    with pytest.raises(ApprovalRequired):
        _publish(book, log, "<html>v1</html>", calls)
    assert calls == []
    entry = log.entries[-1]
    assert entry["action"] == "blocked_publish" and entry["approved_by"] is None


def test_rejected_content_stays_blocked(book_and_log):
    book, log = book_and_log
    content = "<html>v1</html>"
    book.record(subject=outward_subject("publish", "landing", content), decision="rejected", channel="cli")
    with pytest.raises(ApprovalRequired):
        _publish(book, log, content, [])


def test_changed_content_needs_a_new_approval(book_and_log):
    book, log = book_and_log
    book.record(subject=outward_subject("publish", "landing", "<html>v1</html>"), decision="approved", channel="cli")
    calls: list[str] = []
    with pytest.raises(ApprovalRequired):
        _publish(book, log, "<html>v2 with a change</html>", calls)
    assert calls == []


def test_approved_content_runs_mocked_and_is_logged(book_and_log):
    book, log = book_and_log
    content = "<html>v1</html>"
    book.record(subject=outward_subject("publish", "landing", content), decision="approved", channel="cli")
    calls: list[str] = []
    result = _publish(book, log, content, calls)
    assert calls == [content] and result["mocked"] is True
    entry = log.entries[-1]
    assert entry["action"] == "mock_publish" and entry["mocked"] is True
    assert entry["approved_by"] == "founder" and entry["approval_channel"] == "cli"
    assert not validate_entries(log.entries)


def test_approval_book_validates_inputs(book_and_log):
    book, _ = book_and_log
    with pytest.raises(ValueError):
        book.record(subject="x", decision="approved", channel="email")
    with pytest.raises(ValueError):
        book.record(subject="x", decision="maybe", channel="cli")
    with pytest.raises(ValueError):
        outward_subject("wire_money", "x", "y")
