"""Демо-данные для 1С из тех же источников, что и демо сайта.

Пишет общие макеты расширения:
- хт_ДемоКаталог  — разделы, группы и товары из site/catalog/demo_data.py;
- хт_ДемоДоставка — зоны, автопарк и тарифы грузотакси из site/delivery/demo_data.py.

Команда 1С «Заполнить демо-каталог Хозтрейд» читает эти макеты, поэтому каталог и тарифы в 1С и на сайте
(manage.py load_demo_catalog) совпадают. Запуск после правки demo_data.py:
    site\\.venv\\Scripts\\python.exe 1c\\tools\\make_demo_data.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "1c" / "src" / "CommonTemplates"
sys.path.insert(0, str(ROOT / "site"))

from catalog.demo_data import CATALOG  # noqa: E402
from delivery.demo_data import PRICES, TRUCKS, ZONES  # noqa: E402


def write(name, data):
    """Текстовый макет: UTF-8 с BOM и CRLF, как его выгружает Конфигуратор."""
    text = json.dumps(data, ensure_ascii=False, indent=1)
    path = TEMPLATES / name / "Ext" / "Template.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    print(f"{path.relative_to(ROOT)}: {path.stat().st_size // 1024} КБ")


def catalog():
    return [
        {"name": section, "groups": [
            {"name": group, "items": [
                {"sku": sku, "name": name, "unit": unit, "weight": weight, "volume": volume,
                 "retail": retail, "wholesale": wholesale, "qty": qty}
                for name, sku, unit, weight, volume, retail, wholesale, qty in items
            ]}
            for group, items in groups.items()
        ]}
        for section, groups in CATALOG.items()
    ]


def delivery():
    return {
        "zones": [{"name": name, "description": desc} for name, desc in ZONES],
        "trucks": [{"name": name, "capacity_t": cap, "volume_m3": vol} for name, cap, vol in TRUCKS],
        "tariffs": [{"zone": zone, "truck": TRUCKS[i][0], "price": price}
                    for zone, prices in PRICES.items() for i, price in enumerate(prices)],
    }


if __name__ == "__main__":
    write("хт_ДемоКаталог", catalog())
    write("хт_ДемоДоставка", delivery())
