from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "sort", "is_published", "ext_id"]
    list_filter = ["is_published"]
    list_editable = ["sort"]
    search_fields = ["name"]
    readonly_fields = ["ext_id"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Учётные поля приходят из 1С и здесь только для чтения; на сайте ведутся описание и фото."""

    list_display = ["name", "sku", "category", "price_retail", "stock", "unit", "is_published"]
    list_filter = ["is_published", "category"]
    search_fields = ["name", "sku"]
    readonly_fields = ["ext_id", "sku", "name", "full_name", "unit", "weight_kg", "volume_m3",
                       "price_retail", "price_wholesale", "stock", "category", "updated_at"]
    fields = ["name", "full_name", "sku", "category", "unit", "price_retail", "price_wholesale", "stock",
              "weight_kg", "volume_m3", "slug", "description", "image", "is_published", "ext_id", "updated_at"]
