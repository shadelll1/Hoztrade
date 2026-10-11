"""Уведомления менеджерам о заказах, заявках и отзывах: письмо (MANAGER_EMAILS) и Telegram (по желанию).

Telegram включается двумя настройками в .env: TELEGRAM_BOT_TOKEN (токен бота от @BotFather) и TELEGRAM_CHAT_ID
(чат менеджеров, куда добавлен бот). Сообщение уходит в фоновом потоке: недоступный Telegram не задерживает
и не ломает оформление заказа.
"""
import json
import logging
import threading
import urllib.request

from django.conf import settings
from django.core.mail import mail_managers

log = logging.getLogger(__name__)

TELEGRAM_TIMEOUT = 5


def notify(subject, body):
    """Письмо менеджерам и сообщение в Telegram. Сбой любого канала только пишется в лог."""
    if settings.MANAGERS:
        try:
            mail_managers(subject, body, fail_silently=False)
        except Exception:  # любая ошибка SMTP
            log.exception("Не удалось отправить уведомление менеджерам")
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        thread = threading.Thread(target=send_telegram, args=(f"{subject}\n{body}",), daemon=True)
        thread.start()
        return thread
    return None


def send_telegram(text):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": settings.TELEGRAM_CHAT_ID, "text": text[:4000],
                       "disable_web_page_preview": True}).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_TIMEOUT) as response:  # noqa: S310 — адрес https://api.telegram.org
            response.read()
    except Exception:  # сеть, неверный токен, лимиты Telegram
        log.exception("Не удалось отправить уведомление в Telegram")
