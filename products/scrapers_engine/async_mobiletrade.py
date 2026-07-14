import asyncio
import re
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .async_http_client import AsyncScrapeHttpClient
from .detail_parser import DetailPageParser
from .discovery_utils import paginate_discovery
from .parsers import is_iphone_product, is_samsung_phone, normalize_title


class AsyncMobileTradeScraper:
    store_slug = "mobiletrade"
    store_name = "MobileTrade"
    store_url = "https://mobiletrade.pk"

    BRAND_PATHS = {
        "iphone": "/product-category/mobile-phones/apple-iphone/",
        "samsung": "/product-category/mobile-phones/samsung/",
    }
    MAX_PAGES = 40

    def __init__(self, client: AsyncScrapeHttpClient):
        self.client = client
        self.detail_parser = DetailPageParser()

    async def discover_targets(
        self,
        brand: str,
        limit: int = 0,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        urls = await self._discover_product_urls(brand, limit, on_page=on_page)
        return [{"url": url, "brand": brand} for url in urls]

    async def discover_all_targets(
        self,
        brands: tuple[str, ...],
        limit_per_brand: int = 0,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        targets: Dict[str, Dict] = {}

        async def _discover_brand(brand: str) -> None:
            for item in await self.discover_targets(brand, limit_per_brand, on_page=on_page):
                targets[item["url"]] = item

        await asyncio.gather(*[_discover_brand(brand) for brand in brands])
        return list(targets.values())

    async def fetch_record(self, url: str, brand: str) -> Optional[Dict]:
        html = await self.client.fetch_text(url)
        if not html:
            return None
        record = self.detail_parser.parse(html, url, brand)
        if not record:
            return None
        record["source_store"] = self.store_name
        return record

    async def fetch_batch(
        self,
        batch: List[Dict],
        on_item_complete: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        records: List[Dict] = []

        async def _one(item: Dict) -> Optional[Dict]:
            return await self.fetch_record(item["url"], item["brand"])

        tasks = [asyncio.create_task(_one(item)) for item in batch]
        done_count = 0
        total = len(batch)
        for finished in asyncio.as_completed(tasks):
            record = await finished
            done_count += 1
            if record:
                records.append(record)
            if on_item_complete:
                on_item_complete(done_count, total)

        return records

    async def _discover_product_urls(
        self,
        brand: str,
        limit: int = 0,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> List[str]:
        path = self.BRAND_PATHS.get(brand)
        if not path:
            return []

        category_url = urljoin(self.store_url, path)
        before_count = 0

        def build_page_url(page: int) -> str:
            if page <= 1:
                return category_url
            return f"{category_url}page/{page}/"

        def parse_page(html: str, discovered: Dict[str, None]) -> bool:
            nonlocal before_count
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("li.product")
            if not cards:
                return True

            before = len(discovered)
            for card in cards:
                link = card.select_one(
                    "a.woocommerce-LoopProduct-link, "
                    "h2.woocommerce-loop-product__title a, "
                    "h3.woocommerce-loop-product__title a, "
                    "a[href*='/product/']"
                )
                if not link:
                    continue
                href = link.get("href", "").strip()
                if not href or "/product/" not in href:
                    continue
                product_url = href if href.startswith("http") else urljoin(self.store_url, href)
                title = normalize_title(
                    link.get("aria-label")
                    or link.get("title")
                    or link.get_text(" ", strip=True)
                )
                if brand == "iphone" and not is_iphone_product(title):
                    continue
                if brand == "samsung" and not is_samsung_phone(title):
                    continue
                discovered[product_url] = None

            for match in re.findall(r"https://mobiletrade\.pk/product/[a-z0-9-]+/?", html):
                discovered[match.rstrip("/") + "/"] = None

            if before_count > 0 and len(discovered) == before:
                return True
            before_count = len(discovered)
            return False

        return await paginate_discovery(
            self.client,
            build_page_url,
            parse_page,
            max_pages=self.MAX_PAGES,
            limit=limit,
            on_page=on_page,
        )
