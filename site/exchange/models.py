from django.db import models


class ExchangeContact(models.Model):
    """Когда 1С последний раз обращалась к API обмена — для мониторинга (/healthz/) и админки. Одна строка."""

    last_seen_at = models.DateTimeField("Последнее обращение 1С")
    last_path = models.CharField("Адрес", max_length=200, blank=True)

    class Meta:
        verbose_name = "Связь с 1С"
        verbose_name_plural = "Связь с 1С"

    def __str__(self):
        return f"1С: {self.last_seen_at:%d.%m.%Y %H:%M}"
