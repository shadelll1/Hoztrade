from django.contrib import admin

from .models import Activity, Client, Deal, Task


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "email", "company", "created_at"]
    search_fields = ["name", "phone", "email", "company", "inn"]
    raw_id_fields = ["user"]


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ["number", "title", "client", "source", "stage", "manager", "amount", "created_at"]
    list_filter = ["stage", "source", "manager"]
    search_fields = ["title", "client__name", "client__phone"]
    raw_id_fields = ["client", "order", "lead", "profile"]


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
