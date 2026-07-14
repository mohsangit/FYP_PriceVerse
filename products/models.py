from django.conf import settings
from django.db import models


class Store(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    website_url = models.URLField(blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(unique=True)
    brand = models.CharField(max_length=80, blank=True)

    image = models.ImageField(upload_to="products/", blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True)

    short_description = models.CharField(max_length=260, blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    specifications = models.JSONField(default=dict, blank=True)

    insight_tag = models.CharField(max_length=30, default="Buy Now")
    trend_text = models.CharField(max_length=40, default="Stable")
    trend_days = models.IntegerField(default=1)
    is_discontinued = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["brand"]),
            models.Index(fields=["title"]),
            models.Index(fields=["is_discontinued", "-created_at"]),
        ]

    def __str__(self):
        return self.title


class ScrapedListing(models.Model):
    AVAILABILITY_CHOICES = [
        ("in_stock", "In Stock"),
        ("out_of_stock", "Out of Stock"),
        ("pre_order", "Pre-order"),
        ("back_order", "Back Order"),
        ("unknown", "Unknown"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="listings")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="listings")

    product_url = models.URLField()
    image_url = models.URLField(max_length=500, blank=True)
    availability_status = models.CharField(
        max_length=40,
        choices=AVAILABILITY_CHOICES,
        default="unknown",
    )
    specifications = models.JSONField(default=dict, blank=True)

    current_price = models.IntegerField()
    old_price = models.IntegerField(blank=True, null=True)
    discount_pct = models.PositiveIntegerField(default=0)
    is_on_sale = models.BooleanField(default=False)
    source_website = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=10, default="PKR")

    last_scraped_at = models.DateTimeField(auto_now=True)

    @property
    def original_price(self):
        return self.old_price

    @property
    def discounted_price(self):
        return self.current_price

    @property
    def discount_percentage(self):
        return self.discount_pct

    @property
    def sale_status(self):
        return self.is_on_sale

    class Meta:
        unique_together = ("product", "store")
        indexes = [
            models.Index(fields=["product_url"]),
            models.Index(fields=["-last_scraped_at"]),
        ]

    def __str__(self):
        return f"{self.product.title} @ {self.store.name} ({self.current_price})"

class PriceHistory(models.Model):
    listing = models.ForeignKey(ScrapedListing, on_delete=models.CASCADE, related_name="history")
    price = models.IntegerField()
    scraped_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scraped_at"]

    def __str__(self):
        return f"{self.listing} -> {self.price}"


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_favorite",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} ♥ {self.product.title}"


class Review(models.Model):
    """User testimonials / reviews shown in the testimonials section.

    Sample rows are seeded for demo purposes and can later be replaced or
    supplemented by real user-submitted reviews (managed via the admin or the
    front-end submission form).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviews",
        null=True,
        blank=True,
    )
    author_name = models.CharField(max_length=80)
    author_role = models.CharField(
        max_length=80,
        blank=True,
        help_text="Short label shown under the name, e.g. 'Smart Shopper'.",
    )
    rating = models.PositiveSmallIntegerField(default=5)
    body = models.TextField(help_text="The review / testimonial text.")
    highlight_label = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional metric label, e.g. 'Saved'.",
    )
    highlight_value = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional metric value, e.g. 'Rs. 12,000'.",
    )
    is_published = models.BooleanField(default=True)
    is_sample = models.BooleanField(
        default=False,
        help_text="Marks demo/sample reviews so they can be cleared later.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.author_name} ({self.rating}★)"

    @property
    def initials(self):
        parts = [p for p in self.author_name.split() if p]
        if not parts:
            return "PV"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def star_states(self):
        """List of 5 booleans indicating whether each star is filled."""
        return [i < self.rating for i in range(5)]


class PriceAlert(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="price_alerts",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="price_alerts",
    )
    baseline_price = models.IntegerField(
        help_text="Best price across stores when subscribed or last notified.",
    )
    baseline_discount_pct = models.IntegerField(
        default=0,
        help_text="Best discount % when subscribed or last notified.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_price_alert",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} → {self.product.title} (Rs {self.baseline_price})"
