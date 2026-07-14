import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Q

from products.models import Product, PriceHistory, ScrapedListing, Favorite, PriceAlert


class Command(BaseCommand):
    help = "Remove temporary, dummy, and placeholder product data from the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all-products",
            action="store_true",
            help="Delete all products and related listings/history.",
        )

    def _purge_legacy_product_links(self, product_ids=None):
        """Remove rows from legacy tables not managed by current models."""
        legacy_tables = [
            ("core_chatmessage", None),
            ("core_chatsession", None),
            ("products_phone", "product_id"),
        ]
        with connection.cursor() as cursor:
            for table, product_column in legacy_tables:
                try:
                    if product_ids and product_column:
                        placeholders = ",".join(["%s"] * len(product_ids))
                        cursor.execute(
                            f"DELETE FROM {table} WHERE {product_column} IN ({placeholders})",
                            product_ids,
                        )
                    else:
                        cursor.execute(f"DELETE FROM {table}")
                except Exception:
                    pass

    def handle(self, *args, **options):
        if options["all_products"]:
            self._purge_legacy_product_links()
            history_deleted, _ = PriceHistory.objects.all().delete()
            listings_deleted, _ = ScrapedListing.objects.all().delete()
            favorites_deleted, _ = Favorite.objects.all().delete()
            alerts_deleted, _ = PriceAlert.objects.all().delete()
            products_deleted, _ = Product.objects.all().delete()
            self._clean_placeholder_media()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Removed all product data: {products_deleted} products, "
                    f"{listings_deleted} listings, {history_deleted} history rows, "
                    f"{favorites_deleted} favorites, {alerts_deleted} price alerts."
                )
            )
            return

        dummy_filter = (
            Q(short_description__icontains="dummy")
            | Q(short_description__icontains="fyp")
            | Q(short_description__icontains="scraped result")
            | Q(image__icontains="placeholder")
        )
        dummy_products = Product.objects.filter(dummy_filter)
        product_ids = list(dummy_products.values_list("id", flat=True))

        if not product_ids:
            self._clean_placeholder_media()
            self.stdout.write(self.style.SUCCESS("No dummy products found in the database."))
            return

        self._purge_legacy_product_links(product_ids)
        PriceHistory.objects.filter(listing__product_id__in=product_ids).delete()
        ScrapedListing.objects.filter(product_id__in=product_ids).delete()
        Favorite.objects.filter(product_id__in=product_ids).delete()
        PriceAlert.objects.filter(product_id__in=product_ids).delete()
        deleted_count, _ = Product.objects.filter(id__in=product_ids).delete()
        self._clean_placeholder_media()

        self.stdout.write(
            self.style.SUCCESS(f"Removed {deleted_count} dummy/temporary products and related records.")
        )

    def _clean_placeholder_media(self):
        media_dir = os.path.join(settings.MEDIA_ROOT, "products")
        if not os.path.isdir(media_dir):
            return

        removed = 0
        for filename in os.listdir(media_dir):
            if "placeholder" in filename.lower():
                try:
                    os.remove(os.path.join(media_dir, filename))
                    removed += 1
                except OSError:
                    pass

        if removed:
            self.stdout.write(f"Removed {removed} placeholder media file(s).")
