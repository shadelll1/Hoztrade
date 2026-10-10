from django.core.management.base import BaseCommand, CommandError

from catalog.demo_data import CATALOG, demo_payload
from catalog.models import Category
from delivery import demo_data as delivery_demo
from delivery.models import Zone
from delivery.serializers import DeliveryUploadSerializer
from delivery.services import import_delivery
from exchange.serializers import CatalogUploadSerializer
from exchange.services import import_catalog


class Command(BaseCommand):
    help = ("Загрузить демо-каталог и тарифы доставки (тем же импортом, что и выгрузка из 1С). "
            "Если в базе уже есть данные из 1С, демо не загружается — иначе витрина покажет оба каталога.")

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="загрузить демо поверх данных из 1С")

    def handle(self, *args, force=False, **options):
        payload = demo_payload()
        demo_ids = [c["id"] for c in payload["categories"]]
        if not force and Category.objects.filter(ext_id__isnull=False).exclude(ext_id__in=demo_ids).exists():
            self.stdout.write(self.style.WARNING("Каталог уже приходит из 1С — демо-каталог не загружен (--force)."))
        else:
            serializer = CatalogUploadSerializer(data=payload)
            if not serializer.is_valid():
                raise CommandError(serializer.errors)
            result = import_catalog(serializer.validated_data)
            # Порядок разделов — как в демо-данных.
            for n, name in enumerate(CATALOG, start=1):
                Category.objects.filter(name=name, parent__isnull=True, ext_id__in=demo_ids).update(sort=n * 10)
            self.stdout.write(self.style.SUCCESS(f"Демо-каталог загружен: {result}"))

        payload = delivery_demo.demo_payload()
        demo_ids = [z["id"] for z in payload["zones"]]
        if not force and Zone.objects.filter(ext_id__isnull=False).exclude(ext_id__in=demo_ids).exists():
            self.stdout.write(self.style.WARNING("Тарифы доставки уже приходят из 1С — демо не загружено (--force)."))
            return
        serializer = DeliveryUploadSerializer(data=payload)
        if not serializer.is_valid():
            raise CommandError(serializer.errors)
        self.stdout.write(self.style.SUCCESS(f"Доставка загружена: {import_delivery(serializer.validated_data)}"))
