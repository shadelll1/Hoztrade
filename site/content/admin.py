from django.contrib import admin
from django.utils.html import format_html

from .models import Post, Review


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "published_at", "promo_until", "is_published"]
    list_filter = ["kind", "is_published"]
    list_editable = ["is_published"]
    search_fields = ["title", "lead", "body"]
    date_hierarchy = "published_at"
    fields = ["kind", "title", "lead", "body", "image", "promo_until", "published_at", "is_published", "slug"]

    def view_on_site(self, obj):
        return obj.get_absolute_url()


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Модерация: новый отзыв не виден на сайте, пока его не опубликуют."""

    list_display = ["created_at", "product", "name", "stars", "short_text", "status"]
    list_filter = ["status", "rating"]
    list_editable = ["status"]
    search_fields = ["name", "text", "product__name"]
    readonly_fields = ["product", "name", "rating", "text", "created_at"]
    fields = ["product", "name", "rating", "text", "created_at", "status", "reply"]
    actions = ["approve", "reject"]

    @admin.display(description="Оценка")
    def stars(self, obj):
        return format_html('<span style="color:#e0a400">{}</span>', "★" * obj.rating + "☆" * (5 - obj.rating))

    @admin.display(description="Отзыв")
    def short_text(self, obj):
        return obj.text[:80] + ("…" if len(obj.text) > 80 else "")

    @admin.action(description="Опубликовать")
    def approve(self, request, queryset):
        updated = queryset.update(status=Review.Status.APPROVED)
        self.message_user(request, f"Опубликовано отзывов: {updated}")

    @admin.action(description="Отклонить")
    def reject(self, request, queryset):
        updated = queryset.update(status=Review.Status.REJECTED)
        self.message_user(request, f"Отклонено отзывов: {updated}")

    def has_add_permission(self, request):
        return False
