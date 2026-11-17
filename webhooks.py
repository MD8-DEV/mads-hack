"""MOCKED webhook handling for the sale-to-cash flow.

handle_event() is idempotent by event id: an event that was already processed
is acknowledged as a duplicate and never delivers twice. Handled types:

  payment.succeeded -> delivery.deliver() for the order (one delivery per order)
  refund.succeeded  -> access to the order's product is revoked

Unknown types are ignored and recorded. Events come from payments.py and
refunds.py in this process; no external provider sends webhooks here.
"""
from __future__ import annotations

from typing import Any

import delivery
from commerce import CommerceError, CommerceStore, InvalidState, UnknownOrder
from logbook import utc_now
from refunds import revoke_access

HANDLED_TYPES = ("payment.succeeded", "refund.succeeded")


def _record(store: CommerceStore, event: dict[str, Any], status: str, detail: str = "") -> None:
    with store.transaction() as data:
        if status != "duplicate" and event["id"] not in data["processed_event_ids"]:
            data["processed_event_ids"].append(event["id"])
        data["webhook_log"].append(store.stamp({"event_id": event["id"], "type": event.get("type"),
                                                "order_id": event.get("order_id"), "status": status,
                                                "detail": detail[:300], "at": utc_now(), "created_at": utc_now()}))


def handle_event(store: CommerceStore, event: dict[str, Any], *, email_sender=None) -> dict[str, Any]:
    """Process one mock event exactly once. Returns {"event_id", "type", "status", "result"}."""
    if not isinstance(event, dict) or not str(event.get("id") or "").strip():
        raise CommerceError("An event needs an id.")
    event_id, event_type = str(event["id"]), str(event.get("type") or "")
    with store.lock:
        if event_id in store.read()["processed_event_ids"]:
            _record(store, event, "duplicate", "already processed; nothing done")
            return {"event_id": event_id, "type": event_type, "status": "duplicate", "result": None}
        order_id = event.get("order_id")
        if event_type == "payment.succeeded":
            try:
                result = delivery.deliver(store, order_id, idempotency_key=f"deliver:{order_id}",
                                          email_sender=email_sender)
            except (InvalidState, UnknownOrder) as exc:
                _record(store, event, "rejected", str(exc))
                return {"event_id": event_id, "type": event_type, "status": "rejected", "result": str(exc)}
            _record(store, event, "processed", f"delivery {result['delivery']['delivery_id']}")
            return {"event_id": event_id, "type": event_type, "status": "processed", "result": result}
        if event_type == "refund.succeeded":
            try:
                with store.transaction() as data:
                    store.order(data, order_id)
                    revoked = revoke_access(store, data, order_id, "refund")
            except UnknownOrder as exc:
                _record(store, event, "rejected", str(exc))
                return {"event_id": event_id, "type": event_type, "status": "rejected", "result": str(exc)}
            _record(store, event, "processed", f"revoked {revoked} token(s)")
            return {"event_id": event_id, "type": event_type, "status": "processed",
                    "result": {"revoked_tokens": revoked}}
        _record(store, event, "ignored", f"unhandled event type {event_type!r}")
        return {"event_id": event_id, "type": event_type, "status": "ignored", "result": None}
