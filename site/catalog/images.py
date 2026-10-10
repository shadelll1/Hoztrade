"""Фото товаров: оригинал из 1С или админки ужимается до разумного размера, для списков делается миниатюра.

Карточка в каталоге показывает фото шириной около 250 px, а 1С может прислать снимок в несколько мегабайт.
Поэтому сайт хранит две версии в WebP: «полную» (не больше FULL_SIZE по длинной стороне) для карточки товара
и миниатюру (THUMB_SIZE) для списков, корзины и главной.
"""
import io

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

FULL_SIZE = 1600
THUMB_SIZE = 480
QUALITY = 82


def _webp(img, size):
    copy = img.copy()
    copy.thumbnail((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, "WEBP", quality=QUALITY, method=4)
    return buffer.getvalue()


def make_variants(data):
    """Байты картинки -> (полная версия, миниатюра) в WebP. Поворот по EXIF применяется, прозрачность сохраняется."""
    with Image.open(io.BytesIO(data)) as source:
        img = ImageOps.exif_transpose(source)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        return _webp(img, FULL_SIZE), _webp(img, THUMB_SIZE)


def save_product_image(product, data, version=""):
    """Сохраняет фото товара и миниатюру, удаляя прежние файлы. version — версия фото из 1С (пусто — загружено вручную)."""
    full, thumb = make_variants(data)
    for field in (product.image, product.thumb):
        if field:
            field.delete(save=False)
    product.image.save(f"{product.slug}.webp", ContentFile(full), save=False)
    product.thumb.save(f"{product.slug}-thumb.webp", ContentFile(thumb), save=False)
    product.image_1c = version
    product.save(update_fields=["image", "thumb", "image_1c", "updated_at"])
