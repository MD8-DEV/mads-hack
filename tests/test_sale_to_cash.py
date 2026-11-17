"""MOCKED sale-to-cash flow: checkout, mock payment, webhooks, delivery, refunds, payouts, reconciliation.

All data here is FIXTURE data (reserved example.com addresses). Nothing moves money,
contacts a payment provider or touches card or bank data.
"""
from __future__ import annotations

import json
import threading

import pytest

import checkout
import delivery
import payments
import reconcile
import refunds
import webhooks
from commerce import CommerceError, CommerceStore, IdempotencyConflict, InvalidState, UnknownOrder, email_hash

EMAIL = "Fixture.Buyer@Example.com"
CATALOG = {"fixture-product": {"price": 19.0, "currency": "USD"}}


@pytest.fixture()
def store(tmp_path):
    return CommerceStore(tmp_path / "commerce.json", fixture=True, access_url_prefix="/p/run-x/access/")


def new_order(store, key="k1", email=EMAIL, price=19.0):
    return checkout.create_order(store, product_id="fixture-product", buyer_email=email, price=price,
                                 currency="usd", idempotency_key=key, catalog=CATALOG)


def paid_and_delivered(store, key="k1", email=EMAIL, **kwargs):
    order = new_order(store, key, email)
    paid = payments.record_mock_payment(store, order["order_id"], idempotency_key=f"pay:{order['order_id']}",
                                        fee_rate=0.05)
    handled = webhooks.handle_event(store, paid["event"], **kwargs)
    return order, paid, handled


# ---------------------------------------------------------------------------------------------- checkout
def test_create_order_is_a_no_charge_request_with_hashed_email(store):
    order = new_order(store)
    assert order["status"] == "requested" and order["charged"] is False and order["mocked"] is True
    assert order["currency"] == "USD" and order["price"] == 19.0
    assert order["buyer_email_hash"] == email_hash("fixture.buyer@example.com")
    assert order["buyer_email_masked"] == "F***@example.com"
    raw = store.path.read_text(encoding="utf-8")
    assert "Fixture.Buyer" not in raw and "fixture.buyer@" not in raw.lower()


def test_same_idempotency_key_returns_existing_order(store):
    first = new_order(store)
    second = new_order(store, email=EMAIL.lower())
    assert second["order_id"] == first["order_id"] and second["replayed"] is True
    assert len(store.list("orders")) == 1
    with pytest.raises(IdempotencyConflict):
        new_order(store, email="someone.else@example.com")


def test_concurrent_duplicate_submits_create_one_order(store):
    ids, errors = [], []

    def submit():
        try:
            ids.append(new_order(store, key="same-key")["order_id"])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(ids)) == 1 and len(store.list("orders")) == 1


@pytest.mark.parametrize("kwargs", [
    {"product_id": "not-in-catalog"},
    {"product_id": ""},
    {"product_id": "   "},
])
def test_invalid_product_is_rejected_without_an_order(store, kwargs):
    base = {"buyer_email": EMAIL, "price": 19, "currency": "USD", "idempotency_key": "k", "catalog": CATALOG}
    with pytest.raises(checkout.InvalidProduct):
        checkout.create_order(store, **{**base, **kwargs})
    assert store.list("orders") == []


@pytest.mark.parametrize("kwargs", [
    {"buyer_email": "not-an-email"},
    {"price": -1},
    {"price": float("nan")},
    {"price": "abc"},
    {"currency": "dollars"},
    {"idempotency_key": ""},
])
def test_malformed_order_requests_are_rejected(store, kwargs):
    base = {"product_id": "fixture-product", "buyer_email": EMAIL, "price": 19, "currency": "USD",
            "idempotency_key": "k"}
    with pytest.raises(checkout.InvalidOrder):
        checkout.create_order(store, **{**base, **kwargs})
    assert store.list("orders") == []


def test_catalog_is_optional_and_accepts_a_list(store):
    order = checkout.create_order(store, product_id="any", buyer_email=EMAIL, price=0, currency="EUR",
                                  idempotency_key="free")
    assert order["price"] == 0.0
    with pytest.raises(checkout.InvalidProduct):
        checkout.create_order(store, product_id="x", buyer_email=EMAIL, price=1, currency="EUR",
                              idempotency_key="k2", catalog=["y"])


# ---------------------------------------------------------------------------------------------- payments
def test_mock_payment_records_amount_fee_net_and_never_moves_money(store):
    order = new_order(store)
    result = payments.record_mock_payment(store, order["order_id"], idempotency_key="p1", fee_rate=0.05)
    pay = result["payment"]
    assert pay["amount"] == 19.0 and pay["fee"] == 0.95 and pay["net"] == 18.05
    assert pay["money_moved"] is False and pay["provider"] is None and pay["payment_method"] is None
    assert result["fee"]["amount"] == 0.95
    assert result["event"]["type"] == "payment.succeeded" and result["event"]["id"].startswith("evt_")
    assert result["event"]["order_id"] == order["order_id"]
    again = payments.record_mock_payment(store, order["order_id"], idempotency_key="p1")
    other_key = payments.record_mock_payment(store, order["order_id"], idempotency_key="p2")
    assert again["replayed"] and other_key["replayed"]
    assert again["event"]["id"] == result["event"]["id"]
    assert len(store.list("payments")) == 1 and len(store.list("fees")) == 1


def test_mock_payment_validation(store):
    order = new_order(store)
    with pytest.raises(UnknownOrder):
        payments.record_mock_payment(store, "ord_missing", idempotency_key="p")
    with pytest.raises(CommerceError):
        payments.record_mock_payment(store, order["order_id"], idempotency_key="p", fee_rate=1.5)
    with pytest.raises(CommerceError):
        payments.record_mock_payment(store, order["order_id"], idempotency_key="")


def test_no_card_or_bank_fields_exist_anywhere(store):
    order, _, _ = paid_and_delivered(store)
    refunds.refund(store, order["order_id"], reason="FIXTURE", idempotency_key="r1")
    payments.record_mock_payout(store, period="all")
    keys: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                keys.add(k.lower())
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(json.loads(store.path.read_text(encoding="utf-8")))
    forbidden = ("card", "cvv", "iban", "bank", "account_number", "routing", "password")
    assert not [k for k in keys if any(word in k for word in forbidden)]


# ---------------------------------------------------------------------------------------------- webhooks + delivery
def test_payment_event_delivers_once_with_access_and_outbox_email(store):
    order, paid, handled = paid_and_delivered(store)
    assert handled["status"] == "processed"
    dlv = handled["result"]["delivery"]
    assert dlv["download_path"] == f"/p/run-x/access/{dlv['access_token']}"
    assert delivery.has_access(store, dlv["access_token"])
    email = store.outbox()[0]
    assert email["status"] == delivery.NOT_SENT and email["label"] == "MOCKED: not sent"
    assert email["to_masked"] == "F***@example.com" and "MOCKED: no payment was taken" in email["body"]
    again = webhooks.handle_event(store, paid["event"])
    assert again["status"] == "duplicate"
    direct = delivery.deliver(store, order["order_id"], idempotency_key="another-key")
    assert direct["replayed"] and direct["delivery"]["delivery_id"] == dlv["delivery_id"]
    assert len(store.list("deliveries")) == 1 and len(store.outbox()) == 1
    assert [w["status"] for w in store.list("webhook_log")] == ["processed", "duplicate"]


def test_unknown_event_types_are_ignored_and_recorded(store):
    result = webhooks.handle_event(store, {"id": "evt_fixture_1", "type": "customer.created"})
    assert result["status"] == "ignored"
    assert "evt_fixture_1" in store.read()["processed_event_ids"]
    with pytest.raises(CommerceError):
        webhooks.handle_event(store, {"type": "payment.succeeded"})


def test_delivery_requires_a_mock_payment(store):
    order = new_order(store)
    with pytest.raises(InvalidState):
        delivery.deliver(store, order["order_id"], idempotency_key="d")
    forged = webhooks.handle_event(store, {"id": "evt_forged", "type": "payment.succeeded",
                                           "order_id": order["order_id"]})
    assert forged["status"] == "rejected"
    missing = webhooks.handle_event(store, {"id": "evt_missing", "type": "payment.succeeded", "order_id": "ord_nope"})
    assert missing["status"] == "rejected"
    assert store.list("deliveries") == []


def test_email_failure_is_retried_and_delivery_is_kept(store):
    calls = []

    def failing(message):
        calls.append(message)
        raise ConnectionError("FIXTURE outage")

    order, _, handled = paid_and_delivered(store, email_sender=failing)
    dlv, email = handled["result"]["delivery"], handled["result"]["email"]
    assert len(calls) == 3 and len(email["attempts"]) == 3
    assert all(m["to_masked"] == "F***@example.com" and "to" not in m for m in calls)  # never the plain address
    assert email["status"] == "failed" and dlv["email_status"] == "failed" and dlv["email_attempts"] == 3
    assert all(a["ok"] is False and "FIXTURE outage" in a["error"] for a in email["attempts"])
    assert delivery.has_access(store, dlv["access_token"])
    recovered = delivery.retry_failed_emails(store)
    assert recovered[0]["status"] == delivery.NOT_SENT and len(recovered[0]["attempts"]) == 4


def test_custom_max_email_attempts(store):
    order = new_order(store)
    payments.record_mock_payment(store, order["order_id"], idempotency_key="p")
    calls = []

    def down(message):
        calls.append(message)
        raise OSError("FIXTURE: mail server down")

    result = delivery.deliver(store, order["order_id"], idempotency_key="d", max_email_attempts=5, email_sender=down)
    assert len(calls) == 5 and result["email"]["status"] == "failed"


def test_unknown_and_expired_tokens_have_no_access(store):
    from datetime import datetime, timedelta, timezone
    assert not delivery.has_access(store, "nope-nope-nope")
    assert not delivery.has_access(store, "")
    order = new_order(store)
    payments.record_mock_payment(store, order["order_id"], idempotency_key="p")
    token = delivery.deliver(store, order["order_id"], idempotency_key="d", access_days=1)["delivery"]["access_token"]
    assert delivery.has_access(store, token)
    assert not delivery.has_access(store, token, now=datetime.now(timezone.utc) + timedelta(days=2))
    assert delivery.access_for(store, token)["order_id"] == order["order_id"]


# ---------------------------------------------------------------------------------------------- refunds
def test_refund_revokes_access_and_is_idempotent(store):
    order, _, handled = paid_and_delivered(store)
    token = handled["result"]["delivery"]["access_token"]
    result = refunds.refund(store, order["order_id"], reason="FIXTURE: not what I needed", idempotency_key="r1")
    assert result["refund"]["money_moved"] is False and result["refund"]["amount"] == 19.0
    assert result["revoked_tokens"] == 1 and not delivery.has_access(store, token)
    assert result["event"]["type"] == "refund.succeeded"
    again = refunds.refund(store, order["order_id"], reason="again", idempotency_key="r2")
    assert again["replayed"] and len(store.list("refunds")) == 1
    event = webhooks.handle_event(store, result["event"])
    assert event["status"] == "processed" and event["result"]["revoked_tokens"] == 0
    replay = payments.record_mock_payment(store, order["order_id"], idempotency_key="new")
    redeliver = delivery.deliver(store, order["order_id"], idempotency_key="after-refund")
    assert replay["replayed"] and redeliver["replayed"] and len(store.list("payments")) == 1
    assert not delivery.has_access(store, token)
    assert store.read()["orders"][0]["status"] == "refunded"


def test_refund_validation(store):
    with pytest.raises(UnknownOrder):
        refunds.refund(store, "ord_missing", reason="x", idempotency_key="r")
    order = new_order(store)
    with pytest.raises(InvalidState):
        refunds.refund(store, order["order_id"], reason="x", idempotency_key="r")
    with pytest.raises(CommerceError):
        refunds.refund(store, order["order_id"], reason="", idempotency_key="r")


def test_refund_event_revokes_access_even_without_refund_call(store):
    order, _, handled = paid_and_delivered(store)
    token = handled["result"]["delivery"]["access_token"]
    result = webhooks.handle_event(store, {"id": "evt_ref", "type": "refund.succeeded", "order_id": order["order_id"]})
    assert result["status"] == "processed" and not delivery.has_access(store, token)


# ---------------------------------------------------------------------------------------------- payouts + reconcile
def test_payout_is_nets_minus_refunds_and_reconciles(store):
    o1, _, _ = paid_and_delivered(store, key="a", email="a@example.com")
    paid_and_delivered(store, key="b", email="b@example.com")
    refunds.refund(store, o1["order_id"], reason="FIXTURE", idempotency_key="r")
    payout = payments.record_mock_payout(store, period="all")
    assert payout["amount"] == round(18.05 * 2 - 19.0, 2) and payout["money_moved"] is False
    assert payout["gross"] == 38.0 and payout["fees"] == 1.9 and payout["refunds"] == 19.0
    assert payments.record_mock_payout(store, period="all")["replayed"] is True
    result = reconcile.reconcile(store)
    assert result["ok"] and result["mismatches"] == []
    usd = result["totals"]["money"]["USD"]
    assert usd["paid_out"] == payout["amount"] and usd["balance_not_paid_out"] == 0.0
    with pytest.raises(CommerceError):
        payments.record_mock_payout(store, period="last month")


def test_payout_by_month_period(store):
    paid_and_delivered(store)
    month = store.list("payments")[0]["created_at"][:7]
    assert payments.record_mock_payout(store, period="1999-01")["amount"] == 0.0
    assert payments.record_mock_payout(store, period=month)["amount"] == 18.05


def test_reconcile_detects_each_mismatch(store):
    o1, _, h1 = paid_and_delivered(store, key="a", email="a@example.com")
    o2, _, _ = paid_and_delivered(store, key="b", email="b@example.com")
    refunds.refund(store, o2["order_id"], reason="FIXTURE", idempotency_key="r")
    payments.record_mock_payout(store, period="all")
    unpaid = new_order(store, key="c", email="c@example.com")
    paid_only = new_order(store, key="d", email="d@example.com")
    payments.record_mock_payment(store, paid_only["order_id"], idempotency_key="pd")
    assert reconcile.reconcile(store)["mismatches"] == [
        {"kind": "paid_order_without_delivery", "message": "mock-paid order has no delivery",
         "order_id": paid_only["order_id"]}]
    with store.transaction() as data:
        dlv = data["deliveries"][0]
        data["deliveries"].append(dict(dlv, delivery_id="dlv_dup"))
        data["deliveries"].append(dict(dlv, delivery_id="dlv_unpaid", order_id=unpaid["order_id"]))
        next(t for t in data["access_tokens"] if t["order_id"] == o2["order_id"])["active"] = True
        data["payouts"][0]["amount"] += 5
        data["payments"][0]["money_moved"] = True
    kinds = {m["kind"] for m in reconcile.reconcile(store)["mismatches"]}
    assert {"duplicate_delivery", "delivery_without_payment", "paid_order_without_delivery",
            "refunded_order_with_active_access", "payout_total_mismatch", "money_moved"} <= kinds


# ---------------------------------------------------------------------------------------------- test suite + CLI
def test_delivery_test_suite_passes_and_covers_failure_cases(tmp_path):
    result = reconcile.run_delivery_test_suite(tmp_path, product_id="fixture-product", price=19, currency="usd")
    failed = [t for t in result["tests"] if not t["passed"]]
    assert not failed, failed
    assert result["pass_rate"] == 1.0 and result["critical_pass_rate"] == 1.0
    assert result["failure_cases_tested"] >= 3
    names = {t["name"] for t in result["tests"]}
    assert {"happy_path", "duplicate_submit", "repeated_delivery_event", "invalid_product", "email_failure_retry",
            "refund_revokes_access", "reconciliation_clean", "reconciliation_detects_mismatch"} <= names
    assert all(set(t) >= {"name", "passed", "critical", "details"} for t in result["tests"])
    log = result["log_markdown"]
    assert "MOCKED: no money moved" in log and "FIXTURE" in log and "| PASS |" in log and "FAIL |" not in log
    fixture = json.loads((tmp_path / "commerce_fixture.json").read_text(encoding="utf-8"))
    assert fixture["meta"]["fixture"] is True and all(o["fixture"] for o in fixture["orders"])
    # running again starts from a fresh store
    assert reconcile.run_delivery_test_suite(tmp_path, product_id="p", price=5, currency="EUR")["pass_rate"] == 1.0


def test_delivery_test_suite_reports_a_broken_flow_as_failed(tmp_path, monkeypatch):
    def broken_deliver(store, order_id, **kwargs):
        raise InvalidState("FIXTURE: delivery service down")

    monkeypatch.setattr(delivery, "deliver", broken_deliver)
    result = reconcile.run_delivery_test_suite(tmp_path, product_id="p", price=5, currency="EUR")
    assert result["pass_rate"] < 1.0
    assert not next(t for t in result["tests"] if t["name"] == "happy_path")["passed"]
    assert "| FAIL |" in result["log_markdown"]


def test_cli_writes_the_log(tmp_path, capsys):
    out = tmp_path / "nested" / "payment_test_log.md"
    code = reconcile.main(["--out", str(out), "--product-id", "fixture-product", "--price", "12", "--currency", "EUR"])
    assert code == 0 and out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Payment and delivery test log") and "12 EUR" in text
    assert "delivery tests passed" in capsys.readouterr().out
