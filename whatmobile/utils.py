import random
import re
import time

import requests
from django.core.files.base import ContentFile


def polite_sleep(min_seconds: float = 1.0, max_seconds: float = 2.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def download_image_to_phone(phone, image_url: str) -> bool:
    """Download a remote image and store it on the WhatMobile phone record."""
    if not image_url or phone.image:
        return False

    try:
        polite_sleep(0.8, 1.5)
        response = requests.get(
            image_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if response.status_code != 200:
            return False

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "image" not in content_type:
            return False

        ext = "jpg"
        if "png" in content_type:
            ext = "png"
        elif "webp" in content_type:
            ext = "webp"

        filename = f"{phone.slug}.{ext}"
        phone.image.save(filename, ContentFile(response.content), save=True)
        return True
    except Exception:
        return False


def parse_price_value(price_text: str) -> tuple[int | None, str]:
    """Extract the first numeric price and currency symbol from a WhatMobile price string."""
    pkr_value, currency = normalize_price_to_pkr(price_text)
    return pkr_value, currency


def normalize_price_to_pkr(
    price_text: str,
    stored_value: int | None = None,
    stored_currency: str = "",
) -> tuple[int | None, str]:
    """
    Return a positive PKR price.

    Prefers Rs/PKR amounts from WhatMobile text. Converts USD when needed.
    """
    from django.conf import settings

    rate = float(getattr(settings, "USD_TO_PKR_RATE", 278) or 278)
    text = (price_text or "").strip()

    if text:
        rs_match = re.search(
            r"(?:price\s+in\s+rs|rs\.?|pkr)\s*:?\s*([\d,]+(?:\.\d+)?)",
            text,
            re.IGNORECASE,
        )
        if rs_match:
            try:
                value = int(float(rs_match.group(1).replace(",", "")))
                if value > 0:
                    return value, "PKR"
            except ValueError:
                pass

        usd_match = re.search(
            r"(?:price\s+in\s+usd|usd)\s*:?\s*\$?\s*([\d,]+(?:\.\d+)?)|\$\s*([\d,]+(?:\.\d+)?)",
            text,
            re.IGNORECASE,
        )
        if usd_match:
            raw = usd_match.group(1) or usd_match.group(2)
            try:
                usd = float(raw.replace(",", ""))
                if usd > 0:
                    return int(round(usd * rate)), "PKR"
            except (TypeError, ValueError):
                pass

    currency = (stored_currency or "").upper()
    if stored_value and stored_value > 0:
        if currency in {"", "PKR", "RS"} or "rs" in text.lower():
            return int(stored_value), "PKR"
        if currency == "USD":
            return int(round(stored_value * rate)), "PKR"

    if text:
        if "€" in text:
            currency_hint = "EUR"
        elif "$" in text or "usd" in text.lower():
            currency_hint = "USD"
        elif "£" in text:
            currency_hint = "GBP"
        elif "₹" in text:
            currency_hint = "INR"
        elif "Rs" in text or "PKR" in text.upper():
            currency_hint = "PKR"
        else:
            currency_hint = ""

        match = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
        if match:
            try:
                value = int(float(match.group(0)))
            except ValueError:
                value = None
            if value and value > 0:
                if currency_hint == "USD":
                    return int(round(value * rate)), "PKR"
                if currency_hint in {"PKR", "RS", ""}:
                    return value, "PKR"

    return None, "PKR"
