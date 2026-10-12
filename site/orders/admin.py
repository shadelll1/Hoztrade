from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from catalog.templatetags.shop import rub

from .models import Lead, Order, OrderItem
from .privacy import anonymize_lead, anonymize_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ["product", "sku", "name", "unit", "price", "quantity", "amount"]
    exclude = ["product_ext_id"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # Тип покупателя и цены — в фильтрах справа: в строке списка место нужно статусу и сумме
    list_display = ["number", "created", "name", "phone", "delivery", "sum", "status_badge", "ext_number"]
    date_hierarchy = "created_at"
    list_filter = ["status", "delivery", "zone", "customer_type", "price_type"]
    search_fields = ["name", "phone", "email", "company", "inn", "ext_number"]
    readonly_fields = ["token", "price_type", "total", "total_1c", "weight_kg", "volume_m3", "truck_t", "truck_name",
                       "trips", "delivery_cost", "ext_id", "ext_number", "exported_at", "status_text", "created_at"]
    inlines = [OrderItemInline]
    actions = ["anonymize"]
    fieldsets = [
        ("Статус", {"fields": [("status", "status_text"), "created_at"]}),
        ("Покупатель", {"fields": ["customer_type", ("name", "phone"), "email", ("company", "inn"), "user",
                                   "price_type"]}),
        ("Получение", {"fields": ["delivery", "pickup_store", ("zone", "address"),
                                  ("delivery_date", "delivery_interval"), "comment"]}),
        ("Сумма и машина", {"fields": [("total", "total_1c"), ("delivery_cost", "trips"),
                                       ("weight_kg", "volume_m3"), ("truck_name", "truck_t")]}),
        ("Обмен с 1С", {"classes": ["collapse"], "fields": [("ext_number", "exported_at"), "ext_id", "token"]}),
    ]

    @admin.action(description="Обезличить (удалить персональные данные по запросу покупателя)")
    def anonymize(self, request, queryset):
        for order in queryset:
            anonymize_order(order)
        self.message_user(request, f"Обезличено заказов: {queryset.count()}")

    @admin.display(description="Номер")
    def number(self, obj):
        return obj.number

    @admin.display(description="Создан", ordering="created_at")
    def created(self, obj):
        return timezone.localtime(obj.created_at).strftime("%d.%m.%Y %H:%M")

    @admin.display(description="Сумма", ordering="total")
    def sum(self, obj):
        return rub(obj.total_1c if obj.total_1c is not None else obj.grand_total)

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj):
        return format_html('<span class="ht-badge ht-badge--{}">{}</span>', obj.status, obj.get_status_display())


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "name", "phone", "exported_at", "ext_number"]
    list_filter = ["kind"]
    search_fields = ["name", "phone", "email", "text"]
    readonly_fields = ["ext_id", "ext_number", "exported_at", "created_at"]
    actions = ["anonymize"]

    @admin.action(description="Обезличить (удалить персональные данные и файл)")
    def anonymize(self, request, queryset):
        for lead in queryset:
            anonymize_lead(lead)
        self.message_user(request, f"Обезличено заявок: {queryset.count()}")
