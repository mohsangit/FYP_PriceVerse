import asyncio
import threading
import time
from typing import Any, Callable, Dict, Optional

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "running": False,
    "status": "idle",
    "message": "Ready to scrape.",
    "current_store": "",
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


def reset_progress() -> None:
    with _lock:
        _state.update({
            "running": False,
            "status": "idle",
            "message": "Ready to scrape.",
            "current_store": "",
            "current_batch": 0,
            "total_batches": 0,
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
        })


def is_running() -> bool:
    with _lock:
        return bool(_state.get("running"))


def mark_started(batch_size: int) -> None:
    _set(
        running=True,
        status="running",
        message="Scraping started.",
        current_store="",
        current_batch=0,
        total_batches=0,
        batch_processed=0,
        batch_total=0,
        records_processed=0,
        records_added=0,
        records_updated=0,
        records_saved=0,
        total_targets=0,
        progress_pct=0,
        waiting_seconds=0,
        batch_size=batch_size,
        summary=None,
    )


def mark_cleaning_duplicates() -> None:
    _set(status="running", message="Checking database for duplicate records...")


def mark_duplicates_cleaned(merged: int, removed: int) -> None:
    total = merged + removed
    if total:
        message = f"Duplicate cleanup complete. Merged {merged} products, removed {removed} duplicate listings."
    else:
        message = "No duplicate records found. Discovering products..."
    _set(message=message)


def _wait_label(seconds: int) -> str:
    if seconds >= 60:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{seconds} second{'s' if seconds != 1 else ''}"


def mark_discovering(store_name: str) -> None:
    _set(
        status="discovering",
        current_store=store_name,
        current_batch=0,
        total_batches=0,
        waiting_seconds=0,
        message=f"Discovering phone listings on {store_name}...",
    )


def mark_discovering_page(store_name: str, page: int, max_pages: int) -> None:
    _set(
        status="discovering",
        current_store=store_name,
        waiting_seconds=0,
        message=f"Discovering listings on {store_name} (page {page} of up to {max_pages})...",
    )


def mark_store_completed(store_name: str) -> None:
    _set(
        status="running",
        current_store=store_name,
        waiting_seconds=0,
        message=f"{store_name} completed successfully.",
    )


def mark_moving_to_next_store(completed_store: str, next_store: str) -> None:
    _set(
        status="running",
        current_store=next_store,
        current_batch=0,
        total_batches=0,
        batch_processed=0,
        batch_total=0,
        waiting_seconds=0,
        message=f"Moving to {next_store} — starting immediately (no wait).",
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
    _set(
        status="waiting",
        current_store=store_name,
        current_batch=batch_num,
        total_batches=total_batches,
        waiting_seconds=seconds,
        message=(
            f"Batch {batch_num} of {total_batches} on {store_name} complete. "
            f"Waiting {_wait_label(seconds)} before next batch..."
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
    _set(running=False, status="failed", message=message, waiting_seconds=0)


def countdown_wait(seconds: int, on_tick: Optional[Callable[[int], None]] = None) -> None:
    remaining = seconds
    while remaining > 0:
        if on_tick:
            on_tick(remaining)
        sleep_for = min(1, remaining)
        time.sleep(sleep_for)
        remaining -= sleep_for
