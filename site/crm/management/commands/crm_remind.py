"""Напоминания о задачах CRM: письмо исполнителю и сообщение в Telegram менеджеров, когда подходит срок.

На сервере запускается сервисом crm-reminders (deploy/docker-compose.yml) каждые 5 минут. Одна задача — одно
напоминание (reminded_at).
"""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from crm.models import Task
from orders.notifications import send_telegram

AHEAD = timedelta(minutes=15)   # напоминать за 15 минут до срока


class Command(BaseCommand):
    help = "Разослать напоминания о задачах CRM, срок которых подошёл"

    def handle(self, *args, **options):
        due = (Task.objects.filter(done_at__isnull=True, reminded_at__isnull=True, due_at__lte=timezone.now() + AHEAD)
               .select_related("assignee", "deal__client", "client"))
        sent = 0
        for task in due:
            client = task.client or (task.deal.client if task.deal_id else None)
            when = timezone.localtime(task.due_at).strftime("%d.%m %H:%M")
            link = f"{settings.SITE_URL}{task.deal.get_absolute_url()}" if task.deal_id and settings.SITE_URL else ""
            body = "\n".join(filter(None, [
                f"{task.title} — срок {when}",
                f"Клиент: {client} {client.phone}" if client else "",
                link,
            ]))
            if task.assignee and task.assignee.email:
                try:
                    send_mail(f"Задача CRM: {task.title}", body, None, [task.assignee.email])
                except Exception as exc:  # noqa: BLE001 — любая ошибка SMTP; напомним в Telegram
                    self.stderr.write(f"Письмо не отправлено: {exc}")
            if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
                who = task.assignee.get_full_name() or task.assignee.username if task.assignee else "без исполнителя"
                send_telegram(f"⏰ {who}: {body}")
            task.reminded_at = timezone.now()
            task.save(update_fields=["reminded_at"])
            sent += 1
        self.stdout.write(f"Напоминаний: {sent}")
