"""Проверка справочников доставки от 1С. Формат — docs/api.md, POST /api/v1/delivery/."""
from decimal import Decimal

from rest_framework import serializers


class ZoneInSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    sort = serializers.IntegerField(min_value=0, required=False)


class TruckInSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(max_length=150)
    capacity_t = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0.001"))
    volume_m3 = serializers.DecimalField(max_digits=7, decimal_places=3, min_value=0, required=False, default=0)


class TariffInSerializer(serializers.Serializer):
    zone_id = serializers.UUIDField()
    truck_id = serializers.UUIDField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class DeliveryUploadSerializer(serializers.Serializer):
    zones = ZoneInSerializer(many=True)
    trucks = TruckInSerializer(many=True)
    tariffs = TariffInSerializer(many=True)
