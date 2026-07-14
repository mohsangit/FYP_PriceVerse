from .models import Product, Store, ScrapedListing, PriceHistory


def get_site_stats():
    product_count = Product.objects.count()
    store_count = Store.objects.count()
    listing_count = ScrapedListing.objects.count()
    history_count = PriceHistory.objects.count()
    return {
        "product_count": product_count,
        "store_count": store_count,
        "listing_count": listing_count,
        "history_count": history_count,
    }
