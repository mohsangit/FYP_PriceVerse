import asyncio
import threading

from django.conf import settings
from django.db import close_old_connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from core.permissions import admin_required

from .scrape_progress import get_progress, is_running, mark_completed, mark_failed
from .scrapers import format_whatmobile_success_message, run_batched_whatmobile_scrape_async


def _run_whatmobile_scrape_in_background() -> None:
    close_old_connections()
    try:
        limit = int(getattr(settings, "WHATMOBILE_SCRAPE_LIMIT", 0) or 0)
        summary = asyncio.run(run_batched_whatmobile_scrape_async(limit_per_brand=limit))
        message = format_whatmobile_success_message(summary)
        mark_completed(message, summary)
    except Exception as exc:
        mark_failed(
            f"WhatMobile scraping interrupted: {exc} "
            "Click the WhatMobile Scraper button again to resume from the last saved phone."
        )
    finally:
        close_old_connections()


@admin_required
@require_POST
def whatmobile_scrape_start(request):
    if is_running():
        return JsonResponse(
            {"ok": False, "message": "WhatMobile scraping is already in progress."},
            status=409,
        )

    thread = threading.Thread(target=_run_whatmobile_scrape_in_background, daemon=True)
    thread.start()

    return JsonResponse({
        "ok": True,
        "started": True,
        "message": "WhatMobile scraping started.",
    })


@admin_required
@require_GET
def whatmobile_scrape_progress(request):
    progress = get_progress()
    return JsonResponse({"ok": True, **progress})
