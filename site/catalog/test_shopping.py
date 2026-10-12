"""Покупать проще: свойства и фильтры, калькуляторы, «с этим покупают», подсказки поиска, доставка у товара."""
import io
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.attrs import facets, parse
from catalog.calc import calculator
from catalog.companions import companions
from catalog.models import Category, Product


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())


@pytest.mark.parametrize("name, expected", [
    ("Ламинат 32 класс 8 мм, дуб серый, 2,4 м²",
     {"wear": "32 класс", "thick": "8 мм", "color": "Дуб серый", "area": "2,4 м²"}),
    ("Газобетонный блок D500 600×300×200", {"grade": "D500", "dims": "600×300×200"}),
    ("Цемент М500 Д0 50 кг", {"grade": "М500", "pack": "50 кг"}),
    ("Щебень гранитный фр. 5–20 мм, 50 кг", {"fraction": "5–20 мм", "pack": "50 кг"}),
    ("Металлочерепица Монтеррей 0,45 мм, RAL 3005", {"thick": "0,45 мм", "color": "RAL 3005"}),
    ("Труба канализационная 110 мм, 1 м", {"diam": "110 мм", "length": "1 м"}),
    ("Герметик силиконовый санитарный, белый, 280 мл", {"volume": "280 мл", "color": "Белый"}),
    ("Кран шаровый латунный 1/2\"", {"thread": "1/2″"}),
    ("Лопата штыковая с черенком", {}),
])
def test_attrs_from_name(name, expected):
    assert parse(name) == expected


def test_facets_count_with_other_filters():
    items = [(1, {"pack": "25 кг", "color": "Белый"}), (2, {"pack": "25 кг", "color": "Серый"}),
             (3, {"pack": "5 кг", "color": "Белый"})]
    by_key = {f["key"]: f for f in facets(items, {"color": {"Белый"}})}
    # Счётчики фасовки — среди белых; цвета считаются без учёта своего же выбора
    assert {v["value"]: v["count"] for v in by_key["pack"]["values"]} == {"5 кг": 1, "25 кг": 1}
    assert {v["value"]: v["count"] for v in by_key["color"]["values"]} == {"Белый": 2, "Серый": 1}
    assert [v["value"] for v in by_key["pack"]["values"]] == ["5 кг", "25 кг"]   # числовой порядок


def test_attrs_saved_and_filter_listing(client, demo):
    laminate = Category.objects.get(name="Ламинат")
    assert all(p.attrs.get("wear") for p in laminate.products.all())
    r = client.get(laminate.get_absolute_url())
    keys = {f["key"] for f in r.context["filters"]["facets"]}
    assert {"wear", "thick", "color"} <= keys
    r = client.get(laminate.get_absolute_url(), {"f_wear": "33 класс"})
    found = list(r.context["page"].object_list)
    assert found and all(p.attrs["wear"] == "33 класс" for p in found)
    assert r.context["filters"]["active"] and "f_wear" not in r.context["filters"]["reset_url"]


def _product(name, unit="шт"):
    p = Product(name=name, unit=unit)
    p.attrs = parse(name)
    return p


@pytest.mark.parametrize("name, unit, kind, per_unit", [
    ("Ламинат 32 класс 8 мм, дуб серый, 2,4 м²", "упак", "area", Decimal("2.4")),
    ("Штукатурка гипсовая Кнауф Ротбанд 30 кг", "мешок", "layer", Decimal("30")),
    ("Клей для плитки Юнис 2000 25 кг", "мешок", "rate", Decimal("25")),
    ("Гипсокартон Кнауф ГКЛ 12,5 мм 1200×2500", "л.", "area", Decimal("3")),
    ("Газобетонный блок D500 600×300×200", "шт", "masonry", Decimal("0.18")),
    ("Плинтус ПВХ 58 мм, 2,5 м, венге", "шт", "length", Decimal("2.5")),
    ("Брус обрезной 100×100×6000, хвоя", "шт", "volume", Decimal("0.06")),
    ("Металлочерепица Монтеррей 0,45 мм, RAL 3005", "м2", "area", Decimal("1")),
])
def test_calculator_kinds(name, unit, kind, per_unit):
    calc = calculator(_product(name, unit))
    assert calc.kind == kind and calc.per_unit == per_unit


def test_no_calculator_for_tools():
    assert calculator(_product("Перфоратор SDS-plus 800 Вт")) is None


def test_companions_by_rules(demo):
    laminate = Product.objects.published().filter(name__startswith="Ламинат 32").first()
    names = [p.name.lower() for p in companions(laminate)]
    assert any(n.startswith("подложка") for n in names) and any(n.startswith("плинтус") for n in names)
    assert not any(n.startswith("ламинат") for n in names)   # другой цвет того же ламината — не сопутствующий


def test_search_suggest(client, demo):
    data = client.get("/search/suggest/", {"q": "штукатурка"}).json()
    assert data["total"] >= 1 and data["products"][0]["title"].lower().startswith("штукатурка")
    assert [c["name"] for c in data["categories"]] == ["Штукатурки"]
    assert data["all_url"].startswith("/search/?q=")
    assert client.get("/search/suggest/").json()["popular"]   # пустой запрос — частые запросы


def test_product_page_calc_delivery_together(client, demo):
    laminate = Product.objects.published().filter(name__startswith="Ламинат 32").first()
    r = client.get(laminate.get_absolute_url())
    html = r.content.decode()
    assert r.context["calc"].kind == "area" and 'data-kind="area"' in html and 'data-per-unit="2.4"' in html
    assert r.context["delivery"]["product"]["kg"] == float(laminate.weight_kg)
    assert 'id="ship-data"' in html and "data-ship-zone" in html
    assert r.context["companions"] and 'id="together"' in html
    assert "Площадь в упаковке" in html   # свойства — в характеристиках
