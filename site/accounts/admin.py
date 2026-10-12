from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Корпоративные клиенты: менеджер проверяет компанию по ИНН и открывает оптовые цены."""

    list_display = ["__str__", "email", "phone", "inn", "wholesale_badge", "wholesale_requested_at"]
    list_filter = ["wholesale"]
    search_fields = ["company", "inn", "phone", "user__email", "user__first_name"]
    readonly_fields = ["user", "wholesale_requested_at"]
    fields = ["user", "phone", "company", "inn", "wholesale", "wholesale_requested_at", "wholesale_comment"]
    actions = ["approve", "reject"]
    ordering = ["-wholesale_requested_at"]

    @admin.display(description="Оптовые цены", ordering="wholesale")
    def wholesale_badge(self, obj):
        return format_html('<span class="ht-badge ht-badge--ws-{}">{}</span>', obj.wholesale,
                           obj.get_wholesale_display())

    @admin.display(description="Email", ordering="user__email")
    def email(self, obj):
        return obj.user.email

    @admin.action(description="Открыть оптовые цены")
    def approve(self, request, queryset):
        done = queryset.exclude(inn="").update(wholesale=Profile.Wholesale.APPROVED, wholesale_comment="")
        self.message_user(request, f"Оптовые цены открыты: {done}", messages.SUCCESS)

    @admin.action(description="Отклонить заявку на опт")
    def reject(self, request, queryset):
        done = queryset.update(wholesale=Profile.Wholesale.REJECTED)
        self.message_user(request, f"Отклонено: {done}. Причину можно написать в карточке — покупатель её увидит.")


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ["phone", "company", "inn", "wholesale", "wholesale_comment"]


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class SiteUserAdmin(UserAdmin):
    inlines = [ProfileInline]
