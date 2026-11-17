# Payment and delivery test log

> **MOCKED: no money moved.** No payment provider, no card or bank data. Orders, payments, fees, refunds and payouts are simulated records; confirmation emails stay in a local outbox and are not sent. All data below is FIXTURE data (reserved example.com addresses) in a throwaway store, excluded from every analytics count and gate metric.

**Result: 10/10 tests passed (100%); critical 10/10; failure cases tested: 7.**

| Item | Value |
|---|---|
| Started (UTC) | 2026-11-17T19:50:48Z |
| Finished (UTC) | 2026-11-17T19:50:49Z |
| Product id | revision-rounds-scope-tracker-for-freela |
| Price used | 150 EGP (advertised price; nothing was charged) |
| Fee rate used | 5% (FIXTURE, to exercise fee arithmetic; not any provider's rate) |

## Tests

| # | Test | Failure case | Critical | Result | Details |
|---|---|---|---|---|---|
| 1 | happy_path: order -> mock payment -> webhook -> delivery -> access | no | yes | PASS | order ord_f29103df4366 -> mock payment pay_634fbaab0017 -> event evt_9f43093be8c8 -> delivery dlv_ec7e4e3e5a15; access granted; email eml_49e6ee576f40 in outbox (MOCKED: not sent) |
| 2 | duplicate_submit: same idempotency key submitted twice | yes | yes | PASS | two submits with one idempotency key -> one order (ord_b303349c04d1) |
| 3 | repeated_delivery_event: same payment event delivered twice | yes | yes | PASS | same event twice + direct re-delivery + repeated payment call -> one payment, one delivery |
| 4 | invalid_product: order for a product that does not exist | yes | yes | PASS | unknown and empty product ids rejected with InvalidProduct; no order recorded |
| 5 | delivery_requires_payment: delivery attempted for an unpaid order | yes | yes | PASS | unpaid order: direct delivery refused, payment event without a payment rejected, no delivery |
| 6 | email_failure_retry: confirmation email fails, retries, recovery | yes | yes | PASS | always-failing sender: 3 attempts recorded, email 'failed', delivery and access kept; flaky sender: 2 attempts; recovery moved the failed email to the outbox |
| 7 | missing_or_expired_access: unknown or expired access token | yes | yes | PASS | unknown and empty tokens denied; an expired token is denied |
| 8 | refund_revokes_access: refund revokes product access | no | yes | PASS | refund ref_4f05ec6a7070 revoked access; repeated refund call returned the same refund |
| 9 | reconciliation_clean: payout and reconciliation on the fixture store | no | yes | PASS | payout po_c2cfb6a41cdf = nets minus refunds = 705.00 EGP (FIXTURE); reconciliation clean across 8 orders |
| 10 | reconciliation_detects_mismatch: reconciliation catches injected mismatches | yes | yes | PASS | all 5 injected mismatches detected: delivery_without_payment, duplicate_delivery, paid_order_without_delivery, payout_total_mismatch, refunded_order_with_active_access |

## Reconciliation of the fixture store

- Result: clean (no mismatches)
- Orders by status: {'delivered': 5, 'requested': 2, 'refunded': 1}
- Deliveries: 6, refunds: 1, payouts: 1, active access tokens: 5
- Emails by status: {'MOCKED: not sent': 5, 'accepted_by_sender': 1}
- Webhook events by status: {'processed': 6, 'duplicate': 1, 'rejected': 1}
- EGP (FIXTURE amounts, MOCKED, money_moved=false): gross 900.00, fees 45.00, net 855.00, refunds 150.00, recorded payout 705.00, balance not paid out 0.00
- Note: 2 order request(s) without a mock payment (not a mismatch).

## Step log

| Time (UTC) | Test | Step | IDs |
|---|---|---|---|
| 2026-11-17T19:50:48Z | happy_path | start |  |
| 2026-11-17T19:50:48Z | happy_path | create_order (no charge) | order_id=ord_f29103df4366, status=requested |
| 2026-11-17T19:50:48Z | happy_path | record_mock_payment (MOCKED, money_moved=false) | payment_id=pay_634fbaab0017, event_id=evt_9f43093be8c8 |
| 2026-11-17T19:50:48Z | happy_path | handle_event payment.succeeded -> processed | event_id=evt_9f43093be8c8, delivery_id=dlv_ec7e4e3e5a15 |
| 2026-11-17T19:50:48Z | happy_path | access granted; confirmation email in outbox (MOCKED: not sent) | delivery_id=dlv_ec7e4e3e5a15, email_id=eml_49e6ee576f40 |
| 2026-11-17T19:50:48Z | happy_path | PASS |  |
| 2026-11-17T19:50:48Z | duplicate_submit | start |  |
| 2026-11-17T19:50:48Z | duplicate_submit | create_order (no charge) | order_id=ord_b303349c04d1, status=requested |
| 2026-11-17T19:50:48Z | duplicate_submit | create_order again with the same idempotency key | order_id=ord_b303349c04d1, replayed=True |
| 2026-11-17T19:50:48Z | duplicate_submit | PASS |  |
| 2026-11-17T19:50:48Z | repeated_delivery_event | start |  |
| 2026-11-17T19:50:48Z | repeated_delivery_event | create_order (no charge) | order_id=ord_bc9089b257e0, status=requested |
| 2026-11-17T19:50:48Z | repeated_delivery_event | record_mock_payment (MOCKED, money_moved=false) | payment_id=pay_40617ac4326e, event_id=evt_9844aa2e88ae |
| 2026-11-17T19:50:48Z | repeated_delivery_event | handle_event payment.succeeded -> processed | event_id=evt_9844aa2e88ae, delivery_id=dlv_ff488dc0de00 |
| 2026-11-17T19:50:48Z | repeated_delivery_event | handle_event payment.succeeded -> duplicate | event_id=evt_9844aa2e88ae |
| 2026-11-17T19:50:48Z | repeated_delivery_event | deliver() called again directly | delivery_id=dlv_ff488dc0de00, replayed=True |
| 2026-11-17T19:50:48Z | repeated_delivery_event | PASS |  |
| 2026-11-17T19:50:48Z | invalid_product | start |  |
| 2026-11-17T19:50:48Z | invalid_product | create_order rejected: Unknown product 'fixture-unknown-product'. |  |
| 2026-11-17T19:50:48Z | invalid_product | create_order rejected: No product id given. |  |
| 2026-11-17T19:50:48Z | invalid_product | PASS |  |
| 2026-11-17T19:50:48Z | delivery_requires_payment | start |  |
| 2026-11-17T19:50:48Z | delivery_requires_payment | create_order (no charge) | order_id=ord_96ae219a5e8d, status=requested |
| 2026-11-17T19:50:48Z | delivery_requires_payment | deliver() refused: Order ord_96ae219a5e8d has no mock payment; delivery needs one first. | order_id=ord_96ae219a5e8d |
| 2026-11-17T19:50:48Z | delivery_requires_payment | handle_event payment.succeeded -> rejected | event_id=evt_fixture_unpaid |
| 2026-11-17T19:50:48Z | delivery_requires_payment | PASS |  |
| 2026-11-17T19:50:48Z | email_failure_retry | start |  |
| 2026-11-17T19:50:48Z | email_failure_retry | create_order (no charge) | order_id=ord_622e9909dc5b, status=requested |
| 2026-11-17T19:50:48Z | email_failure_retry | record_mock_payment (MOCKED, money_moved=false) | payment_id=pay_dd27f2b9fb1c, event_id=evt_345e32d46cb6 |
| 2026-11-17T19:50:48Z | email_failure_retry | handle_event payment.succeeded -> processed | event_id=evt_345e32d46cb6, delivery_id=dlv_d001f43f0b52 |
| 2026-11-17T19:50:48Z | email_failure_retry | email failed after 3 attempts; delivery kept | delivery_id=dlv_d001f43f0b52, email_id=eml_6b39650d8e34 |
| 2026-11-17T19:50:48Z | email_failure_retry | create_order (no charge) | order_id=ord_d121ff54e308, status=requested |
| 2026-11-17T19:50:48Z | email_failure_retry | record_mock_payment (MOCKED, money_moved=false) | payment_id=pay_a60658ed24b0, event_id=evt_ccc791906186 |
| 2026-11-17T19:50:49Z | email_failure_retry | handle_event payment.succeeded -> processed | event_id=evt_ccc791906186, delivery_id=dlv_9bad1391fbda |
| 2026-11-17T19:50:49Z | email_failure_retry | flaky sender: attempt 1 failed, attempt 2 accepted | email_id=eml_b229007ce71c |
| 2026-11-17T19:50:49Z | email_failure_retry | retry_failed_emails: failed email moved to the outbox | email_id=eml_6b39650d8e34 |
| 2026-11-17T19:50:49Z | email_failure_retry | PASS |  |
| 2026-11-17T19:50:49Z | missing_or_expired_access | start |  |
| 2026-11-17T19:50:49Z | missing_or_expired_access | create_order (no charge) | order_id=ord_c9e7a40a2c1e, status=requested |
| 2026-11-17T19:50:49Z | missing_or_expired_access | record_mock_payment (MOCKED, money_moved=false) | payment_id=pay_38cfb4f6e78e, event_id=evt_85ae24c734d6 |
| 2026-11-17T19:50:49Z | missing_or_expired_access | unknown token denied; 1-day token denied 2 days later | delivery_id=dlv_226f7b4058dc |
| 2026-11-17T19:50:49Z | missing_or_expired_access | PASS |  |
| 2026-11-17T19:50:49Z | refund_revokes_access | start |  |
| 2026-11-17T19:50:49Z | refund_revokes_access | create_order (no charge) | order_id=ord_0821506a167e, status=requested |
| 2026-11-17T19:50:49Z | refund_revokes_access | record_mock_payment (MOCKED, money_moved=false) | payment_id=pay_d7669af5cd80, event_id=evt_993688b040bb |
| 2026-11-17T19:50:49Z | refund_revokes_access | handle_event payment.succeeded -> processed | event_id=evt_993688b040bb, delivery_id=dlv_fd609d16ffbb |
| 2026-11-17T19:50:49Z | refund_revokes_access | refund (MOCKED, money_moved=false) | refund_id=ref_4f05ec6a7070, revoked=1 |
| 2026-11-17T19:50:49Z | refund_revokes_access | handle_event refund.succeeded -> processed | event_id=evt_3bd828628289 |
| 2026-11-17T19:50:49Z | refund_revokes_access | PASS |  |
| 2026-11-17T19:50:49Z | reconciliation_clean | start |  |
| 2026-11-17T19:50:49Z | reconciliation_clean | record_mock_payout (MOCKED) | payout_id=po_c2cfb6a41cdf, amount=705.0 |
| 2026-11-17T19:50:49Z | reconciliation_clean | reconcile -> ok=True, mismatches=0 |  |
| 2026-11-17T19:50:49Z | reconciliation_clean | PASS |  |
| 2026-11-17T19:50:49Z | reconciliation_detects_mismatch | start |  |
| 2026-11-17T19:50:49Z | reconciliation_detects_mismatch | injected: duplicate delivery, delivery without payment, paid order without delivery, re-activated refunded access, payout total +1.00 |  |
| 2026-11-17T19:50:49Z | reconciliation_detects_mismatch | reconcile on the injected copy -> ok=False, found: delivery_without_payment, duplicate_delivery, paid_order_without_delivery, payout_total_mismatch, refunded_order_with_active_access |  |
| 2026-11-17T19:50:49Z | reconciliation_detects_mismatch | PASS |  |
