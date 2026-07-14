from django.core.management.base import BaseCommand

from whatmobile.dedup import cleanup_duplicate_phones


class Command(BaseCommand):
    help = "Remove duplicate WhatMobile phone records from the comparison database."

    def handle(self, *args, **options):
        summary = cleanup_duplicate_phones()
        removed = summary.get("total_cleaned", 0)
        if removed:
            self.stdout.write(self.style.SUCCESS(f"Removed {removed} duplicate WhatMobile record(s)."))
        else:
            self.stdout.write(self.style.SUCCESS("No duplicate WhatMobile records found."))
