"""MOCKED refunds: a refund record that revokes product access.

No money moves: "money_moved" is always false and no provider is contacted.
One full refund per order; the same idempotency key (or a second refund for the
same order) returns the existing refund. A "refund.succeeded" event is emitted
so webhooks.handle_event() can revoke access too (idempotent).
"""
from __future__ import annotations

from typing import Any

from commerce import MOCK_NOTE, CommerceError, CommerceStore, IdempotencyConflict, InvalidState, new_id
from logbook import utc_now


def revoke_access(store: CommerceStore, data: dict[str, Any], order_id: str, reason: str) -> int:
    """Deactivate every access token of an order inside an open transaction. Returns how many changed."""
    changed = 0
    for token in store.find(data, "access_tokens", order_id=order_id):
        if token.get("active"):
            token["active"] = False
            token["revoked_at"] = utc_now()
            token["revoked_reason"] = reason
            changed += 1
    for delivery in store.find(data, "deliveries", order_id=order_id):
        delivery["access_revoked"] = True
        delivery["status"] = "revoked"
    return changed


def refund(store: CommerceStore, order_id: str, *, reason: str, idempotency_key: str) -> dict[str, Any]:
    """Record a MOCKED full refund for a mock-paid order and revoke its access."""
    key = (idempotency_key or "").strip()
    if not key:
        raise CommerceError("An idempotency key is required.")
    reason = (reason or "").strip()
    if not reason:
        raise CommerceError("A refund needs a reason.")
    with store.transaction() as data:
        existing = store.find_one(data, "refunds", idempotency_key=key)
        if existing is not None and existing["order_id"] != order_id:
            raise IdempotencyConflict("This idempotency key was already used for another refund.")
        existing = existing or store.find_one(data, "refunds", order_id=order_id, status="succeeded")
        if existing is not None:
            revoked = revoke_access(store, data, order_id, "refund")  # stays revoked even if re-enabled by mistake
            return {"refund": dict(existing), "event": dict(existing["event"]), "revoked_tokens": revoked,
                    "replayed": True, "mocked": True}
        order = store.order(data, order_id)
        payment = store.find_one(data, "payments", order_id=order_id, status="succeeded")
        if payment is None:
            raise InvalidState(f"Order {order_id} has no mock payment to refund.")
        refund_id = new_id("ref")
        event = {"id": new_id("evt"), "type": "refund.succeeded", "order_id": order_id, "refund_id": refund_id,
                 "created_at": utc_now(), "mocked": True, "fixture": store.fixture}
        record = store.stamp({
            "refund_id": refund_id,
            "order_id": order_id,
            "payment_id": payment["payment_id"],
            "idempotency_key": key,
            "amount": payment["amount"],
            "currency": payment["currency"],
            "reason": reason[:500],
            "status": "succeeded",
            "money_moved": False,
            "provider": None,
            "payout_id": None,
            "event": event,
            "note": "MOCKED refund record: no money moved. " + MOCK_NOTE,
        })
        data["refunds"].append(record)
        data["events"].append(event)
        revoked = revoke_access(store, data, order_id, "refund")
        order["status"] = "refunded"
        order["refund_id"] = refund_id
        order["updated_at"] = utc_now()
        return {"refund": dict(record), "event": dict(event), "revoked_tokens": revoked, "replayed": False,
                "mocked": True}
