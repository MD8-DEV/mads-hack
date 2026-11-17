"""MOCKED automatic delivery: access token, download path and confirmation email.

deliver() creates exactly one delivery per order (idempotent), but only for an
order with a succeeded mock payment that was not refunded. The confirmation
email goes through `email_sender(message)`; the default sender only appends it
to the store outbox, marked "MOCKED: not sent". A sender that raises is
retried up to `max_email_attempts` times; every attempt is recorded, and the
delivery itself stays recorded even when the email finally fails.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from commerce import MOCK_NOTE, CommerceError, CommerceStore, IdempotencyConflict, InvalidState, new_id
from logbook import utc_now

EmailSender = Callable[[dict[str, Any]], Any]
NOT_SENT = "MOCKED: not sent"


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _message(email: dict[str, Any]) -> dict[str, Any]:
    return {k: email[k] for k in ("email_id", "order_id", "to_masked", "to_hash", "subject", "body")}


def _send_with_retries(store: CommerceStore, email_id: str, email_sender: EmailSender | None,
                       max_attempts: int) -> dict[str, Any]:
    """Try to hand one outbox email to the sender; record every attempt."""
    message = _message(store.find_one(store.read(), "emails", email_id=email_id))
    attempts: list[dict[str, Any]] = []
    status = "failed"
    for number in range(1, max(1, int(max_attempts)) + 1):
        try:
            if email_sender is not None:
                email_sender(dict(message))
            attempts.append({"attempt": number, "at": utc_now(), "ok": True, "error": None})
            status = NOT_SENT if email_sender is None else "accepted_by_sender"
            break
        except Exception as exc:  # noqa: BLE001 - any sender failure is recorded and retried
            attempts.append({"attempt": number, "at": utc_now(), "ok": False,
                             "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    with store.transaction() as data:
        email = store.find_one(data, "emails", email_id=email_id)
        email["attempts"] = email.get("attempts", []) + attempts
        email["status"] = status
        email["label"] = NOT_SENT if email_sender is None else "Handed to the configured email_sender (no real send in this prototype)"
        email["updated_at"] = utc_now()
        delivery = store.find_one(data, "deliveries", delivery_id=email["delivery_id"])
        if delivery is not None:
            delivery["email_status"] = status
            delivery["email_attempts"] = len(email["attempts"])
        return dict(email)


def deliver(store: CommerceStore, order_id: str, *, idempotency_key: str, email_sender: EmailSender | None = None,
            max_email_attempts: int = 3, access_days: int | None = None) -> dict[str, Any]:
    """Deliver a mock-paid order once: access token + download path + confirmation email (outbox)."""
    key = (idempotency_key or "").strip()
    if not key:
        raise CommerceError("An idempotency key is required.")
    with store.lock:
        with store.transaction() as data:
            existing = store.find_one(data, "deliveries", order_id=order_id)
            if existing is not None:
                email = store.find_one(data, "emails", email_id=existing.get("email_id"))
                return {"delivery": dict(existing), "email": dict(email) if email else None,
                        "access_url": existing["download_path"], "replayed": True, "mocked": True}
            other = store.find_one(data, "deliveries", idempotency_key=key)
            if other is not None:
                raise IdempotencyConflict("This idempotency key was already used for another delivery.")
            order = store.order(data, order_id)
            if order["status"] == "refunded":
                raise InvalidState(f"Order {order_id} was refunded; nothing to deliver.")
            payment = store.find_one(data, "payments", order_id=order_id, status="succeeded")
            if payment is None:
                raise InvalidState(f"Order {order_id} has no mock payment; delivery needs one first.")
            token = secrets.token_urlsafe(24)
            delivery_id, email_id = new_id("dlv"), new_id("eml")
            url = store.access_url(token)
            expires_at = _iso(datetime.now(timezone.utc) + timedelta(days=access_days)) if access_days else None
            delivery = store.stamp({
                "delivery_id": delivery_id,
                "order_id": order_id,
                "payment_id": payment["payment_id"],
                "idempotency_key": key,
                "product_id": order["product_id"],
                "access_token": token,
                "download_path": url,
                "status": "delivered",
                "access_revoked": False,
                "email_id": email_id,
                "email_status": "pending",
                "email_attempts": 0,
                "note": "MOCKED delivery: access link issued without any payment. " + MOCK_NOTE,
            })
            data["deliveries"].append(delivery)
            data["access_tokens"].append(store.stamp({
                "token": token, "order_id": order_id, "delivery_id": delivery_id,
                "product_id": order["product_id"], "active": True, "expires_at": expires_at,
                "revoked_at": None, "revoked_reason": None}))
            data["emails"].append(store.stamp({
                "email_id": email_id,
                "delivery_id": delivery_id,
                "order_id": order_id,
                "to_masked": order["buyer_email_masked"],
                "to_hash": order["buyer_email_hash"],
                "subject": f"Your access to {order['product_id']} (MOCKED delivery)",
                "body": (f"MOCKED: no payment was taken.\n\nYour access link: {url}\n\n"
                         f"Order {order_id}. This message sits in a local outbox and was not sent."),
                "status": "pending",
                "label": NOT_SENT,
                "attempts": [],
            }))
            order["status"] = "delivered"
            order["delivery_id"] = delivery_id
            order["updated_at"] = utc_now()
        email = _send_with_retries(store, email_id, email_sender, max_email_attempts)
        delivered = store.find_one(store.read(), "deliveries", delivery_id=delivery_id)
        return {"delivery": dict(delivered), "email": email, "access_url": url, "replayed": False, "mocked": True}


def retry_failed_emails(store: CommerceStore, *, email_sender: EmailSender | None = None,
                        max_email_attempts: int = 3) -> list[dict[str, Any]]:
    """Recovery: retry every outbox email whose status is "failed"."""
    with store.lock:
        failed = [e["email_id"] for e in store.read()["emails"] if e.get("status") == "failed"]
        return [_send_with_retries(store, email_id, email_sender, max_email_attempts) for email_id in failed]


def access_for(store: CommerceStore, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    record = store.find_one(store.read(), "access_tokens", token=token)
    return dict(record) if record else None


def has_access(store: CommerceStore, token: str, *, now: datetime | None = None) -> bool:
    """True only for a known, active, unexpired token whose order was not refunded."""
    data = store.read()
    record = store.find_one(data, "access_tokens", token=token) if token else None
    if record is None or not record.get("active") or record.get("revoked_at"):
        return False
    if record.get("expires_at") and record["expires_at"] <= _iso(now or datetime.now(timezone.utc)):
        return False
    order = store.find_one(data, "orders", order_id=record["order_id"])
    return bool(order) and order.get("status") != "refunded"
