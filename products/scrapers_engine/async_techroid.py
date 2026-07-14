import asyncio
import re
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .async_http_client import AsyncScrapeHttpClient
from .detail_parser import DetailPageParser
from .discovery_utils import paginate_discovery
from .parsers import is_iphone_product, is_samsung_phone, normalize_title

_SKIP_SLUG_PARTS = (
    "tab-",
    "watch",
    "buds",
    "adapter",
    "charger",
    "case",
    "cover",
    "macbook",
    "ipad",
    "airpods",
    "power-bank",
    "earphone",
    "headphone",
)


class AsyncTechroidScraper:
    store_slug = "techroid"
    store_name = "Techroid"
    store_url = "https://techroid.com"

    BRAND_PATHS = {
        "iphone": "/collection/smartphones/iphones/",
        "samsung": "/collection/smartphones/samsung/",
    }
    MAX_PAGES = 20

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

    def _normalize_product_url(self, href: str) -> str:
        href = (href or "").strip()
        if not href:
            return ""
        if href.startswith("/"):
            href = urljoin(self.store_url, href)
        href = href.replace("https://www.techroid.com", self.store_url)
        if not href.startswith("http"):
            return ""
        if "/product/" not in href:
            return ""
        return href.rstrip("/") + "/"

    def _is_relevant_product(self, brand: str, title: str, product_url: str) -> bool:
        slug = product_url.lower()
        if any(part in slug for part in _SKIP_SLUG_PARTS):
            return False
        if brand == "iphone":
            return is_iphone_product(title) or "iphone" in slug
        if brand == "samsung":
            return is_samsung_phone(title) or "samsung" in slug or "galaxy" in slug
        return False

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
            before = len(discovered)

            for link in soup.select("a[href*='/product/']"):
                product_url = self._normalize_product_url(link.get("href", ""))
                if not product_url:
                    continue
                title = normalize_title(
                    link.get("aria-label")
                    or link.get("title")
                    or link.get_text(" ", strip=True)
                    or product_url.split("/product/")[-1].replace("-", " ")
                )
                if not self._is_relevant_product(brand, title, product_url):
                    continue
                discovered[product_url] = None

            slug_prefix = "iphone" if brand == "iphone" else "samsung"
            pattern = rf"https://(?:www\.)?techroid\.com/product/(?:{slug_prefix}|galaxy|samsung)[a-z0-9-]*/?"
            for match in re.findall(pattern, html, flags=re.I):
                product_url = self._normalize_product_url(match)
                if product_url and self._is_relevant_product(brand, "", product_url):
                    discovered[product_url] = None

            if not discovered and before == 0:
                return True
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
