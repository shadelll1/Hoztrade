"""Обезличивание персональных данных (152-ФЗ): по запросу покупателя и по сроку хранения.

На сайте остаётся заказ без данных о человеке: номер, товары, суммы, статус — для отчётов и истории. В 1С
документы не меняются: там свои сроки хранения по учёту.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Lead, Order

ANONYMOUS = "Обезличено"


def anonymize_order(order):
    order.name = ANONYMOUS
    order.phone = ""
    order.email = ""
    order.address = ""
    order.comment = ""
    order.company = ""
    order.inn = ""
    order.user = None
    order.save(update_fields=["name", "phone", "email", "address", "comment", "company", "inn", "user", "updated_at"])


def anonymize_lead(lead):
    if lead.attachment:
        lead.attachment.delete(save=False)
    lead.name = ANONYMOUS
    lead.phone = ""
    lead.email = ""
    lead.text = ""
    lead.attachment = ""
    lead.save(update_fields=["name", "phone", "email", "text", "attachment"])


@transaction.atomic
def purge(days):
    """Обезличивает завершённые и отменённые заказы и заявки, переданные в 1С, старше days дней."""
    border = timezone.now() - timedelta(days=days)
    orders = Order.objects.filter(created_at__lt=border, status__in=[Order.Status.DONE, Order.Status.CANCELED]) \
        .exclude(name=ANONYMOUS)
    leads = Lead.objects.filter(created_at__lt=border, exported_at__isnull=False).exclude(name=ANONYMOUS)
    n_orders = n_leads = 0
    for order in orders:
        anonymize_order(order)
        n_orders += 1
    for lead in leads:
        anonymize_lead(lead)
        n_leads += 1
    return n_orders, n_leads
