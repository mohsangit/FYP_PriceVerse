import requests

from products.utils import polite_sleep

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class ScrapeHttpClient:
    def __init__(self, min_delay: float = 1.2, max_delay: float = 2.4):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get(self, url: str, timeout: int = 25) -> requests.Response:
        polite_sleep(self.min_delay, self.max_delay)
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        return response
