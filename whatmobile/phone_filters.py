"""Helpers for WhatMobile phone querysets used across the app."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, Iterable, List

from django.db.models import Q, QuerySet

from .models import WhatMobilePhone
from .phone_matcher import normalize_phone_name

_NON_PHONE_PATTERN = re.compile(
    r"(?:\bwatch|\bipad|\btab\b|\btablet\b|\bairpods\b|\bairtag\b|"
    r"\bhomepod\b|\bpencil\b|\bbuds\b|\bband\b|\bgear\b|\bring\b|"
    r"\bvision\s*pro\b)",
    re.IGNORECASE,
)

_PRICE_SUFFIX_PATTERN = re.compile(
    r"\s*(price\s*&\s*specs|price\s*in\s*pakistan(?:\s*\d{4})?)\s*$",
    re.IGNORECASE,
)
_STORAGE_PATTERN = re.compile(r"\s+\d+\s*(gb|tb)\b", re.IGNORECASE)


def is_scrapeable_phone(brand: str, model_name: str) -> bool:
    """Return True only for Samsung/Apple mobile phones (no watches, tablets, etc.)."""
    name = (model_name or "").strip()
    if not name:
        return False

    brand_key = (brand or "").strip().lower()
    lower = name.lower()

    if brand_key == "apple":
        return "iphone" in lower

    if _NON_PHONE_PATTERN.search(name):
        return False

    return True


def is_comparison_phone(model_name: str) -> bool:
    name = (model_name or "").strip()
    if not name:
        return False
    if "iphone" in name.lower():
        return True
    return not bool(_NON_PHONE_PATTERN.search(name))


def all_phones_queryset() -> QuerySet[WhatMobilePhone]:
    """Return every Samsung/Apple model stored in the WhatMobile database."""
    return WhatMobilePhone.objects.using("whatmobile").order_by("brand", "model_name")


def comparison_phone_queryset() -> QuerySet[WhatMobilePhone]:
    """Mobile phones only — used for retailer matching and full phone lists."""
    queryset = all_phones_queryset()
    phone_filter = Q(brand="apple", model_name__icontains="iphone") | Q(brand="samsung")
    queryset = queryset.filter(phone_filter)
    for term in ("watch", "ipad", "tablet", "airpods", " buds", "gear", "ring"):
        queryset = queryset.exclude(model_name__icontains=term)
    return queryset.exclude(model_name__iregex=r"\btab\b")


def phone_display_label(brand: str, model_name: str) -> str:
    """Format a dropdown label without repeating the brand name."""
    model = (model_name or "").strip()
    if not model:
        return ""

    brand_labels = {"apple": "Apple", "samsung": "Samsung"}
    brand_label = brand_labels.get((brand or "").lower(), (brand or "").title())

    if model.lower().startswith(brand_label.lower()):
        return model
    return f"{brand_label} {model}"


def dropdown_model_key(brand: str, model_name: str) -> str:
    """Canonical key for grouping storage variants and duplicate listings."""
    label = phone_display_label(brand, model_name)
    cleaned = _PRICE_SUFFIX_PATTERN.sub("", label)
    cleaned = _STORAGE_PATTERN.sub("", cleaned)
    normalized = normalize_phone_name(cleaned)
    return f"{(brand or '').strip().lower()}|{normalized}"


def _dropdown_pick_score(phone: WhatMobilePhone) -> tuple:
    name = phone.model_name or ""
    return (
        0 if _STORAGE_PATTERN.search(name) else 1,
        0 if _PRICE_SUFFIX_PATTERN.search(name) else 1,
        len((phone.specifications or {}).get("grouped") or {}),
        len((phone.specifications or {}).get("flat") or {}),
        bool(phone.image or phone.image_url),
        phone.updated_at,
        -phone.id,
    )


def _pick_dropdown_phones(phones: Iterable[WhatMobilePhone]) -> List[WhatMobilePhone]:
    grouped: dict[str, list[WhatMobilePhone]] = defaultdict(list)
    for phone in phones:
        key = dropdown_model_key(phone.brand, phone.model_name)
        grouped[key].append(phone)
    return [max(group, key=_dropdown_pick_score) for group in grouped.values()]


def dropdown_phone_queryset() -> QuerySet[WhatMobilePhone]:
    """One entry per model for comparison dropdowns (no storage-variant duplicates)."""
    picked = _pick_dropdown_phones(comparison_phone_queryset())
    if not picked:
        return WhatMobilePhone.objects.using("whatmobile").none()
    ids = [phone.id for phone in picked]
    return (
        WhatMobilePhone.objects.using("whatmobile")
        .filter(id__in=ids)
        .order_by("brand", "model_name")
    )


def cleanup_non_phones() -> Dict[str, int]:
    """Delete WhatMobile records that are not mobile phones (watches, tablets, etc.)."""
    removed = 0
    for phone in WhatMobilePhone.objects.using("whatmobile").all().iterator():
        if not is_scrapeable_phone(phone.brand, phone.model_name):
            phone.delete()
            removed += 1
    return {"removed_non_phones": removed}
