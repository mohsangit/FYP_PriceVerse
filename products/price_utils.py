from typing import Optional

from .models import Product, ScrapedListing


def discount_pct(current_price: int, old_price: Optional[int]) -> int:
    if not old_price or old_price <= current_price:
        return 0
    return round((old_price - current_price) / old_price * 100)


def _normalize_listing_sale(listing: Optional[ScrapedListing]) -> Optional[ScrapedListing]:
    """Align sale fields from stored original/discounted prices."""
    if not listing:
        return None
    if listing.old_price and listing.old_price > listing.current_price:
        computed = discount_pct(listing.current_price, listing.old_price)
        if computed > 0:
            listing.discount_pct = max(listing.discount_pct or 0, computed)
            listing.is_on_sale = True
    elif not listing.is_on_sale:
        listing.discount_pct = 0
        listing.old_price = None
    return listing


def _product_listings(product: Product, store_slug: str | None = None) -> list:
    """Use prefetched listings when available to avoid extra queries."""
    cache = getattr(product, "_prefetched_objects_cache", {})
    if "listings" in cache:
        listings = list(cache["listings"])
    else:
        listings = list(product.listings.select_related("store").all())
    if store_slug:
        listings = [listing for listing in listings if listing.store.slug == store_slug]
    return listings


def display_listing_for_product(
    product: Product, store_slug: str | None = None
) -> Optional[ScrapedListing]:
    """
    Pick the best listing for product cards: prefer the lowest-priced
    on-sale listing so discount badge and prices display correctly.
    When store_slug is set, only consider that retailer's listing.
    """
    listings = _product_listings(product, store_slug)
    if not listings:
        return None

    normalized = [_normalize_listing_sale(listing) for listing in listings]
    on_sale = [
        listing
        for listing in normalized
        if listing.is_on_sale and listing.discount_pct > 0 and listing.old_price
    ]
    if on_sale:
        return min(on_sale, key=lambda listing: listing.current_price)
    return min(normalized, key=lambda listing: listing.current_price)


def best_listing_for_product(product: Product) -> Optional[ScrapedListing]:
    """Lowest current price across stores."""
    listings = _product_listings(product)
    if not listings:
        return None
    return min(listings, key=lambda listing: listing.current_price)


def best_price_info(product: Product) -> Optional[dict]:
    raw = display_listing_for_product(product) or best_listing_for_product(product)
    listing = _normalize_listing_sale(raw)
    if not listing:
        return None

    best_discount = 0
    for item in product.listings.all():
        item = _normalize_listing_sale(item)
        best_discount = max(best_discount, item.discount_pct or discount_pct(item.current_price, item.old_price))

    return {
        "listing": listing,
        "best_price": listing.current_price,
        "best_discount_pct": best_discount,
        "store_name": listing.store.name,
        "old_price": listing.old_price,
    }
