"""Свойства товара для фильтров и характеристик — из наименования.

1С пока не передаёт характеристики номенклатуры, но наименования в ней ведутся по шаблону
(«Ламинат 32 класс 8 мм, дуб серый, 2,4 м²», «Газобетонный блок D500 600×300×200»), и из них
надёжно выделяются фасовка, толщина, размеры, цвет и т. п. Когда характеристики придут из 1С,
их достаточно записать в Product.attrs теми же ключами — фильтры и карточка их подхватят.
"""
import re
from decimal import Decimal, InvalidOperation

# Ключ -> подпись. Порядок — порядок в фильтрах и характеристиках.
LABELS = {
    "grade": "Марка",
    "wear": "Класс",
    "thick": "Толщина",
    "diam": "Диаметр",
    "size": "Размер",
    "dims": "Габариты",
    "fraction": "Фракция",
    "length": "Длина",
    "width": "Ширина рулона",
    "pack": "Фасовка",
    "volume": "Объём",
    "area": "Площадь в упаковке",
    "pieces": "Штук в упаковке",
    "power": "Мощность",
    "sections": "Секций",
    "thread": "Резьба",
    "color": "Цвет",
}

NUM = r"(\d+(?:,\d+)?)"
_DIMS = re.compile(rf"{NUM}\s*[×x]\s*{NUM}(?:\s*[×x]\s*{NUM})?(\s*(?:мм|см|м)(?![а-яё²]))?", re.I)
_RULES = (
    ("grade", re.compile(r"\b([МM]\d{3}|D\d{3})\b")),
    ("wear", re.compile(r"\b(\d{2})\s*класс")),
    ("pack", re.compile(rf"{NUM}\s*кг\b")),
    ("volume", re.compile(rf"{NUM}\s*(мл|л)(?![а-яё.])")),
    ("area", re.compile(rf"{NUM}\s*м²")),
    ("pieces", re.compile(r"\b(\d+)\s*шт\b")),
    ("power", re.compile(rf"{NUM}\s*(кВт|Вт)\b")),
    ("sections", re.compile(r"\b(\d+)\s*секци")),
    ("thread", re.compile(r'(\d/\d|\d)\s*"')),
)
_MM = re.compile(rf"{NUM}(?:/{NUM})?\s*мм\b")
_FRACTION = re.compile(rf"фр\.?\s*{NUM}\s*[–-]\s*{NUM}\s*мм", re.I)
_METERS = re.compile(rf"(?<![\d,]){NUM}\s*м(?![а-яё²a-z])", re.I)
_RAL = re.compile(r"\bRAL\s*(\d{4})\b", re.I)

# Толщина — у листов, плит и рулонов; диаметр — у труб и дымоходов; иначе просто «размер».
_THICK_WORDS = ("ламинат", "подложк", "поликарбонат", "гипсокартон", "минват", "металлочерепиц", "профнастил",
                "профиль соединительный", "профиль торцевой", "фанер", "осп", "osb", "пеноплэкс", "пенопласт", "шнур")
_DIAM_WORDS = ("труба", "муфта", "отвод", "тройник", "колено", "зонт", "хомут", "фитинг", "заглушк", "переходник")

# Цвета и декоры: длинные варианты раньше коротких («дуб серый» раньше «серый»).
_DECORS = ("дуб беленый", "дуб медовый", "дуб серый", "дуб светлый", "дуб натуральный", "орех тёмный",
           "плитка серая", "дуб", "ясень", "сосна", "венге", "бетон")
_COLORS = {
    "белый": ("белый", "белая", "белое"), "серый": ("серый", "серая", "серое"),
    "прозрачный": ("прозрачный", "прозрачная"), "бронза": ("бронза",), "зелёный": ("зелёный", "зеленый"),
    "коричневый": ("коричневый",), "чёрный": ("чёрный", "черный"), "хром": ("хром",), "антрацит": ("антрацит",),
    "серебро": ("серебро",), "жёлтый": ("жёлтый", "желтый"), "красный": ("красный",), "синий": ("синий",),
    "графит": ("графит",),
}


def _num(text):
    return text.replace(".", ",")


def parse(name):
    """{"pack": "25 кг", "thick": "8 мм", "color": "Дуб серый", ...} по наименованию товара."""
    text = " ".join(name.split())
    low = text.lower()
    attrs = {}

    dims = _DIMS.search(text)
    rest = text
    if dims:
        parts = [p for p in dims.groups()[:3] if p]
        unit = (dims.group(4) or "").strip()
        attrs["dims"] = "×".join(parts) + (f" {unit}" if unit else "")
        rest = text[:dims.start()] + " " + text[dims.end():]

    fraction = _FRACTION.search(rest)
    if fraction:
        attrs["fraction"] = f"{_num(fraction.group(1))}–{_num(fraction.group(2))} мм"
        rest = rest[:fraction.start()] + " " + rest[fraction.end():]

    for key, rx in _RULES:
        m = rx.search(rest)
        if not m:
            continue
        if key == "grade":
            value = m.group(1).replace("M", "М")
        elif key == "wear":
            value = f"{m.group(1)} класс"
        elif key in ("volume", "power"):
            value = f"{_num(m.group(1))} {m.group(2)}"
        elif key == "pieces":
            value = f"{m.group(1)} шт"
        elif key == "sections":
            value = m.group(1)
        elif key == "thread":
            value = f"{m.group(1)}″"
        else:
            value = f"{_num(m.group(1))} {'кг' if key == 'pack' else 'м²'}"
        attrs[key] = value

    mm = _MM.search(rest)
    if mm:
        key = ("thick" if any(w in low for w in _THICK_WORDS)
               else "diam" if any(w in low for w in _DIAM_WORDS) else "size")
        size = _num(mm.group(1)) + (f"/{_num(mm.group(2))}" if mm.group(2) else "")
        attrs[key] = f"{size} мм"
        rest = rest[:mm.start()] + " " + rest[mm.end():]

    meters = _METERS.search(rest)
    if meters:
        attrs["width" if "линолеум" in low else "length"] = f"{_num(meters.group(1))} м"

    ral = _RAL.search(text)
    if ral:
        attrs["color"] = f"RAL {ral.group(1)}"
    else:
        for decor in _DECORS:
            if re.search(rf"\b{decor}\b", low):
                attrs["color"] = decor.capitalize()
                break
        else:
            for color, forms in _COLORS.items():
                if any(re.search(rf"\b{f}\b", low) for f in forms):
                    attrs["color"] = color.capitalize()
                    break
    return attrs


def sort_key(value):
    """Числовая сортировка значений: «2 мм» < «10 мм», текст — по алфавиту после чисел."""
    m = re.match(r"(\d+(?:,\d+)?)", value)
    if m:
        try:
            return (0, Decimal(m.group(1).replace(",", ".")), value)
        except InvalidOperation:
            pass
    return (1, Decimal(0), value.lower())


def as_number(value):
    """Первое число значения: «2,4 м²» -> Decimal('2.4'); None, если числа нет."""
    m = re.match(r"(\d+(?:,\d+)?)", value or "")
    return Decimal(m.group(1).replace(",", ".")) if m else None


def dims_mm(value):
    """«600×300×200» -> [600, 300, 200] в миллиметрах; размеры в метрах и сантиметрах не берём."""
    if not value or value.endswith((" м", " см")):
        return []
    return [Decimal(p.replace(",", ".")) for p in value.replace(" мм", "").split("×")]


def facets(items, chosen, keys_limit=6):
    """Фильтры по свойствам для списка товаров.

    items — [(pk, attrs)], chosen — {ключ: {значения}}. Количество у значения считается по товарам,
    которые проходят все остальные выбранные свойства (как в больших магазинах: выбор цвета не обнуляет
    счётчики самих цветов). Показываются свойства, у которых в списке больше одного значения.
    """
    def passes(attrs, skip):
        return all(attrs.get(k) in vals for k, vals in chosen.items() if k != skip and vals)

    result = []
    for key, label in LABELS.items():
        counts = {}
        for _, attrs in items:
            value = attrs.get(key)
            if value and passes(attrs, key):
                counts[value] = counts.get(value, 0) + 1
        if len(counts) < 2 and not chosen.get(key):
            continue
        values = [{"value": v, "count": n, "checked": v in chosen.get(key, ())}
                  for v, n in sorted(counts.items(), key=lambda kv: sort_key(kv[0]))]
        result.append({"key": key, "param": f"f_{key}", "label": label, "values": values,
                       "active": bool(chosen.get(key))})
    # Самые полезные — у которых больше товаров покрыто свойством; выбранные — всегда.
    result.sort(key=lambda f: (not f["active"], -sum(v["count"] for v in f["values"])))
    return result[:max(keys_limit, sum(f["active"] for f in result))]


def labeled(attrs):
    """[(подпись, значение)] в порядке LABELS — для таблицы характеристик."""
    return [(label, attrs[key]) for key, label in LABELS.items() if attrs.get(key)]
