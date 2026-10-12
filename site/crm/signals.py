"""Обращения появляются сами: заказ, заявка, запрос оптовых цен. Статус заказа из 1С двигает этап.

Сбой CRM не должен ломать оформление заказа или обмен с 1С — ошибка только пишется в лог.
"""
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounts.models import Profile
from orders.models import Lead, Order

from . import services

log = logging.getLogger(__name__)


def _safe(func, *args):
    try:
        func(*args)
    except Exception:  # CRM — вспомогательная: заказ и обмен важнее
        log.exception("CRM: не удалось обработать %s", args[0])


@receiver(post_save, sender=Order)
def order_saved(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    _safe(services.deal_for_order if created else services.sync_order_status, instance)


@receiver(post_save, sender=Lead)
def lead_saved(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        _safe(services.deal_for_lead, instance)


@receiver(pre_save, sender=Profile)
def profile_before(sender, instance, raw=False, **kwargs):
    if raw or not instance.pk:
        instance._crm_old_wholesale = None
        return
    instance._crm_old_wholesale = Profile.objects.filter(pk=instance.pk).values_list("wholesale", flat=True).first()


@receiver(post_save, sender=Profile)
def profile_saved(sender, instance, raw=False, **kwargs):
    old = getattr(instance, "_crm_old_wholesale", None)
    if raw or old == instance.wholesale:
        return
    if instance.wholesale == Profile.Wholesale.PENDING:
        _safe(services.deal_for_wholesale, instance)
    else:
        _safe(services.sync_wholesale, instance)
