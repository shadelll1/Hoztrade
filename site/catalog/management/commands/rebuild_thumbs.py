from django.core.management.base import BaseCommand

from catalog.images import save_product_image
from catalog.models import Product


class Command(BaseCommand):
    help = "Сделать миниатюры для фото товаров, у которых их нет (фото, загруженные до появления миниатюр)"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="пересобрать все фото, а не только без миниатюр")

    def handle(self, *args, all=False, **options):
        products = Product.objects.exclude(image="")
        if not all:
            products = products.filter(thumb="")
        done = 0
        for product in products:
            with product.image.open("rb") as f:
                data = f.read()
            save_product_image(product, data, product.image_1c)
            done += 1
        self.stdout.write(self.style.SUCCESS(f"Фото пересобрано: {done}"))
