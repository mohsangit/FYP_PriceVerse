from django import template
from urllib.parse import urlencode

from products.image_utils import PLACEHOLDER_LABEL, resolve_product_image

register = template.Library()


@register.simple_tag
def product_list_query(q="", source="", page=""):
    """Build a query string for the products list page."""
    params = {}
    if q:
        params["q"] = q
    if source:
        params["source"] = source
    if page:
        params["page"] = page
    return urlencode(params)


@register.simple_tag
def product_image_info(product):
    """Return resolved image metadata for a product."""
    return resolve_product_image(product)


@register.simple_tag
def product_placeholder_label():
    return PLACEHOLDER_LABEL
