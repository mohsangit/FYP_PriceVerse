from typing import Optional


def compute_insight_tag(current_price: int, old_price: Optional[int]) -> str:
    if old_price is None:
        return "Buy Now"
    if current_price <= old_price - 5000:
        return "Best Deal"
    if current_price >= old_price + 5000:
        return "Wait"
    return "Buy Now"


def compute_trend_text(current_price: int, old_price: Optional[int]) -> str:
    if old_price is None:
        return "Stable"
    if current_price < old_price:
        return "Price dropping"
    if current_price > old_price:
        return "Price rising"
    return "Stable"


def compute_trend_days(listing) -> int:
    history = list(listing.history.order_by("-scraped_at")[:30])
    if len(history) < 2:
        return 1
    delta = history[0].scraped_at - history[-1].scraped_at
    return max(1, delta.days)
