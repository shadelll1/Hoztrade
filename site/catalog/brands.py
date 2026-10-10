"""Привязка товаров к брендам по названию: «Штукатурка Кнауф Ротбанд» -> бренд Knauf."""
import re

from .models import Brand, Product


def _patterns():
    return [
        (brand, re.compile(r"(?<![\w-])(" + "|".join(re.escape(s) for s in brand.spellings()) + r")(?![\w-])"))
        for brand in Brand.objects.all()
        if brand.spellings()
    ]


def match_brand(name, patterns):
    text = name.lower()
    for brand, pattern in patterns:
        if pattern.search(text):
            return brand
    return None


def assign_brands(products=None, overwrite=False):
    """Проставляет бренд товарам без бренда (или всем при overwrite). Возвращает число изменённых."""
    patterns = _patterns()
    if not patterns:
        return 0
    if products is None:
        products = Product.objects.all()
    changed = []
    for product in products:
        if product.brand_id and not overwrite:
            continue
        brand = match_brand(f"{product.name} {product.full_name}", patterns)
        if brand is not None and brand.pk != product.brand_id:
            product.brand = brand
            changed.append(product)
    Product.objects.bulk_update(changed, ["brand"], batch_size=500)
    return len(changed)
