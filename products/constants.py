"""Lightweight retailer metadata for UI filters (no scraper imports)."""

PRODUCT_SOURCE_FILTERS = [
    {
        "slug": "mobiletrade",
        "name": "MobileTrade",
        "website_url": "https://mobiletrade.pk",
        "logo": "img/stores/mobiletrade.svg",
    },
    {
        "slug": "priceoye",
        "name": "PriceOye",
        "website_url": "https://priceoye.pk",
        "logo": "img/stores/priceoye.svg",
    },
    {
        "slug": "techroid",
        "name": "Techroid",
        "website_url": "https://techroid.com",
        "logo": "img/stores/techroid.svg",
    },
]

PRODUCT_SOURCE_SLUGS = {item["slug"] for item in PRODUCT_SOURCE_FILTERS}
