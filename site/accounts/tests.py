import io

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import Profile
from catalog.models import Product
from orders.models import Order

TOKEN = "test-token"
PASSWORD = "Kirpich-2026!"
User = get_user_model()


@pytest.fixture(autouse=True)
def setup(settings):
    settings.EXCHANGE_TOKEN = TOKEN
    cache.clear()


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())


def register(client, email="buyer@example.com", **extra):
    data = {"name": "Иван", "email": email, "phone": "8 900 111-22-33", "password1": PASSWORD,
            "password2": PASSWORD, "consent": "on", "website": ""}
    data.update(extra)
    return client.post("/account/register/", data)


def company_user(client, status=Profile.Wholesale.APPROVED):
    register(client, email="snab@stroy.ru")
    profile = Profile.objects.get(user__username="snab@stroy.ru")
    profile.company, profile.inn, profile.wholesale = "ООО «СтройТест»", "7707083893", status
    profile.save()
    return profile


def checkout(client, **extra):
    data = {"customer_type": "person", "name": "Иван", "phone": "+79001112233", "email": "", "delivery": "pickup",
            "store": "Складской проезд, 6, склад 41", "address": "", "comment": "", "consent": "on", "website": ""}
    data.update(extra)
    return client.post("/checkout/", data)


@pytest.mark.django_db
class TestAccount:
    def test_register_login_logout(self, client):
        r = register(client, email="Buyer@Example.com")
        assert r.status_code == 302 and r["Location"] == "/account/"
        user = User.objects.get()
        assert user.username == "buyer@example.com" and user.profile.phone == "+79001112233"
        assert client.get("/account/").status_code == 200

        client.post("/account/logout/")
        assert client.get("/account/").status_code == 302
        r = client.post("/account/login/", {"username": "BUYER@example.com", "password": PASSWORD})
        assert r.status_code == 302
        assert client.get("/account/").context["user"].is_authenticated

    def test_register_validation(self, client):
        register(client)
        client.post("/account/logout/")
        r = register(client)  # тот же email
        assert "email" in r.context["form"].errors
        r = register(client, email="other@example.com", password2="другой")
        assert "password2" in r.context["form"].errors
        r = register(client, email="third@example.com", password1="12345678", password2="12345678")
        assert "password1" in r.context["form"].errors
        assert User.objects.count() == 1

    def test_order_history_and_repeat(self, client, demo):
        register(client)
        cement = Product.objects.get(sku="ЦМ-500-50")
        client.post(f"/cart/add/{cement.pk}/", {"quantity": 3})
        assert checkout(client).status_code == 302
        order = Order.objects.get()
        assert order.user.username == "buyer@example.com" and order.price_type == "retail"

        page = client.get("/account/")
        assert list(page.context["orders"]) == [order]

        client.post(f"/account/orders/{order.token}/repeat/")
        cart = client.get("/cart/").context["cart"]
        assert [(line.product, line.quantity) for line in cart.lines] == [(cement, 3)]

    def test_cannot_repeat_foreign_order(self, client, demo):
        register(client)
        client.post(f"/cart/add/{Product.objects.first().pk}/")
        checkout(client)
        order = Order.objects.get()
        client.post("/account/logout/")
        register(client, email="other@example.com")
        assert client.post(f"/account/orders/{order.token}/repeat/").status_code == 404

    def test_checkout_prefilled_from_profile(self, client, demo):
        register(client)
        client.post(f"/cart/add/{Product.objects.first().pk}/")
        form = client.get("/checkout/").context["form"]
        assert form.initial["phone"] == "+79001112233" and form.initial["email"] == "buyer@example.com"


@pytest.mark.django_db
class TestWholesale:
    def test_request_and_notify(self, client, settings):
        settings.MANAGERS = [("Менеджер", "m@example.com")]
        register(client)
        r = client.post("/account/wholesale/", {"company": "ООО Ромашка", "inn": "1234567890"})
        assert r.status_code == 400 and "inn" in r.context["wholesale_form"].errors
        client.post("/account/wholesale/", {"company": "ООО Ромашка", "inn": "7707083893"})
        profile = Profile.objects.get()
        assert profile.wholesale == "pending" and profile.inn == "7707083893"
        assert "оптовые цены" in mail.outbox[-1].subject
        assert not profile.is_wholesale

    def test_pending_company_sees_retail(self, client, demo):
        company_user(client, status=Profile.Wholesale.PENDING)
        cement = Product.objects.get(sku="ЦМ-500-50")
        client.post(f"/cart/add/{cement.pk}/")
        assert client.get("/cart/").context["cart"].total == cement.price_retail

    def test_approved_company_buys_wholesale(self, client, demo):
        company_user(client)
        cement = Product.objects.get(sku="ЦМ-500-50")
        assert cement.price_wholesale and cement.price_wholesale < cement.price_retail

        page = client.get(cement.get_absolute_url()).content.decode()
        assert "Оптовая цена" in page

        client.post(f"/cart/add/{cement.pk}/", {"quantity": 2})
        assert client.get("/cart/").context["cart"].total == 2 * cement.price_wholesale

        # Тип покупателя и реквизиты из формы игнорируются: заказ всегда на подтверждённую компанию.
        checkout(client, customer_type="person", company="Чужая", inn="500100732259")
        order = Order.objects.get()
        assert order.price_type == "wholesale" and order.customer_type == "company"
        assert (order.company, order.inn) == ("ООО «СтройТест»", "7707083893")
        assert order.total == 2 * cement.price_wholesale
        assert order.items.get().price == cement.price_wholesale

        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {TOKEN}")
        data = api.get("/api/v1/orders/new/").json()["orders"][0]
        assert data["price_type"] == "wholesale" and data["customer"]["inn"] == "7707083893"

    def test_admin_approve_action(self, admin_client, client):
        profile = company_user(client, status=Profile.Wholesale.PENDING)
        admin_client.post("/admin/accounts/profile/", {"action": "approve", "_selected_action": [profile.pk]})
        profile.refresh_from_db()
        assert profile.is_wholesale
