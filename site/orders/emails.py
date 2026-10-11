"""Письма покупателю: «заказ принят» и смена статуса заказа в 1С.

Отправляются, только если у заказа есть email (из формы или учётной записи). Сбой почты не мешает ни
оформлению заказа, ни обмену с 1С — пишется в лог. Ссылки в письме строятся от SITE_URL, а если он не задан —
от адреса текущего запроса.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import Order

log = logging.getLogger(__name__)

# Статусы, о которых покупателю пишем. «Новый» он видит сразу после оформления.
NOTIFY_STATUSES = {
    Order.Status.ACCEPTED, Order.Status.CONFIRMED, Order.Status.SHIPPING, Order.Status.DONE, Order.Status.CANCELED,
}


def _site_url(request=None):
    if settings.SITE_URL:
        return settings.SITE_URL.rstrip("/")
    if request is not None:
        return request.build_absolute_uri("/").rstrip("/")
    return ""


def _send(order, subject, template, request=None):
    recipient = order.email or (order.user.email if order.user_id else "")
    if not recipient:
        return False
    context = {"order": order, "url": _site_url(request) + order.get_absolute_url(), "site": settings.SITE_INFO}
    try:
        send_mail(subject, render_to_string(template, context), None, [recipient], fail_silently=False)
    except Exception:  # любая ошибка SMTP
        log.exception("Не удалось отправить письмо покупателю по заказу %s", order.number)
        return False
    return True


def order_created(order, request=None):
    return _send(order, f"Заказ {order.number} принят — {settings.SITE_INFO['name']}",
                 "emails/order_created.txt", request)


def status_changed(order, request=None):
    if order.status not in NOTIFY_STATUSES:
        return False
    return _send(order, f"Заказ {order.number}: {order.get_status_display().lower()}",
                 "emails/order_status.txt", request)
