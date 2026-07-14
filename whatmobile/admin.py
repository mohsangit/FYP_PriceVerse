from django.contrib import admin

from .models import WhatMobilePhone


@admin.register(WhatMobilePhone)
class WhatMobilePhoneAdmin(admin.ModelAdmin):
    list_display = ("model_name", "brand", "official_price", "updated_at")
    list_filter = ("brand",)
    search_fields = ("model_name", "slug", "source_url")
