"""Resolve product display images with WhatMobile fallback."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.cache import cache

from products.models import Product
from products.price_utils import display_listing_for_product
from products.utils import local_product_image_is_valid
from whatmobile.spec_fallback import find_matching_phone

IMAGE_CACHE_TTL = 3600
PLACEHOLDER_LABEL = "No Image Available"


@dataclass(frozen=True)
class ProductImage:
    src: str
    lightbox_src: str
    is_placeholder: bool
    source: str  # product | listing | whatmobile | placeholder

    @property
    def has_image(self) -> bool:
        return not self.is_placeholder


def _placeholder_image() -> ProductImage:
    src = staticfiles_storage.url("img/placeholder.png")
    return ProductImage(
        src=src,
        lightbox_src=src,
        is_placeholder=True,
        source="placeholder",
    )


def _image_from_url(url: str, source: str) -> ProductImage:
    url = (url or "").strip()
    return ProductImage(src=url, lightbox_src=url, is_placeholder=False, source=source)


def _cache_key(product: Product) -> str:
    version = int(product.updated_at.timestamp()) if product.updated_at else 0
    return f"product-img:{product.pk}:{version}"


def _whatmobile_image_url(product: Product) -> str:
    cached = cache.get(_cache_key(product))
    if cached is not None:
        return cached

    phone = find_matching_phone(product)
    url = ""
    if phone:
        url = (phone.display_image or "").strip()

    cache.set(_cache_key(product), url, IMAGE_CACHE_TTL)
    return url


def resolve_product_image(product: Product) -> ProductImage:
    """
    Image priority:
    1. Product.image (local file)
    2. Product.image_url
    3. Best retailer listing image_url
    4. Matched WhatMobile phone image
    5. Static placeholder
    """
    if product.image and local_product_image_is_valid(product):
        try:
            url = product.image.url
            if url:
                return _image_from_url(url, "product")
        except (ValueError, OSError):
            pass

    if product.image_url:
        return _image_from_url(product.image_url, "product")

    listing = display_listing_for_product(product)
    if listing and listing.image_url:
        return _image_from_url(listing.image_url, "listing")

    wm_url = _whatmobile_image_url(product)
    if wm_url:
        return _image_from_url(wm_url, "whatmobile")

    return _placeholder_image()
