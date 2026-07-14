from django.core.management.base import BaseCommand

from whatmobile.scrapers import format_whatmobile_success_message, run_batched_whatmobile_scrape


class Command(BaseCommand):
    help = "Scrape Apple and Samsung phones from WhatMobile into the comparison database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit-per-brand",
            type=int,
            default=0,
            help="Optional cap per brand (0 = no limit).",
        )

    def handle(self, *args, **options):
        limit = int(options["limit_per_brand"] or 0)
        self.stdout.write("Starting WhatMobile scrape…", ending="\n")
        self.stdout.flush()
        summary = run_batched_whatmobile_scrape(limit_per_brand=limit)
        self.stdout.write(self.style.SUCCESS(format_whatmobile_success_message(summary)))
        self.stdout.write(str(summary))
