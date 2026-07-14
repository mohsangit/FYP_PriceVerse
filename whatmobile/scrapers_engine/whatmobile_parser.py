"""Parse WhatMobile listing and detail pages into structured phone records."""

from __future__ import annotations

import re
import zlib
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from whatmobile.phone_filters import is_scrapeable_phone
from whatmobile.utils import parse_price_value

WHATMOBILE_BASE_URL = "https://www.whatmobile.com.pk/"

BRAND_LISTING_PAGES = {
    "apple": f"{WHATMOBILE_BASE_URL}Apple_Mobiles_Prices",
    "samsung": f"{WHATMOBILE_BASE_URL}Samsung_Mobiles_Prices",
}

BRAND_LINK_PREFIX = {
    "apple": "Apple_",
    "samsung": "Samsung_",
}

LISTING_SKIP_PATTERN = re.compile(
    r"_Mobiles_Prices|_Prices_in_Pakistan|_New-Model-",
    re.IGNORECASE,
)


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Tag):
        value = value.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", str(value)).strip()


def url_to_source_id(page_url: str) -> int:
    """Stable positive integer ID from a WhatMobile URL path."""
    path = urlparse(page_url).path.strip("/").lower()
    return zlib.crc32(path.encode("utf-8")) & 0x7FFFFFFF


def _is_phone_listing_href(brand: str, href: str) -> bool:
    if not href:
        return False
    path = href.split("whatmobile.com.pk", 1)[-1] if "whatmobile.com.pk" in href else href
    path = path.split("?", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    prefix = BRAND_LINK_PREFIX.get(brand, "")
    if not path.startswith(f"/{prefix}"):
        return False
    if LISTING_SKIP_PATTERN.search(path):
        return False
    slug = path.strip("/")
    if slug in {page.rsplit("/", 1)[-1] for page in BRAND_LISTING_PAGES.values()}:
        return False
    return bool(re.search(r"-", slug))


def parse_brand_listing_page(
    html: str,
    page_url: str,
    brand: str = "",
) -> tuple[List[Dict], Optional[str]]:
    """Return phone targets from a WhatMobile brand listing (single page, no pagination)."""
    soup = BeautifulSoup(html, "html.parser")
    targets: Dict[str, Dict] = {}

    for link in soup.select("a[href]"):
        href = (link.get("href") or "").strip()
        if not _is_phone_listing_href(brand, href):
            continue

        full_url = urljoin(page_url, href)
        if full_url in targets:
            continue

        model_name = _clean_text(link) or _clean_text(link.get("title"))
        if not model_name:
            slug = urlparse(full_url).path.strip("/").replace("_", " ").replace("-", " ")
            model_name = slug
        if brand and not is_scrapeable_phone(brand, model_name):
            continue

        source_id = url_to_source_id(full_url)
        targets[full_url] = {
            "url": full_url,
            "source_id": source_id,
            "model_name": model_name,
        }

    return list(targets.values()), None


_SPEC_CATEGORY_HEADERS = frozenset({
    "network", "launch", "body", "display", "memory", "platform", "performance",
    "camera", "main camera", "selfie camera", "battery", "features", "price",
    "connectivity", "sensors", "sound", "comms", "misc", "storage", "build",
    "sim", "ui", "design", "processor", "chipset", "software", "multimedia",
})


def _is_category_header(label: str) -> bool:
    return label.strip().lower() in _SPEC_CATEGORY_HEADERS


def _parse_spec_tables(soup: BeautifulSoup) -> tuple[dict, dict, str, str]:
    grouped: dict = {}
    flat: dict = {}
    release_status = ""
    official_price = ""

    for table in soup.select("table"):
        current_category = ""

        for row in table.select("tr"):
            cells = row.select("td, th")
            if not cells:
                continue

            texts = [_clean_text(cell) for cell in cells]
            texts = [text for text in texts if text]
            if not texts:
                continue

            if len(texts) == 1:
                current_category = texts[0]
                grouped.setdefault(current_category, {})
                continue

            label = texts[0]
            value = texts[-1] if len(texts) > 1 else ""
            if not value or value == label:
                continue

            if _is_category_header(label):
                current_category = label
                grouped.setdefault(current_category, {})
                continue

            category = current_category or "General"
            grouped.setdefault(category, {})[label] = value
            flat_key = f"{category} — {label}" if category != "General" else label
            flat[flat_key] = value

            label_lower = label.lower()
            value_lower = value.lower()
            if label_lower in {"price", "price in pakistan"} or "price in rs" in value_lower:
                official_price = value
            if label_lower in {"status", "launch", "announced", "release"}:
                release_status = value or release_status

    if not official_price:
        for row in soup.select("table tr"):
            text = _clean_text(row)
            if "price in rs" in text.lower() or "price in pakistan" in text.lower():
                official_price = text
                break

    if not official_price:
        price_match = soup.find(string=re.compile(r"Rs\.?\s*[\d,]+", re.IGNORECASE))
        if price_match:
            official_price = _clean_text(price_match)

    return grouped, flat, release_status, official_price


def _extract_image_url(soup: BeautifulSoup, page_url: str) -> str:
    og_image = soup.select_one('meta[property="og:image"]')
    if og_image and og_image.get("content"):
        return urljoin(page_url, og_image["content"].strip())

    for img in soup.select("img[src]"):
        src = (img.get("src") or "").strip()
        if not src or "logo" in src.lower():
            continue
        if any(token in src.lower() for token in ("assets", "phone", "mobile", "news", "images")):
            return urljoin(page_url, src)
    return ""


def parse_phone_detail(html: str, page_url: str, brand: str) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h1")
    model_name = _clean_text(title_el)
    if not model_name or not is_scrapeable_phone(brand, model_name):
        return None

    source_id = url_to_source_id(page_url)
    image_url = _extract_image_url(soup, page_url)

    description = ""
    meta_desc = soup.select_one('meta[name="description"]')
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    grouped, flat, release_status, official_price = _parse_spec_tables(soup)
    if not official_price:
        for el in soup.select("strong, b, .Heading1 strong"):
            text = _clean_text(el)
            if re.search(r"^\d{2,3},\d{3}$", text.replace(",", "")):
                official_price = f"Rs. {text}"
                break

    price_value, price_currency = parse_price_value(official_price)
    if not price_currency and price_value:
        price_currency = "PKR"

    return {
        "brand": brand,
        "model_name": model_name,
        "source_id": source_id,
        "source_url": page_url,
        "image_url": image_url,
        "description": description,
        "release_status": release_status,
        "official_price": official_price,
        "official_price_value": price_value,
        "official_price_currency": price_currency or "PKR",
        "specifications": {
            "grouped": grouped,
            "flat": flat,
        },
    }
