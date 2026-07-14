import asyncio
from typing import Dict, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings

from products.scrapers_engine.async_http_client import AsyncScrapeHttpClient

from .dedup import cleanup_duplicate_phones
from .phone_filters import cleanup_non_phones
from .runner import clear_all_phones, upsert_phone
from .scrape_progress import (
    mark_brand_completed,
    mark_discovering,
    mark_discovering_page,
    mark_scraping_phone,
    mark_started,
    mark_store_completed,
    update_counts,
    update_progress_pct,
)
from .scrape_state import (
    BRAND_ORDER,
    begin_run,
    get_brand_resume_index,
    get_brand_targets,
    get_resume_brand,
    is_brand_complete,
    is_resumable,
    load_state,
    mark_brand_complete,
    mark_brand_phone_complete,
    mark_completed_state,
    mark_failed_state,
    set_brand_targets,
    total_discovered,
    total_processed,
    total_targets,
)
from .scrapers_engine.async_whatmobile import AsyncWhatMobileScraper
from .scrapers_engine.whatmobile_parser import WHATMOBILE_BASE_URL

STORE_NAME = "WhatMobile"
BRAND_LABELS = {"samsung": "Samsung", "apple": "Apple"}
WHATMOBILE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.whatmobile.com.pk/",
    "Cache-Control": "no-cache",
}


def _whatmobile_client_settings() -> Tuple[int, float, float, int, float]:
    max_concurrent = int(getattr(settings, "WHATMOBILE_MAX_CONCURRENT", 1) or 1)
    min_delay = float(getattr(settings, "WHATMOBILE_MIN_DELAY", 1.0) or 1.0)
    max_delay = float(getattr(settings, "WHATMOBILE_MAX_DELAY", 3.0) or 3.0)
    max_retries = int(getattr(settings, "WHATMOBILE_MAX_RETRIES", 6) or 6)
    rate_limit_base = float(getattr(settings, "WHATMOBILE_RATE_LIMIT_BACKOFF", 5.0) or 5.0)
    return max_concurrent, min_delay, max_delay, max_retries, rate_limit_base


def _brand_progress_label(brand: str) -> str:
    return f"{STORE_NAME} ({BRAND_LABELS.get(brand, brand.title())})"


async def _discover_brand(
    scraper: AsyncWhatMobileScraper,
    brand: str,
    limit_per_brand: int,
) -> list:
    label = _brand_progress_label(brand)

    def _on_page(page: int, max_pages: int) -> None:
        mark_discovering_page(label, page, max_pages)

    mark_discovering(label)
    targets = await scraper.discover_targets(brand, limit_per_brand, on_page=_on_page)
    if not targets and brand == "apple":
        raise RuntimeError(
            "No Apple phones discovered from WhatMobile. The site may be temporarily "
            "unavailable. Wait a few minutes and click the button again to resume."
        )
    return targets


async def _scrape_brand_targets(
    scraper: AsyncWhatMobileScraper,
    brand: str,
    targets: list,
    start_index: int,
    upsert_one_async,
    summary: Dict,
) -> None:
    label = _brand_progress_label(brand)
    brand_total = len(targets)

    for index in range(start_index, brand_total):
        item = targets[index]
        model_name = item.get("model_name") or item.get("url") or "phone"

        mark_scraping_phone(label, index + 1, brand_total, model_name)

        record = await scraper.fetch_record(item["url"], item["brand"])
        batch_added = batch_updated = 0

        if record:
            result = await upsert_one_async(record)
            batch_added = result.get("added", 0)
            batch_updated = result.get("updated", 0)

        state = mark_brand_phone_complete(
            brand,
            index + 1,
            added=batch_added,
            updated=batch_updated,
            scraped=1 if record else 0,
        )
        summary["added"] = int(state.get("records_added") or 0)
        summary["updated"] = int(state.get("records_updated") or 0)
        summary["scraped"] = int(state.get("records_scraped") or 0)
        summary["saved"] = summary["added"] + summary["updated"]

        processed = total_processed()
        update_counts(processed, summary["added"], summary["updated"])
        update_progress_pct(processed, max(total_targets(), 1))


def _prepare_scrape_run(limit_per_brand: int) -> Dict:
    """Resolve resume state using the database — must run in a sync thread."""
    from .models import WhatMobilePhone

    resumed = is_resumable(limit_per_brand)
    if resumed:
        saved_state = load_state()
        saved_count = int(saved_state.get("records_added") or 0) + int(
            saved_state.get("records_updated") or 0
        )
        db_count = WhatMobilePhone.objects.using("whatmobile").count()
        if saved_count > 0 and db_count == 0:
            resumed = False

    resume_brand = get_resume_brand() if resumed else None
    resume_index = get_brand_resume_index(resume_brand) if resume_brand else 0
    saved_state = load_state() if resumed else {}

    return {
        "resumed": resumed,
        "resume_brand": resume_brand,
        "resume_index": resume_index,
        "prior_added": int(saved_state.get("records_added") or 0),
        "prior_updated": int(saved_state.get("records_updated") or 0),
        "prior_scraped": int(saved_state.get("records_scraped") or 0),
    }


async def run_batched_whatmobile_scrape_async(limit_per_brand: int = 0) -> Dict:
    prep = await sync_to_async(_prepare_scrape_run, thread_sensitive=True)(limit_per_brand)
    resumed = prep["resumed"]
    resume_brand = prep["resume_brand"]
    resume_index = prep["resume_index"]
    prior_added = prep["prior_added"]
    prior_updated = prep["prior_updated"]
    prior_scraped = prep["prior_scraped"]

    mark_started(
        batch_size=1,
        resumed=resumed,
        resume_index=total_processed() if resumed else 0,
        records_added=prior_added,
        records_updated=prior_updated,
        resume_brand=resume_brand,
    )

    dedup_async = sync_to_async(cleanup_duplicate_phones, thread_sensitive=True)
    cleanup_async = sync_to_async(cleanup_non_phones, thread_sensitive=True)
    clear_async = sync_to_async(clear_all_phones, thread_sensitive=True)
    upsert_one_async = sync_to_async(upsert_phone, thread_sensitive=True)

    if not resumed:
        await clear_async()

    dedup_summary = await dedup_async()
    non_phone_summary = await cleanup_async()

    summary = {
        "store": STORE_NAME,
        "discovered": 0,
        "scraped": prior_scraped,
        "added": prior_added,
        "updated": prior_updated,
        "saved": prior_added + prior_updated,
        "resumed": resumed,
        "resume_brand": resume_brand,
        "resume_index": resume_index,
        "duplicates_cleaned": dedup_summary,
        "non_phones_removed": non_phone_summary,
        "samsung_scraped": 0,
        "apple_scraped": 0,
        "cleared_existing": not resumed,
    }

    max_concurrent, min_delay, max_delay, max_retries, rate_limit_base = _whatmobile_client_settings()

    try:
        if not resumed:
            begin_run(limit_per_brand, fresh=True)
        else:
            begin_run(limit_per_brand, fresh=False)

        async with AsyncScrapeHttpClient(
            extra_headers=WHATMOBILE_HEADERS,
            max_concurrent=max_concurrent,
            min_delay=min_delay,
            max_delay=max_delay,
            max_retries=max_retries,
            rate_limit_backoff_base=rate_limit_base,
        ) as client:
            await client.fetch_text(f"{WHATMOBILE_BASE_URL}", polite=False)
            scraper = AsyncWhatMobileScraper(client)

            for brand in BRAND_ORDER:
                if brand == "samsung" and not is_brand_complete("apple"):
                    continue

                if is_brand_complete(brand):
                    continue

                targets = get_brand_targets(brand)
                if not targets:
                    targets = await _discover_brand(scraper, brand, limit_per_brand)
                    set_brand_targets(brand, targets)

                if not targets:
                    mark_brand_complete(brand)
                    continue

                start_index = get_brand_resume_index(brand)

                await _scrape_brand_targets(
                    scraper,
                    brand,
                    targets,
                    start_index,
                    upsert_one_async,
                    summary,
                )
                mark_brand_complete(brand)
                mark_brand_completed(_brand_progress_label(brand))

        summary["discovered"] = total_discovered()
        summary["samsung_scraped"] = len(get_brand_targets("samsung"))
        summary["apple_scraped"] = len(get_brand_targets("apple"))

        mark_store_completed(STORE_NAME)
        post_dedup = await dedup_async()
        summary["post_duplicates_cleaned"] = post_dedup
        await cleanup_async()

        from products.availability import sync_discontinued_flags

        await sync_to_async(sync_discontinued_flags, thread_sensitive=True)()

        mark_completed_state()
        return summary

    except Exception:
        mark_failed_state()
        raise


def run_batched_whatmobile_scrape(limit_per_brand: int = 0) -> Dict:
    return asyncio.run(run_batched_whatmobile_scrape_async(limit_per_brand=limit_per_brand))


def format_whatmobile_success_message(summary: Dict) -> str:
    cleaned = summary.get("duplicates_cleaned", {})
    cleanup_note = ""
    if cleaned.get("total_cleaned"):
        cleanup_note = f" Cleaned {cleaned['total_cleaned']} duplicate(s) before scraping."
    resume_note = ""
    if summary.get("resumed"):
        brand = summary.get("resume_brand") or "apple"
        resume_note = (
            f" Resumed {BRAND_LABELS.get(brand, brand.title())} "
            f"from phone {int(summary.get('resume_index', 0)) + 1}."
        )
    cleared_note = ""
    if summary.get("cleared_existing"):
        cleared_note = " Cleared previous comparison data before scraping."
    return (
        f"WhatMobile scraping completed successfully."
        f"{resume_note}{cleared_note} "
        f"{summary.get('added', 0)} added, {summary.get('updated', 0)} updated. "
        f"Discovered {summary.get('discovered', 0)} phones "
        f"({summary.get('apple_scraped', 0)} Apple, {summary.get('samsung_scraped', 0)} Samsung), "
        f"scraped {summary.get('scraped', 0)}."
        f"{cleanup_note}"
    )
