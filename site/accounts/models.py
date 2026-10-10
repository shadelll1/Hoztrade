from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Покупатель сайта: контакты для оформления заказа и статус корпоративного клиента.

    Вход — по email (он же username пользователя Django). Оптовые цены видит только компания,
    которую подтвердил менеджер: заявку проверяют по ИНН, а не выдают автоматически.
    """

    class Wholesale(models.TextChoices):
        NONE = "none", "Нет"
        PENDING = "pending", "На проверке"
        APPROVED = "approved", "Подтверждён"
        REJECTED = "rejected", "Отклонён"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="Пользователь",
                                on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField("Телефон", max_length=20, blank=True)
    company = models.CharField("Организация", max_length=250, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    wholesale = models.CharField("Оптовые цены", max_length=10, choices=Wholesale.choices,
                                 default=Wholesale.NONE)
    wholesale_requested_at = models.DateTimeField("Заявка на опт", null=True, blank=True)
    wholesale_comment = models.CharField("Комментарий менеджера", max_length=250, blank=True,
                                         help_text="Покупатель видит его в личном кабинете")

    class Meta:
        verbose_name = "Профиль покупателя"
        verbose_name_plural = "Покупатели"

    def __str__(self):
        return self.company or self.user.get_full_name() or self.user.email

    @property
    def is_wholesale(self):
        return self.wholesale == self.Wholesale.APPROVED


def is_wholesale(user):
    """Видит ли пользователь оптовые цены."""
    if not getattr(user, "is_authenticated", False):
        return False
    profile = getattr(user, "profile", None)
    return bool(profile and profile.is_wholesale)
