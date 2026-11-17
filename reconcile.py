"""Reconciliation and the end-to-end delivery test suite for the MOCKED sale-to-cash flow.

reconcile(store) cross-checks orders, payments, fees, refunds, payouts,
deliveries and access tokens, and lists every mismatch it finds.

run_delivery_test_suite(work_dir, ...) runs the scripted delivery tests on a
fresh FIXTURE store (excluded from analytics) and returns PASS/FAIL per test
plus a readable log. Step 5.3 uses it for its T gate.

CLI (writes the log of a real run):
    python reconcile.py --out outputs/payment_test_log.md [--product-id ID --price 19 --currency USD]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import checkout
import delivery
import payments
import refunds
import webhooks
from commerce import COLLECTIONS, CommerceStore, InvalidState, money, same_money
from logbook import utc_now

FIXTURE_FEE_RATE = 0.05  # FIXTURE: illustrative rate to exercise fee arithmetic; not any provider's rate


# ---------------------------------------------------------------------------------------------- reconcile
def reconcile(store: CommerceStore) -> dict[str, Any]:
    """Match orders <-> payments <-> fees <-> refunds <-> payouts <-> deliveries <-> access tokens."""
    data = store.read()
    mismatches: list[dict[str, Any]] = []
    warnings: list[str] = []

    def add(kind: str, message: str, **ids: Any) -> None:
        mismatches.append({"kind": kind, "message": message, **{k: v for k, v in ids.items() if v is not None}})

    orders = {o["order_id"]: o for o in data["orders"]}
    for key, count in Counter(o["idempotency_key"] for o in data["orders"]).items():
        if count > 1:
            add("duplicate_order", f"{count} orders share one idempotency key", idempotency_key=key)

    # payments and fees
    paid: dict[str, list[dict]] = defaultdict(list)
    for p in data["payments"]:
        order = orders.get(p["order_id"])
        if order is None:
            add("payment_without_order", "payment references an unknown order", payment_id=p["payment_id"],
                order_id=p["order_id"])
        elif not same_money(p["amount"], order["price"]):
            add("payment_amount_mismatch", f"payment {p['amount']} != order price {order['price']}",
                payment_id=p["payment_id"], order_id=p["order_id"])
        if not same_money(p["net"], p["amount"] - p["fee"]):
            add("net_mismatch", f"net {p['net']} != amount {p['amount']} - fee {p['fee']}", payment_id=p["payment_id"])
        fees = [f for f in data["fees"] if f["payment_id"] == p["payment_id"]]
        if len(fees) != 1:
            add("fee_record_count", f"{len(fees)} fee records for one payment (expected 1)", payment_id=p["payment_id"])
        elif not same_money(fees[0]["amount"], p["fee"]):
            add("fee_mismatch", f"fee record {fees[0]['amount']} != payment fee {p['fee']}", payment_id=p["payment_id"])
        if p.get("status") == "succeeded":
            paid[p["order_id"]].append(p)
    payment_ids = {p["payment_id"] for p in data["payments"]}
    for f in data["fees"]:
        if f["payment_id"] not in payment_ids:
            add("fee_without_payment", "fee record references an unknown payment", fee_id=f["fee_id"])
    for order_id, plist in paid.items():
        if len(plist) > 1:
            add("duplicate_payment", f"{len(plist)} succeeded payments for one order", order_id=order_id)

    # refunds
    refunded: dict[str, list[dict]] = defaultdict(list)
    for r in data["refunds"]:
        plist = paid.get(r["order_id"], [])
        if not plist:
            add("refund_without_payment", "refund for an order without a mock payment", refund_id=r["refund_id"],
                order_id=r["order_id"])
        elif not same_money(r["amount"], plist[0]["amount"]):
            add("refund_amount_mismatch", f"refund {r['amount']} != payment {plist[0]['amount']}",
                refund_id=r["refund_id"])
        if r.get("status") == "succeeded":
            refunded[r["order_id"]].append(r)
    for order_id, rlist in refunded.items():
        if len(rlist) > 1:
            add("duplicate_refund", f"{len(rlist)} refunds for one order", order_id=order_id)

    # deliveries
    delivered: dict[str, list[dict]] = defaultdict(list)
    for d in data["deliveries"]:
        delivered[d["order_id"]].append(d)
        if d["order_id"] not in orders:
            add("delivery_without_order", "delivery references an unknown order", delivery_id=d["delivery_id"])
        elif not paid.get(d["order_id"]):
            add("delivery_without_payment", "delivery for an order with no mock payment",
                delivery_id=d["delivery_id"], order_id=d["order_id"])
    for order_id, dlist in delivered.items():
        if len(dlist) > 1:
            add("duplicate_delivery", f"{len(dlist)} deliveries for one order", order_id=order_id)
    for order_id in paid:
        if order_id not in delivered and order_id not in refunded:
            add("paid_order_without_delivery", "mock-paid order has no delivery", order_id=order_id)

    # access tokens
    for t in data["access_tokens"]:
        if t.get("active") and (t["order_id"] in refunded or orders.get(t["order_id"], {}).get("status") == "refunded"):
            add("refunded_order_with_active_access", "refunded order still has an active access token",
                order_id=t["order_id"], delivery_id=t.get("delivery_id"))
        if not any(d["delivery_id"] == t.get("delivery_id") for d in data["deliveries"]):
            add("token_without_delivery", "access token without a delivery record", order_id=t["order_id"])

    # payouts
    pay_by_id = {p["payment_id"]: p for p in data["payments"]}
    ref_by_id = {r["refund_id"]: r for r in data["refunds"]}
    seen_payments: Counter[str] = Counter()
    seen_refunds: Counter[str] = Counter()
    for po in data["payouts"]:
        unknown = [i for i in po["payment_ids"] if i not in pay_by_id] + [i for i in po["refund_ids"] if i not in ref_by_id]
        if unknown:
            add("payout_unknown_record", f"payout references unknown records {unknown}", payout_id=po["payout_id"])
        expected = money(sum(pay_by_id[i]["net"] for i in po["payment_ids"] if i in pay_by_id)
                         - sum(ref_by_id[i]["amount"] for i in po["refund_ids"] if i in ref_by_id))
        if not same_money(po["amount"], expected):
            add("payout_total_mismatch", f"payout {po['amount']} != nets minus refunds {expected}",
                payout_id=po["payout_id"])
        seen_payments.update(po["payment_ids"])
        seen_refunds.update(po["refund_ids"])
    for pid, count in seen_payments.items():
        if count > 1:
            add("payment_in_multiple_payouts", f"payment in {count} payouts", payment_id=pid)
    for rid, count in seen_refunds.items():
        if count > 1:
            add("refund_in_multiple_payouts", f"refund in {count} payouts", refund_id=rid)

    # nothing may claim that money moved; every record must be labelled mocked
    for name in COLLECTIONS:
        for record in data.get(name, []):
            if isinstance(record, dict):
                if record.get("money_moved"):
                    add("money_moved", f"a {name} record claims money moved")
                if record.get("mocked") is not True:
                    add("unlabelled_record", f"a {name} record is not labelled mocked")

    # totals (per currency; amounts in different currencies are never added together)
    by_currency: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for p in data["payments"]:
        if p.get("status") == "succeeded":
            c = by_currency[p["currency"]]
            c["gross"] += p["amount"]
            c["fees"] += p["fee"]
            c["net"] += p["net"]
    for r in data["refunds"]:
        if r.get("status") == "succeeded":
            by_currency[r["currency"]]["refunds"] += r["amount"]
    for po in data["payouts"]:
        if po.get("currency"):
            by_currency[po["currency"]]["paid_out"] += po["amount"]
    totals_money = {}
    for cur, c in by_currency.items():
        row = {k: money(c.get(k, 0.0)) for k in ("gross", "fees", "net", "refunds", "paid_out")}
        row["balance_not_paid_out"] = money(row["net"] - row["refunds"] - row["paid_out"])
        totals_money[cur] = row
    emails = Counter(e.get("status") for e in data["emails"])
    if emails.get("failed"):
        warnings.append(f"{emails['failed']} confirmation email(s) failed after retries; delivery is recorded and "
                        "the emails can be retried (delivery.retry_failed_emails).")
    open_requests = [o for o in data["orders"] if o["status"] == "requested"]
    if open_requests:
        warnings.append(f"{len(open_requests)} order request(s) without a mock payment (not a mismatch).")
    totals = {
        "orders": len(data["orders"]),
        "orders_by_status": dict(Counter(o["status"] for o in data["orders"])),
        "payments": len(data["payments"]),
        "deliveries": len(data["deliveries"]),
        "refunds": len(data["refunds"]),
        "payouts": len(data["payouts"]),
        "active_access_tokens": sum(1 for t in data["access_tokens"] if t.get("active")),
        "emails_by_status": dict(emails),
        "webhooks_by_status": dict(Counter(w.get("status") for w in data["webhook_log"])),
        "money": totals_money,
        "money_moved": False,
        "fixture": bool(data.get("meta", {}).get("fixture")),
    }
    return {"ok": not mismatches, "totals": totals, "mismatches": mismatches, "warnings": warnings, "mocked": True}


# ---------------------------------------------------------------------------------------------- test suite
class _CheckFailed(AssertionError):
    pass


def _check(condition: Any, message: str) -> None:
    if not condition:
        raise _CheckFailed(message)


class _Suite:
    def __init__(self, store: CommerceStore, product_id: str, price: float, currency: str):
        self.store = store
        self.product_id = product_id
        self.price = price
        self.currency = currency
        self.catalog = {product_id: {"price": price, "currency": currency}}
        self.steps: list[dict[str, Any]] = []
        self.tests: list[dict[str, Any]] = []
        self._buyers = 0
        self.current = ""

    # --- helpers
    def log(self, step: str, **ids: Any) -> None:
        self.steps.append({"at": utc_now(), "test": self.current, "step": step,
                           "ids": {k: v for k, v in ids.items() if v not in (None, "")}})

    def buyer(self) -> str:
        self._buyers += 1
        return f"fixture-buyer-{self._buyers}@example.com"  # FIXTURE address on a reserved domain

    def order(self, key: str | None = None) -> dict[str, Any]:
        email = self.buyer()
        order = checkout.create_order(self.store, product_id=self.product_id, buyer_email=email, price=self.price,
                                      currency=self.currency, idempotency_key=key or f"fixture:{email}",
                                      catalog=self.catalog, metadata={"fixture": True})
        self.log("create_order (no charge)", order_id=order["order_id"], status=order["status"])
        return order

    def pay(self, order: dict[str, Any]) -> dict[str, Any]:
        result = payments.record_mock_payment(self.store, order["order_id"], idempotency_key=f"pay:{order['order_id']}",
                                              fee_rate=FIXTURE_FEE_RATE)
        self.log("record_mock_payment (MOCKED, money_moved=false)", payment_id=result["payment"]["payment_id"],
                 event_id=result["event"]["id"])
        return result

    def webhook(self, event: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        result = webhooks.handle_event(self.store, event, **kwargs)
        dlv = (result.get("result") or {}).get("delivery", {}) if isinstance(result.get("result"), dict) else {}
        self.log(f"handle_event {event.get('type')} -> {result['status']}", event_id=event.get("id"),
                 delivery_id=dlv.get("delivery_id"))
        return result

    def count(self, collection: str, **match: Any) -> int:
        return len(self.store.find(self.store.read(), collection, **match))

    def run(self, name: str, description: str, fn: Callable[[], str], *, failure_case: bool, critical: bool = True) -> None:
        self.current = name
        self.log("start")
        try:
            details = fn()
            passed = True
        except _CheckFailed as exc:
            passed, details = False, f"Check failed: {exc}"
        except Exception as exc:  # noqa: BLE001 - an unexpected error is a failed test, never a crash
            passed, details = False, f"Error: {type(exc).__name__}: {exc}"
        self.log("PASS" if passed else "FAIL")
        self.tests.append({"name": name, "description": description, "passed": passed, "critical": critical,
                           "failure_case": failure_case, "details": details})

    # --- the tests
    def happy_path(self) -> str:
        order = self.order()
        _check(order["status"] == "requested" and order["charged"] is False, "new order must be an uncharged request")
        _check("@" not in order["buyer_email_hash"] and order["buyer_email_masked"].startswith("f***@"),
               "only a hash and a masked email may be stored")
        paid = self.pay(order)
        _check(paid["payment"]["money_moved"] is False and paid["payment"]["provider"] is None,
               "mock payment must not move money or name a provider")
        _check(paid["event"]["type"] == "payment.succeeded", "payment must emit payment.succeeded")
        handled = self.webhook(paid["event"])
        _check(handled["status"] == "processed", f"webhook status {handled['status']}")
        dlv = handled["result"]["delivery"]
        _check(self.count("deliveries", order_id=order["order_id"]) == 1, "exactly one delivery expected")
        _check(delivery.has_access(self.store, dlv["access_token"]), "buyer must have access after delivery")
        email = handled["result"]["email"]
        _check(email["status"] == delivery.NOT_SENT, f"confirmation email status {email['status']}")
        self.log("access granted; confirmation email in outbox (MOCKED: not sent)", delivery_id=dlv["delivery_id"],
                 email_id=email["email_id"])
        return (f"order {order['order_id']} -> mock payment {paid['payment']['payment_id']} -> event "
                f"{paid['event']['id']} -> delivery {dlv['delivery_id']}; access granted; email {email['email_id']} "
                "in outbox (MOCKED: not sent)")

    def duplicate_submit(self) -> str:
        key = "fixture:duplicate-submit"
        first = self.order(key)
        email = f"fixture-buyer-{self._buyers}@example.com"
        second = checkout.create_order(self.store, product_id=self.product_id, buyer_email=email, price=self.price,
                                       currency=self.currency, idempotency_key=key, catalog=self.catalog)
        self.log("create_order again with the same idempotency key", order_id=second["order_id"],
                 replayed=str(second["replayed"]))
        _check(second["order_id"] == first["order_id"] and second["replayed"], "same key must return the same order")
        _check(self.count("orders", idempotency_key=key) == 1, "duplicate submit created a second order")
        return f"two submits with one idempotency key -> one order ({first['order_id']})"

    def repeated_event(self) -> str:
        order = self.order()
        paid = self.pay(order)
        first = self.webhook(paid["event"])
        again = self.webhook(paid["event"])
        _check(first["status"] == "processed" and again["status"] == "duplicate",
               f"statuses {first['status']}/{again['status']}")
        direct = delivery.deliver(self.store, order["order_id"], idempotency_key="fixture:direct-redelivery")
        self.log("deliver() called again directly", delivery_id=direct["delivery"]["delivery_id"],
                 replayed=str(direct["replayed"]))
        repay = payments.record_mock_payment(self.store, order["order_id"], idempotency_key=f"pay:{order['order_id']}")
        _check(direct["replayed"] and repay["replayed"], "re-delivery and re-payment must be replays")
        _check(self.count("deliveries", order_id=order["order_id"]) == 1, "repeated event delivered twice")
        _check(self.count("payments", order_id=order["order_id"]) == 1, "repeated payment recorded twice")
        return "same event twice + direct re-delivery + repeated payment call -> one payment, one delivery"

    def invalid_product(self) -> str:
        before = self.count("orders")
        rejected = 0
        for bad in ("fixture-unknown-product", ""):
            try:
                checkout.create_order(self.store, product_id=bad, buyer_email=self.buyer(), price=self.price,
                                      currency=self.currency, idempotency_key=f"fixture:bad:{bad}", catalog=self.catalog)
            except checkout.InvalidProduct as exc:
                rejected += 1
                self.log(f"create_order rejected: {exc}")
        _check(rejected == 2, "invalid products must be rejected")
        _check(self.count("orders") == before, "an invalid product created an order")
        return "unknown and empty product ids rejected with InvalidProduct; no order recorded"

    def delivery_requires_payment(self) -> str:
        order = self.order()
        try:
            delivery.deliver(self.store, order["order_id"], idempotency_key="fixture:unpaid")
            raise _CheckFailed("delivery without payment was allowed")
        except InvalidState as exc:
            self.log(f"deliver() refused: {exc}", order_id=order["order_id"])
        forged = {"id": "evt_fixture_unpaid", "type": "payment.succeeded", "order_id": order["order_id"]}
        result = self.webhook(forged)
        _check(result["status"] == "rejected", f"event for an unpaid order was {result['status']}")
        _check(self.count("deliveries", order_id=order["order_id"]) == 0, "unpaid order was delivered")
        return "unpaid order: direct delivery refused, payment event without a payment rejected, no delivery"

    def email_failure(self) -> str:
        calls = {"n": 0}

        def failing_sender(message: dict) -> None:
            calls["n"] += 1
            raise ConnectionError("FIXTURE: simulated mail server outage")

        order = self.order()
        paid = self.pay(order)
        handled = self.webhook(paid["event"], email_sender=failing_sender)
        dlv, email = handled["result"]["delivery"], handled["result"]["email"]
        _check(handled["status"] == "processed", "delivery must be recorded although the email failed")
        _check(calls["n"] == 3 and len(email["attempts"]) == 3, f"expected 3 attempts, saw {calls['n']}")
        _check(email["status"] == "failed" and dlv["email_status"] == "failed", "failed email must be visible")
        _check(delivery.has_access(self.store, dlv["access_token"]), "access must still work")
        self.log("email failed after 3 attempts; delivery kept", delivery_id=dlv["delivery_id"], email_id=email["email_id"])

        flaky = {"n": 0}

        def flaky_sender(message: dict) -> None:
            flaky["n"] += 1
            if flaky["n"] == 1:
                raise TimeoutError("FIXTURE: first attempt times out")

        order2 = self.order()
        handled2 = self.webhook(self.pay(order2)["event"], email_sender=flaky_sender)
        email2 = handled2["result"]["email"]
        _check(len(email2["attempts"]) == 2 and email2["status"] == "accepted_by_sender", "retry must succeed")
        self.log("flaky sender: attempt 1 failed, attempt 2 accepted", email_id=email2["email_id"])
        recovered = delivery.retry_failed_emails(self.store)
        _check(any(e["email_id"] == email["email_id"] and e["status"] == delivery.NOT_SENT for e in recovered),
               "failed email must be recoverable")
        self.log("retry_failed_emails: failed email moved to the outbox", email_id=email["email_id"])
        return ("always-failing sender: 3 attempts recorded, email 'failed', delivery and access kept; flaky sender: "
                "2 attempts; recovery moved the failed email to the outbox")

    def missing_or_expired_access(self) -> str:
        _check(not delivery.has_access(self.store, "fixture-unknown-token"), "unknown token granted access")
        _check(not delivery.has_access(self.store, ""), "empty token granted access")
        order = self.order()
        self.pay(order)
        result = delivery.deliver(self.store, order["order_id"], idempotency_key=f"deliver:{order['order_id']}",
                                  access_days=1)
        token = result["delivery"]["access_token"]
        later = datetime.now(timezone.utc) + timedelta(days=2)
        _check(delivery.has_access(self.store, token), "fresh token must work")
        _check(not delivery.has_access(self.store, token, now=later), "expired token granted access")
        self.log("unknown token denied; 1-day token denied 2 days later", delivery_id=result["delivery"]["delivery_id"])
        return "unknown and empty tokens denied; an expired token is denied"

    def refund_revokes(self) -> str:
        order = self.order()
        handled = self.webhook(self.pay(order)["event"])
        token = handled["result"]["delivery"]["access_token"]
        first = refunds.refund(self.store, order["order_id"], reason="FIXTURE: buyer asked", idempotency_key="fixture:refund-1")
        self.log("refund (MOCKED, money_moved=false)", refund_id=first["refund"]["refund_id"],
                 revoked=str(first["revoked_tokens"]))
        again = refunds.refund(self.store, order["order_id"], reason="FIXTURE: buyer asked", idempotency_key="fixture:refund-1")
        event = self.webhook(first["event"])
        _check(first["refund"]["money_moved"] is False, "refund must not move money")
        _check(not delivery.has_access(self.store, token), "refunded order still has access")
        _check(again["replayed"] and self.count("refunds", order_id=order["order_id"]) == 1, "refund was duplicated")
        _check(event["status"] == "processed", "refund event must be processed")
        return f"refund {first['refund']['refund_id']} revoked access; repeated refund call returned the same refund"

    def reconciliation_clean(self) -> str:
        payout = payments.record_mock_payout(self.store, period="all")
        self.log("record_mock_payout (MOCKED)", payout_id=payout["payout_id"], amount=str(payout["amount"]))
        data = self.store.read()
        expected = money(sum(p["net"] for p in data["payments"]) - sum(r["amount"] for r in data["refunds"]))
        _check(same_money(payout["amount"], expected), f"payout {payout['amount']} != {expected}")
        again = payments.record_mock_payout(self.store, period="all")
        _check(again["replayed"] and again["payout_id"] == payout["payout_id"], "second payout call must be a replay")
        result = reconcile(self.store)
        self.log(f"reconcile -> ok={result['ok']}, mismatches={len(result['mismatches'])}")
        _check(result["ok"], "mismatches: " + "; ".join(m["kind"] for m in result["mismatches"]))
        return (f"payout {payout['payout_id']} = nets minus refunds = {payout['amount']:.2f} {self.currency} (FIXTURE); "
                f"reconciliation clean across {result['totals']['orders']} orders")

    def reconciliation_detects(self, work_dir: Path) -> str:
        copy_path = work_dir / "commerce_fixture_injected.json"
        shutil.copyfile(self.store.path, copy_path)
        broken = CommerceStore(copy_path, fixture=True, access_url_prefix=self.store.access_url_prefix)
        email = self.buyer()
        unpaid = checkout.create_order(broken, product_id=self.product_id, buyer_email=email, price=self.price,
                                       currency=self.currency, idempotency_key="fixture:inject-unpaid")
        paid_only = checkout.create_order(broken, product_id=self.product_id, buyer_email=self.buyer(), price=self.price,
                                          currency=self.currency, idempotency_key="fixture:inject-paid-only")
        payments.record_mock_payment(broken, paid_only["order_id"], idempotency_key="fixture:inject-pay")
        with broken.transaction() as data:
            some = next(d for d in data["deliveries"] if d["status"] == "delivered")
            data["deliveries"].append(dict(some, delivery_id="dlv_fixture_injected_dup"))
            data["deliveries"].append(dict(some, delivery_id="dlv_fixture_injected_unpaid", order_id=unpaid["order_id"]))
            revoked = next(t for t in data["access_tokens"] if t.get("revoked_reason") == "refund")
            revoked["active"] = True
            data["payouts"][-1]["amount"] = money(data["payouts"][-1]["amount"] + 1)
        self.log("injected: duplicate delivery, delivery without payment, paid order without delivery, "
                 "re-activated refunded access, payout total +1.00")
        result = reconcile(broken)
        kinds = {m["kind"] for m in result["mismatches"]}
        expected = {"duplicate_delivery", "delivery_without_payment", "paid_order_without_delivery",
                    "refunded_order_with_active_access", "payout_total_mismatch"}
        self.log(f"reconcile on the injected copy -> ok={result['ok']}, found: {', '.join(sorted(kinds))}")
        _check(not result["ok"], "reconcile reported ok on broken data")
        _check(expected <= kinds, f"missed: {sorted(expected - kinds)}")
        return "all 5 injected mismatches detected: " + ", ".join(sorted(expected))


def _table_cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def _log_markdown(suite: _Suite, *, started: str, finished: str, recon: dict[str, Any]) -> str:
    tests = suite.tests
    passed = sum(1 for t in tests if t["passed"])
    critical = [t for t in tests if t["critical"]]
    failure_cases = sum(1 for t in tests if t["failure_case"])
    lines = [
        "# Payment and delivery test log",
        "",
        "> **MOCKED: no money moved.** No payment provider, no card or bank data. Orders, payments, fees, refunds "
        "and payouts are simulated "
        "records; confirmation emails stay in a local outbox and are not sent. All data below is FIXTURE data "
        "(reserved example.com addresses) in a throwaway store, excluded from every analytics count and gate metric.",
        "",
        f"**Result: {passed}/{len(tests)} tests passed ({passed / len(tests):.0%}); critical "
        f"{sum(1 for t in critical if t['passed'])}/{len(critical)}; failure cases tested: {failure_cases}.**",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Started (UTC) | {started} |",
        f"| Finished (UTC) | {finished} |",
        f"| Product id | {_table_cell(suite.product_id)} |",
        f"| Price used | {suite.price:g} {suite.currency} (advertised price; nothing was charged) |",
        f"| Fee rate used | {FIXTURE_FEE_RATE:.0%} (FIXTURE, to exercise fee arithmetic; not any provider's rate) |",
        "",
        "## Tests",
        "",
        "| # | Test | Failure case | Critical | Result | Details |",
        "|---|---|---|---|---|---|",
    ]
    for i, t in enumerate(tests, start=1):
        lines.append(f"| {i} | {t['name']}: {_table_cell(t['description'])} | {'yes' if t['failure_case'] else 'no'} | "
                     f"{'yes' if t['critical'] else 'no'} | {'PASS' if t['passed'] else 'FAIL'} | "
                     f"{_table_cell(t['details'])} |")
    lines += ["", "## Reconciliation of the fixture store", "",
              f"- Result: {'clean (no mismatches)' if recon['ok'] else 'MISMATCHES FOUND'}",
              f"- Orders by status: {recon['totals']['orders_by_status']}",
              f"- Deliveries: {recon['totals']['deliveries']}, refunds: {recon['totals']['refunds']}, "
              f"payouts: {recon['totals']['payouts']}, active access tokens: {recon['totals']['active_access_tokens']}",
              f"- Emails by status: {recon['totals']['emails_by_status']}",
              f"- Webhook events by status: {recon['totals']['webhooks_by_status']}"]
    for cur, row in recon["totals"]["money"].items():
        lines.append(f"- {cur} (FIXTURE amounts, MOCKED, money_moved=false): gross {row['gross']:.2f}, fees "
                     f"{row['fees']:.2f}, net {row['net']:.2f}, refunds {row['refunds']:.2f}, recorded payout "
                     f"{row['paid_out']:.2f}, balance not paid out {row['balance_not_paid_out']:.2f}")
    for m in recon["mismatches"]:
        lines.append(f"- Mismatch: {m['kind']}: {m['message']}")
    for w in recon["warnings"]:
        lines.append(f"- Note: {w}")
    lines += ["", "## Step log", "", "| Time (UTC) | Test | Step | IDs |", "|---|---|---|---|"]
    for s in suite.steps:
        ids = ", ".join(f"{k}={v}" for k, v in s["ids"].items())
        lines.append(f"| {s['at']} | {s['test']} | {_table_cell(s['step'])} | {_table_cell(ids)} |")
    return "\n".join(lines) + "\n"


def run_delivery_test_suite(work_dir: Path, *, product_id: str, price: float, currency: str) -> dict[str, Any]:
    """Run the scripted MOCKED delivery tests on a fresh FIXTURE store inside work_dir."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "commerce_fixture.json"
    for stale in (path, work_dir / "commerce_fixture_injected.json"):
        if stale.exists():
            stale.unlink()
    store = CommerceStore(path, fixture=True, access_url_prefix="/fixture/access/")
    suite = _Suite(store, str(product_id or "fixture-product"), float(price), str(currency or "USD").upper())
    started = utc_now()
    suite.run("happy_path", "order -> mock payment -> webhook -> delivery -> access", suite.happy_path,
              failure_case=False)
    suite.run("duplicate_submit", "same idempotency key submitted twice", suite.duplicate_submit, failure_case=True)
    suite.run("repeated_delivery_event", "same payment event delivered twice", suite.repeated_event, failure_case=True)
    suite.run("invalid_product", "order for a product that does not exist", suite.invalid_product, failure_case=True)
    suite.run("delivery_requires_payment", "delivery attempted for an unpaid order", suite.delivery_requires_payment,
              failure_case=True)
    suite.run("email_failure_retry", "confirmation email fails, retries, recovery", suite.email_failure,
              failure_case=True)
    suite.run("missing_or_expired_access", "unknown or expired access token", suite.missing_or_expired_access,
              failure_case=True)
    suite.run("refund_revokes_access", "refund revokes product access", suite.refund_revokes, failure_case=False)
    suite.run("reconciliation_clean", "payout and reconciliation on the fixture store", suite.reconciliation_clean,
              failure_case=False)
    suite.run("reconciliation_detects_mismatch", "reconciliation catches injected mismatches",
              lambda: suite.reconciliation_detects(work_dir), failure_case=True)
    finished = utc_now()
    recon = reconcile(store)
    tests = suite.tests
    passed = sum(1 for t in tests if t["passed"])
    critical = [t for t in tests if t["critical"]]
    return {
        "tests": [{k: t[k] for k in ("name", "description", "passed", "critical", "failure_case", "details")} for t in tests],
        "passed": passed,
        "total": len(tests),
        "pass_rate": round(passed / len(tests), 4),
        "critical_pass_rate": round(sum(1 for t in critical if t["passed"]) / len(critical), 4) if critical else 1.0,
        "failure_cases_tested": sum(1 for t in tests if t["failure_case"]),
        "reconciliation": recon,
        "log_markdown": _log_markdown(suite, started=started, finished=finished, recon=recon),
        "started_at": started,
        "finished_at": finished,
        "fixture": True,
        "mocked": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MOCKED delivery test suite and write its log.")
    parser.add_argument("--out", required=True, help="where to write the markdown log")
    parser.add_argument("--product-id", default="fixture-product")
    parser.add_argument("--price", type=float, default=10.0, help="advertised price used by the FIXTURE orders")
    parser.add_argument("--currency", default="USD")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="vv-delivery-tests-") as tmp:
        result = run_delivery_test_suite(Path(tmp), product_id=args.product_id, price=args.price,
                                         currency=args.currency)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result["log_markdown"], encoding="utf-8")
    print(f"{result['passed']}/{result['total']} delivery tests passed; failure cases tested: "
          f"{result['failure_cases_tested']}. MOCKED: no money moved. Log: {out}")
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
