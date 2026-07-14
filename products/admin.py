from django.contrib import admin
from .models import Store, Product, ScrapedListing, PriceHistory, Favorite, PriceAlert, Review

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "website_url")
    search_fields = ("name", "slug")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "brand", "slug", "category", "insight_tag", "created_at")
    search_fields = ("title", "slug", "brand", "category")
    list_filter = ("brand", "category", "insight_tag")

@admin.register(ScrapedListing)
class ScrapedListingAdmin(admin.ModelAdmin):
    list_display = (
        "product", "store", "current_price", "old_price",
        "discount_pct", "is_on_sale", "availability_status", "last_scraped_at",
    )
    search_fields = ("product__title", "store__name", "product_url", "source_website")
    list_filter = ("store", "availability_status", "is_on_sale")

@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("listing", "price", "scraped_at")
    list_filter = ("scraped_at",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__username", "product__title")
    list_filter = ("created_at",)


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "baseline_price", "baseline_discount_pct", "created_at")
    search_fields = ("user__username", "user__email", "product__title")
    list_filter = ("created_at",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("author_name", "author_role", "rating", "is_published", "is_sample", "created_at")
    list_filter = ("is_published", "is_sample", "rating", "created_at")
    search_fields = ("author_name", "author_role", "body", "user__username")
    list_editable = ("is_published",)
