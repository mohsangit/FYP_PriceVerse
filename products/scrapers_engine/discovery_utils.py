import asyncio
from typing import Callable, Dict, Optional

from .async_http_client import AsyncScrapeHttpClient

DISCOVERY_PAGE_CONCURRENCY = 6


async def fetch_discovery_pages(
    client: AsyncScrapeHttpClient,
    page_urls: list[str],
    concurrency: int = DISCOVERY_PAGE_CONCURRENCY,
) -> list[Optional[str]]:
    """Fetch multiple listing pages concurrently without polite delays."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _fetch(url: str) -> Optional[str]:
        async with semaphore:
            return await client.fetch_text(url, polite=False)

    return await asyncio.gather(*[_fetch(url) for url in page_urls])


async def paginate_discovery(
    client: AsyncScrapeHttpClient,
    build_page_url: Callable[[int], str],
    parse_page: Callable[[str, Dict[str, None]], bool],
    *,
    max_pages: int = 40,
    limit: int = 0,
    on_page: Optional[Callable[[int, int], None]] = None,
) -> list[str]:
    """
    Discover product URLs by fetching listing pages in parallel chunks.
    parse_page(html, discovered_dict) -> should_stop (True when no more pages).
    """
    discovered: Dict[str, None] = {}
    page = 1

    while page <= max_pages:
        if limit and len(discovered) >= limit:
            break

        chunk_end = min(page + DISCOVERY_PAGE_CONCURRENCY - 1, max_pages)
        page_numbers = list(range(page, chunk_end + 1))
        urls = [build_page_url(num) for num in page_numbers]
        html_pages = await fetch_discovery_pages(client, urls)

        stop = False
        for page_num, html in zip(page_numbers, html_pages):
            if on_page:
                on_page(page_num, max_pages)

            if not html:
                stop = True
                break

            if parse_page(html, discovered):
                stop = True
                break

            if limit and len(discovered) >= limit:
                stop = True
                break

        if stop:
            break

        page = chunk_end + 1

    urls = list(discovered.keys())
    if limit:
        urls = urls[:limit]
    return urls
