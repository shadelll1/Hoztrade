"""Калькуляторы «сколько нужно» на странице товара.

По товару определяется вид расчёта и его параметры; сам расчёт делает static/js/calc.js. Нормы расхода —
средние по типу материала (как у производителей на упаковке), в карточке они показываются покупателю.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from .attrs import as_number, dims_mm

D = Decimal
ZERO = Decimal(0)


@dataclass
class Calc:
    kind: str            # area | layer | rate | masonry | length | volume
    title: str
    per_unit: Decimal    # сколько даёт одна единица товара: м², кг, л, м² кладки или погонные метры
    reserve: int = 5     # запас, %
    rate: Decimal = ZERO       # расход: кг/м² на 1 мм слоя (layer) или кг|л на м² за слой (rate)
    thickness: Decimal = ZERO  # слой по умолчанию, мм
    layers: int = 1
    room: bool = False   # площадь — из длины и ширины комнаты
    note: str = ""
    fields: list = field(default_factory=list)

    def as_data(self):
        """data-атрибуты формы калькулятора."""
        return {"kind": self.kind, "per-unit": _s(self.per_unit), "reserve": self.reserve, "rate": _s(self.rate),
                "thickness": _s(self.thickness), "layers": self.layers}


def _s(value):
    return format(D(value).normalize(), "f")


# Смеси слоем: (слова в названии, кг на м² на 1 мм, слой по умолчанию, мм)
_LAYER = (
    (("штукатурка гипсовая", "ротбанд", "гипсвелл", "волма слой", "машинного нанесения"), D("0.9"), 10),
    (("штукатурка",), D("1.6"), 10),
    (("шпаклёвка полимерная",), D("0.6"), 2),
    (("шпаклёвка",), D("1.0"), 2),
    (("наливной пол",), D("1.6"), 10),
    (("стяжка",), D("1.9"), 30),
    (("гидроизоляция обмазочная",), D("1.5"), 2),
)
# Расход на м² за слой: (слова, норма, слоёв, что покрывают)
_RATE = (
    (("клей для керамогранита",), D("5.5"), 1, "Клей: ~5,5 кг на м² при плитке 30–60 см"),
    (("клей для плитки", "клей плиточный"), D("4.5"), 1, "Клей: ~4,5 кг на м² при плитке до 30 см"),
    (("затирка",), D("0.5"), 1, "Затирка: ~0,5 кг на м² при шве 2–3 мм"),
    (("бетоноконтакт",), D("0.35"), 1, "Расход ~0,35 кг на м²"),
    (("грунтовка", "грунт "), D("0.15"), 1, "Расход ~0,15 л на м² за слой"),
    (("водоэмульсионная",), D("0.2"), 2, "Расход ~0,2 кг на м² за слой"),
    (("фасадная",), D("0.25"), 2, "Расход ~0,25 кг на м² за слой"),
    (("интерьерная",), D("0.12"), 2, "Расход ~0,12 л на м² за слой"),
    (("антисептик",), D("0.2"), 2, "Расход ~0,2 л на м² за слой"),
    (("огнебиозащита",), D("0.3"), 2, "Расход ~0,3 л на м² за слой"),
    (("грунт-эмаль",), D("0.12"), 2, "Расход ~0,12 кг на м² за слой"),
)
_FLOOR = ("ламинат", "подложк", "линолеум")
_SHEETS = ("гипсокартон", "поликарбонат", "профнастил", "плита osb", "фанера", "ондулин")
_BLOCKS = ("блок", "кирпич облицовочный", "кирпич рядовой", "кирпич строительный", "пазогребневая")
_TIMBER = ("брус", "доска обрезная", "доска строганая", "брусок")
_LENGTHS = ("плинтус", "желоб", "профиль", "конёк", "планка", "уголок", "карниз")


def calculator(product):
    """Calc или None, если для товара расчёт не нужен (инструмент, сантехника и т. п.)."""
    name = product.title.lower()
    attrs = product.attrs or {}
    pack_kg = as_number(attrs.get("pack"))
    pack_l = as_number(attrs.get("volume"))
    if pack_l and attrs.get("volume", "").endswith("мл"):
        pack_l = pack_l / 1000

    for words, rate, thickness in _LAYER:
        if pack_kg and any(w in name for w in words):
            return Calc("layer", "Сколько смеси нужно", pack_kg, reserve=5, rate=rate, thickness=D(thickness),
                        note=f"Расход {_s(rate).replace('.', ',')} кг на м² при слое 1 мм, запас 5 %")

    for words, rate, layers, note in _RATE:
        pack = pack_kg or pack_l
        if pack and any(w in name for w in words):
            return Calc("rate", "Сколько нужно на площадь", pack, reserve=5, rate=rate, layers=layers,
                        note=f"{note}, запас 5 %")

    area = as_number(attrs.get("area"))
    if area and product.unit != "м2":
        floor = any(w in name for w in _FLOOR)
        reserve = 7 if "ламинат" in name else 10 if "мембран" in name or "изоспан" in name else 5
        return Calc("area", "Сколько упаковок нужно", area, reserve=reserve, room=floor,
                    note=f"В упаковке {attrs['area']}, запас {reserve} % на подрезку")
    if product.unit in ("м2", "м²"):
        reserve = 15 if "металлочерепиц" in name else 7
        return Calc("area", "Сколько квадратных метров нужно", D(1), reserve=reserve, room="линолеум" in name,
                    note=f"Запас {reserve} % на подрезку и нахлёсты")

    dims = dims_mm(attrs.get("dims"))
    if dims and len(dims) >= 2 and any(w in name for w in _SHEETS):
        sheet = dims[0] * dims[1] / D(1_000_000)
        return Calc("area", "Сколько листов нужно", sheet, reserve=10,
                    note=f"Лист {attrs['dims']} мм — {_s(sheet.quantize(D('0.01'))).replace('.', ',')} м², "
                         f"запас 10 %")
    if dims and len(dims) == 3 and "вагонка" in name:
        cover = dims[1] * dims[2] / D(1_000_000)
        return Calc("area", "Сколько досок нужно", cover, reserve=10,
                    note=f"Одна доска закрывает {_s(cover.quantize(D('0.001'))).replace('.', ',')} м², запас 10 %")
    if dims and len(dims) == 3 and any(w in name for w in _TIMBER):
        piece = dims[0] * dims[1] * dims[2] / D(1_000_000_000)
        return Calc("volume", "Сколько штук в нужном объёме", piece, reserve=0,
                    note=f"Одна штука — {_s(piece.quantize(D('0.0001'))).replace('.', ',')} м³, "
                         f"в кубе ~{int(D(1) / piece)} шт")
    if dims and len(dims) == 3 and any(w in name for w in _BLOCKS):
        face = dims[0] * dims[1] / D(1_000_000)
        return Calc("masonry", "Сколько блоков на стены", face, reserve=5,
                    note=f"Блок {attrs['dims']} мм кладётся длинной стороной вдоль стены, запас 5 %")

    length = as_number(attrs.get("length"))
    if length and product.unit == "шт" and any(w in name for w in _LENGTHS):
        return Calc("length", "Сколько штук нужно", length, reserve=5,
                    note=f"Длина одной — {attrs['length']}, запас 5 %")
    return None
