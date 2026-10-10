from django.contrib import admin

from .models import ExchangeContact


@admin.register(ExchangeContact)
class ExchangeContactAdmin(admin.ModelAdmin):
    list_display = ["last_seen_at", "last_path"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
