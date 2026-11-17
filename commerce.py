"""MOCKED sale-to-cash records: a small JSON-file store.

Everything here is a record of a simulated flow. Nothing moves money, talks to
a payment provider, or touches card or bank data. Every record carries
"mocked": true, and buyer emails are stored only as a SHA-256 hash plus a
masked form (a***@domain).

Collections: orders, payments, fees, payouts, deliveries, refunds,
emails (the outbox; nothing is sent), events (emitted mock events),
processed_event_ids and webhook_log (idempotent event handling),
access_tokens (product access, revoked on refund).

Module map (sale to cash, all MOCKED):
  checkout.create_order        -> no-charge order request
  payments.record_mock_payment -> settlement record + "payment.succeeded" event
  webhooks.handle_event        -> idempotent event handling, triggers delivery
  delivery.deliver             -> one delivery per order, access token, confirmation email (outbox)
  refunds.refund               -> refund record, access revoked
  payments.record_mock_payout  -> payout record = nets minus refunds
  reconcile.reconcile          -> cross-checks every collection
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from logbook import _atomic_write_json, utc_now

MOCK_NOTE = "MOCKED: no money moved. No payment provider, no card or bank data."
COLLECTIONS = ("orders", "payments", "fees", "payouts", "deliveries", "refunds", "emails", "events",
               "processed_event_ids", "webhook_log", "access_tokens")
EMAIL_RE = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
MONEY_TOLERANCE = 0.005


class CommerceError(ValueError):
    """Base error for the mocked sale-to-cash flow."""


class UnknownOrder(CommerceError, LookupError):
    """The order id does not exist in this store."""


class InvalidState(CommerceError):
    """The requested step does not fit the order's current state (e.g. delivery before payment)."""


class IdempotencyConflict(CommerceError):
    """An idempotency key was reused for a different request."""


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def email_hash(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()


def mask_email(email: str) -> str:
    email = (email or "").strip()
    local, _, domain = email.partition("@")
    return f"{local[:1] or '?'}***@{domain.lower()}" if domain else "***"


def valid_email(email: str) -> bool:
    return bool(email) and len(email) <= 254 and bool(EMAIL_RE.match(email.strip()))


def money(value: float) -> float:
    return round(float(value) + 0.0, 2)


def same_money(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < MONEY_TOLERANCE


class CommerceStore:
    """JSON-file store with atomic writes and a per-file re-entrant lock.

    `fixture=True` marks every record as FIXTURE data (test runs), which analytics must exclude.
    `access_url_prefix` is where the web app serves product access (e.g. "/p/<run_id>/access/").
    """

    def __init__(self, path: Path | str, *, fixture: bool = False, access_url_prefix: str = "/access/"):
        self.path = Path(path)
        self.fixture = fixture
        self.access_url_prefix = access_url_prefix if access_url_prefix.endswith("/") else access_url_prefix + "/"
        self.lock = _lock_for(self.path)

    # --- raw file access
    def _empty(self) -> dict[str, Any]:
        data: dict[str, Any] = {name: [] for name in COLLECTIONS}
        data["meta"] = {"mocked": True, "fixture": self.fixture, "note": MOCK_NOTE, "created_at": utc_now()}
        return data

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        data = self._empty()
        data.update({k: v for k, v in raw.items() if k in COLLECTIONS or k == "meta"})
        return data

    def read(self) -> dict[str, Any]:
        """A deep copy of the whole store (safe to inspect)."""
        with self.lock:
            return copy.deepcopy(self._load())

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        """Load, let the caller mutate, then write atomically. Nothing is written if the block raises."""
        with self.lock:
            data = self._load()
            yield data
            _atomic_write_json(self.path, data)

    # --- record helpers
    def stamp(self, record: dict[str, Any]) -> dict[str, Any]:
        record.setdefault("created_at", utc_now())
        record["mocked"] = True
        record["fixture"] = self.fixture
        return record

    @staticmethod
    def find(data: dict[str, Any], collection: str, **match: Any) -> list[dict[str, Any]]:
        return [r for r in data.get(collection, []) if all(r.get(k) == v for k, v in match.items())]

    @staticmethod
    def find_one(data: dict[str, Any], collection: str, **match: Any) -> dict[str, Any] | None:
        for record in data.get(collection, []):
            if all(record.get(k) == v for k, v in match.items()):
                return record
        return None

    def order(self, data: dict[str, Any], order_id: str) -> dict[str, Any]:
        order = self.find_one(data, "orders", order_id=order_id)
        if order is None:
            raise UnknownOrder(f"Unknown order {order_id!r}.")
        return order

    def access_url(self, token: str) -> str:
        return f"{self.access_url_prefix}{token}"

    # --- convenience views (copies)
    def list(self, collection: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.read().get(collection, []))

    def outbox(self) -> list[dict[str, Any]]:
        return self.list("emails")
