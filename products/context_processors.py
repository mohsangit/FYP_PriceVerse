from .models import Favorite, PriceAlert
from .stats import get_site_stats


def site_stats(request):
    return {"site_stats": get_site_stats()}


def favorites(request):
    if request.user.is_authenticated:
        ids = set(
            Favorite.objects.filter(user=request.user).values_list("product_id", flat=True)
        )
        alert_ids = set(
            PriceAlert.objects.filter(user=request.user).values_list("product_id", flat=True)
        )
        return {
            "favorite_product_ids": ids,
            "favorites_count": len(ids),
            "price_alert_product_ids": alert_ids,
            "price_alerts_count": len(alert_ids),
        }
    return {
        "favorite_product_ids": set(),
        "favorites_count": 0,
        "price_alert_product_ids": set(),
        "price_alerts_count": 0,
    }
