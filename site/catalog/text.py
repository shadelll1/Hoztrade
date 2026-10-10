"""Транслитерация для адресов страниц (ЧПУ)."""
import re

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())


def slugify_ru(text: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", transliterate(text)).strip("-")
    return slug[:max_length].rstrip("-") or "item"


def make_slug(text: str, model, suffix: str = "") -> str:
    """Уникальный slug для модели: транслит названия, при совпадении — с хвостом из ID 1С или номера."""
    base = slugify_ru(text)
    slug = base
    if not model.objects.filter(slug=slug).exists():
        return slug
    if suffix:
        slug = f"{base}-{suffix}"
        if not model.objects.filter(slug=slug).exists():
            return slug
    n = 2
    while model.objects.filter(slug=f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"
