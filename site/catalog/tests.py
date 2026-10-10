import io
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.demo_data import CATALOG
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
        expected = sum(len(items) for items in CATALOG["Стройматериалы"].values())
        assert r.context["page"].paginator.count == expected

    def test_filters_in_stock_and_price(self, client, demo):
        url = Category.objects.get(name="Стройматериалы").get_absolute_url()
        r = client.get(url, {"in_stock": "1"})
        assert all(p.stock > 0 for p in r.context["page"].object_list)
        r = client.get(url, {"price_max": "200", "sort": "price"})
        prices = [p.price_retail for p in r.context["page"].object_list]
        assert prices == sorted(prices) and all(p <= 200 for p in prices)

    def test_search_cyrillic_case_insensitive(self, client, demo):
        r = client.get("/search/", {"q": "ЦЕМЕНТ м500"})
        found = r.context["page"].object_list
        assert {"ЦМ-500-50", "ЦМ-500-25", "ЦМ-БЛ-25"} <= {p.sku for p in found}
        assert all("цемент" in p.name.lower() and "м500" in p.name.lower() for p in found)

    def test_unpublished_is_404(self, client, demo):
        product = Product.objects.get(sku="ЦМ-500-50")
        product.is_published = False
        product.save()
        assert client.get(product.get_absolute_url()).status_code == 404

    def test_truck_capacity(self, client, demo):
        r = client.get(Product.objects.get(sku="ЦМ-500-50").get_absolute_url())
        fits = {truck.capacity_t: n for truck, n in r.context["trucks"]}
        assert fits[Decimal("1.5")] == 30 and fits[Decimal("20")] == 400  # мешки по 50 кг


@pytest.mark.django_db
def test_sitemap_and_robots(client):
    call_command("load_demo_catalog", stdout=io.StringIO())
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    body = r.content.decode()
    product = Product.objects.published().first()
    assert product.get_absolute_url() in body and "/catalog/" in body
    robots = client.get("/robots.txt").content.decode()
    assert "Disallow: /checkout/" in robots and "Sitemap: http://testserver/sitemap.xml" in robots


@pytest.mark.django_db
def test_404_page(client, settings):
    settings.DEBUG = False
    r = client.get("/product/net-takogo/")
    assert r.status_code == 404 and "Такой страницы нет" in r.content.decode()


@pytest.mark.django_db
def test_tree_cache_invalidation(client, settings):
    from django.core.cache import cache
    from rest_framework.test import APIClient

    cache.clear()
    settings.EXCHANGE_TOKEN = "t"
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION="Token t")
    root = "11111111-1111-1111-1111-111111111111"
    api.post("/api/v1/catalog/", {"categories": [{"id": root, "name": "Кровля"}],
                                  "products": [{"id": "22222222-2222-2222-2222-222222222222", "category_id": root,
                                                "name": "Ондулин"}]}, format="json")
    assert [n.name for n in client.get("/").context["catalog_tree"]] == ["Кровля"]
    Category.objects.filter(ext_id=root).update(name="Кровля и водосток")   # update() без сигналов: дерево из памяти
    assert [n.name for n in client.get("/").context["catalog_tree"]] == ["Кровля"]
    category = Category.objects.get(ext_id=root)
    category.save()                                                          # сохранение — через сигнал
    assert [n.name for n in client.get("/").context["catalog_tree"]] == ["Кровля и водосток"]
