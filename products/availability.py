"""Product availability helpers — discontinued detection and listing sort."""

from __future__ import annotations

from django.db.models import QuerySet

from whatmobile.discontinued import is_product_discontinued


def apply_discontinued_from_record(product, record: dict) -> bool:
    """Apply scraped discontinued flag when provided by a retailer scraper."""
    source = record.get("source_store") or ""
    if source in {"PriceOye", "Techroid"} and "is_discontinued" in record:
        flag = bool(record.get("is_discontinued"))
        if product.is_discontinued != flag:
            type(product).objects.filter(pk=product.pk).update(is_discontinued=flag)
            product.is_discontinued = flag
        return flag
    return refresh_product_discontinued(product)


def refresh_product_discontinued(product) -> bool:
    """Update cached discontinued flag on a product from live DB checks."""
    flag = is_product_discontinued(product)
    if getattr(product, "is_discontinued", False) != flag:
        type(product).objects.filter(pk=product.pk).update(is_discontinued=flag)
        product.is_discontinued = flag
    return flag


def sync_discontinued_flags(product_ids: set[int] | None = None) -> int:
    """Refresh discontinued flags for all or selected products."""
    from products.models import Product

    qs = Product.objects.prefetch_related("listings")
    if product_ids:
        qs = qs.filter(pk__in=product_ids)

    updated = 0
    for product in qs.iterator(chunk_size=100):
        before = product.is_discontinued
        refresh_product_discontinued(product)
        if before != product.is_discontinued:
            updated += 1
    return updated


def available_first(queryset: QuerySet) -> QuerySet:
    """Available products first; discontinued products last."""
    return queryset.order_by("is_discontinued", "-created_at")
