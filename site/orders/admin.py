from django.contrib import admin

from .models import Lead, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ["product", "sku", "name", "unit", "price", "quantity", "amount"]
    exclude = ["product_ext_id"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "created_at", "name", "phone", "customer_type", "delivery", "total",
                    "status", "ext_number", "exported_at"]
    list_filter = ["status", "delivery", "customer_type"]
    search_fields = ["name", "phone", "email", "company", "inn", "ext_number"]
    readonly_fields = ["token", "total", "total_1c", "weight_kg", "truck_t", "ext_id", "ext_number", "exported_at",
                       "status_text", "created_at"]
    inlines = [OrderItemInline]

    @admin.display(description="Номер")
    def number(self, obj):
        return obj.number


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "name", "phone", "exported_at", "ext_number"]
    list_filter = ["kind"]
    search_fields = ["name", "phone", "email", "text"]
    readonly_fields = ["ext_id", "ext_number", "exported_at", "created_at"]
