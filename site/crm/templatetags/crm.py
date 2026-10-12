"""Фильтры CRM: возраст обращения коротко, инициалы менеджера, монограмма клиента."""
import re

from django import template
from django.utils import timezone

register = template.Library()
LEGAL_FORMS = ("ООО", "ИП", "АО", "ЗАО", "ОАО", "ТСЖ", "ПАО")


@register.filter
def ago(value):
    """«5 мин», «3 ч», «2 дн», «14 нед» — сколько прошло (для карточек на доске)."""
    if not value:
        return ""
    minutes = int((timezone.now() - value).total_seconds() // 60)
    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} мин"
    if minutes < 60 * 24:
        return f"{minutes // 60} ч"
    days = minutes // (60 * 24)
    return f"{days} дн" if days < 60 else f"{days // 7} нед"


@register.filter
def monogram(name):
    """«СИ» для «Сергей Иванов», «СМ» для «ООО «СтройМонтаж»» — кружок клиента в списках."""
    words = [re.sub(r"[^\w-]", "", w) for w in str(name or "").split() if not w.startswith("(")]
    words = [w for w in words if w and w[0].isalpha() and w.upper() not in LEGAL_FORMS]
    if not words:
        return "?"
    if len(words) == 1:
        caps = [ch for ch in words[0] if ch.isupper()]
        return ("".join(caps[:2]) if len(caps) > 1 else words[0][:2]).upper()
    return (words[0][0] + words[1][0]).upper()


@register.filter
def initials(user):
    """«ММ» для «Мария Менеджер», первые буквы логина — если имени нет."""
    if not user:
        return ""
    parts = [p for p in (user.first_name, user.last_name) if p]
    if parts:
        return "".join(p[0] for p in parts).upper()[:2]
    return (user.username or "?")[:2].upper()
