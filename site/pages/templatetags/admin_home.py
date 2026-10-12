"""Главная админки: табло «что требует внимания» и разделы плитками с числом записей.

Каждая цифра — только если у сотрудника есть право смотреть эти данные; ссылка ведёт на уже отфильтрованный список.
"""
from datetime import timedelta

from django import template
from django.urls import reverse
from django.utils import timezone

register = template.Library()

EXCHANGE_STALE_MIN = 15   # 1С обменивается раз в 5 минут; дольше 15 минут тишины — повод проверить
APP_ORDER = ["orders", "crm", "catalog", "content", "delivery", "accounts", "exchange", "auth"]


def _ago(moment, now):
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} мин назад"
    if minutes < 60 * 24:
        return f"{minutes // 60} ч назад"
    return f"{minutes // (60 * 24)} дн назад"


@register.simple_tag(takes_context=True)
def admin_dashboard(context):
    """Плитки табло: заголовок, число, пояснение, ссылка, горит ли (нужно действие)."""
    user = context["request"].user
    now = timezone.now()
    day_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    tiles = []

    if user.has_perm("orders.view_order"):
        from orders.models import Order
        new = Order.objects.filter(status=Order.Status.NEW).count()
        today = Order.objects.filter(created_at__gte=day_start).count()
        tiles.append({"label": "Новые заказы", "num": new, "hot": bool(new),
                      "note": f"сегодня оформлено {today}",
                      "url": reverse("admin:orders_order_changelist") + "?status__exact=new"})

    if user.is_active and (user.is_superuser or user.has_perm("crm.use_crm")):
        from crm.models import Deal, Task
        waiting = Deal.objects.filter(stage__in=Deal.OPEN, first_touch_at__isnull=True).count()
        overdue = Task.objects.filter(done_at__isnull=True, due_at__lt=now).count()
        tiles.append({"label": "Ждут ответа в CRM", "num": waiting, "hot": bool(waiting),
                      "note": f"просрочено задач {overdue}" if overdue else "просроченных задач нет",
                      "url": reverse("crm:board") + "?only=wait"})

    if user.has_perm("content.view_review"):
        from content.models import Review
        n = Review.objects.filter(status=Review.Status.NEW).count()
        tiles.append({"label": "Отзывы на модерации", "num": n, "hot": bool(n),
                      "note": "покупатели ждут публикации" if n else "все разобраны",
                      "url": reverse("admin:content_review_changelist") + "?status__exact=new"})

    if user.has_perm("accounts.view_profile"):
        from accounts.models import Profile
        n = Profile.objects.filter(wholesale=Profile.Wholesale.PENDING).count()
        tiles.append({"label": "Заявки на опт", "num": n, "hot": bool(n),
                      "note": "проверить ИНН и открыть цены" if n else "новых нет",
                      "url": reverse("admin:accounts_profile_changelist") + "?wholesale__exact=pending"})

    if user.has_perm("exchange.view_exchangecontact"):
        from exchange.models import ExchangeContact
        from orders.models import Lead, Order
        contact = ExchangeContact.objects.order_by("-last_seen_at").first()
        waiting = (Order.objects.filter(exported_at__isnull=True).count()
                   + Lead.objects.filter(exported_at__isnull=True).count())
        stale = contact is None or now - contact.last_seen_at > timedelta(minutes=EXCHANGE_STALE_MIN)
        tiles.append({"label": "Обмен с 1С", "text": _ago(contact.last_seen_at, now) if contact else "не было",
                      "hot": stale,
                      "note": (f"ждут выгрузки в 1С: {waiting}" if waiting else "всё забрано в 1С")
                      + (". 1С давно не выходила на связь" if stale else ""),
                      "url": reverse("admin:exchange_exchangecontact_changelist")})
    return tiles


@register.simple_tag(takes_context=True)
def admin_shortcuts(context):
    """Частые действия одной кнопкой — только те, на которые у сотрудника есть права."""
    user = context["request"].user
    today = timezone.localdate()
    links = []
    if user.has_perm("orders.view_order"):
        links.append({"label": "Заказы за сегодня", "url": reverse("admin:orders_order_changelist")
                      + f"?created_at__day={today.day}&created_at__month={today.month}&created_at__year={today.year}"})
    if user.has_perm("content.add_post"):
        links.append({"label": "Добавить акцию или новость", "url": reverse("admin:content_post_add")})
    if user.has_perm("content.view_review"):
        links.append({"label": "Отзывы на модерации", "url": reverse("admin:content_review_changelist")
                      + "?status__exact=new"})
    if user.has_perm("catalog.view_product"):
        links.append({"label": "Товары без фото", "url": reverse("admin:catalog_product_changelist")
                      + "?image__exact="})
    if user.is_superuser or user.has_perm("crm.use_crm"):
        links.append({"label": "Открыть CRM", "url": reverse("crm:board"), "primary": True})
    return links


@register.simple_tag
def admin_apps(app_list):
    """Разделы в рабочем порядке (заказы первыми) и число записей у каждой модели."""
    rank = {label: i for i, label in enumerate(APP_ORDER)}
    apps = sorted(app_list, key=lambda a: rank.get(a["app_label"], len(rank)))
    for app in apps:
        for m in app["models"]:
            model = m.get("model")
            m["count"] = model._default_manager.count() if model is not None else None
    return apps
