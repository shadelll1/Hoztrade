"""API обмена заказами и заявками. Контракт — docs/api.md.

1С забирает новые заказы и заявки (GET .../new/), создаёт у себя документы и подтверждает получение
(POST .../ack/). Пока подтверждения нет, объект отдаётся снова — так ничего не теряется при сбое
посередине. Статусы заказов 1С присылает отдельно (POST orders/status/).
"""
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response

from orders import emails
from orders.models import Lead, Order

from .views import ExchangeView

BATCH = 100


def _num(value):
    return float(value) if value is not None else None


def order_to_json(order):
    return {
        "id": order.pk,
        "number": order.number,
        "created_at": timezone.localtime(order.created_at).isoformat(),
        "customer": {
            "type": order.customer_type,
            "name": order.name,
            "phone": order.phone,
            "email": order.email,
            "company": order.company,
            "inn": order.inn,
        },
        "delivery": _delivery_json(order),
        "comment": order.comment,
        "price_type": order.price_type,
        "total": _num(order.total),
        "weight_kg": _num(order.weight_kg),
        "volume_m3": _num(order.volume_m3),
        "items": [
            {
                "product_id": str(i.product_ext_id) if i.product_ext_id else None,
                "sku": i.sku,
                "name": i.name,
                "unit": i.unit,
                "quantity": _num(i.quantity),
                "price": _num(i.price),
                "amount": _num(i.amount),
            }
            for i in order.items.all()
        ],
    }


def _delivery_json(order):
    time_from, time_to = order.interval_times
    zone = order.zone
    return {
        "method": order.delivery,
        "store": order.pickup_store,
        "address": order.address,
        "date": order.delivery_date.isoformat() if order.delivery_date else None,
        "time_from": time_from,
        "time_to": time_to,
        "zone_id": str(zone.ext_id) if zone is not None and zone.ext_id else None,
        "zone": zone.name if zone is not None else "",
        "truck_t": _num(order.truck_t),
        "truck": order.truck_name,
        "trips": order.trips if order.delivery == Order.Delivery.TRUCK else 0,
        "cost": _num(order.delivery_cost),
    }


def lead_to_json(request, lead):
    file = None
    if lead.attachment:
        file = {
            "name": lead.attachment.name.rsplit("/", 1)[-1],
            "url": request.build_absolute_uri(reverse("exchange:lead_file", args=[lead.pk])),
        }
    return {
        "id": lead.pk,
        "kind": lead.kind,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "text": lead.text,
        "created_at": timezone.localtime(lead.created_at).isoformat(),
        "file": file,
    }


class AckItem(serializers.Serializer):
    id = serializers.IntegerField()
    ext_id = serializers.UUIDField(required=False, allow_null=True)
    ext_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class StatusItem(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=Order.Status.choices)
    status_text = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    ext_number = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    total = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)


def _ack(model, items):
    now = timezone.now()
    done = 0
    for item in items:
        updated = model.objects.filter(pk=item["id"]).update(
            exported_at=now, ext_id=item.get("ext_id"), ext_number=item.get("ext_number", ""),
        )
        done += updated
    return done


class NewOrdersView(ExchangeView):
    def get(self, request):
        orders = Order.objects.filter(exported_at__isnull=True).prefetch_related("items").order_by("pk")[:BATCH]
        return Response({"orders": [order_to_json(o) for o in orders]})


class OrdersAckView(ExchangeView):
    def post(self, request):
        s = AckItem(data=request.data.get("orders", []), many=True)
        if not s.is_valid():
            return Response({"errors": s.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"acknowledged": _ack(Order, s.validated_data)})


class OrdersStatusView(ExchangeView):
    def post(self, request):
        s = StatusItem(data=request.data.get("orders", []), many=True)
        if not s.is_valid():
            return Response({"errors": s.errors}, status=status.HTTP_400_BAD_REQUEST)
        orders = Order.objects.in_bulk([item["id"] for item in s.validated_data])
        updated = 0
        for item in s.validated_data:
            order = orders.get(item["id"])
            if order is None:
                continue
            status_changed = order.status != item["status"]
            order.status = item["status"]
            order.status_text = item["status_text"]
            if item["ext_number"]:
                order.ext_number = item["ext_number"]
            if item.get("total") is not None:
                order.total_1c = item["total"]
            order.save(update_fields=["status", "status_text", "ext_number", "total_1c", "updated_at"])
            updated += 1
            if status_changed:
                emails.status_changed(order, request)
        return Response({"updated": updated})


class NewLeadsView(ExchangeView):
    def get(self, request):
        leads = Lead.objects.filter(exported_at__isnull=True).order_by("pk")[:BATCH]
        return Response({"leads": [lead_to_json(request, lead) for lead in leads]})


class LeadsAckView(ExchangeView):
    def post(self, request):
        s = AckItem(data=request.data.get("leads", []), many=True)
        if not s.is_valid():
            return Response({"errors": s.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"acknowledged": _ack(Lead, s.validated_data)})


class LeadFileView(ExchangeView):
    """Файл заявки (смета, фото) — только для 1С, по токену обмена."""

    def get(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)
        if not lead.attachment:
            raise Http404
        return FileResponse(lead.attachment.open("rb"), as_attachment=True,
                            filename=lead.attachment.name.rsplit("/", 1)[-1])
