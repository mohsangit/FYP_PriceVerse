from typing import Dict, Optional

from bs4 import BeautifulSoup
from .extractors import (
    detect_brand,
    normalize_availability,
    parse_json_ld_product,
    parse_meta_fallback,
    parse_spec_tables,
    pick_product_image,
    pick_techroid_product_image,
    product_from_json_ld,
    strip_html,
    upgrade_image_url,
)
from .parsers import (
    is_iphone_product,
    is_samsung_phone,
    normalize_title,
    parse_fallback_price_from_tables,
    parse_onsale_discount_pct,
    parse_priceoye_discontinued,
    parse_priceoye_prices,
    parse_techroid_discontinued,
    parse_woocommerce_prices,
    split_current_old_prices,
    _apply_discontinued_metadata,
)
from .validators import validate_scraped_record, _is_valid_image_url


def _calc_sale_fields(current_price: int, old_price) -> tuple[int, bool]:
    if not old_price or old_price <= current_price:
        return 0, False
    pct = round((old_price - current_price) / old_price * 100)
    return pct, pct > 0


class DetailPageParser:
    """Parse a product detail page into a normalized scrape record."""

    def parse(self, html: str, product_url: str, brand_key: str) -> Optional[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        record: Dict = {
            "product_url": product_url,
            "category": "Mobile Phones",
            "specifications": {},
        }

        ld_product = parse_json_ld_product(soup)
        if ld_product:
            record.update(product_from_json_ld(ld_product, product_url))

        meta = parse_meta_fallback(soup)
        for key, value in meta.items():
            if value and not record.get(key):
                record[key] = value

        title_el = soup.select_one("h1.product_title, h1")
        if title_el and not record.get("title"):
            record["title"] = normalize_title(title_el.get_text(" ", strip=True))

        explicit_discount_pct = 0

        if not record.get("current_price"):
            price_el = soup.select_one("p.price, .summary .price, [class*='price']")
            price_text = price_el.get_text(" ", strip=True) if price_el else soup.get_text(" ", strip=True)
            current, old = split_current_old_prices(price_text)
            record["current_price"] = current
            record["old_price"] = old

        # PriceOye-specific: discounted price, original price, and % OFF badge.
        po_current, po_old, po_pct = parse_priceoye_prices(soup)
        if po_current:
            record["current_price"] = po_current
            if po_old and po_old > po_current:
                record["old_price"] = po_old
            if po_pct:
                explicit_discount_pct = po_pct

        wc_current, wc_old = parse_woocommerce_prices(soup)
        if wc_current:
            record["current_price"] = wc_current
            if wc_old:
                record["old_price"] = wc_old

        if int(record.get("current_price") or 0) <= 0:
            fallback_current, fallback_old = parse_fallback_price_from_tables(soup)
            if fallback_current:
                record["current_price"] = fallback_current
                if fallback_old:
                    record["old_price"] = fallback_old

        html_specs = parse_spec_tables(soup)
        merged_specs = dict(record.get("specifications") or {})
        merged_specs.update(html_specs)
        record["specifications"] = merged_specs

        if "techroid.com" in (product_url or "").lower():
            record["image_url"] = pick_techroid_product_image(
                soup, str(record.get("image_url") or "")
            )
        elif not _is_valid_image_url(str(record.get("image_url") or "")):
            record["image_url"] = pick_product_image(soup)
        else:
            record["image_url"] = upgrade_image_url(str(record.get("image_url") or ""))

        if not record.get("availability_status") or record["availability_status"] == "unknown":
            stock_el = soup.select_one(".stock, .availability, [class*='stock']")
            if stock_el:
                classes = " ".join(stock_el.get("class") or [])
                record["availability_status"] = normalize_availability(
                    stock_el.get_text(" ", strip=True) + " " + classes
                )

        record["title"] = normalize_title(record.get("title") or "")
        record["brand"] = detect_brand(record["title"], record.get("brand") or "")

        if not record.get("description"):
            record["description"] = strip_html(
                f"{record.get('brand', '')} {record['title']} available in Pakistan."
            ).strip()

        if not record.get("specifications"):
            record["specifications"] = {"Model": record["title"]}

        record["short_description"] = (record.get("description") or "")[:260]

        if brand_key == "iphone" and not is_iphone_product(record["title"]):
            return None
        if brand_key == "samsung" and not is_samsung_phone(record["title"]):
            return None

        current_price = int(record.get("current_price") or 0)
        old_price = record.get("old_price")
        try:
            old_price = int(old_price) if old_price else None
        except (TypeError, ValueError):
            old_price = None

        # Discount % preference: explicit site badge -> generic onsale badge -> computed.
        sale_el = soup.select_one(".save-price, .onsale, .product-label.onsale, span.onsale")
        badge_pct = explicit_discount_pct or parse_onsale_discount_pct(
            sale_el.get_text(" ", strip=True) if sale_el else ""
        )

        computed_pct, _ = _calc_sale_fields(current_price, old_price)
        discount_pct = badge_pct or computed_pct
        is_on_sale = discount_pct > 0

        if is_on_sale and current_price and (not old_price or old_price <= current_price):
            old_price = round(current_price / (1 - discount_pct / 100))

        record["current_price"] = current_price
        record["old_price"] = old_price if is_on_sale else None
        record["discount_pct"] = discount_pct
        record["is_on_sale"] = is_on_sale

        if "priceoye.pk" in (product_url or "").lower():
            record["is_discontinued"] = parse_priceoye_discontinued(soup)
            _apply_discontinued_metadata(record, "PriceOye")
        elif "techroid.com" in (product_url or "").lower():
            record["is_discontinued"] = parse_techroid_discontinued(soup)
            _apply_discontinued_metadata(record, "Techroid")

        is_valid, _ = validate_scraped_record(record)
        return record if is_valid else None
