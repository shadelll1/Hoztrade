from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.images import save_product_image
from catalog.models import Product
from catalog.tree import invalidate_tree

DEFAULT_DIR = Path(settings.BASE_DIR).parent / "1c" / "demo-images"


class Command(BaseCommand):
    help = ("Загрузить картинки демо-товаров из папки (имя файла — артикул, как в 1С: «Загрузить картинки товаров "
            "из папки»). Для витрины без 1С; когда картинки приходят из 1С, загружать их нужно там.")

    def add_arguments(self, parser):
        parser.add_argument("folder", nargs="?", default=str(DEFAULT_DIR), help=f"папка с картинками ({DEFAULT_DIR})")

    def handle(self, *args, folder, **options):
        folder = Path(folder)
        if not folder.is_dir():
            raise CommandError(f"Нет папки {folder}")
        files = {p.stem: p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
        done = 0
        for product in Product.objects.filter(sku__in=files):
            save_product_image(product, files[product.sku].read_bytes())
            done += 1
        invalidate_tree()
        self.stdout.write(self.style.SUCCESS(f"Файлов: {len(files)}, товаров с новой картинкой: {done}."))
