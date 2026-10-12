"""Расчёт доставки и загрузка справочников доставки из 1С."""
import math
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Min, Q

from .models import Tariff, Truck, Zone

ZERO = Decimal("0")


@dataclass(frozen=True)
class Quote:
    """Расчёт доставки заказа: какая машина, сколько рейсов и сколько стоит."""

    zone: Zone
    truck: Truck
    trips: int
    price: Decimal  # за рейс

    @property
    def cost(self):
        return self.price * self.trips


def trips_needed(truck, weight_kg, volume_m3):
    """Сколько рейсов нужно машине, чтобы увезти груз (по весу и, если известен объём кузова, по объёму)."""
    trips = math.ceil(weight_kg / truck.capacity_kg) if weight_kg > 0 else 1
    if truck.volume_m3 > 0 and volume_m3 > 0:
        trips = max(trips, math.ceil(volume_m3 / truck.volume_m3))
    return max(trips, 1)


def pick_truck(trucks, weight_kg, volume_m3):
    """Наименьшая машина, которая увезёт груз за один рейс; если такой нет — самая большая в несколько рейсов.

    trucks — машины по возрастанию грузоподъёмности. Возвращает (машина, рейсов) или (None, 0).
    """
    for truck in trucks:
        if trips_needed(truck, weight_kg, volume_m3) == 1:
            return truck, 1
    if not trucks:
        return None, 0
    biggest = trucks[-1]
    return biggest, trips_needed(biggest, weight_kg, volume_m3)


def fleet():
    """Машины в работе по возрастанию грузоподъёмности."""
    return list(Truck.objects.filter(is_active=True).order_by("capacity_t", "name"))


def fleet_with_prices():
    """Машины в работе с самым дешёвым рейсом (min_price) по действующим зонам — для витрины автопарка."""
    in_zone = Q(tariffs__zone__is_active=True)
    return list(Truck.objects.filter(is_active=True)
                .annotate(min_price=Min("tariffs__price", filter=in_zone)).order_by("capacity_t", "name"))


def zones():
    """Зоны, в которые есть хотя бы один тариф."""
    return list(Zone.objects.filter(is_active=True, tariffs__truck__is_active=True).distinct())


def _tariffs():
    """Тарифы действующих машин: {id зоны: {id машины: цена}} — один запрос."""
    result = {}
    rows = Tariff.objects.filter(truck__is_active=True).values_list("zone_id", "truck_id", "price")
    for zone_id, truck_id, price in rows:
        result.setdefault(zone_id, {})[truck_id] = price
    return result


def _quote(zone, prices, trucks, weight_kg, volume_m3):
    truck, trips = pick_truck([t for t in trucks if t.pk in prices], Decimal(weight_kg), Decimal(volume_m3))
    if truck is None:
        return None
    return Quote(zone=zone, truck=truck, trips=trips, price=prices[truck.pk])


def quote(zone, weight_kg, volume_m3):
    """Расчёт доставки в зону. None — в зону не возим (нет тарифов)."""
    return _quote(zone, _tariffs().get(zone.pk, {}), fleet(), weight_kg, volume_m3)


def quotes(weight_kg, volume_m3, trucks=None):
    """Расчёт для всех зон: {zone_id: Quote}. Три запроса на любое число зон."""
    trucks = fleet() if trucks is None else trucks
    tariffs = _tariffs()
    result = {}
    for zone in zones():
        q = _quote(zone, tariffs.get(zone.pk, {}), trucks, weight_kg, volume_m3)
        if q is not None:
            result[zone.pk] = q
    return result


def tariff_table():
    """Таблица тарифов для страницы «Доставка»: (машины, [(зона, [цена или None по машинам])])."""
    trucks = fleet()
    prices = {(t.zone_id, t.truck_id): t.price for t in Tariff.objects.filter(truck__is_active=True)}
    rows = [(z, [prices.get((z.pk, t.pk)) for t in trucks]) for z in zones()]
    return trucks, rows


@transaction.atomic
def import_delivery(data):
    """Полная загрузка зон, машин и тарифов из 1С (данные DeliveryUploadSerializer).

    Зоны и машины upsert по ID 1С; которых нет в посылке — выключаются (на них ссылаются заказы).
    Тарифы заменяются целиком.
    """
    zone_ids = [z["id"] for z in data["zones"]]
    truck_ids = [t["id"] for t in data["trucks"]]

    for n, item in enumerate(data["zones"], start=1):
        Zone.objects.update_or_create(ext_id=item["id"], defaults={
            "name": item["name"], "description": item.get("description", ""),
            "sort": item.get("sort", n * 10), "is_active": True,
        })
    for item in data["trucks"]:
        Truck.objects.update_or_create(ext_id=item["id"], defaults={
            "name": item["name"], "capacity_t": item["capacity_t"],
            "volume_m3": item.get("volume_m3") or ZERO, "is_active": True,
        })
    off_zones = Zone.objects.filter(is_active=True).exclude(ext_id__in=zone_ids).update(is_active=False)
    off_trucks = Truck.objects.filter(is_active=True).exclude(ext_id__in=truck_ids).update(is_active=False)

    zones_by_id = dict(Zone.objects.filter(ext_id__in=zone_ids).values_list("ext_id", "pk"))
    trucks_by_id = dict(Truck.objects.filter(ext_id__in=truck_ids).values_list("ext_id", "pk"))
    prices = {
        (zones_by_id[t["zone_id"]], trucks_by_id[t["truck_id"]]): t["price"]
        for t in data["tariffs"]
        if t["zone_id"] in zones_by_id and t["truck_id"] in trucks_by_id
    }
    Tariff.objects.all().delete()
    tariffs = Tariff.objects.bulk_create(
        [Tariff(zone_id=z, truck_id=t, price=price) for (z, t), price in prices.items()]
    )
    return {"zones": len(zone_ids), "trucks": len(truck_ids), "tariffs": len(tariffs),
            "disabled": {"zones": off_zones, "trucks": off_trucks}}
