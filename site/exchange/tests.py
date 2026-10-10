import uuid

import pytest
from rest_framework.test import APIClient

from catalog.models import Category, Product

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def exchange_token(settings):
    settings.EXCHANGE_TOKEN = TOKEN


@pytest.fixture
def api():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {TOKEN}")
    return client


def payload():
    root, child, item = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    return {
        "full": True,
        # Дочерняя группа нарочно раньше родителя.
        "categories": [
            {"id": str(child), "parent_id": str(root), "name": "Сухие смеси"},
            {"id": str(root), "parent_id": None, "name": "Стройматериалы"},
        ],
        "products": [{"id": str(item), "category_id": str(child), "sku": "СМ-001",
                      "name": "Штукатурка гипсовая 30 кг", "unit": "шт", "weight_kg": 30, "volume_m3": 0.025}],
        "prices": [{"product_id": str(item), "retail": 520, "wholesale": None}],
        "stock": [{"product_id": str(item), "quantity": 140}],
    }


@pytest.mark.django_db
class TestCatalogUpload:
    def test_no_token_is_401(self):
        assert APIClient().get("/api/v1/ping/").status_code == 401

    def test_wrong_token_is_401(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token wrong")
        assert client.get("/api/v1/ping/").status_code == 401

    def test_ping(self, api):
        assert api.get("/api/v1/ping/").json()["status"] == "ok"

    def test_upload_creates_tree_prices_stock(self, api):
        data = payload()
        r = api.post("/api/v1/catalog/", data, format="json")
        assert r.status_code == 200, r.content
        assert r.json()["products"]["created"] == 1

        child = Category.objects.get(name="Сухие смеси")
        assert child.parent.name == "Стройматериалы"
        product = Product.objects.get()
        assert product.category == child
        assert product.price_retail == 520 and product.price_wholesale is None
        assert product.stock == 140
        assert product.slug == "shtukaturka-gipsovaya-30-kg"

    def test_repeat_upload_is_idempotent(self, api):
        data = payload()
        api.post("/api/v1/catalog/", data, format="json")
        r = api.post("/api/v1/catalog/", data, format="json")
        assert r.json()["products"] == {"created": 0, "updated": 0, "unpublished": 0}
        assert Product.objects.count() == 1 and Category.objects.count() == 2

    def test_full_upload_unpublishes_missing(self, api):
        api.post("/api/v1/catalog/", payload(), format="json")
        r = api.post("/api/v1/catalog/", payload(), format="json")  # другие ID
        assert r.json()["products"]["unpublished"] == 1
        assert Product.objects.published().count() == 1

    def test_bad_data_is_400(self, api):
        r = api.post("/api/v1/catalog/", {"products": [{"id": "not-uuid"}]}, format="json")
        assert r.status_code == 400
