import io
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

    def test_partial_upload_with_removed(self, api):
        data = payload()
        api.post("/api/v1/catalog/", data, format="json")
        item = data["products"][0]["id"]
        # Изменилась только цена: частичная посылка без full, остальное не трогается
        r = api.post("/api/v1/catalog/", {"full": False, "products": data["products"],
                                          "prices": [{"product_id": item, "retail": 555}]}, format="json")
        assert r.json()["products"]["updated"] == 0 and r.json()["total"] == {"categories": 2, "products": 1}
        assert Product.objects.get().price_retail == 555 and Category.objects.filter(is_published=True).count() == 2

        r = api.post("/api/v1/catalog/", {"full": False, "removed": {"products": [item],
                                                                     "categories": [data["categories"][0]["id"]]}},
                     format="json")
        body = r.json()
        assert body["products"]["unpublished"] == 1 and body["categories"]["unpublished"] == 1
        assert body["total"] == {"categories": 1, "products": 0}

    def test_partial_category_keeps_parent_from_db(self, api):
        data = payload()
        api.post("/api/v1/catalog/", data, format="json")
        child = dict(data["categories"][0], name="Сухие смеси и штукатурки", sort=7)
        api.post("/api/v1/catalog/", {"full": False, "categories": [child]}, format="json")
        updated = Category.objects.get(ext_id=child["id"])
        assert updated.name == "Сухие смеси и штукатурки" and updated.parent.name == "Стройматериалы"

    def test_bad_data_is_400(self, api):
        r = api.post("/api/v1/catalog/", {"products": [{"id": "not-uuid"}]}, format="json")
        assert r.status_code == 400


def png_bytes(color="red"):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.django_db
class TestProductImages:
    def upload(self, api, image):
        data = payload()
        data["products"][0]["image"] = image
        return data, api.post("/api/v1/catalog/", data, format="json").json()

    def test_handshake_upload_and_remove(self, api, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        data, result = self.upload(api, "v1")
        pid = data["products"][0]["id"]
        assert result["images_needed"] == [pid]

        url = f"/api/v1/products/{pid}/image/?version=v1"
        r = api.generic("PUT", url, png_bytes(), content_type="image/png")
        assert r.status_code == 200, r.content
        product = Product.objects.get()
        assert product.image.name.endswith(".png") and product.image_1c == "v1"

        # Та же версия — фото не просим снова; новая версия — просим.
        assert api.post("/api/v1/catalog/", data, format="json").json()["images_needed"] == []
        data["products"][0]["image"] = "v2"
        assert api.post("/api/v1/catalog/", data, format="json").json()["images_needed"] == [pid]

        # В 1С картинку убрали — на сайте тоже.
        data["products"][0]["image"] = None
        api.post("/api/v1/catalog/", data, format="json")
        product.refresh_from_db()
        assert not product.image and product.image_1c == ""

    def test_manual_image_kept_without_field(self, api):
        data, result = self.upload(api, None)
        assert result["images_needed"] == []
        Product.objects.update(image="products/manual.jpg")
        del data["products"][0]["image"]
        api.post("/api/v1/catalog/", data, format="json")
        assert Product.objects.get().image.name == "products/manual.jpg"

    def test_rejects_non_image(self, api):
        data, _ = self.upload(api, "v1")
        url = f"/api/v1/products/{data['products'][0]['id']}/image/?version=v1"
        r = api.generic("PUT", url, b"not an image", content_type="image/png")
        assert r.status_code == 400
        assert APIClient().generic("PUT", url, png_bytes(), content_type="image/png").status_code == 401
