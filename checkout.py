"""MOCKED checkout: a no-charge order request.

create_order() records that a buyer asked for a product at the advertised
price. Nothing is charged, no payment provider is contacted and no card or
bank data exists anywhere in this flow. The buyer's email is stored only as
a SHA-256 hash of the lowercased address plus a masked form (a***@domain).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from commerce import (CURRENCY_RE, MOCK_NOTE, CommerceError, CommerceStore, IdempotencyConflict, email_hash,
                      mask_email, money, new_id, valid_email)


class InvalidOrder(CommerceError):
    """The order request is malformed (email, price, currency or idempotency key)."""


class InvalidProduct(InvalidOrder):
    """The product does not exist in the catalog (or no product id was given)."""


def _in_catalog(product_id: str, catalog: Mapping[str, Any] | Iterable[str]) -> bool:
    if isinstance(catalog, Mapping):
        return product_id in catalog
    return product_id in set(catalog)


def _clean_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if len(clean) >= 10:
            break
        if isinstance(value, (bool, int, float)) or value is None:
            clean[str(key)[:40]] = value
        else:
            clean[str(key)[:40]] = str(value)[:120]
    return clean


def create_order(store: CommerceStore, *, product_id: str, buyer_email: str, price: float, currency: str,
                 idempotency_key: str, catalog: Mapping[str, Any] | Iterable[str] | None = None,
                 metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Record a MOCKED no-charge order (status "requested"). Same idempotency key -> the existing order."""
    product_id = (product_id or "").strip()
    if not product_id:
        raise InvalidProduct("No product id given.")
    if catalog is not None and not _in_catalog(product_id, catalog):
        raise InvalidProduct(f"Unknown product {product_id!r}.")
    key = (idempotency_key or "").strip()
    if not key:
        raise InvalidOrder("An idempotency key is required.")
    if not valid_email(buyer_email or ""):
        raise InvalidOrder("A valid email address is required.")
    try:
        amount = float(price)
    except (TypeError, ValueError):
        raise InvalidOrder(f"Invalid price {price!r}.") from None
    if not math.isfinite(amount) or amount < 0:
        raise InvalidOrder(f"Invalid price {price!r}.")
    currency = (currency or "").strip().upper()
    if not CURRENCY_RE.match(currency):
        raise InvalidOrder(f"Invalid currency {currency!r}: use a 3-letter code.")
    hashed = email_hash(buyer_email)

    with store.transaction() as data:
        existing = store.find_one(data, "orders", idempotency_key=key)
        if existing is not None:
            if existing["product_id"] != product_id or existing["buyer_email_hash"] != hashed:
                raise IdempotencyConflict("This idempotency key was already used for a different order.")
            return dict(existing, replayed=True)
        order = store.stamp({
            "order_id": new_id("ord"),
            "idempotency_key": key,
            "product_id": product_id,
            "price": money(amount),
            "currency": currency,
            "buyer_email_hash": hashed,
            "buyer_email_masked": mask_email(buyer_email),
            "status": "requested",
            "charged": False,
            "metadata": _clean_metadata(metadata),
            "note": "MOCKED no-charge order request: no payment was taken. " + MOCK_NOTE,
        })
        data["orders"].append(order)
        return dict(order, replayed=False)
