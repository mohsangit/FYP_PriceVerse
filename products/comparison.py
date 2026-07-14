"""Helpers for the two-phone comparison feature.

Phone specifications are stored as free-form JSON whose keys are inconsistent
across products (e.g. ``Battery`` vs ``Battery Capacity``, ``Rear Camera`` vs
``Rear Cameras``, ``Processor`` vs ``Chip`` vs ``CPU``).  These helpers map that
messy data onto a fixed set of comparison fields and decide, where it makes
sense, which phone "wins" a given numeric spec.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import Product
from .price_utils import best_price_info, display_listing_for_product

# Each comparison row: a human label, the possible source spec keys (synonyms),
# whether the value is numeric, and which direction is "better".
COMPARE_FIELDS = [
    {"label": "Display Size", "keys": ["Display Size", "Display", "Screen Size", "Screen"], "numeric": True, "better": "high", "unit": '"'},
    {"label": "Resolution", "keys": ["Resolution"], "numeric": False},
    {"label": "Refresh Rate", "keys": ["Refresh Rate", "Refresh"], "numeric": True, "better": "high", "unit": "Hz"},
    {"label": "Processor", "keys": ["Processor", "Chip", "Chipset", "CPU"], "numeric": False},
    {"label": "RAM", "keys": ["RAM", "Memory"], "numeric": True, "better": "high", "unit": "GB"},
    {"label": "Storage", "keys": ["Storage", "Storage Options", "Internal Storage"], "numeric": True, "better": "high", "unit": "GB"},
    {"label": "Rear Camera", "keys": ["Rear Camera", "Rear Cameras", "Main Camera", "Camera"], "numeric": True, "better": "high", "unit": "MP"},
    {"label": "Front Camera", "keys": ["Front Camera", "Selfie Camera"], "numeric": True, "better": "high", "unit": "MP"},
    {"label": "Battery Capacity", "keys": ["Battery Capacity", "Battery"], "numeric": True, "better": "high", "unit": "mAh"},
    {"label": "Charging Speed", "keys": ["Charging Speed", "Charging", "Fast Charging"], "numeric": True, "better": "high", "unit": "W"},
    {"label": "Operating System", "keys": ["Operating System", "OS"], "numeric": False},
]


def _merged_specs(product: Product) -> dict:
    """Combine product-level specs with any specs attached to listings."""
    specs: dict = {}
    for listing in product.listings.all():
        if listing.specifications:
            specs.update(listing.specifications)
    if product.specifications:
        specs.update(product.specifications)
    return specs


def _lookup_spec(specs: dict, keys: list[str]) -> Optional[str]:
    """Case-insensitive lookup that tries each synonym key in order."""
    lowered = {str(k).strip().lower(): v for k, v in (specs or {}).items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return None


def _parse_number(text: Optional[str]) -> Optional[float]:
    """Pull the first sensible number out of a spec string."""
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(text).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def build_phone_payload(product: Product) -> dict:
    """Build the canonical, database-only data used by both the UI and the AI."""
    specs = _merged_specs(product)
    info = best_price_info(product)
    listing = (info or {}).get("listing") or display_listing_for_product(product)

    if product.image:
        image = product.image.url
    elif product.image_url:
        image = product.image_url
    else:
        image = ""

    fields = []
    for field in COMPARE_FIELDS:
        raw = _lookup_spec(specs, field["keys"])
        fields.append(
            {
                "label": field["label"],
                "value": raw or "—",
                "raw": raw,
                "numeric": field["numeric"],
                "better": field.get("better"),
                "number": _parse_number(raw) if field["numeric"] else None,
                "has_value": bool(raw),
            }
        )

    return {
        "id": product.id,
        "slug": product.slug,
        "name": product.title,
        "brand": product.brand or "",
        "image": image,
        "price": info["best_price"] if info else (listing.current_price if listing else None),
        "old_price": (info or {}).get("old_price") if info else (listing.old_price if listing else None),
        "discount_pct": (info or {}).get("best_discount_pct", 0) if info else 0,
        "is_on_sale": bool(listing and listing.is_on_sale),
        "store": (info or {}).get("store_name") if info else (listing.store.name if listing else None),
        "availability": listing.get_availability_status_display() if listing else "Unknown",
        "fields": fields,
    }


def _decide_winner(field_a: dict, field_b: dict) -> Optional[str]:
    if not field_a["numeric"] or field_a["number"] is None or field_b["number"] is None:
        return None
    if field_a["number"] == field_b["number"]:
        return None
    better = field_a.get("better", "high")
    if better == "low":
        return "a" if field_a["number"] < field_b["number"] else "b"
    return "a" if field_a["number"] > field_b["number"] else "b"


def _price_winner(payload_a: dict, payload_b: dict) -> Optional[str]:
    pa, pb = payload_a.get("price"), payload_b.get("price")
    if pa is None or pb is None or pa == pb:
        return None
    return "a" if pa < pb else "b"


def build_comparison(product_a: Product, product_b: Product) -> dict:
    """Return both payloads plus per-row winners and category summaries."""
    payload_a = build_phone_payload(product_a)
    payload_b = build_phone_payload(product_b)

    rows = []
    wins = {"a": 0, "b": 0}
    for field_a, field_b in zip(payload_a["fields"], payload_b["fields"]):
        winner = _decide_winner(field_a, field_b)
        if winner:
            wins[winner] += 1
        rows.append(
            {
                "label": field_a["label"],
                "a": field_a["value"],
                "b": field_b["value"],
                "winner": winner,
            }
        )

    price_winner = _price_winner(payload_a, payload_b)
    if price_winner:
        wins[price_winner] += 1

    price_row = {
        "label": "Best Price",
        "a": f"Rs. {payload_a['price']:,}" if payload_a["price"] else "—",
        "b": f"Rs. {payload_b['price']:,}" if payload_b["price"] else "—",
        "winner": price_winner,
    }
    rows.insert(0, price_row)

    overall = None
    if wins["a"] != wins["b"]:
        overall = "a" if wins["a"] > wins["b"] else "b"

    return {
        "a": payload_a,
        "b": payload_b,
        "rows": rows,
        "wins": wins,
        "overall": overall,
    }
