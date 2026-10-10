"""Загрузка данных из 1С в базу сайта."""
from decimal import Decimal

from django.db import transaction

from catalog.models import Category, Product

_PRODUCT_FIELDS = ("sku", "name", "full_name", "unit", "weight_kg", "volume_m3")


@transaction.atomic
def import_catalog(data: dict) -> dict:
    """Upsert групп, товаров, цен и остатков по ID 1С.

    data — проверенные данные CatalogUploadSerializer. При full=True всё, чего нет в посылке,
    снимается с публикации (не удаляется: на товары ссылаются заказы).
    """
    result = {
        "categories": _import_categories(data["categories"], data["full"]),
        "products": _import_products(data["products"], data["full"]),
        "prices": _import_prices(data["prices"]),
        "stock": _import_stock(data["stock"]),
        "images_needed": _sync_images(data["products"]),
    }
    return result


def _import_categories(items, full):
    stats = {"created": 0, "updated": 0, "unpublished": 0}
    existing = {c.ext_id: c for c in Category.objects.filter(ext_id__in=[i["id"] for i in items])}

    for item in items:
        category = existing.get(item["id"])
        if category is None:
            category = Category(ext_id=item["id"], name=item["name"], sort=item.get("sort", 500))
            category.save()
            existing[item["id"]] = category
            stats["created"] += 1
        elif (category.name != item["name"] or not category.is_published
              or ("sort" in item and category.sort != item["sort"])):
            category.name = item["name"]
            category.is_published = True
            category.save(update_fields=["name", "is_published", "updated_at"])
            stats["updated"] += 1
        if "sort" in item and category.sort != item["sort"]:
            category.sort = item["sort"]
            category.save(update_fields=["sort"])

    # Родителей связываем после создания всех групп: группа может прийти раньше родителя.
    for item in items:
        category = existing[item["id"]]
        parent = existing.get(item.get("parent_id"))
        if category.parent_id != (parent.pk if parent else None):
            category.parent = parent
            category.save(update_fields=["parent", "updated_at"])

    if full:
        stats["unpublished"] = (
            Category.objects.filter(ext_id__isnull=False, is_published=True)
            .exclude(ext_id__in=existing.keys())
            .update(is_published=False)
        )
    return stats


def _import_products(items, full):
    stats = {"created": 0, "updated": 0, "unpublished": 0}
    categories = dict(Category.objects.filter(ext_id__isnull=False).values_list("ext_id", "pk"))
    existing = {p.ext_id: p for p in Product.objects.filter(ext_id__in=[i["id"] for i in items])}

    for item in items:
        values = {f: item[f] for f in _PRODUCT_FIELDS}
        values["unit"] = values["unit"] or "шт"
        values["category_id"] = categories.get(item.get("category_id"))

        product = existing.get(item["id"])
        if product is None:
            Product(ext_id=item["id"], is_published=True, **values).save()
            stats["created"] += 1
            continue

        changed = [f for f, v in values.items() if getattr(product, f) != v]
        if not product.is_published:
            product.is_published = True
            changed.append("is_published")
        if changed:
            for f, v in values.items():
                setattr(product, f, v)
            product.save(update_fields=changed + ["updated_at"])
            stats["updated"] += 1

    if full:
        stats["unpublished"] = (
            Product.objects.filter(ext_id__isnull=False, is_published=True)
            .exclude(ext_id__in=[i["id"] for i in items])
            .update(is_published=False)
        )
    return stats


def _sync_images(items):
    """Сверка версий фото: возвращает ID товаров, фото которых 1С должна прислать (PUT .../image/).

    Фото из 1С, которого больше нет в 1С, удаляется. Фото, загруженное на сайте вручную, не трогаем,
    пока 1С не пришлёт своё.
    """
    items = [i for i in items if "image" in i]
    products = {p.ext_id: p for p in Product.objects.filter(ext_id__in=[i["id"] for i in items])}
    needed = []
    for item in items:
        product = products.get(item["id"])
        if product is None:
            continue
        version = item["image"] or ""
        if not version:
            if product.image_1c:
                remove_product_image(product)
        elif version != product.image_1c or not product.image:
            needed.append(str(item["id"]))
    return needed


def remove_product_image(product):
    if product.image:
        product.image.delete(save=False)
    product.image = ""
    product.image_1c = ""
    product.save(update_fields=["image", "image_1c", "updated_at"])


def _import_prices(items):
    products = {p.ext_id: p for p in Product.objects.filter(ext_id__in=[i["product_id"] for i in items])}
    changed = []
    for item in items:
        product = products.get(item["product_id"])
        if product is None:
            continue
        product.price_retail = item["retail"]
        product.price_wholesale = item.get("wholesale")
        changed.append(product)
    Product.objects.bulk_update(changed, ["price_retail", "price_wholesale"], batch_size=500)
    return len(changed)


def _import_stock(items):
    products = {p.ext_id: p for p in Product.objects.filter(ext_id__in=[i["product_id"] for i in items])}
    changed = []
    for item in items:
        product = products.get(item["product_id"])
        if product is None:
            continue
        product.stock = max(item["quantity"], Decimal("0"))
        changed.append(product)
    Product.objects.bulk_update(changed, ["stock"], batch_size=500)
    return len(changed)
