import random
import time
import requests
from django.core.files.base import ContentFile

MIN_IMAGE_BYTES = 1024


def polite_sleep(min_seconds: float = 1.5, max_seconds: float = 3.5):
    """
    Adds a random delay between requests to reduce burst.
    This is NOT a guarantee against blocking, but it helps reduce load.
    """
    time.sleep(random.uniform(min_seconds, max_seconds))


def detect_image_extension(content: bytes) -> str | None:
    """Return a file extension from image magic bytes, or None if not a usable image."""
    if not content or len(content) < MIN_IMAGE_BYTES:
        return None

    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:4] == b"RIFF" and len(content) >= 12 and content[8:12] == b"WEBP":
        return "webp"
    if content[4:8] == b"ftyp" and b"avif" in content[:32]:
        return "avif"
    if content[:15].lower().startswith(b"<!doctype") or content[:5].lower() == b"<html":
        return None
    return None


def local_product_image_is_valid(product) -> bool:
    """True when product.image points at a readable image file on disk."""
    if not product.image:
        return False
    try:
        path = product.image.path
    except (ValueError, OSError):
        return False

    try:
        with open(path, "rb") as handle:
            content = handle.read()
    except OSError:
        return False

    detected = detect_image_extension(content)
    if not detected:
        return False

    name = (product.image.name or "").lower()
    if detected == "jpg":
        return name.endswith((".jpg", ".jpeg"))
    return name.endswith(f".{detected}")


def local_product_image_needs_download(product) -> bool:
    return not local_product_image_is_valid(product)


def download_image_to_product(product, image_url: str, *, force: bool = False) -> bool:
    """
    Attempts to download an image and store in product.image.
    Returns True if saved, else False.
    """
    if not image_url:
        return False

    if product.image:
        if not force and local_product_image_is_valid(product):
            return False
        try:
            product.image.delete(save=False)
        except Exception:
            pass

    try:
        polite_sleep(1.0, 2.0)

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        r = requests.get(image_url, headers=headers, timeout=12)
        if r.status_code != 200:
            return False

        ext = detect_image_extension(r.content)
        if not ext:
            return False

        filename = f"{product.slug}.{ext}"
        product.image.save(filename, ContentFile(r.content), save=True)
        return True
    except Exception:
        return False
