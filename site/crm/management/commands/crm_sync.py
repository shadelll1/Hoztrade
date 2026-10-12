from django.core.management.base import BaseCommand

from crm.services import backfill


class Command(BaseCommand):
    help = "Завести в CRM обращения по заказам, заявкам и запросам опта, созданным до CRM. Повторно не дублирует"

    def handle(self, *args, **options):
        made = backfill()
        self.stdout.write(self.style.SUCCESS(
            f"Обращений создано: заказы {made['orders']}, заявки {made['leads']}, опт {made['b2b']}"))
