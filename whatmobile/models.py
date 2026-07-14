from django.db import models


class WhatMobilePhone(models.Model):
    """WhatMobile phone data — stored in a separate database from retailer products."""

    BRAND_CHOICES = [
        ("samsung", "Samsung"),
        ("apple", "Apple"),
    ]

    brand = models.CharField(max_length=40, choices=BRAND_CHOICES, db_index=True)
    model_name = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True)
    source_id = models.PositiveIntegerField(unique=True)
    source_url = models.URLField(max_length=500, unique=True)

    image = models.ImageField(upload_to="whatmobile/", blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True)

    official_price = models.CharField(max_length=120, blank=True)
    official_price_value = models.IntegerField(blank=True, null=True)
    official_price_currency = models.CharField(max_length=10, blank=True)

    description = models.TextField(blank=True)
    release_status = models.CharField(max_length=120, blank=True)
    specifications = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["brand", "model_name"]
        indexes = [
            models.Index(fields=["brand", "model_name"]),
            models.Index(fields=["-updated_at"]),
        ]

    def __str__(self):
        return self.model_name

    @property
    def display_image(self) -> str:
        if self.image:
            return self.image.url
        return self.image_url or ""
