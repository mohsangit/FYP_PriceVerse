from typing import Callable, Dict, List, Optional

from products.scrapers_engine.async_http_client import AsyncScrapeHttpClient

from .whatmobile_parser import (
    WHATMOBILE_BASE_URL,
    BRAND_LISTING_PAGES,
    parse_brand_listing_page,
    parse_phone_detail,
)


class AsyncWhatMobileScraper:
    store_slug = "whatmobile"
    store_name = "WhatMobile"
    store_url = WHATMOBILE_BASE_URL

    def __init__(self, client: AsyncScrapeHttpClient):
        self.client = client

    async def discover_targets(
        self,
        brand: str,
        limit: int = 0,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        page_url = BRAND_LISTING_PAGES.get(brand)
        if not page_url:
            return []

        if on_page:
            on_page(1, 1)

        html = await self.client.fetch_text(page_url)
        if not html:
            return []

        page_targets, _ = parse_brand_listing_page(html, page_url, brand=brand)
        results = [{**item, "brand": brand} for item in page_targets]
        if limit:
            results = results[:limit]
        return results

    async def discover_all_targets(
        self,
        brands: tuple[str, ...],
        limit_per_brand: int = 0,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        targets: Dict[str, Dict] = {}
        for brand in brands:
            for item in await self.discover_targets(brand, limit_per_brand, on_page=on_page):
                targets[item["url"]] = item
        return list(targets.values())

    async def fetch_record(self, url: str, brand: str) -> Optional[Dict]:
        html = await self.client.fetch_text(url)
        if not html:
            return None
        return parse_phone_detail(html, url, brand)

    async def fetch_batch(
        self,
        batch: List[Dict],
        on_item_complete: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        records: List[Dict] = []
        total = len(batch)

        for index, item in enumerate(batch, start=1):
            record = await self.fetch_record(item["url"], item["brand"])
            if record:
                records.append(record)
            if on_item_complete:
                on_item_complete(index, total)

        return records
