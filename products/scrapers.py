import asyncio
from typing import Callable, Dict, List, Tuple

from asgiref.sync import sync_to_async
from django.conf import settings

from .scrape_progress import (
    async_countdown_wait,
    mark_batch,
    mark_cleaning_duplicates,
    mark_discovering,
    mark_discovering_page,
    mark_duplicates_cleaned,
    mark_moving_to_next_store,
    mark_started,
    mark_store_completed,
    mark_waiting,
    update_batch_progress,
    update_counts,
    update_progress_pct,
)
from .scrapers_engine.async_http_client import AsyncScrapeHttpClient
from .scrapers_engine.async_mobiletrade import AsyncMobileTradeScraper
from .scrapers_engine.async_priceoye import AsyncPriceOyeScraper
from .scrapers_engine.async_techroid import AsyncTechroidScraper
from .scrapers_engine.dedup import cleanup_duplicate_records
from .scrapers_engine.runner import upsert_results

# Order matters: MobileTrade, PriceOye, then Techroid.
SCRAPER_CONFIG: List[Tuple[str, Dict]] = [
    (
        "mobiletrade",
        {
            "name": "MobileTrade",
            "url": "https://mobiletrade.pk",
            "scraper_cls": AsyncMobileTradeScraper,
        },
    ),
    (
        "priceoye",
        {
            "name": "PriceOye",
            "url": "https://priceoye.pk",
            "scraper_cls": AsyncPriceOyeScraper,
        },
    ),
    (
        "techroid",
        {
            "name": "Techroid",
            "url": "https://techroid.com",
            "scraper_cls": AsyncTechroidScraper,
        },
    ),
]

SCRAPER_LOOKUP = {slug: config for slug, config in SCRAPER_CONFIG}
BRANDS = ("iphone", "samsung")


def _batch_settings() -> Tuple[int, int]:
    batch_size = int(getattr(settings, "SCRAPE_BATCH_SIZE", 25) or 25)
    delay_seconds = int(getattr(settings, "SCRAPE_BATCH_DELAY_SECONDS", 5) or 5)
    return batch_size, delay_seconds


def _chunk(items: List, size: int) -> List[List]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _discover_store_targets(
    scraper,
    store_name: str,
    limit_per_brand: int,
) -> List[Dict]:
    def _on_page(page: int, max_pages: int) -> None:
        mark_discovering_page(store_name, page, max_pages)

    mark_discovering(store_name)
    return await scraper.discover_all_targets(BRANDS, limit_per_brand, on_page=_on_page)


async def run_batched_phone_scrape_async(limit_per_brand: int = 0) -> Dict:
    """
    MobileTrade first, then PriceOye, then Techroid.
    All store targets are discovered upfront (fast, parallel) so there is no
    delay between websites. Batch waits (5s) apply only between batches
    within the same website.
    """
    batch_size, delay_seconds = _batch_settings()
    mark_started(batch_size)

    mark_cleaning_duplicates()
    dedup_async = sync_to_async(cleanup_duplicate_records, thread_sensitive=True)
    dedup_summary = await dedup_async()
    mark_duplicates_cleaned(
        dedup_summary.get("merged_products", 0),
        dedup_summary.get("removed_listings", 0),
    )

    summary = {
        "stores": {},
        "total_scraped": 0,
        "total_added": 0,
        "total_updated": 0,
        "total_saved": 0,
        "duplicates_cleaned": dedup_summary,
        "batch_size": batch_size,
        "batch_delay_seconds": delay_seconds,
    }
    processed_total = 0
    added_total = 0
    updated_total = 0

    upsert_async = sync_to_async(upsert_results, thread_sensitive=True)

    async with AsyncScrapeHttpClient() as client:
        store_plans: List[Dict] = []
        for store_slug, config in SCRAPER_CONFIG:
            scraper = config["scraper_cls"](client)
            targets = await _discover_store_targets(scraper, config["name"], limit_per_brand)
            store_plans.append({
                "slug": store_slug,
                "config": config,
                "scraper": scraper,
                "targets": targets,
            })

        grand_total_targets = sum(len(plan["targets"]) for plan in store_plans)
        update_progress_pct(processed_total, grand_total_targets)

        for plan_index, plan in enumerate(store_plans):
            store_slug = plan["slug"]
            config = plan["config"]
            scraper = plan["scraper"]
            targets = plan["targets"]
            store_name = config["name"]

            store_summary = {
                "discovered": len(targets),
                "scraped": 0,
                "added": 0,
                "updated": 0,
                "saved": 0,
                "batches": 0,
            }

            batches = _chunk(targets, batch_size)
            store_summary["batches"] = len(batches)

            for index, batch in enumerate(batches, start=1):
                mark_batch(store_name, index, len(batches), len(targets))
                update_batch_progress(0, len(batch))

                def _on_item(done: int, total: int) -> None:
                    update_batch_progress(done, total)
                    update_counts(processed_total + done, added_total, updated_total)
                    update_progress_pct(processed_total + done, grand_total_targets)

                records = await scraper.fetch_batch(batch, on_item_complete=_on_item)
                result = await upsert_async(
                    store_slug=store_slug,
                    store_name=store_name,
                    store_url=config["url"],
                    results=records,
                )

                batch_added = result.get("added", 0)
                batch_updated = result.get("updated", 0)

                processed_total += len(batch)
                added_total += batch_added
                updated_total += batch_updated
                store_summary["scraped"] += len(records)
                store_summary["added"] += batch_added
                store_summary["updated"] += batch_updated
                store_summary["saved"] += batch_added + batch_updated
                update_counts(processed_total, added_total, updated_total)
                update_progress_pct(processed_total, grand_total_targets)
                update_batch_progress(len(batch), len(batch))

                if index < len(batches):
                    mark_waiting(store_name, index, len(batches), delay_seconds)

                    def _tick(remaining: int) -> None:
                        mark_waiting(store_name, index, len(batches), remaining)

                    await async_countdown_wait(delay_seconds, on_tick=_tick)

            mark_store_completed(store_name)
            summary["stores"][store_slug] = store_summary
            summary["total_scraped"] += store_summary["scraped"]
            summary["total_added"] += store_summary["added"]
            summary["total_updated"] += store_summary["updated"]
            summary["total_saved"] += store_summary["saved"]

            next_plan = store_plans[plan_index + 1] if plan_index + 1 < len(store_plans) else None
            if next_plan:
                mark_moving_to_next_store(store_name, next_plan["config"]["name"])

    mark_cleaning_duplicates()
    post_dedup = await dedup_async()
    summary["post_duplicates_cleaned"] = post_dedup

    from products.availability import sync_discontinued_flags

    await sync_to_async(sync_discontinued_flags, thread_sensitive=True)()

    return summary


def run_batched_phone_scrape(limit_per_brand: int = 0) -> Dict:
    return asyncio.run(run_batched_phone_scrape_async(limit_per_brand=limit_per_brand))


def format_scrape_success_message(summary: Dict) -> str:
    parts = []
    for store_slug, store_data in summary.get("stores", {}).items():
        name = SCRAPER_LOOKUP.get(store_slug, {}).get("name", store_slug.title())
        parts.append(
            f"{name}: {store_data.get('added', 0)} added, {store_data.get('updated', 0)} updated"
        )
    detail = " | ".join(parts)
    cleaned = summary.get("duplicates_cleaned", {})
    cleanup_note = ""
    if cleaned.get("total_cleaned"):
        cleanup_note = f" Cleaned {cleaned['total_cleaned']} duplicate(s) before scraping."
    return (
        f"Scraping completed successfully. "
        f"{summary.get('total_added', 0)} added, {summary.get('total_updated', 0)} updated."
        f"{cleanup_note} {detail}"
    )
