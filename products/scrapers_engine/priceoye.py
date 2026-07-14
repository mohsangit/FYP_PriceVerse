import re
from typing import Dict, List, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseScraper
from .detail_parser import DetailPageParser
from .http_client import ScrapeHttpClient
from .parsers import is_iphone_product, is_samsung_phone, normalize_title, split_current_old_prices


class PriceOyeScraper(BaseScraper):
    store_slug = "priceoye"
    store_name = "PriceOye"
    store_url = "https://priceoye.pk"

    BRAND_PATHS = {
        "iphone": "/mobiles/apple",
        "samsung": "/mobiles/samsung",
    }

    MAX_PAGES = 40

    def __init__(self, client: ScrapeHttpClient | None = None):
        self.client = client or ScrapeHttpClient()
        self.detail_parser = DetailPageParser()

    def discover_targets(self, brand: str, limit: int = 0) -> List[Dict]:
        return [{"url": url, "brand": brand} for url in self._discover_product_urls(brand, limit)]

    def fetch_record(self, url: str, brand: str) -> Dict | None:
        return self._fetch_complete_record(url, brand)

    def scrape_brand(self, brand: str, limit: int = 0) -> List[Dict]:
        product_urls = self._discover_product_urls(brand, limit)
        results: List[Dict] = []

        for url in product_urls:
            record = self._fetch_complete_record(url, brand)
            if record:
                results.append(record)
            if limit and len(results) >= limit:
                break

        return results

    def _discover_product_urls(self, brand: str, limit: int = 0) -> List[str]:
        path = self.BRAND_PATHS.get(brand)
        if not path:
            return []

        prefix = "apple" if brand == "iphone" else "samsung"
        discovered: Dict[str, None] = {}

        for page in range(1, self.MAX_PAGES + 1):
            if limit and len(discovered) >= limit:
                break

            page_url = f"{self.store_url}{path}?page={page}"
            try:
                response = self.client.get(page_url)
            except Exception:
                break

            soup = BeautifulSoup(response.text, "html.parser")
            before = len(discovered)

            for box in soup.select(".productBox"):
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
            for slug in re.findall(slug_pattern, response.text):
                full_url = f"{self.store_url}/mobiles/{prefix}/{slug}"
                discovered[full_url] = None

            if page > 1 and len(discovered) == before and not soup.select(".productBox"):
                break

        urls = list(discovered.keys())
        if limit:
            urls = urls[:limit]
        return urls

    def _fetch_complete_record(self, url: str, brand: str) -> Dict | None:
        try:
            response = self.client.get(url)
        except Exception:
            return None

        record = self.detail_parser.parse(response.text, url, brand)
        if not record:
            return None

        record["source_store"] = self.store_name
        return record
