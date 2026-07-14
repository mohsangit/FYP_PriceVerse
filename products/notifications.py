from typing import Tuple

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from .models import PriceAlert, Product
from .price_utils import best_price_info


def product_page_url(product: Product) -> str:
    path = reverse("products:detail", kwargs={"slug": product.slug})
    base = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}{path}"


def _price_improved(alert: PriceAlert, info: dict) -> bool:
    price_dropped = info["best_price"] < alert.baseline_price
    discount_improved = info["best_discount_pct"] > alert.baseline_discount_pct
    return price_dropped or discount_improved


def send_price_drop_email(alert: PriceAlert, product: Product, info: dict) -> None:
    user = alert.user
    if not user.email:
        return

    product_url = product_page_url(product)
    context = {
        "user": user,
        "product": product,
        "info": info,
        "product_url": product_url,
        "discount_pct": info["best_discount_pct"],
    }

    subject = f"Price drop: {product.title} is now at a better price!"
    message = render_to_string("products/emails/price_drop.txt", context)
    html_message = render_to_string("products/emails/price_drop.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def send_price_alert_subscribed_email(alert: PriceAlert, product: Product) -> None:
    user = alert.user
    if not user.email:
        return

    info = best_price_info(product) or {}
    product_url = product_page_url(product)
    context = {
        "user": user,
        "product": product,
        "product_url": product_url,
        "current_price": info.get("best_price"),
        "discount_pct": info.get("best_discount_pct", 0),
    }

    subject = f"Price alert set: {product.title}"
    message = render_to_string("products/emails/price_alert_subscribed.txt", context)
    html_message = render_to_string("products/emails/price_alert_subscribed.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def check_price_alerts_for_products(product_ids) -> int:
    if not product_ids:
        return 0

    alerts = (
        PriceAlert.objects.filter(product_id__in=product_ids)
        .select_related("user", "product")
    )

    sent_count = 0
    for alert in alerts:
        info = best_price_info(alert.product)
        if not info:
            continue

        if not _price_improved(alert, info):
            continue

        send_price_drop_email(alert, alert.product, info)
        alert.baseline_price = info["best_price"]
        alert.baseline_discount_pct = info["best_discount_pct"]
        alert.save(update_fields=["baseline_price", "baseline_discount_pct"])
        sent_count += 1

    return sent_count


def baseline_for_product(product: Product) -> Tuple[int, int]:
    info = best_price_info(product)
    if info:
        return info["best_price"], info["best_discount_pct"]
    return 0, 0
