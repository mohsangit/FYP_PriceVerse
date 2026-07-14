"""Detect discontinued phones from scraped WhatMobile and retailer data."""

from __future__ import annotations

import re

DISCONTINUED_MESSAGE = "This phone is discontinued."

_DISCONTINUED_RE = re.compile(r"\bdiscontinued\b", re.IGNORECASE)


def is_discontinued_text(*values: str | None) -> bool:
    """Return True only when scraped text explicitly contains 'discontinued'."""
    for value in values:
        if not value:
            continue
        if _DISCONTINUED_RE.search(str(value)):
            return True
    return False


def _iter_spec_texts(specifications: dict | None) -> list[str]:
    texts: list[str] = []
    stored = specifications or {}
    grouped = stored.get("grouped") or {}
    for category, values in grouped.items():
        if category:
            texts.append(str(category))
        if isinstance(values, dict):
            for label, value in values.items():
                texts.append(str(label))
                texts.append(str(value))
    flat = stored.get("flat") or {}
    for label, value in flat.items():
        texts.append(str(label))
        texts.append(str(value))
    return texts


def is_whatmobile_phone_discontinued(phone) -> bool:
    """Determine discontinued status from a WhatMobile phone record."""
    return is_discontinued_text(
        phone.release_status,
        phone.official_price,
        *_iter_spec_texts(phone.specifications),
    )


def is_product_discontinued(product) -> bool:
    """Determine discontinued status for a retailer product page."""
    from whatmobile.spec_fallback import find_matching_phone

    if is_discontinued_text(product.description, product.short_description):
        return True

    for listing in product.listings.all():
        specs = listing.specifications or {}
        if is_discontinued_text(*[str(value) for value in specs.values()]):
            return True

    phone = find_matching_phone(product)
    if phone and is_whatmobile_phone_discontinued(phone):
        return True

    return False
