import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from whatmobile.comparison import build_comparison
from whatmobile.discontinued import DISCONTINUED_MESSAGE
from whatmobile.phone_filters import dropdown_phone_queryset, phone_display_label
from whatmobile.spec_fallback import get_display_specifications

from .models import Product, Favorite, PriceAlert, ScrapedListing
from .notifications import baseline_for_product, send_price_alert_subscribed_email
from .price_utils import best_price_info, discount_pct, display_listing_for_product
from .availability import available_first
from .constants import PRODUCT_SOURCE_FILTERS, PRODUCT_SOURCE_SLUGS

logger = logging.getLogger(__name__)


@login_required
def product_list(request):
    q = (request.GET.get("q") or "").strip()
    source = (request.GET.get("source") or "").strip().lower()
    if source and source not in PRODUCT_SOURCE_SLUGS:
        source = ""
    per_page = int(getattr(settings, "PRODUCTS_PER_PAGE", 30) or 30)

    products = available_first(
        Product.objects.prefetch_related(
            Prefetch("listings", queryset=ScrapedListing.objects.select_related("store"))
        )
    )
    if source:
        products = products.filter(listings__store__slug=source).distinct()
    if q:
        products = products.filter(
            Q(title__icontains=q)
            | Q(brand__icontains=q)
            | Q(category__icontains=q)
            | Q(short_description__icontains=q)
            | Q(description__icontains=q)
        )

    paginator = Paginator(products, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    product_cards = []
    for product in page_obj.object_list:
        product_cards.append({
            "product": product,
            "best_listing": display_listing_for_product(product, source or None),
        })

    active_source = next(
        (item for item in PRODUCT_SOURCE_FILTERS if item["slug"] == source),
        None,
    )

    return render(
        request,
        "products/list.html",
        {
            "product_cards": product_cards,
            "page_obj": page_obj,
            "paginator": paginator,
            "q": q,
            "source": source,
            "active_source": active_source,
            "source_filters": PRODUCT_SOURCE_FILTERS,
            "per_page": per_page,
        },
    )


@login_required
def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug)
    listings = product.listings.select_related("store").all()

    listing_rows = []
    for listing in listings:
        listing_rows.append({
            "listing": listing,
            "discount_pct": listing.discount_pct or discount_pct(listing.current_price, listing.old_price),
        })

    best = best_price_info(product)
    display_specifications, specs_source = get_display_specifications(product)
    from products.availability import refresh_product_discontinued

    is_discontinued = refresh_product_discontinued(product)

    histories = []
    for listing in listings:
        points = list(listing.history.all().order_by("-scraped_at")[:30])
        points.reverse()

        histories.append({
            "store": listing.store.name,
            "prices": [p.price for p in points],
            "labels": [p.scraped_at.strftime("%d %b %H:%M") for p in points],
        })

    return render(
        request,
        "products/detail.html",
        {
            "product": product,
            "listings": listings,
            "listing_rows": listing_rows,
            "best": best,
            "histories": histories,
            "best_listing": display_listing_for_product(product),
            "display_specifications": display_specifications,
            "specs_source": specs_source,
            "is_discontinued": is_discontinued,
            "discontinued_message": DISCONTINUED_MESSAGE if is_discontinued else "",
        },
    )


@login_required
def favorites_list(request):
    favorites = (
        Favorite.objects.filter(user=request.user)
        .select_related("product")
        .prefetch_related(
            Prefetch("product__listings", queryset=ScrapedListing.objects.select_related("store"))
        )
        .order_by("product__is_discontinued", "-created_at")
    )
    product_cards = [
        {"product": fav.product, "best_listing": display_listing_for_product(fav.product)}
        for fav in favorites
    ]
    return render(request, "products/favorites.html", {"product_cards": product_cards})


@login_required
@require_POST
def toggle_favorite(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    favorite = Favorite.objects.filter(user=request.user, product=product).first()

    if favorite:
        favorite.delete()
        is_favorited = False
    else:
        Favorite.objects.create(user=request.user, product=product)
        is_favorited = True

    favorites_count = Favorite.objects.filter(user=request.user).count()
    return JsonResponse({
        "is_favorited": is_favorited,
        "favorites_count": favorites_count,
        "product_id": product.id,
    })


@login_required
@require_POST
def toggle_price_alert(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    alert = PriceAlert.objects.filter(user=request.user, product=product).first()

    if alert:
        alert.delete()
        is_subscribed = False
    else:
        baseline_price, baseline_discount = baseline_for_product(product)
        alert = PriceAlert.objects.create(
            user=request.user,
            product=product,
            baseline_price=baseline_price,
            baseline_discount_pct=baseline_discount,
        )
        is_subscribed = True
        try:
            send_price_alert_subscribed_email(alert, product)
        except Exception:
            alert.delete()
            return JsonResponse(
                {"error": "Could not send confirmation email. Please try again."},
                status=502,
            )

    alerts_count = PriceAlert.objects.filter(user=request.user).count()
    return JsonResponse({
        "is_subscribed": is_subscribed,
        "alerts_count": alerts_count,
        "product_id": product.id,
        "email_sent": is_subscribed,
    })


@login_required
def compare(request):
    """Phone selector page — choose two WhatMobile phones then start comparison."""
    phones_qs = dropdown_phone_queryset()
    phone_options = [
        {
            "id": phone.id,
            "model_name": phone.model_name,
            "brand": phone.brand,
            "label": phone_display_label(phone.brand, phone.model_name),
        }
        for phone in phones_qs
    ]

    def _clean_id(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    return render(
        request,
        "products/compare.html",
        {
            "phone_options": phone_options,
            "selected_a": _clean_id(request.GET.get("a")),
            "selected_b": _clean_id(request.GET.get("b")),
            "whatmobile_count": phones_qs.count(),
        },
    )


@login_required
def compare_results(request):
    """Dedicated comparison results page using WhatMobile specs and bridged prices."""
    def _clean_id(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    id_a = _clean_id(request.GET.get("a"))
    id_b = _clean_id(request.GET.get("b"))

    comparison = None
    phone_a = phone_b = None
    build_error = ""

    if not id_a or not id_b:
        build_error = "Please select two phones to compare."
    elif id_a == id_b:
        build_error = "Please choose two different phones."
    else:
        phones = {
            p.id: p
            for p in dropdown_phone_queryset().filter(id__in=[id_a, id_b])
        }
        phone_a = phones.get(id_a)
        phone_b = phones.get(id_b)
        if not phone_a or not phone_b:
            build_error = "One or both phones were not found. Run the WhatMobile scraper first."
        else:
            try:
                comparison = build_comparison(phone_a, phone_b)
            except Exception:
                logger.exception("Failed to build comparison for %s vs %s", id_a, id_b)
                build_error = "We couldn't load the comparison right now. Please try again."

    return render(
        request,
        "products/compare_results.html",
        {
            "comparison": comparison,
            "selected_a": id_a,
            "selected_b": id_b,
            "phone_a": phone_a,
            "phone_b": phone_b,
            "build_error": build_error,
        },
    )
