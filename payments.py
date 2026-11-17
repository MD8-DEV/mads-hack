"""MOCKED settlement and payout records.

record_mock_payment() writes what a settlement record would contain (amount,
fee, net) and emits a "payment.succeeded" event for webhooks.handle_event().
It is a bookkeeping simulation only: "money_moved" is always false, there is
no payment provider, no card data and no charge. record_mock_payout() sums the
nets of mock payments minus refunds into a MOCKED payout record that is never
sent to any bank account.
"""
from __future__ import annotations

import math
import re
from typing import Any

from commerce import MOCK_NOTE, CommerceError, CommerceStore, InvalidState, money, new_id
from logbook import utc_now

PERIOD_RE = re.compile(r"^(all|\d{4}(-\d{2}(-\d{2})?)?)$")


def _event(store: CommerceStore, event_type: str, **fields: Any) -> dict[str, Any]:
    return {"id": new_id("evt"), "type": event_type, "created_at": utc_now(), "mocked": True,
            "fixture": store.fixture, **fields}


def record_mock_payment(store: CommerceStore, order_id: str, *, idempotency_key: str,
                        fee_rate: float = 0.0) -> dict[str, Any]:
    """MOCKED settlement record for an order. Idempotent per key and per order (one payment per order)."""
    key = (idempotency_key or "").strip()
    if not key:
        raise CommerceError("An idempotency key is required.")
    try:
        rate = float(fee_rate)
    except (TypeError, ValueError):
        raise CommerceError(f"Invalid fee rate {fee_rate!r}.") from None
    if not math.isfinite(rate) or not 0 <= rate < 1:
        raise CommerceError("The fee rate must be between 0 and 1.")

    with store.transaction() as data:
        existing = (store.find_one(data, "payments", idempotency_key=key)
                    or store.find_one(data, "payments", order_id=order_id, status="succeeded"))
        if existing is not None:
            if existing["order_id"] != order_id:
                raise CommerceError("This idempotency key was already used for a different order.")
            fee = store.find_one(data, "fees", payment_id=existing["payment_id"])
            return {"payment": dict(existing), "fee": dict(fee) if fee else None, "event": dict(existing["event"]),
                    "replayed": True, "mocked": True}
        order = store.order(data, order_id)
        if order["status"] == "refunded":
            raise InvalidState(f"Order {order_id} was refunded; it cannot be paid again.")
        amount = money(order["price"])
        fee_amount = money(amount * rate)
        payment_id = new_id("pay")
        event = _event(store, "payment.succeeded", order_id=order_id, payment_id=payment_id)
        payment = store.stamp({
            "payment_id": payment_id,
            "order_id": order_id,
            "idempotency_key": key,
            "amount": amount,
            "currency": order["currency"],
            "fee": fee_amount,
            "fee_rate": rate,
            "net": money(amount - fee_amount),
            "status": "succeeded",
            "money_moved": False,
            "provider": None,
            "payment_method": None,
            "payout_id": None,
            "event": event,
            "note": "MOCKED settlement record. " + MOCK_NOTE,
        })
        fee = store.stamp({
            "fee_id": new_id("fee"),
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": fee_amount,
            "rate": rate,
            "currency": order["currency"],
            "money_moved": False,
        })
        data["payments"].append(payment)
        data["fees"].append(fee)
        data["events"].append(event)
        order["status"] = "mock_paid"
        order["payment_id"] = payment_id
        order["updated_at"] = utc_now()
        return {"payment": dict(payment), "fee": dict(fee), "event": dict(event), "replayed": False, "mocked": True}


def record_mock_payout(store: CommerceStore, *, period: str, currency: str | None = None) -> dict[str, Any]:
    """MOCKED payout for a period ("all", "YYYY", "YYYY-MM" or "YYYY-MM-DD").

    Covers every succeeded mock payment and refund in the period not yet in a payout:
    amount = sum(net of payments) - sum(refund amounts). Calling it again with nothing new
    returns the latest payout for the period. No money moves and no bank account exists.
    """
    period = (period or "").strip()
    if not PERIOD_RE.match(period):
        raise CommerceError("Period must be 'all', 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD'.")

    def in_period(record: dict[str, Any]) -> bool:
        return period == "all" or str(record.get("created_at", "")).startswith(period)

    with store.transaction() as data:
        payments = [p for p in data["payments"]
                    if p.get("status") == "succeeded" and not p.get("payout_id") and in_period(p)]
        refunds = [r for r in data["refunds"]
                   if r.get("status") == "succeeded" and not r.get("payout_id") and in_period(r)]
        currencies = {p["currency"] for p in payments} | {r["currency"] for r in refunds}
        if currency:
            currency = currency.upper()
            payments = [p for p in payments if p["currency"] == currency]
            refunds = [r for r in refunds if r["currency"] == currency]
        elif len(currencies) > 1:
            raise CommerceError(f"Several currencies in this period ({', '.join(sorted(currencies))}): "
                                "record one payout per currency.")
        else:
            currency = next(iter(currencies), None)
        if not payments and not refunds:
            previous = [p for p in data["payouts"] if p.get("period") == period
                        and (currency is None or p.get("currency") == currency)]
            if previous:
                return dict(previous[-1], replayed=True)
        gross = money(sum(p["amount"] for p in payments))
        fees = money(sum(p["fee"] for p in payments))
        nets = money(sum(p["net"] for p in payments))
        refunded = money(sum(r["amount"] for r in refunds))
        payout = store.stamp({
            "payout_id": new_id("po"),
            "period": period,
            "currency": currency,
            "gross": gross,
            "fees": fees,
            "net_of_fees": nets,
            "refunds": refunded,
            "amount": money(nets - refunded),
            "payment_ids": [p["payment_id"] for p in payments],
            "refund_ids": [r["refund_id"] for r in refunds],
            "status": "recorded",
            "money_moved": False,
            "destination": None,
            "note": "MOCKED payout record: nothing was paid out and no bank account exists. " + MOCK_NOTE,
        })
        for p in payments:
            p["payout_id"] = payout["payout_id"]
        for r in refunds:
            r["payout_id"] = payout["payout_id"]
        data["payouts"].append(payout)
        return dict(payout, replayed=False)
