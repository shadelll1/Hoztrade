from django.contrib import admin

from .models import Tariff, Truck, Zone


class TariffInline(admin.TabularInline):
    model = Tariff
    extra = 0


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    """Зоны и тарифы ведутся в 1С; на сайте их можно поправить, но следующий обмен перезапишет."""

    list_display = ["name", "description", "sort", "is_active", "ext_id"]
    list_filter = ["is_active"]
    readonly_fields = ["ext_id"]
    inlines = [TariffInline]


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ["name", "capacity_t", "volume_m3", "is_active", "ext_id"]
    list_filter = ["is_active"]
    readonly_fields = ["ext_id"]
