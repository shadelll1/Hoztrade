"""CRM менеджеров: клиенты, обращения (сделки) по этапам, задачи и лента событий.

Обращения создаются сами из заказов, заявок и запросов оптовых цен (crm/signals.py), статусы заказов из 1С
двигают их по этапам. 1С остаётся учётной системой: CRM — рабочее место менеджера поверх сайта.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Client(models.Model):
    """Покупатель: частное лицо или компания. Узнаётся по телефону, затем по email."""

    name = models.CharField("Имя", max_length=150)
    phone = models.CharField("Телефон", max_length=20, blank=True, db_index=True, help_text="+7XXXXXXXXXX")
    email = models.EmailField("Email", blank=True, db_index=True)
    company = models.CharField("Организация", max_length=250, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Учётная запись на сайте", null=True,
                             blank=True, on_delete=models.SET_NULL, related_name="crm_clients")
    notes = models.TextField("Заметки", blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["name"]

    def __str__(self):
        return self.company or self.name

    def get_absolute_url(self):
        return reverse("crm:client", args=[self.pk])


class Deal(models.Model):
    """Обращение клиента: заказ, заявка, звонок. Идёт по этапам до «Выполнено» или «Отказ»."""

    class Stage(models.TextChoices):
        NEW = "new", "Новые"
        CONTACT = "contact", "Связались"
        OFFER = "offer", "Счёт / КП"
        ORDER = "order", "Заказ"
        WON = "won", "Выполнено"
        LOST = "lost", "Отказ"

    class Source(models.TextChoices):
        ORDER = "order", "Заказ с сайта"
        LIST = "list", "Заказ по списку"
        CALLBACK = "callback", "Обратный звонок"
        B2B = "b2b", "Оптовые цены"
        PHONE = "phone", "Звонок"
        STORE = "store", "Магазин"
        OTHER = "other", "Другое"

    OPEN = (Stage.NEW, Stage.CONTACT, Stage.OFFER, Stage.ORDER)
    CLOSED = (Stage.WON, Stage.LOST)

    client = models.ForeignKey(Client, verbose_name="Клиент", on_delete=models.PROTECT, related_name="deals")
    title = models.CharField("Суть", max_length=200)
    source = models.CharField("Источник", max_length=10, choices=Source.choices, default=Source.OTHER)
    stage = models.CharField("Этап", max_length=10, choices=Stage.choices, default=Stage.NEW, db_index=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Менеджер", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="crm_deals")
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2, default=Decimal("0"))
    lost_reason = models.CharField("Причина отказа", max_length=200, blank=True)

    order = models.OneToOneField("orders.Order", verbose_name="Заказ", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="deal")
    lead = models.OneToOneField("orders.Lead", verbose_name="Заявка", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="deal")
    profile = models.ForeignKey("accounts.Profile", verbose_name="Запрос оптовых цен", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="deals")

    created_at = models.DateTimeField("Создано", default=timezone.now, db_index=True)
    first_touch_at = models.DateTimeField("Первый ответ", null=True, blank=True,
                                          help_text="Когда менеджер впервые что-то сделал по обращению")
    closed_at = models.DateTimeField("Закрыто", null=True, blank=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Обращение"
        verbose_name_plural = "Обращения"
        ordering = ["-created_at"]
        permissions = [("use_crm", "Работа в CRM"), ("view_reports", "Отчёты CRM")]

    def __str__(self):
        return f"{self.number} {self.title}"

    def get_absolute_url(self):
        return reverse("crm:deal", args=[self.pk])

    @property
    def number(self):
        return f"О-{self.pk:05d}" if self.pk else "О-новое"

    @property
    def is_open(self):
        return self.stage in self.OPEN


class Task(models.Model):
    """Дело менеджера со сроком: «перезвонить завтра в 10», «отправить счёт»."""

    deal = models.ForeignKey(Deal, verbose_name="Обращение", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="tasks")
    client = models.ForeignKey(Client, verbose_name="Клиент", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="tasks")
    title = models.CharField("Что сделать", max_length=200)
    due_at = models.DateTimeField("Срок", db_index=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Исполнитель", null=True,
                                 on_delete=models.SET_NULL, related_name="crm_tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Поставил", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    done_at = models.DateTimeField("Выполнена", null=True, blank=True)
    reminded_at = models.DateTimeField("Напоминание отправлено", null=True, blank=True, editable=False)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["done_at", "due_at"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return self.done_at is None and self.due_at < timezone.now()


class Activity(models.Model):
    """Лента обращения и клиента: заметки менеджеров и события (новый этап, статус из 1С, задача выполнена)."""

    class Kind(models.TextChoices):
        NOTE = "note", "Заметка"
        CALL = "call", "Звонок"
        STAGE = "stage", "Этап"
        SYSTEM = "system", "Событие"
        TASK = "task", "Задача"

    deal = models.ForeignKey(Deal, verbose_name="Обращение", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="activities")
    client = models.ForeignKey(Client, verbose_name="Клиент", on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.NOTE)
    text = models.TextField("Текст")
    stage = models.CharField("Новый этап", max_length=10, choices=Deal.Stage.choices, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Автор", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField("Когда", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Событие"
        verbose_name_plural = "Лента"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.text[:60]
