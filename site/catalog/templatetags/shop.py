"""Фильтры витрины: деньги, количества, склонения, иконки разделов."""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

NBSP = " "


def _group(int_part: str) -> str:
    out = []
    while len(int_part) > 3:
        out.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    out.insert(0, int_part)
    return NBSP.join(out)


@register.filter
def rub(value):
    """1234.5 -> «1 234,50 ₽», 1234 -> «1 234 ₽» (неразрывные пробелы)."""
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "−" if value < 0 else ""
    value = abs(value).quantize(Decimal("0.01"))
    int_part, frac = f"{value:.2f}".split(".")
    text = _group(int_part) + ("" if frac == "00" else "," + frac)
    return f"{sign}{text}{NBSP}₽"


@register.filter
def qty(value):
    """Количество без лишних нулей: 140.000 -> 140, 2.500 -> 2,5."""
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    text = format(value.normalize(), "f")
    int_part, _, frac = text.partition(".")
    return _group(int_part) + ("," + frac if frac else "")


@register.filter
def plural(n, forms):
    """{{ n|plural:"товар,товара,товаров" }}"""
    one, few, many = forms.split(",")
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


# Склонение единиц измерения после числа; остальные (шт, кг, м², упак) не склоняются.
_UNIT_FORMS = {
    "мешок": "мешок,мешка,мешков",
    "лист": "лист,листа,листов",
    "рулон": "рулон,рулона,рулонов",
    "ведро": "ведро,ведра,вёдер",
    "пачка": "пачка,пачки,пачек",
}


@register.simple_tag
def unit_count(n, unit):
    """«48 рулонов», «2 мешка», «140 шт»."""
    text = qty(n)
    forms = _UNIT_FORMS.get(unit)
    try:
        whole = Decimal(n) == Decimal(n).to_integral_value()
    except (InvalidOperation, TypeError, ValueError):
        whole = False
    if forms and whole:
        unit = plural(Decimal(n), forms)
    elif forms:
        unit = forms.split(",")[1]  # дробное: «2,5 мешка»
    return f"{text}{NBSP}{unit}"


# Иконки разделов (линейные, 24×24, цвет — currentColor). Ключ — слово из названия корневого раздела.
_ICONS = {
    "строй": '<path d="M3 5h18v14H3z"/><path d="M3 9.7h18M3 14.3h18M9 5v4.7M15 5v4.7M6 9.7v4.6M12 9.7v4.6M18 9.7v4.6M9 14.3V19M15 14.3V19"/>',
    "смес": '<path d="M7 4h10l2 4v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8z"/><path d="M5 8h14M9 13h6M9 16h4"/>',
    "сантех": '<path d="M4 10h9a4 4 0 0 1 4 4v1"/><path d="M8 10V6a2 2 0 0 1 2-2h1"/><path d="M17 18v.5M17 21v.5"/><path d="M4 8v4"/>',
    "ламинат": '<path d="M3 7h18v10H3z"/><path d="M3 12h18M9 7v5M15 12v5"/>',
    "поликарб": '<path d="M3 20V11a9 9 0 0 1 18 0v9"/><path d="M8 20v-9a4 4 0 0 1 8 0v9M3 20h18M12 2v18"/>',
    "печ": '<path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16"/><path d="M3 21h18M8 13h8v5H8z"/><path d="M12 6c1.2 1.4 1.2 2.6 0 4-1.2-1.4-1.2-2.6 0-4z"/>',
    "креп": '<path d="M14 3l7 7-3 3-7-7z"/><path d="M11 6l-8 8 3 3 4 1 8-8"/>',
}
_DEFAULT_ICON = '<path d="M4 7l8-4 8 4v10l-8 4-8-4z"/><path d="M4 7l8 4 8-4M12 11v10"/>'


@register.simple_tag
def category_icon(name, size=24):
    key = (name or "").lower()
    body = next((svg for word, svg in _ICONS.items() if word in key), _DEFAULT_ICON)
    return format_html(
        '<svg class="icon" width="{0}" height="{0}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{1}</svg>',
        size, mark_safe(body),
    )


@register.simple_tag
def root_of(category):
    """Корневой раздел категории (для иконки товара без фото)."""
    node = category
    seen = set()
    while node is not None and node.parent_id and node.pk not in seen:
        seen.add(node.pk)
        node = node.parent
    return node


@register.simple_tag(takes_context=True)
def url_with(context, **kwargs):
    """Текущий query string с заменёнными параметрами (фильтры, сортировка, страницы)."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    if "page" not in kwargs:
        params.pop("page", None)
    query = params.urlencode()
    return f"?{query}" if query else "?"


@register.simple_tag
def stars(rating):
    """★★★★☆ по оценке 1–5 (дробная округляется)."""
    try:
        full = max(0, min(5, round(float(rating))))
    except (TypeError, ValueError):
        full = 0
    return "★" * full + "☆" * (5 - full)
