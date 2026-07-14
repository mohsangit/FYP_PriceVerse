import asyncio
import random
from typing import Dict, Optional

import aiohttp
from django.conf import settings

from .proxy import get_proxy_url

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _client_settings() -> dict:
    return {
        "max_concurrent": int(getattr(settings, "SCRAPE_MAX_CONCURRENT", 4) or 4),
        "min_delay": float(getattr(settings, "SCRAPE_MIN_DELAY", 0.8) or 0.8),
        "max_delay": float(getattr(settings, "SCRAPE_MAX_DELAY", 1.6) or 1.6),
        "timeout": int(getattr(settings, "SCRAPE_REQUEST_TIMEOUT", 25) or 25),
        "max_retries": int(getattr(settings, "SCRAPE_MAX_RETRIES", 3) or 3),
        "retry_backoff": float(getattr(settings, "SCRAPE_RETRY_BACKOFF", 2.0) or 2.0),
    }


class AsyncScrapeHttpClient:
    """
    Async HTTP client with semaphore-limited concurrency, polite delays,
    retries, and optional direct proxy support.
    """

    def __init__(
        self,
        max_concurrent: Optional[int] = None,
        min_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        rate_limit_backoff_base: Optional[float] = None,
    ):
        cfg = _client_settings()
        self.max_concurrent = max_concurrent if max_concurrent is not None else cfg["max_concurrent"]
        self.min_delay = min_delay if min_delay is not None else cfg["min_delay"]
        self.max_delay = max_delay if max_delay is not None else cfg["max_delay"]
        self.timeout = timeout if timeout is not None else cfg["timeout"]
        self.max_retries = max_retries if max_retries is not None else cfg["max_retries"]
        self.retry_backoff = retry_backoff if retry_backoff is not None else cfg["retry_backoff"]

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        self._proxy: Optional[str] = None
        self._headers = {**DEFAULT_HEADERS, **(extra_headers or {})}
        self.rate_limit_backoff_base = rate_limit_backoff_base

    async def __aenter__(self):
        self._proxy = get_proxy_url()
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.max_concurrent, ssl=True)
        self._session = aiohttp.ClientSession(
            headers=self._headers,
            timeout=timeout,
            connector=connector,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_text(self, url: str, polite: bool = True) -> Optional[str]:
        if not self._session:
            raise RuntimeError("AsyncScrapeHttpClient must be used as an async context manager.")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with self._semaphore:
                    if polite:
                        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))
                    async with self._session.get(url, proxy=self._proxy) as response:
                        if response.status == 429:
                            if self.rate_limit_backoff_base:
                                wait = self.rate_limit_backoff_base * (2 ** attempt)
                            else:
                                wait = min(120.0, 20.0 * (2 ** attempt))
                            await asyncio.sleep(min(wait, 120.0))
                            last_error = RuntimeError(f"HTTP 429 Too Many Requests for {url}")
                            continue
                        response.raise_for_status()
                        return await response.text()
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_backoff ** attempt)
        return None
