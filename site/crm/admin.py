from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from catalog.templatetags.shop import rub

from .models import Activity, Client, Deal, Task


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "email", "company", "created_at"]
    search_fields = ["name", "phone", "email", "company", "inn"]
    raw_id_fields = ["user"]


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ["num", "title", "client", "source", "stage_badge", "manager_name", "sum", "created", "crm_link"]
    list_display_links = ["num", "title"]
    list_filter = ["stage", "source", "manager"]
    search_fields = ["title", "client__name", "client__phone"]
    raw_id_fields = ["client", "order", "lead", "profile"]
    date_hierarchy = "created_at"

    @admin.display(description="Номер", ordering="pk")
    def num(self, obj):
        return obj.number

    @admin.display(description="Менеджер", ordering="manager__first_name")
    def manager_name(self, obj):
        return (obj.manager.get_full_name() or obj.manager.username) if obj.manager else "—"

    @admin.display(description="Сумма", ordering="amount")
    def sum(self, obj):
        return rub(obj.amount) if obj.amount else "—"

    @admin.display(description="Создано", ordering="created_at")
    def created(self, obj):
        return timezone.localtime(obj.created_at).strftime("%d.%m.%Y %H:%M")

    @admin.display(description="Этап", ordering="stage")
    def stage_badge(self, obj):
        return format_html('<span class="ht-badge ht-badge--stage-{}">{}</span>', obj.stage, obj.get_stage_display())

    @admin.display(description="")
    def crm_link(self, obj):
        return format_html('<a href="{}">В CRM</a>', reverse("crm:deal", args=[obj.pk]))

    def view_on_site(self, obj):
        """Кнопка «Смотреть на сайте» в карточке ведёт в CRM — там с обращением и работают."""
        return reverse("crm:deal", args=[obj.pk])


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "assignee", "due_at", "done_at", "deal"]
    list_filter = ["assignee"]
    raw_id_fields = ["deal", "client"]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "client", "deal", "author", "text"]
    list_filter = ["kind"]
    raw_id_fields = ["deal", "client"]
