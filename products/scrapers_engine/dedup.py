"""
Remove or merge duplicate product and listing records before scraping.
"""

import re
from collections import defaultdict
from typing import Dict

from django.db import transaction
from django.db.models import Count

from products.models import Favorite, PriceAlert, Product, ScrapedListing


def _title_key(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").lower().strip())


def _pick_canonical_product(products: list[Product]) -> Product:
    return max(
        products,
        key=lambda p: (
            p.listings.count(),
            len(p.description or ""),
            len(p.specifications or {}),
            -p.id,
        ),
    )


def _merge_product_into(canonical: Product, duplicate: Product) -> None:
    if canonical.id == duplicate.id:
        return

    for listing in list(duplicate.listings.all()):
        conflict = ScrapedListing.objects.filter(product=canonical, store=listing.store).first()
        if conflict:
            if listing.last_scraped_at > conflict.last_scraped_at:
                conflict.delete()
                listing.product = canonical
                listing.save(update_fields=["product"])
            else:
                listing.delete()
        else:
            listing.product = canonical
            listing.save(update_fields=["product"])

    for favorite in list(duplicate.favorited_by.all()):
        if Favorite.objects.filter(user=favorite.user, product=canonical).exists():
            favorite.delete()
        else:
            favorite.product = canonical
            favorite.save(update_fields=["product"])

    for alert in list(duplicate.price_alerts.all()):
        if PriceAlert.objects.filter(user=alert.user, product=canonical).exists():
            alert.delete()
        else:
            alert.product = canonical
            alert.save(update_fields=["product"])

    if not canonical.brand and duplicate.brand:
        canonical.brand = duplicate.brand
    if not canonical.image_url and duplicate.image_url:
        canonical.image_url = duplicate.image_url
    if len(duplicate.description or "") > len(canonical.description or ""):
        canonical.description = duplicate.description
    if duplicate.specifications:
        merged = dict(canonical.specifications or {})
        for key, value in duplicate.specifications.items():
            if key and value and key not in merged:
                merged[key] = value
        canonical.specifications = merged
    canonical.save()

    duplicate.delete()


def _merge_duplicate_products() -> int:
    grouped: dict[str, list[Product]] = defaultdict(list)
    for product in Product.objects.all().iterator():
        key = _title_key(product.title)
        if key:
            grouped[key].append(product)

    merged = 0
    for products in grouped.values():
        if len(products) < 2:
            continue
        canonical = _pick_canonical_product(products)
        for duplicate in products:
            if duplicate.id != canonical.id:
                _merge_product_into(canonical, duplicate)
                merged += 1
    return merged


def _merge_duplicate_listings() -> int:
    duplicate_groups = (
        ScrapedListing.objects.exclude(product_url="")
        .values("store_id", "product_url")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )

    removed = 0
    for group in duplicate_groups:
        listings = list(
            ScrapedListing.objects.filter(
                store_id=group["store_id"],
                product_url=group["product_url"],
            ).select_related("product", "store")
        )
        listings.sort(key=lambda item: item.last_scraped_at, reverse=True)
        for listing in listings[1:]:
            listing.delete()
            removed += 1
    return removed


@transaction.atomic
def cleanup_duplicate_records() -> Dict[str, int]:
    """
    Check the database for duplicate products/listings, merge or remove them,
    and return counts of merged/removed records.
    """
    merged_products = _merge_duplicate_products()
    removed_listings = _merge_duplicate_listings()
    return {
        "merged_products": merged_products,
        "removed_listings": removed_listings,
        "total_cleaned": merged_products + removed_listings,
    }
