import io
import uuid

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APIClient

from catalog.models import Product
from orders.forms import inn_is_valid, normalize_phone
from orders.models import Lead, Order

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


def checkout_data(**extra):
    data = {"customer_type": "person", "name": "Иван", "phone": "8 (900) 123-45-67", "email": "",
            "delivery": "truck", "address": "Чебоксары, ул. Ленина, 1", "store": "",
            "comment": "", "consent": "on", "website": ""}
    data.update(extra)
    return data


def test_phone_and_inn():
    assert normalize_phone("8 (900) 123-45-67") == "+79001234567"
    assert normalize_phone("+7 900 1234567") == "+79001234567"
    assert inn_is_valid("7707083893")          # Сбербанк
    assert not inn_is_valid("7707083890")
    assert inn_is_valid("500100732259")        # корректный ИНН физлица/ИП
    assert not inn_is_valid("12345")


@pytest.mark.django_db
class TestCartAndCheckout:
    def test_add_update_remove(self, client, demo):
        cement = Product.objects.get(sku="ЦМ-500-50")
        client.post(f"/cart/add/{cement.pk}/", {"quantity": 3})
        r = client.get("/cart/")
        assert r.context["cart"].total == 3 * cement.price_retail
        assert r.context["cart"].truck == 1.5  # 150 кг
        client.post(f"/cart/update/{cement.pk}/", {"quantity": 40})  # 2 т
        assert client.get("/cart/").context["cart"].truck == 3
        client.post(f"/cart/remove/{cement.pk}/")
        assert not client.get("/cart/").context["cart"].lines

    def test_add_via_fetch_returns_count(self, client, demo):
        p = Product.objects.first()
        r = client.post(f"/cart/add/{p.pk}/", HTTP_X_REQUESTED_WITH="fetch")
        assert r.json()["count"] == 1

    def test_checkout_creates_order_snapshot(self, client, demo):
        cement = Product.objects.get(sku="ЦМ-500-50")
        client.post(f"/cart/add/{cement.pk}/", {"quantity": 2})
        r = client.post("/checkout/", checkout_data())
        order = Order.objects.get()
        assert r.status_code == 302 and str(order.token) in r["Location"]
        assert order.phone == "+79001234567"
        assert order.total == 2 * cement.price_retail and order.truck_t == 1.5
        item = order.items.get()
        assert item.product_ext_id == cement.ext_id and item.quantity == 2
        assert client.get("/cart/").context["cart"].lines == []
        assert client.get(order.get_absolute_url()).status_code == 200

    def test_company_requires_valid_inn(self, client, demo):
        client.post(f"/cart/add/{Product.objects.first().pk}/")
        r = client.post("/checkout/", checkout_data(customer_type="company", company="ООО Ромашка", inn="1234567890"))
        assert r.status_code == 200 and "inn" in r.context["form"].errors
        r = client.post("/checkout/", checkout_data(customer_type="company", company="ООО Ромашка", inn="7707083893"))
        assert r.status_code == 302

    def test_consent_and_honeypot(self, client, demo):
        client.post(f"/cart/add/{Product.objects.first().pk}/")
        assert "consent" in client.post("/checkout/", checkout_data(consent="")).context["form"].errors
        assert client.post("/checkout/", checkout_data(website="http://spam")).status_code == 200
        assert not Order.objects.exists()

    def test_empty_cart_redirects(self, client, db):
        assert client.get("/checkout/").status_code == 302


@pytest.mark.django_db
class TestLeads:
    def test_order_list_with_file(self, client, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        f = SimpleUploadedFile("smeta.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = client.post("/order-list/", {"name": "Пётр", "phone": "+79001112233", "text": "",
                                         "attachment": f, "consent": "on"})
        assert r.status_code == 302
        lead = Lead.objects.get()
        assert lead.kind == "list" and lead.attachment.name.endswith(".pdf")

    def test_order_list_needs_text_or_file(self, client, db):
        r = client.post("/order-list/", {"name": "Пётр", "phone": "+79001112233", "consent": "on"})
        assert r.status_code == 200 and not Lead.objects.exists()

    def test_bad_file_type(self, client, db):
        f = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        r = client.post("/order-list/", {"name": "Пётр", "phone": "+79001112233", "attachment": f, "consent": "on"})
        assert "attachment" in r.context["form"].errors

    def test_callback_fetch(self, client, db):
        r = client.post("/callback/", {"name": "Анна", "phone": "89005556677", "consent": "on"},
                        HTTP_X_REQUESTED_WITH="fetch")
        assert r.json()["ok"] and Lead.objects.get().kind == "callback"

    def test_throttle(self, client, db):
        for _ in range(5):
            client.post("/callback/", {"name": "Анна", "phone": "89005556677", "consent": "on"})
        client.post("/callback/", {"name": "Анна", "phone": "89005556677", "consent": "on"})
        assert Lead.objects.count() == 5


@pytest.mark.django_db
class TestExchangeOrders:
    def make_order(self, client):
        p = Product.objects.get(sku="ЦМ-500-50")
        client.post(f"/cart/add/{p.pk}/", {"quantity": 2})
        client.post("/checkout/", checkout_data())
        return Order.objects.latest("pk")

    def test_new_ack_status_cycle(self, client, api, demo):
        order = self.make_order(client)
        data = api.get("/api/v1/orders/new/").json()["orders"]
        assert [o["id"] for o in data] == [order.pk]
        assert data[0]["customer"]["phone"] == "+79001234567"
        assert data[0]["items"][0]["product_id"] == str(order.items.get().product_ext_id)

        ext = str(uuid.uuid4())
        r = api.post("/api/v1/orders/ack/", {"orders": [{"id": order.pk, "ext_id": ext, "ext_number": "УТ-00012"}]},
                     format="json")
        assert r.json()["acknowledged"] == 1
        assert api.get("/api/v1/orders/new/").json()["orders"] == []

        r = api.post("/api/v1/orders/status/", {"orders": [{"id": order.pk, "status": "confirmed",
                                                             "status_text": "В работе"}]}, format="json")
        assert r.json()["updated"] == 1
        order.refresh_from_db()
        assert order.status == "confirmed" and order.ext_number == "УТ-00012" and order.in_1c

    def test_status_validation(self, api, db):
        r = api.post("/api/v1/orders/status/", {"orders": [{"id": 1, "status": "bogus"}]}, format="json")
        assert r.status_code == 400

    def test_leads_and_file(self, api, client, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        client.post("/order-list/", {"name": "Пётр", "phone": "+79001112233", "text": "Цемент 10 мешков",
                                     "attachment": SimpleUploadedFile("s.txt", b"list"), "consent": "on"})
        leads = api.get("/api/v1/leads/new/").json()["leads"]
        assert leads[0]["text"] == "Цемент 10 мешков" and leads[0]["file"]["name"].endswith(".txt")
        r = api.get(leads[0]["file"]["url"].replace("http://testserver", ""))
        assert r.status_code == 200 and b"".join(r.streaming_content) == b"list"
        assert APIClient().get(leads[0]["file"]["url"].replace("http://testserver", "")).status_code == 401
        api.post("/api/v1/leads/ack/", {"leads": [{"id": leads[0]["id"], "ext_number": "000123"}]}, format="json")
        assert api.get("/api/v1/leads/new/").json()["leads"] == []
