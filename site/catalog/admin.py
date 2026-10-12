from django.contrib import admin
from django.utils.html import format_html

from catalog.templatetags.shop import qty, rub

from .brands import assign_brands
from .images import save_product_image
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

    list_display = ["photo", "name", "sku", "brand", "category", "price", "stock_qty", "is_published"]
    list_display_links = ["photo", "name"]
    list_filter = ["is_published", "brand", "category"]
    search_fields = ["name", "sku"]
    readonly_fields = ["ext_id", "sku", "name", "full_name", "unit", "weight_kg", "volume_m3",
                       "price_retail", "price_wholesale", "stock", "category", "updated_at"]
    # Сверху — то, что ведётся на сайте; ниже компактно — что пришло из 1С (меняется только там)
    fieldsets = [
        ("На сайте", {"fields": [("is_published", "brand"), "image", "description", "slug"]}),
        ("Из 1С", {"description": "Название, цены и остатки приходят из 1С при обмене — меняйте их в 1С.",
                   "fields": ["name", "full_name", ("sku", "unit", "category"),
                              ("price_retail", "price_wholesale", "stock"), ("weight_kg", "volume_m3")]}),
        ("Служебное", {"classes": ["collapse"], "fields": [("ext_id", "updated_at")]}),
    ]

    @admin.display(description="Фото")
    def photo(self, obj):
        pic = obj.thumb or obj.image
        if not pic:
            return format_html('<span class="ht-thumb ht-thumb--none" title="Фото нет">{}</span>', "нет")
        return format_html('<img class="ht-thumb" src="{}" alt="" loading="lazy">', pic.url)

    @admin.display(description="Цена", ordering="price_retail")
    def price(self, obj):
        return rub(obj.price_retail)

    @admin.display(description="Остаток", ordering="stock")
    def stock_qty(self, obj):
        return f"{qty(obj.stock)} {obj.unit}"

    def save_model(self, request, obj, form, change):
        """Фото, загруженное вручную, ужимается и получает миниатюру — как фото из 1С."""
        super().save_model(request, obj, form, change)
        if "image" in form.changed_data:
            if obj.image:
                obj.image.open("rb")
                data = obj.image.read()
                obj.image.close()
                save_product_image(obj, data)
            elif obj.thumb:
                obj.thumb.delete(save=False)
                obj.save(update_fields=["thumb"])
