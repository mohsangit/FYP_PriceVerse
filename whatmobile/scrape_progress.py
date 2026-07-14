import asyncio
import threading
import time
from typing import Any, Callable, Dict, Optional

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "running": False,
    "status": "idle",
    "message": "Ready to scrape WhatMobile.",
    "current_store": "WhatMobile",
    "current_batch": 0,
    "total_batches": 0,
    "batch_size": 25,
    "batch_processed": 0,
    "batch_total": 0,
    "records_processed": 0,
    "records_added": 0,
    "records_updated": 0,
    "records_saved": 0,
    "total_targets": 0,
    "progress_pct": 0,
    "waiting_seconds": 0,
    "summary": None,
}


def get_progress() -> Dict[str, Any]:
    with _lock:
        return dict(_state)


def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def is_running() -> bool:
    with _lock:
        return bool(_state.get("running"))


def mark_started(
    batch_size: int,
    *,
    resumed: bool = False,
    resume_index: int = 0,
    records_added: int = 0,
    records_updated: int = 0,
    resume_brand: Optional[str] = None,
) -> None:
    message = "WhatMobile scraping started — Apple first, then Samsung."
    if resumed:
        brand_label = (resume_brand or "apple").title()
        if resume_brand == "apple":
            brand_label = "Apple"
        elif resume_brand == "samsung":
            brand_label = "Samsung"
        message = f"Resuming {brand_label} scrape from phone {resume_index + 1}..."
    _set(
        running=True,
        status="running",
        message=message,
        current_store="WhatMobile",
        current_batch=resume_index,
        total_batches=0,
        batch_processed=resume_index,
        batch_total=0,
        records_processed=resume_index,
        records_added=records_added,
        records_updated=records_updated,
        records_saved=records_added + records_updated,
        total_targets=0,
        progress_pct=0,
        waiting_seconds=0,
        batch_size=batch_size,
        summary=None,
        resumed=resumed,
    )


def mark_scraping_phone(
    store_name: str,
    phone_index: int,
    total_targets: int,
    model_name: str,
) -> None:
    pct = min(100, round((phone_index / total_targets) * 100)) if total_targets > 0 else 0
    _set(
        status="running",
        current_store=store_name,
        current_batch=phone_index,
        total_batches=total_targets,
        batch_processed=phone_index,
        batch_total=total_targets,
        total_targets=total_targets,
        progress_pct=pct,
        waiting_seconds=0,
        message=f"Scraping {store_name}: {model_name} ({phone_index} of {total_targets})",
    )


def mark_discovering(store_name: str) -> None:
    _set(
        status="discovering",
        current_store=store_name,
        message=f"Discovering {store_name} phone listings...",
    )


def mark_discovering_page(store_name: str, page: int, max_pages: int) -> None:
    _set(
        status="discovering",
        current_store=store_name,
        message=f"Discovering listings on {store_name} (page {page} of up to {max_pages})...",
    )


def mark_store_completed(store_name: str) -> None:
    _set(
        status="running",
        current_store=store_name,
        message=f"{store_name} scraping completed successfully (Apple and Samsung).",
    )


def mark_brand_completed(store_name: str) -> None:
    _set(
        status="running",
        current_store=store_name,
        message=f"{store_name} brand completed. Continuing with next brand...",
    )


def mark_batch(store_name: str, batch_num: int, total_batches: int, total_targets: int) -> None:
    _set(
        current_store=store_name,
        current_batch=batch_num,
        total_batches=total_batches,
        total_targets=total_targets,
        status="running",
        waiting_seconds=0,
        message=(
            f"Scraping batch {batch_num} of {total_batches} on {store_name} "
            f"({total_targets} phones total)..."
        ),
    )


def mark_waiting(store_name: str, batch_num: int, total_batches: int, seconds: int) -> None:
    label = f"{seconds} second{'s' if seconds != 1 else ''}"
    if seconds >= 60:
        minutes = seconds // 60
        label = f"{minutes} minute{'s' if minutes != 1 else ''}"
    _set(
        status="waiting",
        current_store=store_name,
        current_batch=batch_num,
        total_batches=total_batches,
        waiting_seconds=seconds,
        message=(
            f"Batch {batch_num} of {total_batches} on {store_name} complete. "
            f"Waiting {label} before next batch..."
        ),
    )


def update_counts(processed: int, added: int, updated: int) -> None:
    _set(
        records_processed=processed,
        records_added=added,
        records_updated=updated,
        records_saved=added + updated,
    )


def update_progress_pct(processed: int, total: int) -> None:
    pct = min(100, round((processed / total) * 100)) if total > 0 else 0
    _set(progress_pct=pct)


def update_batch_progress(batch_processed: int, batch_total: int) -> None:
    _set(batch_processed=batch_processed, batch_total=batch_total)


async def async_countdown_wait(seconds: int, on_tick: Optional[Callable[[int], None]] = None) -> None:
    remaining = seconds
    while remaining > 0:
        if on_tick:
            on_tick(remaining)
        sleep_for = min(1, remaining)
        await asyncio.sleep(sleep_for)
        remaining -= sleep_for


def mark_completed(message: str, summary: Dict) -> None:
    _set(
        running=False,
        status="completed",
        message=message,
        progress_pct=100,
        waiting_seconds=0,
        summary=summary,
    )


def mark_failed(message: str) -> None:
    _set(running=False, status="failed", message=message, waiting_seconds=0, resumed=False)


def countdown_wait(seconds: int, on_tick: Optional[Callable[[int], None]] = None) -> None:
    remaining = seconds
    while remaining > 0:
        if on_tick:
            on_tick(remaining)
        sleep_for = min(1, remaining)
        time.sleep(sleep_for)
        remaining -= sleep_for
