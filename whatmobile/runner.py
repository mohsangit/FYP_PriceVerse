from typing import Dict, List

from django.utils.text import slugify

from whatmobile.phone_filters import is_scrapeable_phone
from whatmobile.models import WhatMobilePhone
from whatmobile.utils import download_image_to_phone


def clear_all_phones() -> int:
    """Delete all phone records from the comparison database."""
    deleted, _ = WhatMobilePhone.objects.using("whatmobile").all().delete()
    return deleted


def _unique_slug(model_name: str, brand: str, source_id: int) -> str:
    base = slugify(model_name) or slugify(brand) or "phone"
    return f"{base}-{source_id}"[:240]


def upsert_phone(record: Dict) -> Dict:
    """Insert or update a single WhatMobile phone record."""
    source_id = record.get("source_id")
    model_name = (record.get("model_name") or "").strip()
    brand = (record.get("brand") or "").strip()
    source_url = (record.get("source_url") or "").strip()
    if not source_id or not model_name or not source_url:
        return {"added": 0, "updated": 0, "skipped": 1, "saved": 0}
    if not is_scrapeable_phone(brand, model_name):
        return {"added": 0, "updated": 0, "skipped": 1, "saved": 0}

    slug = _unique_slug(model_name, brand, source_id)
    defaults = {
        "brand": record.get("brand") or "",
        "model_name": model_name,
        "slug": slug,
        "source_url": source_url,
        "image_url": (record.get("image_url") or "").strip(),
        "description": (record.get("description") or "").strip(),
        "release_status": (record.get("release_status") or "").strip(),
        "official_price": (record.get("official_price") or "").strip(),
        "official_price_value": record.get("official_price_value"),
        "official_price_currency": (record.get("official_price_currency") or "").strip(),
        "specifications": record.get("specifications") or {},
    }

    phone, created = WhatMobilePhone.objects.using("whatmobile").update_or_create(
        source_id=source_id,
        defaults=defaults,
    )

    image_url = defaults["image_url"]
    if image_url and not phone.image:
        download_image_to_phone(phone, image_url)

    if created:
        return {"added": 1, "updated": 0, "skipped": 0, "saved": 1}
    return {"added": 0, "updated": 1, "skipped": 0, "saved": 1}


def upsert_phones(results: List[Dict]) -> Dict:
    added = 0
    updated = 0
    skipped = 0

    for record in results:
        result = upsert_phone(record)
        added += result.get("added", 0)
        updated += result.get("updated", 0)
        skipped += result.get("skipped", 0)

    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "saved": added + updated,
    }
