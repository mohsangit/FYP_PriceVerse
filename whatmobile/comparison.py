"""Build side-by-side comparisons using WhatMobile specs and bridged retailer prices."""

from __future__ import annotations

import re
from typing import Optional

from .discontinued import DISCONTINUED_MESSAGE, is_whatmobile_phone_discontinued
from .models import WhatMobilePhone
from .phone_matcher import resolve_phone_price

CATEGORY_ORDER = [
    "Network",
    "Launch",
    "Body",
    "Display",
    "Platform",
    "Memory",
    "Main Camera",
    "Selfie camera",
    "Sound",
    "Comms",
    "Features",
    "Battery",
    "Misc",
    "Our Tests",
    "EU LABEL",
    "General",
    "Specifications",
]

# Unified labels shown first in the comparison table.
KEY_SPEC_ROWS = [
    {"label": "Display Size", "category": "Display", "keys": ["Size", "Display Size", "Screen Size"]},
    {"label": "Resolution", "category": "Display", "keys": ["Resolution"]},
    {"label": "Display Type", "category": "Display", "keys": ["Type"]},
    {"label": "Processor", "category": "Platform", "keys": ["Chipset", "CPU", "Processor"]},
    {"label": "Operating System", "category": "Platform", "keys": ["OS", "Operating System"]},
    {"label": "RAM / Storage", "category": "Memory", "keys": ["Internal", "RAM", "Storage"]},
    {"label": "Rear Camera", "category": "Main Camera", "keys": ["Quad", "Triple", "Dual", "Single", "Main Camera"]},
    {"label": "Front Camera", "category": "Selfie camera", "keys": ["Single", "Dual", "Front Camera"]},
    {"label": "Battery", "category": "Battery", "keys": ["Type", "Capacity", "Battery"]},
    {"label": "Charging", "category": "Battery", "keys": ["Charging", "Charging Speed"]},
    {"label": "Weight", "category": "Body", "keys": ["Weight"]},
    {"label": "Dimensions", "category": "Body", "keys": ["Dimensions"]},
    {"label": "Build", "category": "Body", "keys": ["Build"]},
    {"label": "Colors", "category": "Misc", "keys": ["Colors"]},
    {"label": "Release Status", "category": "Launch", "keys": ["Status"]},
]

NUMERIC_BETTER_HIGH = {
    "display size": "high",
    "size": "high",
    "resolution": "high",
    "refresh rate": "high",
    "internal": "high",
    "ram": "high",
    "main camera": "high",
    "selfie camera": "high",
    "rear camera": "high",
    "front camera": "high",
    "battery": "high",
    "charging": "high",
}

NUMERIC_BETTER_LOW = {
    "weight": "low",
    "dimensions": "low",
    "price": "low",
}


def _parse_number(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(text).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _winner_for_values(value_a: str, value_b: str, label: str) -> Optional[str]:
    if value_a in ("—", "") or value_b in ("—", ""):
        return None

    label_key = label.lower()
    direction = None
    for key, better in {**NUMERIC_BETTER_HIGH, **NUMERIC_BETTER_LOW}.items():
        if key in label_key:
            direction = better
            break
    if not direction:
        return None

    num_a = _parse_number(value_a)
    num_b = _parse_number(value_b)
    if num_a is None or num_b is None or num_a == num_b:
        return None

    if direction == "low":
        return "a" if num_a < num_b else "b"
    return "a" if num_a > num_b else "b"


def _brand_label(phone: WhatMobilePhone) -> str:
    if phone.brand == "apple":
        return "Apple"
    if phone.brand == "samsung":
        return "Samsung"
    return phone.brand.title()


def _format_price(price_info: dict) -> str:
    price = price_info.get("price")
    if price is not None and price > 0:
        return f"Rs. {int(price):,}"

    return "—"


def _price_winner(payload_a: dict, payload_b: dict) -> Optional[str]:
    price_a = payload_a.get("price")
    price_b = payload_b.get("price")

    if price_a is None or price_b is None or price_a == price_b:
        return None

    return "a" if price_a < price_b else "b"


def _get_grouped_specs(phone: WhatMobilePhone) -> dict:
    """Return grouped WhatMobile specs, falling back to flat storage if needed."""
    stored = phone.specifications or {}
    grouped = dict(stored.get("grouped") or {})
    if grouped:
        return grouped

    flat = stored.get("flat") or {}
    if flat:
        return {"Specifications": dict(flat)}

    return {}


def _lookup_spec(grouped: dict, category: str, keys: list[str]) -> str:
    category_values = grouped.get(category) or {}
    for key in keys:
        value = category_values.get(key)
        if value not in (None, ""):
            return str(value).strip()

    lowered_keys = {str(k).lower(): v for k, v in category_values.items()}
    for key in keys:
        value = lowered_keys.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()

    for cat_values in grouped.values():
        if not isinstance(cat_values, dict):
            continue
        lowered = {str(k).lower(): v for k, v in cat_values.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value not in (None, ""):
                return str(value).strip()

    return "—"


def _is_valid_spec_value(value) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or text in {"—", "-"}:
        return False
    if text.lower() in {"n/a", "na", "unknown", "none", "not available", "price n/a"}:
        return False
    return True


def _build_row(label: str, value_a: str, value_b: str, category: str = "") -> dict:
    winner = _winner_for_values(value_a, value_b, label)
    return {
        "label": label,
        "a": value_a,
        "b": value_b,
        "winner": winner,
        "category": category,
    }


def build_phone_payload(phone: WhatMobilePhone) -> dict:
    price_info = resolve_phone_price(phone)
    grouped = _get_grouped_specs(phone)
    discontinued = is_whatmobile_phone_discontinued(phone) or bool(price_info.get("is_discontinued"))

    return {
        "id": phone.id,
        "slug": phone.slug,
        "name": phone.model_name,
        "brand": _brand_label(phone),
        "image": phone.display_image,
        "description": phone.description,
        "release_status": "" if discontinued else phone.release_status,
        "price": price_info.get("price"),
        "old_price": price_info.get("old_price"),
        "discount_pct": price_info.get("discount_pct", 0),
        "is_on_sale": price_info.get("is_on_sale", False),
        "store": price_info.get("store", ""),
        "availability": "" if discontinued else price_info.get("availability", ""),
        "price_source": price_info.get("source", "whatmobile"),
        "price_currency": price_info.get("currency", ""),
        "price_display": _format_price(price_info),
        "grouped_specs": grouped,
        "is_discontinued": discontinued,
        "discontinued_message": DISCONTINUED_MESSAGE if discontinued else "",
    }


def _ordered_categories(grouped_a: dict, grouped_b: dict) -> list[str]:
    keys = set(grouped_a.keys()) | set(grouped_b.keys())
    ordered = [cat for cat in CATEGORY_ORDER if cat in keys]
    for cat in sorted(keys):
        if cat not in ordered:
            ordered.append(cat)
    return ordered


def _build_key_spec_rows(grouped_a: dict, grouped_b: dict) -> list[dict]:
    rows = []
    seen_pairs = set()

    for spec in KEY_SPEC_ROWS:
        value_a = _lookup_spec(grouped_a, spec["category"], spec["keys"])
        value_b = _lookup_spec(grouped_b, spec["category"], spec["keys"])
        if not (_is_valid_spec_value(value_a) and _is_valid_spec_value(value_b)):
            continue
        rows.append(_build_row(spec["label"], value_a, value_b, "Key Specifications"))
        for key in spec["keys"]:
            seen_pairs.add((spec["category"], key.lower()))

    return rows, seen_pairs


def build_comparison(phone_a: WhatMobilePhone, phone_b: WhatMobilePhone) -> dict:
    payload_a = build_phone_payload(phone_a)
    payload_b = build_phone_payload(phone_b)

    wins = {"a": 0, "b": 0}
    rows = []

    price_row = None
    if _is_valid_spec_value(payload_a["price_display"]) and _is_valid_spec_value(payload_b["price_display"]):
        price_winner = _price_winner(payload_a, payload_b)
        if price_winner:
            wins[price_winner] += 1
        price_row = _build_row("Price", payload_a["price_display"], payload_b["price_display"], "Overview")
        price_row["winner"] = price_winner
        rows.append(price_row)

    key_rows, seen_pairs = _build_key_spec_rows(
        payload_a["grouped_specs"],
        payload_b["grouped_specs"],
    )
    for row in key_rows:
        if row["winner"]:
            wins[row["winner"]] += 1
        rows.append(row)

    sections = []
    if key_rows:
        sections.append({"category": "Key Specifications", "rows": key_rows})

    for category in _ordered_categories(payload_a["grouped_specs"], payload_b["grouped_specs"]):
        spec_rows = []
        keys_a = payload_a["grouped_specs"].get(category, {})
        keys_b = payload_b["grouped_specs"].get(category, {})
        all_keys = list(dict.fromkeys(list(keys_a.keys()) + list(keys_b.keys())))

        for label in all_keys:
            if category == "Misc" and label.lower() == "price":
                continue
            if (category, label.lower()) in seen_pairs:
                continue

            value_a = keys_a.get(label)
            value_b = keys_b.get(label)
            if not (_is_valid_spec_value(value_a) and _is_valid_spec_value(value_b)):
                continue

            row = _build_row(str(label), str(value_a), str(value_b), category)
            if row["winner"]:
                wins[row["winner"]] += 1
            spec_rows.append(row)
            rows.append(row)

        if spec_rows:
            sections.append({"category": category, "rows": spec_rows})

    overall = None
    if wins["a"] != wins["b"]:
        overall = "a" if wins["a"] > wins["b"] else "b"

    return {
        "a": payload_a,
        "b": payload_b,
        "price_row": price_row,
        "key_rows": key_rows,
        "rows": rows,
        "sections": sections,
        "wins": wins,
        "overall": overall,
        "has_specs": len(key_rows) > 0 or any(section["rows"] for section in sections),
    }
