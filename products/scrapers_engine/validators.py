from typing import Dict, List, Tuple


REQUIRED_FIELDS = (
    "title",
    "brand",
    "product_url",
    "current_price",
    "image_url",
    "availability_status",
)


INVALID_IMAGE_FRAGMENTS = (
    "lazy.svg",
    "placeholder",
    "logo.svg",
    "logo.webp",
    "bar.svg",
    "filterbar",
    "techroid-logo",
    "logo-01-scaled",
)


def _is_valid_image_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    lower = url.lower()
    return not any(fragment in lower for fragment in INVALID_IMAGE_FRAGMENTS)


def validate_scraped_record(record: Dict) -> Tuple[bool, List[str]]:
    """Return (is_valid, missing_fields)."""
    missing = []
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or value == "":
            missing.append(field)

    try:
        price = int(record.get("current_price") or 0)
    except (TypeError, ValueError):
        price = 0
    if price <= 0:
        missing.append("current_price")

    if not _is_valid_image_url(str(record.get("image_url") or "")):
        missing.append("image_url")

    description = (record.get("description") or "").strip()
    specifications = record.get("specifications") or {}
    if not description and not specifications:
        missing.append("description_or_specifications")

    return (len(missing) == 0, missing)
