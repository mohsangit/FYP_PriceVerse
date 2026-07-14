from abc import ABC, abstractmethod
from typing import Dict, List


class BaseScraper(ABC):
    store_slug: str
    store_name: str
    store_url: str

    @abstractmethod
    def scrape_brand(self, brand: str, limit: int = 80) -> List[Dict]:
        """
        Scrape phone listings for a brand ('iphone' or 'samsung').

        Each result dict:
        {
            "title": "...",
            "product_url": "...",
            "current_price": 12345,
            "old_price": 15000,          # optional
            "image_url": "https://...",  # optional
            "category": "Mobile Phones",
            "description": "...",
        }
        """
        raise NotImplementedError
