import io

import pytest
from django.core.management import call_command

from catalog.models import Category, Product
from catalog.templatetags.shop import plural, qty, rub, unit_count


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())


def test_rub_and_qty():
    assert rub(1234) == "1 234 ₽"
    assert rub("1234.50") == "1 234,50 ₽"
    assert qty("140.000") == "140"
    assert qty("2.500") == "2,5"


def test_plural_and_units():
    assert plural(1, "товар,товара,товаров") == "товар"
    assert plural(3, "товар,товара,товаров") == "товара"
    assert plural(11, "товар,товара,товаров") == "товаров"
    assert unit_count(340, "мешок") == "340 мешков"
    assert unit_count(2, "лист") == "2 листа"
    assert unit_count(140, "шт") == "140 шт"


@pytest.mark.django_db
class TestStorefront:
    def test_pages_render(self, client, demo):
        root = Category.objects.get(name="Стройматериалы")
        product = Product.objects.get(sku="ЦМ-500-50")
        for url in ["/", "/catalog/", root.get_absolute_url(), product.get_absolute_url()]:
            assert client.get(url).status_code == 200, url

    def test_category_includes_nested_products(self, client, demo):
        r = client.get(Category.objects.get(name="Стройматериалы").get_absolute_url())
        assert r.context["page"].paginator.count == 23

    def test_filters_in_stock_and_price(self, client, demo):
        url = Category.objects.get(name="Стройматериалы").get_absolute_url()
        r = client.get(url, {"in_stock": "1"})
        assert all(p.stock > 0 for p in r.context["page"].object_list)
        r = client.get(url, {"price_max": "200", "sort": "price"})
        prices = [p.price_retail for p in r.context["page"].object_list]
        assert prices == sorted(prices) and all(p <= 200 for p in prices)

    def test_search_cyrillic_case_insensitive(self, client, demo):
        r = client.get("/search/", {"q": "ЦЕМЕНТ м500"})
        assert [p.sku for p in r.context["page"].object_list] == ["ЦМ-500-50"]

    def test_unpublished_is_404(self, client, demo):
        product = Product.objects.get(sku="ЦМ-500-50")
        product.is_published = False
        product.save()
        assert client.get(product.get_absolute_url()).status_code == 404

    def test_truck_capacity(self, client, demo):
        r = client.get(Product.objects.get(sku="ЦМ-500-50").get_absolute_url())
        assert dict(r.context["trucks"])[1.5] == 30
