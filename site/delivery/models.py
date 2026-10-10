"""Доставка грузотакси: зоны, машины и тарифы. Ведутся в 1С и приходят с обменом (docs/api.md)."""
from decimal import Decimal

from django.db import models


class Zone(models.Model):
    """Зона доставки — справочник 1С «Зоны и тарифы доставки»."""

    ext_id = models.UUIDField("ID в 1С", unique=True, null=True, blank=True)
    name = models.CharField("Наименование", max_length=100)
    description = models.CharField("Описание", max_length=300, blank=True)
    sort = models.PositiveIntegerField("Порядок", default=500)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "Зона доставки"
        verbose_name_plural = "Зоны доставки"
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name


class Truck(models.Model):
    """Машина грузотакси — справочник 1С «Транспортные средства»."""

    ext_id = models.UUIDField("ID в 1С", unique=True, null=True, blank=True)
    name = models.CharField("Наименование", max_length=150)
    capacity_t = models.DecimalField("Грузоподъёмность, т", max_digits=6, decimal_places=3)
    # 0 — объём кузова не указан, машина подбирается только по весу.
    volume_m3 = models.DecimalField("Объём кузова, м³", max_digits=7, decimal_places=3, default=Decimal("0"))
    is_active = models.BooleanField("В работе", default=True)

    class Meta:
        verbose_name = "Машина"
        verbose_name_plural = "Автопарк"
        ordering = ["capacity_t", "name"]

    def __str__(self):
        return self.name

    @property
    def capacity_kg(self):
        return self.capacity_t * 1000


class Tariff(models.Model):
    """Стоимость одного рейса машины в зону."""

    zone = models.ForeignKey(Zone, verbose_name="Зона", on_delete=models.CASCADE, related_name="tariffs")
    truck = models.ForeignKey(Truck, verbose_name="Машина", on_delete=models.CASCADE, related_name="tariffs")
    price = models.DecimalField("Стоимость рейса", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"
        ordering = ["zone__sort", "truck__capacity_t"]
        constraints = [models.UniqueConstraint(fields=["zone", "truck"], name="delivery_tariff_zone_truck")]

    def __str__(self):
        return f"{self.zone} — {self.truck}: {self.price}"
