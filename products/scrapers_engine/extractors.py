import html
import json
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .validators import INVALID_IMAGE_FRAGMENTS


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", cleaned)).strip()


def detect_brand(title: str, brand_hint: str = "") -> str:
    if brand_hint:
        return brand_hint.strip()
    t = (title or "").lower()
    if "iphone" in t or (t.startswith("apple ") and "macbook" not in t):
        return "Apple"
    if "samsung" in t or "galaxy" in t:
        return "Samsung"
    return ""


def normalize_availability(value: str) -> str:
    v = (value or "").lower()
    if "instock" in v or "in stock" in v or "in_stock" in v:
        return "in_stock"
    if "outofstock" in v or "out of stock" in v or "out_of_stock" in v:
        return "out_of_stock"
    if "preorder" in v or "pre-order" in v:
        return "pre_order"
    if "backorder" in v or "back order" in v:
        return "back_order"
    return "unknown"


def parse_json_ld_product(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                return item
            graph = item.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and node.get("@type") == "Product":
                        return node
    return None


def product_from_json_ld(data: Dict[str, Any], fallback_url: str = "") -> Dict[str, Any]:
    offers = data.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    brand = data.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name", "")
    brand = str(brand or "").strip()

    image = data.get("image")
    if isinstance(image, list):
        image = image[0] if image else ""
    image_url = str(image or "").strip()

    price_raw = offers.get("price") or offers.get("lowPrice") or 0
    high_raw = offers.get("highPrice")
    try:
        current_price = int(float(str(price_raw).replace(",", "")))
    except (TypeError, ValueError):
        current_price = 0

    old_price = None
    try:
        if high_raw:
            high_price = int(float(str(high_raw).replace(",", "")))
            if high_price > current_price > 0:
                old_price = high_price
    except (TypeError, ValueError):
        old_price = None

    availability = normalize_availability(str(offers.get("availability") or ""))
    description = strip_html(str(data.get("description") or ""))

    specs: Dict[str, str] = {}
    for prop in data.get("additionalProperty") or []:
        if isinstance(prop, dict):
            name = str(prop.get("name") or "").strip()
            value = str(prop.get("value") or "").strip()
            if name and value:
                specs[name] = value

    return {
        "title": strip_html(str(data.get("name") or "")),
        "brand": brand,
        "product_url": str(data.get("url") or offers.get("url") or fallback_url).strip(),
        "current_price": current_price,
        "old_price": old_price,
        "image_url": image_url,
        "description": description,
        "specifications": specs,
        "availability_status": availability,
        "category": str(data.get("category") or "Mobile Phones").strip(),
    }


def parse_spec_tables(soup: BeautifulSoup) -> Dict[str, str]:
    specs: Dict[str, str] = {}

    for table in soup.select("table"):
        table_text = table.get_text(" ", strip=True)
        if "Choose an option" in table_text or table_text.count("Clear") > 1:
            continue

        for row in table.select("tr"):
            cells = row.select("th, td")
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if not key or not value:
                continue
            if len(key) > 80 or len(value) > 400:
                continue
            if key.lower() in ("choose an option", "clear"):
                continue
            # Skip variant selector rows (Color | Silver | Orange | ...)
            if len(cells) > 3 and key.lower() in ("color", "storage"):
                continue
            specs[key] = value

    for dl in soup.select("dl"):
        dts = dl.select("dt")
        dds = dl.select("dd")
        for dt, dd in zip(dts, dds):
            key = dt.get_text(" ", strip=True)
            value = dd.get_text(" ", strip=True)
            if key and value:
                specs[key] = value

    return specs


def _gallery_image_url(img) -> str:
    return (
        img.get("data-large_image")
        or img.get("data-src")
        or img.get("src")
        or ""
    ).strip()


def _is_techroid_hosted_image(url: str) -> bool:
    lower = (url or "").lower()
    return "techroid.com/wp-content/uploads" in lower


def pick_product_image(soup: BeautifulSoup) -> str:
    meta = parse_meta_fallback(soup)
    if _is_valid_image_url(meta.get("image_url", "")):
        return upgrade_image_url(meta["image_url"])

    for img in soup.select(
        ".woocommerce-product-gallery img, img.wp-post-image, img[src*='wp-content/uploads']"
    ):
        url = _gallery_image_url(img)
        if _is_valid_image_url(url):
            return upgrade_image_url(url)

    for img in soup.select("img[src*='images.priceoye']"):
        url = img.get("src") or img.get("data-src") or ""
        if _is_valid_image_url(url):
            return upgrade_image_url(url)

    return ""


def pick_techroid_product_image(soup: BeautifulSoup, json_ld_url: str = "") -> str:
    """
    Techroid JSON-LD often lists stale *-front.jpg URLs (404).
    Prefer og:image and WooCommerce gallery assets on techroid.com.
    """
    meta = parse_meta_fallback(soup)
    og_image = upgrade_image_url(meta.get("image_url", ""))
    if _is_valid_image_url(og_image) and _is_techroid_hosted_image(og_image):
        return og_image

    for img in soup.select(".woocommerce-product-gallery img"):
        url = upgrade_image_url(_gallery_image_url(img))
        if _is_valid_image_url(url) and _is_techroid_hosted_image(url):
            return url

    for img in soup.select("img[src*='wp-content/uploads']"):
        url = upgrade_image_url(_gallery_image_url(img))
        if _is_valid_image_url(url) and _is_techroid_hosted_image(url):
            return url

    json_ld_url = upgrade_image_url(json_ld_url or "")
    if _is_valid_image_url(json_ld_url) and _is_techroid_hosted_image(json_ld_url):
        return json_ld_url

    return pick_product_image(soup)


def _is_valid_image_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    lower = url.lower()
    return not any(fragment in lower for fragment in INVALID_IMAGE_FRAGMENTS)


def parse_meta_fallback(soup: BeautifulSoup) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    og_title = soup.select_one('meta[property="og:title"]')
    og_image = soup.select_one('meta[property="og:image"]')
    og_desc = soup.select_one('meta[property="og:description"]')
    if og_title:
        result["title"] = og_title.get("content", "").strip()
    if og_image:
        result["image_url"] = og_image.get("content", "").strip()
    if og_desc:
        result["description"] = og_desc.get("content", "").strip()
    return result


def upgrade_image_url(url: str) -> str:
    """Prefer larger images when a thumbnail size is embedded in the URL."""
    if not url:
        return url
    return re.sub(r"-\d+x\d+\.(webp|jpg|jpeg|png)$", r".\1", url, flags=re.I)
