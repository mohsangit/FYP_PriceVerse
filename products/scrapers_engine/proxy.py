"""
Optional proxy resolution for scraping.

Supports SCRAPE_PROXY_URL for a direct proxy URL.
"""

from typing import Optional

from django.conf import settings


def get_proxy_url() -> Optional[str]:
    direct = getattr(settings, "SCRAPE_PROXY_URL", "").strip()
    return direct or None
