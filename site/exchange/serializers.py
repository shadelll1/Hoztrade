"""Проверка входящих данных от 1С. Формат — docs/api.md."""
from rest_framework import serializers


class CategoryInSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True, required=False)
    name = serializers.CharField(max_length=150)
    sort = serializers.IntegerField(min_value=0, required=False)


class ProductInSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    category_id = serializers.UUIDField(allow_null=True, required=False)
    sku = serializers.CharField(max_length=50, allow_blank=True, required=False, default="")
    name = serializers.CharField(max_length=150)
    full_name = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    unit = serializers.CharField(max_length=25, allow_blank=True, required=False, default="")
    weight_kg = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False, default=0)
    volume_m3 = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=0, required=False, default=0)


class PriceInSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    retail = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    wholesale = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, allow_null=True, required=False)


class StockInSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)


class CatalogUploadSerializer(serializers.Serializer):
    full = serializers.BooleanField(required=False, default=False)
    categories = CategoryInSerializer(many=True, required=False, default=list)
    products = ProductInSerializer(many=True, required=False, default=list)
    prices = PriceInSerializer(many=True, required=False, default=list)
    stock = StockInSerializer(many=True, required=False, default=list)
