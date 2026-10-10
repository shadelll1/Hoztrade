from django.core.management.base import BaseCommand

from orders.privacy import purge


class Command(BaseCommand):
    help = ("Обезличить персональные данные в выполненных и отменённых заказах и в заявках, переданных в 1С, "
            "старше заданного срока (152-ФЗ). Запускать по расписанию, например раз в сутки.")

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=365 * 3, help="срок хранения, дней (по умолчанию 3 года)")

    def handle(self, *args, days, **options):
        orders, leads = purge(days)
        self.stdout.write(self.style.SUCCESS(f"Обезличено: заказов {orders}, заявок {leads} (старше {days} дн.)"))
