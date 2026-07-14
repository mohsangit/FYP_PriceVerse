import re

from django.core.management.base import BaseCommand

from products.models import ScrapedListing
from products.scrapers_engine.detail_parser import DetailPageParser
from products.scrapers_engine.http_client import ScrapeHttpClient
from products.utils import download_image_to_product, local_product_image_is_valid

_STALE_TECHROID_IMAGE = re.compile(
    r"-(?:front|back)\.(?:jpe?g|png|webp|avif)$|samsung\.com/",
    re.I,
)


class Command(BaseCommand):
    help = "Re-download product images for retailer listings with missing or corrupt files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--store",
            default="techroid",
            help="Store slug to repair (default: techroid).",
        )

    def handle(self, *args, **options):
        store_slug = options["store"]
        repaired = 0
        skipped = 0
        failed = 0

        parser = DetailPageParser()
        client = ScrapeHttpClient()

        listings = (
            ScrapedListing.objects.filter(store__slug=store_slug)
            .select_related("product")
            .order_by("product_id")
        )

        for listing in listings:
            product = listing.product
            if local_product_image_is_valid(product):
                skipped += 1
                continue

            image_url = (listing.image_url or product.image_url or "").strip()
            if _STALE_TECHROID_IMAGE.search(image_url) or (
                store_slug == "techroid" and "techroid.com/wp-content" not in image_url.lower()
            ):
                refreshed = self._refresh_image_url(client, parser, listing)
                if refreshed:
                    image_url = refreshed
                    listing.image_url = image_url
                    listing.save(update_fields=["image_url"])
                    product.image_url = image_url
                    product.save(update_fields=["image_url"])

            if not image_url:
                failed += 1
                self.stdout.write(self.style.WARNING(f"FAIL {product.slug} (no image URL)"))
                continue

            if download_image_to_product(product, image_url, force=True):
                repaired += 1
                self.stdout.write(f"OK  {product.slug}")
            else:
                failed += 1
                self.stdout.write(self.style.WARNING(f"FAIL {product.slug} -> {image_url[:80]}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. repaired={repaired} skipped={skipped} failed={failed}"
            )
        )

    def _refresh_image_url(self, client, parser, listing) -> str:
        product_url = (listing.product_url or "").strip()
        if not product_url:
            return ""

        brand = "iphone" if "iphone" in product_url.lower() else "samsung"
        try:
            response = client.get(product_url)
            html = response.text
            if not html:
                return ""
            record = parser.parse(html, product_url, brand)
            return (record or {}).get("image_url") or ""
        except Exception:
            return ""
