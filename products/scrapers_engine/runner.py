from typing import Dict, List

from django.utils.text import slugify

from products.insights import compute_insight_tag, compute_trend_days, compute_trend_text
from products.models import Store, Product, ScrapedListing, PriceHistory
from products.availability import apply_discontinued_from_record
from products.notifications import check_price_alerts_for_products
from products.price_utils import discount_pct
from products.scrapers_engine.validators import validate_scraped_record
from products.utils import download_image_to_product, local_product_image_needs_download


def _merge_specifications(existing: dict, incoming: dict) -> dict:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if key and value and key not in merged:
            merged[key] = value
    return merged


def _update_product_from_record(product: Product, record: Dict) -> None:
    title = (record.get("title") or "").strip()
    brand = (record.get("brand") or "").strip()
    description = (record.get("description") or "").strip()
    category = (record.get("category") or "Mobile Phones").strip()
    image_url = (record.get("image_url") or "").strip()
    specifications = record.get("specifications") or {}
    short_description = (record.get("short_description") or description[:260]).strip()

    changed = []

    if title and product.title != title:
        product.title = title
        changed.append("title")
    if brand and product.brand != brand:
        product.brand = brand
        changed.append("brand")
    if category and product.category != category:
        product.category = category
        changed.append("category")
    if short_description and product.short_description != short_description:
        product.short_description = short_description
        changed.append("short_description")
    if description and len(description) > len(product.description or ""):
        product.description = description
        changed.append("description")
    if image_url:
        product.image_url = image_url
        changed.append("image_url")

    merged_specs = _merge_specifications(product.specifications, specifications)
    if merged_specs != product.specifications:
        product.specifications = merged_specs
        changed.append("specifications")

    if changed:
        product.save(update_fields=changed)


def upsert_results(store_slug: str, store_name: str, store_url: str, results: List[Dict]) -> Dict:
    store, _ = Store.objects.get_or_create(
        slug=store_slug,
        defaults={"name": store_name, "website_url": store_url},
    )

    listings = []
    skipped = 0
    added = 0
    updated = 0
    affected_product_ids = set()

    for record in results:
        is_valid, _ = validate_scraped_record(record)
        if not is_valid:
            skipped += 1
            continue

        title = (record.get("title") or "").strip()
        product_slug = slugify(title)
        if not product_slug:
            skipped += 1
            continue

        product, product_created = Product.objects.get_or_create(
            slug=product_slug,
            defaults={
                "title": title,
                "brand": record.get("brand") or "",
                "category": record.get("category") or "Mobile Phones",
                "short_description": (record.get("short_description") or "")[:260],
                "description": record.get("description") or "",
                "specifications": record.get("specifications") or {},
                "image_url": record.get("image_url") or "",
            },
        )

        _update_product_from_record(product, record)

        current_price = int(record.get("current_price") or 0)
        old_price = record.get("old_price")
        try:
            old_price = int(old_price) if old_price else None
        except (TypeError, ValueError):
            old_price = None

        sale_discount = int(record.get("discount_pct") or 0)
        on_sale = bool(record.get("is_on_sale"))

        if old_price and old_price > current_price:
            on_sale = True
            # Prefer the discount % scraped from the site badge; fall back to computed.
            sale_discount = sale_discount or discount_pct(current_price, old_price)
        elif on_sale and sale_discount > 0 and current_price and not old_price:
            old_price = round(current_price / (1 - sale_discount / 100))
        elif sale_discount > 0 and current_price and not old_price:
            on_sale = True
            old_price = round(current_price / (1 - sale_discount / 100))
        else:
            on_sale = False
            sale_discount = 0
            old_price = None

        listing, listing_created = ScrapedListing.objects.update_or_create(
            product=product,
            store=store,
            defaults={
                "product_url": record.get("product_url") or "",
                "image_url": record.get("image_url") or "",
                "availability_status": record.get("availability_status") or "unknown",
                "specifications": record.get("specifications") or {},
                "current_price": current_price,
                "old_price": old_price if on_sale else None,
                "discount_pct": sale_discount,
                "is_on_sale": on_sale,
                "source_website": record.get("source_store") or store_name,
                "currency": "PKR",
            },
        )

        PriceHistory.objects.create(listing=listing, price=listing.current_price)

        product.insight_tag = compute_insight_tag(current_price, old_price)
        product.trend_text = compute_trend_text(current_price, old_price)
        product.trend_days = compute_trend_days(listing)
        product.save(update_fields=["insight_tag", "trend_text", "trend_days"])

        image_url = (record.get("image_url") or "").strip()
        if image_url and local_product_image_needs_download(product):
            download_image_to_product(product, image_url, force=bool(product.image))

        apply_discontinued_from_record(product, record)

        listings.append(listing)
        affected_product_ids.add(product.id)

        if product_created or listing_created:
            added += 1
        else:
            updated += 1

    check_price_alerts_for_products(affected_product_ids)
    return {
        "listings": listings,
        "added": added,
        "updated": updated,
        "skipped": skipped,
    }
