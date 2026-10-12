"""Логика CRM: клиент по телефону/email, обращения из заказов и заявок, этапы, синхронизация со статусами 1С."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from orders.forms import normalize_phone

from .models import Activity, Client, Deal

# Статус заказа (из 1С) -> этап обращения. Этап только растёт: менеджер мог продвинуть сделку дальше сам.
ORDER_STAGE = {
    "accepted": Deal.Stage.ORDER,
    "confirmed": Deal.Stage.ORDER,
    "shipping": Deal.Stage.ORDER,
    "done": Deal.Stage.WON,
    "canceled": Deal.Stage.LOST,
}
STAGE_ORDER = [s for s, _ in Deal.Stage.choices]


def phone_key(value):
    """+7XXXXXXXXXX или пусто, если номер не российский — тогда клиента узнаём по email."""
    try:
        return normalize_phone(value)
    except ValidationError:
        return ""


def managers():
    """Сотрудники с доступом к CRM — для выбора ответственного и отчётов."""
    User = get_user_model()
    perm = Q(user_permissions__codename="use_crm") | Q(groups__permissions__codename="use_crm")
    return User.objects.filter(is_active=True).filter(perm | Q(is_superuser=True)).distinct().order_by("first_name",
                                                                                                         "username")


def find_or_create_client(name, phone="", email="", company="", inn="", user=None):
    """Клиент по телефону, затем по email, затем по учётной записи; пустые поля дополняются новыми данными."""
    phone = phone_key(phone)
    email = (email or "").strip().lower()
    client = None
    if phone:
        client = Client.objects.filter(phone=phone).order_by("pk").first()
    if client is None and email:
        client = Client.objects.filter(email__iexact=email).order_by("pk").first()
    if client is None and user is not None:
        client = Client.objects.filter(user=user).order_by("pk").first()
    if client is None:
        return Client.objects.create(name=name or phone or email or "Без имени", phone=phone, email=email,
                                     company=company, inn=inn, user=user)
    changed = []
    for field, value in (("phone", phone), ("email", email), ("company", company), ("inn", inn), ("user", user)):
        if value and not getattr(client, field):
            setattr(client, field, value)
            changed.append(field)
    if changed:
        client.save(update_fields=changed)
    return client


def log(deal, text, kind=Activity.Kind.SYSTEM, author=None, stage="", client=None, when=None):
    return Activity.objects.create(deal=deal, client=client or deal.client, kind=kind, text=text, author=author,
                                   stage=stage, created_at=when or timezone.now())


def _amount(order):
    return order.total_1c if order.total_1c is not None else order.grand_total


@transaction.atomic
def deal_for_order(order):
    """Обращение по заказу с сайта (одно на заказ)."""
    existing = Deal.objects.filter(order=order).first()
    if existing:
        return existing
    client = find_or_create_client(order.name, order.phone, order.email, order.company, order.inn, order.user)
    items = order.items.count() if order.pk else 0
    deal = Deal.objects.create(
        client=client, source=Deal.Source.ORDER, order=order, amount=_amount(order), created_at=order.created_at,
        title=f"Заказ {order.number}" + (f", {order.get_delivery_display().lower()}" if order.delivery else ""),
    )
    log(deal, f"Заказ {order.number} оформлен на сайте" + (f", позиций: {items}" if items else ""),
        when=order.created_at)
    sync_order_status(order, deal)
    if deal.closed_at and order.updated_at < deal.closed_at:   # старый заказ: закрыт тогда, когда сменился статус
        deal.closed_at = order.updated_at
        deal.save(update_fields=["closed_at"])
    return deal


@transaction.atomic
def deal_for_lead(lead):
    existing = Deal.objects.filter(lead=lead).first()
    if existing:
        return existing
    client = find_or_create_client(lead.name, lead.phone, lead.email)
    source = Deal.Source.LIST if lead.kind == "list" else Deal.Source.CALLBACK
    title = "Перезвонить" if source == Deal.Source.CALLBACK else "Собрать заказ по списку"
    deal = Deal.objects.create(client=client, source=source, lead=lead, title=title, created_at=lead.created_at)
    text = lead.get_kind_display() + (f": {lead.text}" if lead.text else "")
    log(deal, text + (" (приложен файл)" if lead.attachment else ""), when=lead.created_at)
    return deal


@transaction.atomic
def deal_for_wholesale(profile):
    """Запрос оптовых цен: менеджер проверяет компанию по ИНН и подтверждает в админке."""
    deal = Deal.objects.filter(profile=profile, stage__in=Deal.OPEN).first()
    if deal:
        return deal
    user = profile.user
    client = find_or_create_client(user.get_full_name() or user.email, profile.phone, user.email,
                                   profile.company, profile.inn, user)
    deal = Deal.objects.create(client=client, source=Deal.Source.B2B, profile=profile,
                               title=f"Оптовые цены: {profile.company or user.email}",
                               created_at=profile.wholesale_requested_at or timezone.now())
    log(deal, f"Запрос оптовых цен, ИНН {profile.inn or 'не указан'}", when=deal.created_at)
    return deal


def set_stage(deal, stage, author=None, reason=""):
    """Новый этап с записью в ленту. Менеджер, сделавший первое действие, отмечается как первый ответ."""
    if stage == deal.stage:
        return False
    old = deal.get_stage_display()
    deal.stage = stage
    fields = ["stage", "updated_at"]
    if stage in Deal.CLOSED:
        deal.closed_at = timezone.now()
        fields.append("closed_at")
    elif deal.closed_at:
        deal.closed_at = None
        fields.append("closed_at")
    if stage == Deal.Stage.LOST and reason:
        deal.lost_reason = reason[:200]
        fields.append("lost_reason")
    deal.save(update_fields=fields)
    text = f"Этап: {old} → {deal.get_stage_display()}" + (f". Причина: {reason}" if reason else "")
    log(deal, text, Activity.Kind.STAGE, author=author, stage=stage)
    if author is not None:
        touch(deal, author)
    return True


def touch(deal, user):
    """Первый ответ менеджера: время реакции — в отчёты; ничей «новый» — забирает себе."""
    fields = []
    if deal.first_touch_at is None:
        deal.first_touch_at = timezone.now()
        fields.append("first_touch_at")
    if deal.manager_id is None and user is not None:
        deal.manager = user
        fields.append("manager")
    if fields:
        deal.save(update_fields=[*fields, "updated_at"])


def sync_order_status(order, deal=None):
    """Статус заказа из 1С двигает обращение вперёд (назад — никогда) и обновляет сумму."""
    deal = deal or Deal.objects.filter(order=order).first()
    if deal is None:
        return
    amount = _amount(order)
    if deal.amount != amount:
        deal.amount = amount
        deal.save(update_fields=["amount", "updated_at"])
    target = ORDER_STAGE.get(order.status)
    if target is None or deal.stage == target:
        return
    if deal.stage in Deal.CLOSED and target not in Deal.CLOSED:
        return
    if target not in Deal.CLOSED and STAGE_ORDER.index(target) < STAGE_ORDER.index(deal.stage):
        return
    set_stage(deal, target)
    note = f"Статус в 1С: {order.get_status_display()}" + (f" ({order.status_text})" if order.status_text else "")
    log(deal, note)


def sync_wholesale(profile):
    deal = Deal.objects.filter(profile=profile, stage__in=Deal.OPEN).first()
    if deal is None:
        return
    if profile.wholesale == "approved":
        set_stage(deal, Deal.Stage.WON)
    elif profile.wholesale == "rejected":
        set_stage(deal, Deal.Stage.LOST, reason=profile.wholesale_comment)


def backfill():
    """Обращения для заказов, заявок и запросов опта, созданных до CRM. Повторный запуск не дублирует."""
    from accounts.models import Profile
    from orders.models import Lead, Order

    made = {"orders": 0, "leads": 0, "b2b": 0}
    for order in Order.objects.filter(deal__isnull=True).order_by("created_at"):
        deal_for_order(order)
        made["orders"] += 1
    for lead in Lead.objects.filter(deal__isnull=True).order_by("created_at"):
        deal_for_lead(lead)
        made["leads"] += 1
    for profile in Profile.objects.filter(wholesale=Profile.Wholesale.PENDING).exclude(deals__stage__in=Deal.OPEN):
        deal_for_wholesale(profile)
        made["b2b"] += 1
    return made


def can_use(user):
    return user.is_active and (user.is_superuser or user.has_perm("crm.use_crm"))


def can_report(user):
    return user.is_active and (user.is_superuser or user.has_perm("crm.view_reports"))
