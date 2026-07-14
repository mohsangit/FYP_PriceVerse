from django.core.management.base import BaseCommand

from products.models import Product
from products.notifications import check_price_alerts_for_products


class Command(BaseCommand):
    help = "Check subscribed products and send price-drop emails when prices improve."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Check every product that has active price alerts.",
        )

    def handle(self, *args, **options):
        if options["all"]:
            product_ids = Product.objects.filter(price_alerts__isnull=False).values_list("id", flat=True).distinct()
        else:
            product_ids = Product.objects.values_list("id", flat=True)

        sent = check_price_alerts_for_products(product_ids)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} price alert email(s)."))
