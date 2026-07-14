"""Remove duplicate WhatMobile phone records, keeping one canonical entry per model."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict

from django.db import transaction

from .models import WhatMobilePhone
from .phone_matcher import _name_tokens


def _model_key(phone: WhatMobilePhone) -> str:
    tokens = _name_tokens(phone.model_name)
    brand = (phone.brand or "").strip().lower()
    return f"{brand}|{' '.join(tokens)}"


def _pick_canonical_phone(phones: list[WhatMobilePhone]) -> WhatMobilePhone:
    return max(
        phones,
        key=lambda phone: (
            len((phone.specifications or {}).get("grouped") or {}),
            len((phone.specifications or {}).get("flat") or {}),
            len(phone.description or ""),
            bool(phone.image or phone.image_url),
            phone.updated_at,
            -phone.id,
        ),
    )


def _merge_specs(canonical: WhatMobilePhone, duplicate: WhatMobilePhone) -> dict:
    merged = dict(canonical.specifications or {})
    duplicate_specs = duplicate.specifications or {}

    merged_grouped = dict(merged.get("grouped") or {})
    for category, values in (duplicate_specs.get("grouped") or {}).items():
        bucket = dict(merged_grouped.get(category) or {})
        for label, value in (values or {}).items():
            if label and value and label not in bucket:
                bucket[label] = value
        if bucket:
            merged_grouped[category] = bucket
    merged["grouped"] = merged_grouped

    merged_flat = dict(merged.get("flat") or {})
    for label, value in (duplicate_specs.get("flat") or {}).items():
        if label and value and label not in merged_flat:
            merged_flat[label] = value
    merged["flat"] = merged_flat

    return merged


def _merge_phone_into(canonical: WhatMobilePhone, duplicate: WhatMobilePhone) -> None:
    if canonical.id == duplicate.id:
        return

    canonical.specifications = _merge_specs(canonical, duplicate)

    if not canonical.description and duplicate.description:
        canonical.description = duplicate.description
    elif len(duplicate.description or "") > len(canonical.description or ""):
        canonical.description = duplicate.description

    if not canonical.official_price and duplicate.official_price:
        canonical.official_price = duplicate.official_price
        canonical.official_price_value = duplicate.official_price_value
        canonical.official_price_currency = duplicate.official_price_currency

    if not canonical.release_status and duplicate.release_status:
        canonical.release_status = duplicate.release_status

    if not canonical.image and duplicate.image:
        canonical.image = duplicate.image
    if not canonical.image_url and duplicate.image_url:
        canonical.image_url = duplicate.image_url

    canonical.save()
    duplicate.delete()


@transaction.atomic(using="whatmobile")
def cleanup_duplicate_phones() -> Dict[str, int]:
    """Merge duplicate WhatMobile records that represent the same phone model."""
    grouped: dict[str, list[WhatMobilePhone]] = defaultdict(list)
    for phone in WhatMobilePhone.objects.using("whatmobile").all().iterator():
        key = _model_key(phone)
        if key:
            grouped[key].append(phone)

    removed = 0
    for phones in grouped.values():
        if len(phones) < 2:
            continue
        canonical = _pick_canonical_phone(phones)
        for duplicate in phones:
            if duplicate.id != canonical.id:
                _merge_phone_into(canonical, duplicate)
                removed += 1

    return {
        "removed_duplicates": removed,
        "total_cleaned": removed,
    }
