from typing import List, Dict
from .base import BaseScraper

class DarazScraper(BaseScraper):
    store_slug = "daraz"

    def search(self, keyword: str) -> List[Dict]:
        # NOTE: Real Daraz scraping can be blocked and may violate ToS.
        # Implement only if you have permission / allowed access.
        return []
