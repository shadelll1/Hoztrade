import io
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Product
from delivery.demo_data import demo_payload
from delivery.models import Tariff, Truck, Zone
from delivery.services import pick_truck, quote
from orders.models import Order

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def setup(settings):
    settings.EXCHANGE_TOKEN = TOKEN
    cache.clear()


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())


@pytest.fixture
def api():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {TOKEN}")
    return client


def zone(name="Чебоксары"):
    return Zone.objects.get(name=name)


@pytest.mark.django_db
class TestPickTruck:
    def test_smallest_that_fits(self, demo):
        trucks = list(Truck.objects.order_by("capacity_t"))
        assert pick_truck(trucks, Decimal("1500"), Decimal("0"))[0].capacity_t == Decimal("1.5")
        assert pick_truck(trucks, Decimal("1501"), Decimal("0"))[0].capacity_t == 3

    def test_volume_matters(self, demo):
        # Лёгкий, но объёмный груз (утеплитель): 300 кг, 20 м³ — ГАЗели (9 м³) и ГАЗону (18 м³) не влезет
        truck, trips = pick_truck(list(Truck.objects.order_by("capacity_t")), Decimal("300"), Decimal("20"))
        assert truck.capacity_t == 5 and trips == 1

    def test_several_trips_on_biggest(self, demo):
        truck, trips = pick_truck(list(Truck.objects.order_by("capacity_t")), Decimal("45000"), Decimal("0"))
        assert truck.capacity_t == 20 and trips == 3

    def test_quote_cost(self, demo):
        q = quote(zone("Новочебоксарск"), Decimal("4200"), Decimal("3"))
        assert q.truck.capacity_t == 5 and q.price == 2200 and q.cost == 2200
        assert quote(zone(), Decimal("45000"), Decimal("0")).cost == 3 * 4500

    def test_zone_without_small_truck(self, demo):
        Tariff.objects.filter(zone=zone(), truck__capacity_t__lt=5).delete()
        q = quote(zone(), Decimal("100"), Decimal("0"))
        assert q.truck.capacity_t == 5 and q.cost == 1800


@pytest.mark.django_db
class TestDeliveryApi:
    def test_requires_token(self, db):
        assert APIClient().post("/api/v1/delivery/", demo_payload(), format="json").status_code == 401

    def test_full_replace(self, api, demo):
        payload = demo_payload()
        payload["zones"] = payload["zones"][:2]
        payload["trucks"] = payload["trucks"][:3]
        payload["tariffs"].append(dict(payload["tariffs"][0], price=999))  # дубль — побеждает последний
        r = api.post("/api/v1/delivery/", payload, format="json")
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["zones"] == 2 and body["tariffs"] == 6 and body["disabled"] == {"zones": 2, "trucks": 2}
        assert Zone.objects.filter(is_active=True).count() == 2
        assert Tariff.objects.get(zone=zone(), truck__capacity_t=Decimal("1.5")).price == 999

    def test_validation(self, api, db):
        payload = demo_payload()
        payload["trucks"][0]["capacity_t"] = 0
        assert api.post("/api/v1/delivery/", payload, format="json").status_code == 400


def checkout(client, **extra):
    cement = Product.objects.get(sku="ЦМ-500-50")
    client.post(f"/cart/add/{cement.pk}/", {"quantity": extra.pop("quantity", 2)})
    data = {"customer_type": "person", "name": "Иван", "phone": "+79001234567", "delivery": "truck",
            "zone": zone().pk, "address": "Чебоксары, ул. Ленина, 1", "consent": "on"}
    data.update(extra)
    return client.post("/checkout/", data)


@pytest.mark.django_db
class TestCheckoutDelivery:
    def test_zone_required_for_truck(self, client, demo):
        r = checkout(client, zone="")
        assert r.status_code == 200 and "zone" in r.context["form"].errors

    def test_cost_from_server_not_form(self, client, demo):
        checkout(client, zone=zone("Межгород до 60 км").pk, delivery_cost="1", quantity=100)  # 5 т
        order = Order.objects.get()
        assert order.truck_t == 5 and order.delivery_cost == 4200

    def test_pickup_ignores_zone(self, client, demo):
        checkout(client, delivery="pickup", store="Складской проезд, 6, склад 41")
        order = Order.objects.get()
        assert order.zone is None and order.delivery_cost is None and order.grand_total == order.total

    def test_past_date_rejected(self, client, demo):
        yesterday = timezone.localdate() - timedelta(days=1)
        r = checkout(client, delivery_date=yesterday.isoformat())
        assert "delivery_date" in r.context["form"].errors

    def test_without_tariffs_manager_prices(self, client, demo):
        Tariff.objects.all().delete()
        checkout(client, zone="")
        order = Order.objects.get()
        assert order.delivery_cost is None and order.truck_t == Decimal("1.5")
        page = client.get(order.get_absolute_url()).content.decode()
        assert "назовёт менеджер" in page

    def test_checkout_page_shows_zone_prices(self, client, demo):
        cement = Product.objects.get(sku="ЦМ-500-50")
        client.post(f"/cart/add/{cement.pk}/", {"quantity": 2})
        body = client.get("/checkout/").content.decode()
        assert "Новочебоксарск" in body and 'data-cost="1100' in body


@pytest.mark.django_db
def test_delivery_page(client, demo):
    r = client.get("/delivery/")
    body = r.content.decode()
    assert r.status_code == 200 and "Межгород до 60 км" in body and "delivery-calc-data" in body
    assert len(r.context["rows"]) == 4 and len(r.context["trucks"]) == 5


@pytest.mark.django_db
def test_demo_ids_are_stable(demo):
    before = set(Zone.objects.values_list("ext_id", flat=True))
    call_command("load_demo_catalog", stdout=io.StringIO())
    assert set(Zone.objects.values_list("ext_id", flat=True)) == before
    assert all(isinstance(z, uuid.UUID) for z in before)
