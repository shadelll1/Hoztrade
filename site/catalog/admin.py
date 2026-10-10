from django.contrib import admin

from .brands import assign_brands
from .models import Brand, Category, Product


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "aliases", "products_count", "sort", "is_published"]
    list_editable = ["sort", "is_published"]
    search_fields = ["name", "aliases"]
    actions = ["link_products"]

    @admin.display(description="Товаров")
    def products_count(self, obj):
        return obj.products.count()

    @admin.action(description="Привязать товары по названию")
    def link_products(self, request, queryset):
        self.message_user(request, f"Товаров привязано к брендам: {assign_brands()}")


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

    list_display = ["name", "sku", "brand", "category", "price_retail", "stock", "unit", "is_published"]
    list_filter = ["is_published", "brand", "category"]
    search_fields = ["name", "sku"]
    readonly_fields = ["ext_id", "sku", "name", "full_name", "unit", "weight_kg", "volume_m3",
                       "price_retail", "price_wholesale", "stock", "category", "updated_at"]
    fields = ["name", "full_name", "sku", "brand", "category", "unit", "price_retail", "price_wholesale", "stock",
              "weight_kg", "volume_m3", "slug", "description", "image", "is_published", "ext_id", "updated_at"]
