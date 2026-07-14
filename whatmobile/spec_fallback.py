"""Fill missing product specifications from the WhatMobile database."""

from __future__ import annotations

from typing import Optional

from products.models import Product

from .models import WhatMobilePhone
from .phone_filters import comparison_phone_queryset
from .phone_matcher import _match_score, _name_tokens


def find_matching_phone(product: Product) -> Optional[WhatMobilePhone]:
    """Find the best WhatMobile phone record for a retailer product."""
    needle_tokens = _name_tokens(product.title)
    if not needle_tokens:
        return None

    brand = (product.brand or "").lower()
    if "samsung" in brand:
        candidates = comparison_phone_queryset().filter(brand="samsung")
    elif "apple" in brand or "iphone" in brand:
        candidates = comparison_phone_queryset().filter(brand="apple")
    else:
        candidates = comparison_phone_queryset()

    best_phone = None
    best_score = 0

    for phone in candidates.only("id", "model_name", "brand"):
        haystack_tokens = _name_tokens(phone.model_name)
        score = _match_score(needle_tokens, haystack_tokens)
        if score > best_score:
            best_score = score
            best_phone = phone

    if best_score >= 500 and best_phone:
        return WhatMobilePhone.objects.filter(pk=best_phone.id).first()
    return None


def _merged_product_specs(product: Product) -> dict:
    specs: dict = {}
    for listing in product.listings.all():
        for key, value in (listing.specifications or {}).items():
            if key and value not in (None, ""):
                specs[str(key)] = value
    for key, value in (product.specifications or {}).items():
        if key and value not in (None, ""):
            specs[str(key)] = value
    return specs


_TRIVIAL_SPEC_KEYS = frozenset({"model", "title", "name", "brand", "product"})


def _has_meaningful_specs(specs: dict) -> bool:
    if not specs:
        return False
    meaningful = 0
    for key, value in specs.items():
        if str(key).strip().lower() in _TRIVIAL_SPEC_KEYS:
            continue
        if str(value).strip():
            meaningful += 1
    return meaningful > 0


def flatten_phone_specifications(phone: WhatMobilePhone) -> dict:
    """Convert WhatMobile grouped specs into a flat display dictionary."""
    stored = phone.specifications or {}
    flat = dict(stored.get("flat") or {})
    if flat:
        return {str(key): str(value) for key, value in flat.items() if value not in (None, "")}

    grouped = stored.get("grouped") or {}
    result: dict = {}
    for category, values in grouped.items():
        for label, value in (values or {}).items():
            if not label or value in (None, ""):
                continue
            key = f"{category} — {label}" if category and category != "General" else str(label)
            result[key] = str(value)
    return result


def get_display_specifications(product: Product) -> tuple[dict, str]:
    """
    Return specifications for the product detail page.

    Price and image are always handled separately from the product record.
    Uses retailer/listing specs when present; otherwise falls back to WhatMobile.
    """
    product_specs = _merged_product_specs(product)
    if _has_meaningful_specs(product_specs):
        return product_specs, "product"

    phone = find_matching_phone(product)
    if phone:
        phone_specs = flatten_phone_specifications(phone)
        if _has_meaningful_specs(phone_specs):
            return phone_specs, "whatmobile"

    return product_specs, "product"
