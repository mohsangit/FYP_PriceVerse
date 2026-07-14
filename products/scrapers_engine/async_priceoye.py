import asyncio
import re
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .async_http_client import AsyncScrapeHttpClient
from .detail_parser import DetailPageParser
from .discovery_utils import paginate_discovery
from .parsers import is_iphone_product, is_samsung_phone, normalize_title


class AsyncPriceOyeScraper:
    store_slug = "priceoye"
    store_name = "PriceOye"
    store_url = "https://priceoye.pk"

    BRAND_PATHS = {
        "iphone": "/mobiles/apple",
        "samsung": "/mobiles/samsung",
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
        try:
            html = await self.client.fetch_text(url)
            if not html:
                return None
            record = self.detail_parser.parse(html, url, brand)
            if not record:
                return None
            record["source_store"] = self.store_name
            return record
        except Exception:
            return None

    async def fetch_batch(
        self,
        batch: List[Dict],
        on_item_complete: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        records: List[Dict] = []
        total = len(batch)

        async def _one(item: Dict) -> Optional[Dict]:
            return await self.fetch_record(item["url"], item["brand"])

        tasks = [asyncio.create_task(_one(item)) for item in batch]
        done_count = 0
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

        prefix = "apple" if brand == "iphone" else "samsung"
        before_count = 0

        def build_page_url(page: int) -> str:
            return f"{self.store_url}{path}?page={page}"

        def parse_page(html: str, discovered: Dict[str, None]) -> bool:
            nonlocal before_count
            soup = BeautifulSoup(html, "html.parser")
            boxes = soup.select(".productBox")
            if not boxes:
                return True

            before = len(discovered)
            for box in boxes:
                link = box.select_one("a[href*='/mobiles/']")
                if not link:
                    continue
                href = link.get("href", "").strip()
                if not href:
                    continue
                full_url = href if href.startswith("http") else urljoin(self.store_url, href)
                title = normalize_title(link.get("data-vars-value") or link.get_text(" ", strip=True))
                if brand == "iphone" and not is_iphone_product(title):
                    continue
                if brand == "samsung" and not is_samsung_phone(title):
                    continue
                discovered[full_url] = None

            slug_pattern = rf"https://priceoye\.pk/mobiles/{prefix}/([a-z0-9-]+)"
            for slug in re.findall(slug_pattern, html):
                discovered[f"{self.store_url}/mobiles/{prefix}/{slug}"] = None

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
