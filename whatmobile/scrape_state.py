"""Persistent WhatMobile scrape state for resume-after-interrupt support."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings

STATE_VERSION = 2
BRAND_ORDER = ("apple", "samsung")


def _state_path() -> Path:
    configured = getattr(settings, "WHATMOBILE_STATE_FILE", None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "whatmobile_scrape_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brand_phase() -> Dict[str, Any]:
    return {
        "targets": [],
        "next_index": 0,
        "complete": False,
        "discovered": 0,
    }


def _empty_state() -> Dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "status": "idle",
        "limit_per_brand": 0,
        "current_brand": BRAND_ORDER[0],
        "brands": {brand: _brand_phase() for brand in BRAND_ORDER},
        "records_added": 0,
        "records_updated": 0,
        "records_scraped": 0,
        "updated_at": "",
    }


def _normalize_target(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item)
    if "source_id" not in normalized and normalized.get("gsmarena_id") is not None:
        normalized["source_id"] = normalized.pop("gsmarena_id")
    normalized.pop("gsmarena_id", None)
    return normalized


def _normalize_brand_targets(state: Dict[str, Any]) -> Dict[str, Any]:
    brands = state.get("brands") or {}
    for brand in BRAND_ORDER:
        phase = brands.get(brand) or {}
        targets = phase.get("targets") or []
        if targets:
            phase["targets"] = [_normalize_target(item) for item in targets]
            brands[brand] = phase
    state["brands"] = brands
    return state


def _migrate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if int(state.get("version") or 0) >= STATE_VERSION:
        return _normalize_brand_targets(state)

    migrated = _empty_state()
    migrated["status"] = state.get("status") or "idle"
    migrated["limit_per_brand"] = int(state.get("limit_per_brand") or 0)
    migrated["records_added"] = int(state.get("records_added") or 0)
    migrated["records_updated"] = int(state.get("records_updated") or 0)
    migrated["records_scraped"] = int(state.get("records_scraped") or 0)

    flat_targets = list(state.get("targets") or [])
    samsung_targets = [item for item in flat_targets if item.get("brand") == "samsung"]
    apple_targets = [item for item in flat_targets if item.get("brand") == "apple"]

    if not samsung_targets and not apple_targets:
        samsung_targets = [item for item in flat_targets if item.get("brand") != "apple"]
        apple_targets = [item for item in flat_targets if item.get("brand") == "apple"]

    next_index = int(state.get("next_index") or 0)
    migrated["brands"]["samsung"]["targets"] = samsung_targets
    migrated["brands"]["samsung"]["discovered"] = len(samsung_targets)
    migrated["brands"]["apple"]["targets"] = apple_targets
    migrated["brands"]["apple"]["discovered"] = len(apple_targets)

    if next_index < len(apple_targets):
        migrated["current_brand"] = "apple"
        migrated["brands"]["apple"]["next_index"] = next_index
    elif next_index < len(apple_targets) + len(samsung_targets):
        migrated["current_brand"] = "samsung"
        migrated["brands"]["apple"]["next_index"] = len(apple_targets)
        migrated["brands"]["apple"]["complete"] = bool(apple_targets)
        migrated["brands"]["samsung"]["next_index"] = next_index - len(apple_targets)
    else:
        migrated["brands"]["apple"]["complete"] = bool(apple_targets)
        migrated["brands"]["samsung"]["complete"] = bool(samsung_targets)
        migrated["brands"]["apple"]["next_index"] = len(apple_targets)
        migrated["brands"]["samsung"]["next_index"] = len(samsung_targets)

    return _normalize_brand_targets(migrated)


def load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_state()
        return _migrate_state(data)
    except (OSError, json.JSONDecodeError):
        return _empty_state()


def save_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["version"] = STATE_VERSION
    payload["updated_at"] = _utc_now()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_state() -> None:
    path = _state_path()
    if path.exists():
        path.unlink()


def _brand_state(state: Dict[str, Any], brand: str) -> Dict[str, Any]:
    brands = state.setdefault("brands", {name: _brand_phase() for name in BRAND_ORDER})
    if brand not in brands:
        brands[brand] = _brand_phase()
    return brands[brand]


def is_brand_complete(brand: str) -> bool:
    phase = _brand_state(load_state(), brand)
    return bool(phase.get("complete"))


def get_brand_targets(brand: str) -> List[Dict]:
    return list(_brand_state(load_state(), brand).get("targets") or [])


def get_brand_resume_index(brand: str) -> int:
    phase = _brand_state(load_state(), brand)
    if phase.get("complete"):
        return len(phase.get("targets") or [])
    return int(phase.get("next_index") or 0)


def get_resume_brand() -> Optional[str]:
    state = load_state()
    for brand in BRAND_ORDER:
        phase = _brand_state(state, brand)
        if phase.get("complete"):
            continue
        targets = phase.get("targets") or []
        next_index = int(phase.get("next_index") or 0)
        if not targets or next_index < len(targets):
            return brand
    return None


def total_discovered() -> int:
    state = load_state()
    return sum(int(_brand_state(state, brand).get("discovered") or 0) for brand in BRAND_ORDER)


def total_targets() -> int:
    state = load_state()
    return sum(len(_brand_state(state, brand).get("targets") or []) for brand in BRAND_ORDER)


def total_processed() -> int:
    state = load_state()
    total = 0
    for brand in BRAND_ORDER:
        phase = _brand_state(state, brand)
        if phase.get("complete"):
            total += len(phase.get("targets") or [])
        else:
            total += int(phase.get("next_index") or 0)
    return total


def is_resumable(limit_per_brand: int = 0) -> bool:
    state = load_state()
    if state.get("status") not in {"scraping", "failed", "discovering"}:
        return False
    saved_limit = int(state.get("limit_per_brand") or 0)
    if saved_limit != int(limit_per_brand or 0):
        return False
    return get_resume_brand() is not None


def begin_run(limit_per_brand: int = 0, *, fresh: bool = False) -> Dict[str, Any]:
    if fresh:
        state = _empty_state()
        state["status"] = "discovering"
        state["limit_per_brand"] = int(limit_per_brand or 0)
        state["current_brand"] = BRAND_ORDER[0]
    else:
        state = load_state()
        state["status"] = "scraping"
    save_state(state)
    return state


def set_brand_targets(brand: str, targets: List[Dict]) -> Dict[str, Any]:
    state = load_state()
    phase = _brand_state(state, brand)
    phase["targets"] = targets
    phase["discovered"] = len(targets)
    phase["next_index"] = int(phase.get("next_index") or 0)
    state["current_brand"] = brand
    state["status"] = "scraping"
    save_state(state)
    return state


def mark_brand_phone_complete(
    brand: str,
    next_index: int,
    *,
    added: int = 0,
    updated: int = 0,
    scraped: int = 0,
) -> Dict[str, Any]:
    state = load_state()
    phase = _brand_state(state, brand)
    phase["next_index"] = next_index
    state["current_brand"] = brand
    state["status"] = "scraping"
    state["records_added"] = int(state.get("records_added") or 0) + added
    state["records_updated"] = int(state.get("records_updated") or 0) + updated
    state["records_scraped"] = int(state.get("records_scraped") or 0) + scraped
    save_state(state)
    return state


def mark_brand_complete(brand: str) -> Dict[str, Any]:
    state = load_state()
    phase = _brand_state(state, brand)
    phase["complete"] = True
    phase["next_index"] = len(phase.get("targets") or [])
    state["status"] = "scraping"
    save_state(state)
    return state


def mark_failed_state() -> None:
    state = load_state()
    if any(_brand_state(state, brand).get("targets") for brand in BRAND_ORDER):
        state["status"] = "failed"
        save_state(state)


def mark_completed_state() -> None:
    clear_state()


# Backward-compatible helpers used elsewhere
def get_resume_index() -> int:
    return total_processed()


def get_saved_targets() -> List[Dict]:
    targets: List[Dict] = []
    for brand in BRAND_ORDER:
        targets.extend(get_brand_targets(brand))
    return targets


def begin_discovery(limit_per_brand: int = 0) -> Dict[str, Any]:
    return begin_run(limit_per_brand, fresh=False)


def begin_scraping(targets: List[Dict], limit_per_brand: int = 0) -> Dict[str, Any]:
    state = begin_run(limit_per_brand, fresh=True)
    samsung_targets = [item for item in targets if item.get("brand") == "samsung"]
    apple_targets = [item for item in targets if item.get("brand") == "apple"]
    _brand_state(state, "samsung")["targets"] = samsung_targets
    _brand_state(state, "samsung")["discovered"] = len(samsung_targets)
    _brand_state(state, "apple")["targets"] = apple_targets
    _brand_state(state, "apple")["discovered"] = len(apple_targets)
    state["status"] = "scraping"
    save_state(state)
    return state


def mark_phone_complete(
    next_index: int,
    *,
    added: int = 0,
    updated: int = 0,
    scraped: int = 0,
) -> Dict[str, Any]:
    brand = get_resume_brand() or BRAND_ORDER[0]
    return mark_brand_phone_complete(
        brand,
        next_index,
        added=added,
        updated=updated,
        scraped=scraped,
    )
