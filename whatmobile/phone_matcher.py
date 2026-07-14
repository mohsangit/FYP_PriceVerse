"""Match WhatMobile phones to retailer Product records for discounted pricing."""

from __future__ import annotations

import re
from typing import Optional

from django.db.models import Q

from products.models import Product
from products.price_utils import best_price_info, display_listing_for_product

from .discontinued import is_whatmobile_phone_discontinued
from .models import WhatMobilePhone
from .utils import normalize_price_to_pkr

_NOISE_WORDS = (
    "5g",
    "4g",
    "lte",
    "dual sim",
    "single sim",
    "pakistan",
    "pta",
    "approved",
    "unofficial",
    "official",
    "global",
    "international",
    "new",
    "brand new",
    "box packed",
    "used",
    "refurbished",
)

_BRAND_TOKENS = frozenset({"apple", "samsung", "galaxy", "iphone"})


def normalize_phone_name(name: str) -> str:
    text = (name or "").lower()
    for word in _NOISE_WORDS:
        text = text.replace(word, " ")
    text = re.sub(r"\b\d+\s*(gb|tb|mb)\b", " ", text)
    text = re.sub(r"\b\d+\s*mm\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _name_tokens(name: str) -> list[str]:
    tokens = [token for token in normalize_phone_name(name).split() if token not in _BRAND_TOKENS]
    return tokens


def _match_score(needle_tokens: list[str], haystack_tokens: list[str]) -> int:
    if not needle_tokens or not haystack_tokens:
        return 0
    if needle_tokens == haystack_tokens:
        return 10_000

    needle_set = set(needle_tokens)
    haystack_set = set(haystack_tokens)
    overlap = len(needle_set & haystack_set)
    if overlap == 0:
        return 0

    if needle_set == haystack_set:
        return 9_000

    # Require every significant token to match — prevents iPhone 16 matching iPhone 16e.
    if needle_set.issubset(haystack_set) or haystack_set.issubset(needle_set):
        length_penalty = abs(len(needle_tokens) - len(haystack_tokens)) * 250
        return overlap * 1_000 - length_penalty

    ratio = overlap / max(len(needle_set), len(haystack_set))
    if ratio < 0.75:
        return 0
    return int(ratio * 500) - abs(len(needle_tokens) - len(haystack_tokens)) * 100


def find_matching_product(phone: WhatMobilePhone) -> Optional[Product]:
    needle_tokens = _name_tokens(phone.model_name)
    if not needle_tokens:
        return None

    if phone.brand == "samsung":
        brand_q = Q(brand__icontains="samsung")
    else:
        brand_q = Q(brand__icontains="apple") | Q(brand__icontains="iphone")

    candidates = Product.objects.filter(brand_q).only("id", "title", "brand")
    best_product = None
    best_score = 0

    for product in candidates:
        haystack_tokens = _name_tokens(product.title)
        score = _match_score(needle_tokens, haystack_tokens)
        if score > best_score:
            best_score = score
            best_product = product

    if best_score >= 500:
        return best_product
    return None


def _discounted_listing(product: Product):
    info = best_price_info(product)
    listing = (info or {}).get("listing") or display_listing_for_product(product)
    if not listing:
        return None
    if listing.is_on_sale and listing.discount_pct > 0 and listing.old_price:
        return listing
    return None


def resolve_phone_price(phone: WhatMobilePhone) -> dict:
    """Discounted retailer price when available; otherwise WhatMobile official price in PKR."""
    discontinued = is_whatmobile_phone_discontinued(phone)

    product = find_matching_product(phone)
    if product:
        listing = _discounted_listing(product)
        if listing:
            return {
                "price": listing.current_price,
                "old_price": listing.old_price,
                "discount_pct": listing.discount_pct,
                "is_on_sale": True,
                "store": listing.store.name,
                "availability": "" if discontinued else listing.get_availability_status_display(),
                "source": "retailer",
                "currency": "PKR",
                "is_discontinued": discontinued,
            }

    pkr_value, _ = normalize_price_to_pkr(
        phone.official_price,
        phone.official_price_value,
        phone.official_price_currency,
    )
    if pkr_value and not discontinued:
        return {
            "price": pkr_value,
            "old_price": None,
            "discount_pct": 0,
            "is_on_sale": False,
            "store": "WhatMobile",
            "availability": phone.release_status or "Official price",
            "source": "whatmobile",
            "currency": "PKR",
            "price_label": f"Rs. {pkr_value:,}",
            "is_discontinued": False,
        }

    if discontinued:
        return {
            "price": pkr_value if pkr_value and pkr_value > 0 else None,
            "old_price": None,
            "discount_pct": 0,
            "is_on_sale": False,
            "store": "",
            "availability": "",
            "source": "whatmobile",
            "currency": "PKR",
            "price_label": "",
            "is_discontinued": True,
        }

    return {
        "price": None,
        "old_price": None,
        "discount_pct": 0,
        "is_on_sale": False,
        "store": "",
        "availability": phone.release_status or "Unknown",
        "source": "whatmobile",
        "currency": "PKR",
        "price_label": "",
        "is_discontinued": False,
    }
