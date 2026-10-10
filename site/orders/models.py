import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse

from catalog.models import Product


class ExchangeFields(models.Model):
    """Поля обмена с 1С: когда 1С забрала объект, что создала у себя и какой там статус."""

    ext_id = models.UUIDField("ID в 1С", null=True, blank=True, editable=False)
    ext_number = models.CharField("Номер в 1С", max_length=30, blank=True, editable=False)
    exported_at = models.DateTimeField("Получен 1С", null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    @property
    def in_1c(self):
        return self.exported_at is not None


class Order(ExchangeFields):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        ACCEPTED = "accepted", "Принят в работу"
        CONFIRMED = "confirmed", "Подтверждён"
        SHIPPING = "shipping", "Передан в доставку"
        DONE = "done", "Выполнен"
        CANCELED = "canceled", "Отменён"

    class CustomerType(models.TextChoices):
        PERSON = "person", "Частное лицо"
        COMPANY = "company", "Организация или ИП"

    class Delivery(models.TextChoices):
        PICKUP = "pickup", "Самовывоз"
        TRUCK = "truck", "Доставка грузотакси"

    token = models.UUIDField("Ключ доступа", default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Пользователь", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="orders")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    status_text = models.CharField("Состояние в 1С", max_length=100, blank=True)

    customer_type = models.CharField("Покупатель", max_length=10, choices=CustomerType.choices,
                                     default=CustomerType.PERSON)
    name = models.CharField("Контактное лицо", max_length=150)
    phone = models.CharField("Телефон", max_length=20, help_text="В формате +7XXXXXXXXXX")
    email = models.EmailField("Email", blank=True)
    company = models.CharField("Организация", max_length=250, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True)

    delivery = models.CharField("Получение", max_length=10, choices=Delivery.choices, default=Delivery.PICKUP)
    pickup_store = models.CharField("Пункт самовывоза", max_length=250, blank=True)
    address = models.CharField("Адрес доставки", max_length=500, blank=True)
    delivery_date = models.DateField("Желаемая дата", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True)

    total = models.DecimalField("Сумма", max_digits=14, decimal_places=2, default=Decimal("0"))
    # Итог из 1С: учитывает скидки и акции, которые настроены в учётной системе, а не на сайте.
    total_1c = models.DecimalField("Сумма в 1С", max_digits=14, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField("Вес, кг", max_digits=12, decimal_places=3, default=Decimal("0"))
    truck_t = models.DecimalField("Машина, т", max_digits=5, decimal_places=1, null=True, blank=True)

    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ {self.number}"

    @property
    def number(self):
        return f"Х-{self.pk:06d}" if self.pk else "Х-новый"

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.token])

    @property
    def discount(self):
        """Скидка, которую дала 1С (разница с суммой на сайте)."""
        if self.total_1c is None or self.total_1c >= self.total:
            return None
        return self.total - self.total_1c


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, verbose_name="Товар", null=True, on_delete=models.SET_NULL)
    # Снимок на момент заказа: товар могут переименовать или снять с публикации.
    product_ext_id = models.UUIDField("ID товара в 1С", null=True)
    sku = models.CharField("Артикул", max_length=50, blank=True)
    name = models.CharField("Наименование", max_length=500)
    unit = models.CharField("Единица", max_length=25)
    price = models.DecimalField("Цена", max_digits=14, decimal_places=2)
    quantity = models.DecimalField("Количество", max_digits=14, decimal_places=3)
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Строка заказа"
        verbose_name_plural = "Товары заказа"

    def __str__(self):
        return self.name


class Lead(ExchangeFields):
    """Заявка с сайта. В 1С становится лидом."""

    class Kind(models.TextChoices):
        CALLBACK = "callback", "Обратный звонок"
        LIST = "list", "Заказ по списку"

    kind = models.CharField("Тип", max_length=10, choices=Kind.choices)
    name = models.CharField("Имя", max_length=150)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("Email", blank=True)
    text = models.TextField("Что нужно", blank=True)
    attachment = models.FileField("Файл", upload_to="leads/%Y/%m/", blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"
