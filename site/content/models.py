"""Контент сайта, который ведёт маркетолог в админке: акции, новости, советы и отзывы покупателей."""
from django.db import models
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product
from catalog.text import make_slug


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True, published_at__lte=timezone.now())

    def active_promos(self):
        today = timezone.localdate()
        return self.published().filter(kind=Post.Kind.PROMO).filter(
            Q(promo_until__isnull=True) | Q(promo_until__gte=today))


class Post(models.Model):
    class Kind(models.TextChoices):
        PROMO = "promo", "Акция"
        NEWS = "news", "Новость"
        ADVICE = "advice", "Совет"

    kind = models.CharField("Раздел", max_length=10, choices=Kind.choices, default=Kind.NEWS)
    title = models.CharField("Заголовок", max_length=200)
    slug = models.SlugField("Адрес", max_length=220, unique=True, blank=True)
    lead = models.CharField("Анонс", max_length=300, help_text="Одна-две фразы для карточки и описания страницы")
    body = models.TextField("Текст", help_text="Абзацы разделяются пустой строкой")
    image = models.ImageField("Картинка", upload_to="posts/%Y/", blank=True)
    promo_until = models.DateField("Акция действует до", null=True, blank=True,
                                   help_text="Только для акций; пусто — бессрочно")
    published_at = models.DateTimeField("Дата публикации", default=timezone.now)
    is_published = models.BooleanField("Опубликовано", default=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = "Публикация"
        verbose_name_plural = "Акции, новости и советы"
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.title, Post)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("content:post", args=[self.slug])

    @property
    def is_expired(self):
        return self.kind == self.Kind.PROMO and self.promo_until is not None and self.promo_until < timezone.localdate()


class ReviewQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(status=Review.Status.APPROVED)

    def summary(self):
        """{"count": N, "rating": средняя оценка или None} по одобренным отзывам."""
        data = self.approved().aggregate(count=Count("pk"), rating=Avg("rating"))
        return {"count": data["count"], "rating": round(data["rating"], 1) if data["rating"] else None}


class Review(models.Model):
    """Отзыв о товаре. На сайте появляется после одобрения в админке."""

    class Status(models.TextChoices):
        NEW = "new", "На модерации"
        APPROVED = "approved", "Опубликован"
        REJECTED = "rejected", "Отклонён"

    product = models.ForeignKey(Product, verbose_name="Товар", on_delete=models.CASCADE, related_name="reviews")
    name = models.CharField("Имя", max_length=80)
    rating = models.PositiveSmallIntegerField("Оценка", choices=[(n, str(n)) for n in range(1, 6)])
    text = models.TextField("Отзыв", max_length=2000)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.NEW)
    reply = models.TextField("Ответ магазина", blank=True)
    created_at = models.DateTimeField("Оставлен", auto_now_add=True)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.product}"
