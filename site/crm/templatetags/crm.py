"""Фильтры CRM: возраст обращения коротко, инициалы менеджера."""
from django import template
from django.utils import timezone

register = template.Library()


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
def initials(user):
    """«ММ» для «Мария Менеджер», первые буквы логина — если имени нет."""
    if not user:
        return ""
    parts = [p for p in (user.first_name, user.last_name) if p]
    if parts:
        return "".join(p[0] for p in parts).upper()[:2]
    return (user.username or "?")[:2].upper()
