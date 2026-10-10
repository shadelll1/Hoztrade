from django.core.management.base import BaseCommand, CommandError

from catalog.demo_data import CATALOG, demo_payload
from catalog.models import Category
from exchange.serializers import CatalogUploadSerializer
from exchange.services import import_catalog


class Command(BaseCommand):
    help = "Загрузить демо-каталог (тем же импортом, что и выгрузка из 1С)"

    def handle(self, *args, **options):
        serializer = CatalogUploadSerializer(data=demo_payload())
        if not serializer.is_valid():
            raise CommandError(serializer.errors)
        result = import_catalog(serializer.validated_data)
        # Порядок разделов — как в демо-данных (1С пока порядок не передаёт).
        for n, name in enumerate(CATALOG, start=1):
            Category.objects.filter(name=name, parent__isnull=True).update(sort=n * 10)
        self.stdout.write(self.style.SUCCESS(f"Демо-каталог загружен: {result}"))
