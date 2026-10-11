"""Картинки демо-товаров: фото с Pixabay (Pixabay Content License — можно на коммерческом сайте без указания
автора)
и рисунки в едином стиле для фасованного товара (мешки, вёдра, баллоны), где фото «безымянной» упаковки
вводило бы в заблуждение, и для редких товаров, которых на фотобанке нет.

Результат — папка 1c/demo-images/<артикул>.jpg (800×800) и credits.json (откуда каждое фото). В 1С:
раздел «Сайт» → «Загрузить картинки товаров из папки», затем «Выгрузить каталог на сайт».

  python 1c/tools/product_images.py search   — кандидаты с Pixabay и листы для выбора (ключ — 1c/tools/.pixabay-key)
  python 1c/tools/product_images.py build    — собрать картинки по выбору (CHOICES) и рисункам
"""
import io
import json
import re
import sys
import tempfile
import textwrap
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

TOOLS = Path(__file__).resolve().parent
OUT = TOOLS.parent / "demo-images"
# Скачанное с фотобанка — во временную папку, не в проект
CACHE = Path(tempfile.gettempdir()) / "hoztrade-pixabay"
FONTS = Path("C:/Windows/Fonts")
SIZE = 800
CANDIDATES = 8

# Понятие картинки -> запрос к Pixabay. Один снимок может подходить нескольким товарам (брус разных сечений).
PHOTO = {
    "brick-red": "red bricks stack",
    "brick-yellow": "yellow bricks",
    "brick-brown": "brown brick stack",
    "brick-white": "white silicate bricks",
    "aerated-block": "gas concrete block",
    "foam-block": "concrete blocks stack",
    "clay-block": "cinder blocks",
    "beam": "wooden beams lumber",
    "board": "wooden planks lumber stack",
    "batten": "wooden slats",
    "paneling": "wood paneling wall",
    "plywood": "plywood sheets",
    "osb": "osb board",
    "profnastil-red": "red corrugated metal sheet",
    "profnastil-green": "green corrugated metal roof",
    "profnastil-brown": "brown metal roof",
    "profnastil-zinc": "galvanized corrugated sheet",
    "metal-tile-red": "red metal roof tiles",
    "metal-tile-green": "green metal roof",
    "metal-tile-brown": "brown metal roof tiles",
    "ondulin-brown": "corrugated roof brown",
    "ondulin-green": "green corrugated roof",
    "ondulin-red": "red corrugated roof",
    "gutter": "rain gutter",
    "downpipe": "downspout",
    "mineral-wool": "mineral wool insulation",
    "xps": "insulation panels",
    "eps": "polystyrene insulation",
    "drywall": "plasterboard",
    "metal-profile": "metal studs drywall",
    "pp-pipe": "plastic water pipes",
    "sewer-pipe": "pvc pipes",
    "pp-fitting": "plastic pipe fittings",
    "sewer-fitting": "pvc pipe fittings",
    "ball-valve": "ball valve",
    "pipe-coil": "plastic pipe coil",
    "flex-hose": "braided hose",
    "faucet-kitchen": "kitchen faucet",
    "faucet-kitchen-black": "black kitchen faucet",
    "faucet-bath": "bathtub faucet",
    "faucet-sink": "bathroom faucet chrome",
    "shower": "shower head",
    "shower-hose": "shower hose",
    "water-heater": "electric boiler",
    "toilet": "white toilet bathroom",
    "sink": "white bathroom sink",
    "bathtub": "white bathtub",
    "siphon": "sink drain pipe",
    "radiator": "white radiator",
    "pump": "circulation pump heating",
    "expansion-tank": "expansion vessel heating",
    "laminate-oak": "oak laminate floor",
    "laminate-grey": "grey wood floor",
    "laminate-walnut": "walnut wood floor",
    "laminate-white": "white oak floor",
    "laminate-honey": "honey oak floor",
    "laminate-ash": "light wood floor",
    "laminate-smoked": "smoked oak floor",
    "laminate-dark": "dark wood floor",
    "laminate-pine": "pine wood floor",
    "laminate-scandi": "scandinavian wood floor",
    "laminate-wenge": "wenge dark wood",
    "laminate-concrete": "concrete floor texture",
    "cork": "cork texture",
    "baseboard": "baseboard floor",
    "linoleum-wood": "vinyl wood floor",
    "linoleum-tile": "grey tile floor",
    "linoleum-grey": "grey vinyl floor",
    "polycarbonate": "polycarbonate sheet",
    "polycarbonate-color": "greenhouse polycarbonate",
    "greenhouse": "greenhouse frame",
    "stove-door": "cast iron stove door",
    "grate": "fire grate",
    "stove-top": "cast iron stove top",
    "fire-brick": "refractory bricks",
    "chimney": "stainless steel chimney pipe",
    "paint-white": "white paint bucket",
    "sealant": "caulk",
    "liquid-nails": "silicone gun",
    "wood-screws": "wood screws",
    "roof-screws": "roofing screws",
    "metal-screws": "self tapping screws",
    "wall-plugs": "wall plugs",
    "anchor": "anchor bolts",
    "nails": "iron nails",
    "bracket": "angle bracket",
    "perforated-tape": "perforated metal strip",
    "pipe-clamp": "pipe clamp",
    "threaded-rod": "threaded rod",
    "putty-knife": "plastering trowel",
    "level": "spirit level",
    "wheelbarrow": "wheelbarrow",
    "trowel": "brick trowel",
    "straightedge": "aluminum level tool",
    "paint-roller": "paint roller",
    "paint-brush": "paint brush",
    "tape-measure": "tape measure",
    "utility-knife": "utility knife",
    "shovel": "shovel",
    "gloves": "work gloves",
    "mixer-paddle": "mixing mortar",
    "drill": "cordless drill",
    "hammer-drill": "hammer drill",
    "grinder": "angle grinder",
    "jigsaw": "jigsaw power tool",
    "mixer": "mortar mixer drill",
    "cutting-disc": "cutting disc",
}

# Артикул (регулярное выражение, первое совпадение) -> понятие из PHOTO или рисунок ("draw:<вид>").
RULES = [
    # Фасованные смеси — рисунок мешка с названием и весом
    (r"^(ЦМ|ПБ-|КС-|ПС-|КРЗ|ЩБ|ШТ-|ШП-(КМ|КФ|ВШ|ПФ|ФЦ)|КЛ-(CM|Ю)|НП-|ГИ-ОБ|ПЛ-СП|ПЛ-ГЛ|ЗТ-)", "draw:bag"),
    (r"^(ШП-ШР|ГР-БК|ГИ-МБ|ИН-ВД)", "draw:bucket"),
    (r"^(ГР-ГП|ГР-CT17|ГИ-ПР|АС-)", "draw:canister"),
    (r"^ЭМ-", "draw:can"),
    (r"^(ПН-МП|ПН-МБ|ПН-ОЧ)", "draw:spray"),
    (r"^(ГМ-75|ГМ-СД|ИЗ-|УТ-ФЛ|ЛН-ПИ|ЛН-СРП|ГИ-ЛН|ПД-XPS|ПД-ХВ|ПЛ-ШН)", "draw:roll"),
    (r"^(ПГП|ПР-ПДВ|ПР-КРБ|ПК-ТШ|ПК-НП|ПК-UP|ОН-ГВ|ОН-КН|КР-ГКЛ|ПЛТ-УГ|ПРГ-|ВН-ПР|СФ-ИНС|РД-КМ|ПЛ-ЗВ|ПЛ-ВК|ПЛ-ДШ|ДМ-ХМ)", "draw:part"),
    # Фото
    (r"^КР-П-|^КР-О-175", "brick-red"),
    (r"^КР-О-Ж", "brick-yellow"),
    (r"^КР-О-К", "brick-brown"),
    (r"^КР-С-", "brick-white"),
    (r"^ГБ-", "aerated-block"),
    (r"^ПБЛ-", "foam-block"),
    (r"^КЕБ-", "clay-block"),
    (r"^БР(-|\d)", "beam"),
    (r"^БРС-", "batten"),
    (r"^ДС-", "board"),
    (r"^ВГ-", "paneling"),
    (r"^ФН-", "plywood"),
    (r"^ОСП-", "osb"),
    (r"^ПН-С\d+-(2|3005)", "profnastil-red"),
    (r"^ПН-С\d+-6005", "profnastil-green"),
    (r"^ПН-С\d+-8017", "profnastil-brown"),
    (r"^ПН-С\d+-ОЦ", "profnastil-zinc"),
    (r"^МЧ-М-(045|8017)", "metal-tile-brown"),
    (r"^МЧ-М-3005", "metal-tile-red"),
    (r"^МЧ-М-6005", "metal-tile-green"),
    (r"^ОН-2000-З", "ondulin-green"),
    (r"^ОН-2000-К", "ondulin-red"),
    (r"^ОН-2000", "ondulin-brown"),
    (r"^КР-СК-", "roof-screws"),
    (r"^ВД-Ж", "gutter"),
    (r"^ВД-Т", "downpipe"),
    (r"^МВ-", "mineral-wool"),
    (r"^ПП-", "xps"),
    (r"^ППС", "eps"),
    (r"^ГКЛ", "drywall"),
    (r"^ПР-", "metal-profile"),
    (r"^ТР-PP", "pp-pipe"),
    (r"^ТР-К-", "sewer-pipe"),
    (r"^ТР-МП", "pipe-coil"),
    (r"^ФТ-(У|МФ)", "pp-fitting"),
    (r"^ФТ-", "sewer-fitting"),
    (r"^КШ-", "ball-valve"),
    (r"^ПВ-ГБ", "flex-hose"),
    (r"^СМ-К-05", "faucet-kitchen-black"),
    (r"^СМ-К-", "faucet-kitchen"),
    (r"^СМ-(В|ТС)-", "faucet-bath"),
    (r"^СМ-Р-", "faucet-sink"),
    (r"^(СМ-Д|ДШ-ЛК)", "shower"),
    (r"^ДШ-ШЛ", "shower-hose"),
    (r"^ВН-", "water-heater"),
    (r"^СФ-УН", "toilet"),
    (r"^СФ-(РК|ПД)", "sink"),
    (r"^СФ-ВН", "bathtub"),
    (r"^СФ-СФ", "siphon"),
    (r"^РД-(БМ|АЛ)", "radiator"),
    (r"^РД-НС", "pump"),
    (r"^РД-БК", "expansion-tank"),
    (r"^ЛМ-33-ДН", "laminate-oak"),
    (r"^ЛМ-(32-ДС|ВЛ-ДС)", "laminate-grey"),
    (r"^ЛМ-34-ОР", "laminate-walnut"),
    (r"^ЛМ-32-ДБ", "laminate-white"),
    (r"^ЛМ-32-ДМ", "laminate-honey"),
    (r"^ЛМ-32-ЯС", "laminate-ash"),
    (r"^ЛМ-33-ДД", "laminate-smoked"),
    (r"^ЛМ-33-ОТ", "laminate-dark"),
    (r"^ЛМ-33-СС", "laminate-pine"),
    (r"^ЛМ-34-ДС", "laminate-scandi"),
    (r"^ЛМ-34-ВН", "laminate-wenge"),
    (r"^ЛМ-ВЛ-БТ", "laminate-concrete"),
    (r"^ПД-ПРБ", "cork"),
    (r"^ПЛТ-", "baseboard"),
    (r"^ЛН-Б-ДС|^ЛН-ПК", "linoleum-wood"),
    (r"^ЛН-Б-ПС", "linoleum-tile"),
    (r"^ЛН-К", "linoleum-grey"),
    (r"^ПК-С-\d+(П|-12)?$", "polycarbonate"),
    (r"^ПК-С-", "polycarbonate-color"),
    (r"^ПК-М-", "polycarbonate"),
    (r"^ТП-", "greenhouse"),
    (r"^ПЛ-(ДТ|ДП)", "stove-door"),
    (r"^ПЛ-(РД|РУ)", "grate"),
    (r"^ПЛ-П\d", "stove-top"),
    (r"^ПЛ-ША", "fire-brick"),
    (r"^ДМ-", "chimney"),
    (r"^КРС-", "paint-white"),
    (r"^ГМ-(СС|СУ|АК)", "sealant"),
    (r"^КЛ-ЖГ", "liquid-nails"),
    (r"^КР-СД", "wood-screws"),
    (r"^КР-СМ", "metal-screws"),
    (r"^КР-(ДГ|ДР)", "wall-plugs"),
    (r"^КР-АБ", "anchor"),
    (r"^КР-ГВ", "nails"),
    (r"^КР-УГ", "bracket"),
    (r"^КР-ЛП", "perforated-tape"),
    (r"^КР-ХТ", "pipe-clamp"),
    (r"^КР-ШП", "threaded-rod"),
    (r"^ИН-ШП", "putty-knife"),
    (r"^ИН-УР", "level"),
    (r"^ИН-ТЧ", "wheelbarrow"),
    (r"^ИН-КЛ", "trowel"),
    (r"^ИН-ПР-", "straightedge"),
    (r"^ИН-ВЛ", "paint-roller"),
    (r"^ИН-КС", "paint-brush"),
        (r"^ИН-РЛ", "tape-measure"),
    (r"^ИН-НЖ", "utility-knife"),
    (r"^ИН-ЛП", "shovel"),
    (r"^ИН-ПРЧ", "gloves"),
    (r"^ИН-МКС", "mixer-paddle"),
    (r"^ЭИ-ДШ", "drill"),
    (r"^ЭИ-ПФ", "hammer-drill"),
    (r"^ЭИ-УШМ", "grinder"),
    (r"^ЭИ-ЛБ", "jigsaw"),
    (r"^ЭИ-МКС", "mixer"),
    (r"^ЭИ-КР", "cutting-disc"),
]

# Понятие -> номер кандидата из search (1..8) или «понятие:номер» (снимок другого понятия), по листам выбора.
# Нет в словаре или 0 — подходящего фото нет, товар получает рисунок.
CHOICES = {
    "anchor": 2, "baseboard": 6, "bathtub": 5, "batten": 6, "beam": 1, "board": 4, "brick-brown": 5, "brick-red": 5,
    "brick-white": 1, "brick-yellow": 5, "chimney": 2, "clay-block": 6, "cork": 6, "cutting-disc": 1, "downpipe": 4,
    "drill": 4, "faucet-bath": 6, "faucet-kitchen": 4, "faucet-kitchen-black": 1, "faucet-sink": 6,
    "flex-hose": 1, "foam-block": 3, "gloves": 1, "greenhouse": 7, "grinder": 1, "gutter": 6, "hammer-drill": 6,
    "jigsaw": 1, "laminate-ash": "laminate-pine:2", "laminate-concrete": 6, "laminate-dark": "laminate-scandi:5",
    "laminate-grey": 3, "laminate-honey": 1, "laminate-oak": 1, "laminate-pine": 4, "laminate-scandi": 3,
    "laminate-smoked": "laminate-oak:5", "laminate-walnut": 4, "laminate-wenge": "laminate-smoked:3",
    "laminate-white": "laminate-smoked:4", "level": 2, "linoleum-grey": "laminate-concrete:6", "linoleum-tile": 7,
    "linoleum-wood": 2, "metal-profile": 3, "metal-screws": "wood-screws:3", "metal-tile-brown": "profnastil-brown:1",
    "metal-tile-green": 1, "metal-tile-red": 1, "mineral-wool": 1, "ondulin-brown": 2, "ondulin-green": 6,
    "ondulin-red": 1, "osb": 1, "paint-brush": "paint-white:2", "paint-roller": 5, "paint-white": 4,
    "paneling": 5, "perforated-tape": 2, "pipe-clamp": 1, "pipe-coil": 1, "plywood": 1, "polycarbonate": 3,
    "polycarbonate-color": "polycarbonate:1", "pp-fitting": 6, "pp-pipe": "pp-fitting:8", "profnastil-brown": 5,
    "profnastil-green": 2, "profnastil-red": "ondulin-red:1", "profnastil-zinc": 5, "pump": 2, "radiator": 4,
    "roof-screws": "wood-screws:3", "sewer-fitting": 1, "sewer-pipe": 2, "shovel": 8, "shower": 5,
    "shower-hose": 5, "sink": 8, "siphon": 1, "stove-door": 1, "stove-top": 6, "straightedge": 7,
    "tape-measure": 5, "threaded-rod": 5, "toilet": 8, "trowel": "putty-knife:1", "utility-knife": 8,
    "wall-plugs": 6, "wheelbarrow": 4, "wood-screws": 4,
    # второй круг поиска (retry)
    "ball-valve": "ball-valve~2:2", "eps": "eps~2:1", "nails": "nails~2:4",
    "putty-knife": "putty-knife~2:2", "sealant": "sealant~2:3",
}


def products():
    """Артикул -> (название, раздел, группа) из демо-каталога сайта."""
    sys.path.insert(0, str(TOOLS.parents[1] / "site"))
    from catalog.demo_data import CATALOG
    from catalog.demo_data_extra import EXTRA

    result = {}
    for source in (CATALOG, EXTRA):
        for section, groups in source.items():
            for group, rows in groups.items():
                for row in rows:
                    result.setdefault(row[1], (row[0], section, group))
    return result


def concept(sku):
    for pattern, name in RULES:
        if re.search(pattern, sku):
            return name
    return None


# ---------------------------------------------------------------------------------------------------------
# Pixabay: кандидаты и листы для выбора

def api_key():
    return (TOOLS / ".pixabay-key").read_text(encoding="utf-8-sig").strip()


def fetch(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "Hoztrade-catalog/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def search(retry=False):
    """Кандидаты по запросам PHOTO. retry — новый круг для понятий без выбранного фото: кандидаты пишутся
    под именем «понятие~2», выбор первого круга не теряется."""
    key = api_key()
    CACHE.mkdir(parents=True, exist_ok=True)
    meta_path = CACHE / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if retry and meta_path.exists() else {}
    used = sorted({concept(s) for s in products()} & set(PHOTO))
    if retry:
        used = [name for name in used if not CHOICES.get(name)]
    keys = []
    for name in used:
        query = urllib.parse.urlencode({"key": key, "q": PHOTO[name], "image_type": "photo", "per_page": CANDIDATES,
                                        "safesearch": "true", "order": "popular"})
        hits = json.loads(fetch("https://pixabay.com/api/?" + query))["hits"][:CANDIDATES]
        time.sleep(0.8)  # лимит API — 100 запросов в минуту
        key_name = f"{name}~2" if retry else name
        meta[key_name] = [{"id": h["id"], "page": h["pageURL"], "user": h["user"], "tags": h["tags"],
                           "large": h["largeImageURL"]} for h in hits]
        folder = CACHE / key_name
        folder.mkdir(exist_ok=True)
        for i, hit in enumerate(hits, 1):
            (folder / f"{i}.jpg").write_bytes(fetch(hit["webformatURL"]))
        keys.append(key_name)
        print(f"{key_name}: {len(hits)}")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets(keys, prefix="retry" if retry else "sheet")


def candidate(meta, name, choice):
    """Снимок по выбору: номер кандидата понятия или «понятие:номер»."""
    if isinstance(choice, str):
        name, _, number = choice.rpartition(":")
        choice = int(number)
    return meta[name][choice - 1]


def sheets(names, per_sheet=7, thumb=150, prefix="sheet"):
    label_w = 170
    for start in range(0, len(names), per_sheet):
        chunk = names[start:start + per_sheet]
        sheet = Image.new("RGB", (label_w + CANDIDATES * (thumb + 6), len(chunk) * (thumb + 6)), "white")
        d = ImageDraw.Draw(sheet)
        for row, name in enumerate(chunk):
            y = row * (thumb + 6)
            d.text((4, y + 4), name, font=font("arialbd.ttf", 16), fill="black")
            for line, part in enumerate(textwrap.wrap(PHOTO[name.split("~")[0]], 18)):
                d.text((4, y + 28 + line * 18), part, font=font("arial.ttf", 14), fill=(90, 90, 90))
            for i in range(1, CANDIDATES + 1):
                path = CACHE / name / f"{i}.jpg"
                x = label_w + (i - 1) * (thumb + 6)
                if path.exists():
                    with Image.open(path) as img:
                        sheet.paste(ImageOps.fit(img.convert("RGB"), (thumb, thumb)), (x, y))
                d.rectangle((x, y, x + 22, y + 20), fill="black")
                d.text((x + 6, y + 1), str(i), font=font("arialbd.ttf", 15), fill="white")
        out = CACHE / f"{prefix}-{start // per_sheet + 1:02d}.jpg"
        sheet.save(out, quality=85)
        print(out)


# ---------------------------------------------------------------------------------------------------------
# Рисунки упаковки: мешок, ведро, канистра, банка, баллон, рулон, коробка — с названием товара на этикетке

BG = (246, 247, 245)
INK = (34, 40, 46)
# Цвет этикетки по разделу каталога
BANDS = {
    "Стройматериалы": (30, 79, 138),
    "Сухие смеси": (21, 128, 61),
    "Сантехника": (14, 116, 144),
    "Ламинат и напольные покрытия": (146, 64, 14),
    "Поликарбонат": (2, 132, 199),
    "Печное литьё": (153, 27, 27),
    "Краски и химия": (180, 83, 9),
    "Крепёж и инструмент": (71, 85, 105),
}
UNIT = r"\d+(?:[,.]\d+)?\s*(?:кг|мл|л|м²|м|шт)\b"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def fit(draw, text, width, size, bold=True):
    name = "arialbd.ttf" if bold else "arial.ttf"
    while size > 14 and draw.textlength(text, font=font(name, size)) > width:
        size -= 2
    return font(name, size)


def label_text(name):
    """«Штукатурка гипсовая Кнауф Ротбанд 30 кг» -> ("ШТУКАТУРКА", ["гипсовая Кнауф", "Ротбанд"], "30 кг")."""
    matches = list(re.finditer(UNIT, name))
    amount = matches[-1].group(0) if matches else ""
    rest = name[:matches[-1].start()] + name[matches[-1].end():] if matches else name
    rest = re.sub(r"\s*,\s*(,|$)", r"\1", rest).strip(" ,")
    title, _, tail = rest.partition(" ")
    return title.upper(), textwrap.wrap(tail.strip(" ,"), 20)[:3], amount


def shadow(img, box, strength=110):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=strength)
    img.paste((150, 155, 150), (0, 0), mask.filter(ImageFilter.GaussianBlur(18)))


def darker(color, by=22):
    return tuple(max(0, c - by) for c in color)


def label(d, box, name, band):
    """Этикетка с названием; возвращает фасовку («30 кг») для плашки."""
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=band)
    title, lines, amount = label_text(name)
    width = x1 - x0 - 30
    f = fit(d, title, width, 50)
    y = y0 + 14
    d.text(((x0 + x1 - d.textlength(title, font=f)) / 2, y), title, font=f, fill="white")
    y += f.size + 12
    for line in lines:
        f2 = fit(d, line, width, 30, bold=False)
        d.text(((x0 + x1 - d.textlength(line, font=f2)) / 2, y), line, font=f2, fill="white")
        y += f2.size + 6
    return amount


def badge(d, cx, y, amount):
    if amount:
        f = font("arialbd.ttf", 40)
        w = d.textlength(amount, font=f)
        d.rounded_rectangle((cx - w / 2 - 20, y, cx + w / 2 + 20, y + 66), radius=16, fill="white")
        d.text((cx - w / 2, y + 10), amount, font=f, fill=INK)


def draw_bag(name, band):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (170, 690, 630, 745))
    d = ImageDraw.Draw(img)
    color = (214, 208, 200)
    d.rounded_rectangle((190, 110, 610, 715), radius=46, fill=color)
    d.rounded_rectangle((190, 110, 222, 715), radius=20, fill=darker(color))
    d.rounded_rectangle((578, 110, 610, 715), radius=20, fill=darker(color))
    d.rectangle((210, 110, 590, 140), fill=darker(color, 12))
    for x in range(222, 580, 18):
        d.line((x, 126, x + 9, 126), fill=darker(color), width=3)
    badge(d, 400, 520, label(d, (222, 210, 578, 470), name, band))
    f = font("arialbd.ttf", 28)
    d.text((400 - d.textlength("ХОЗТРЕЙД", font=f) / 2, 640), "ХОЗТРЕЙД", font=f, fill=darker(color, 60))
    return img


def draw_bucket(name, band):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (180, 680, 620, 740))
    d = ImageDraw.Draw(img)
    d.polygon([(190, 190), (610, 190), (575, 710), (225, 710)], fill=(250, 250, 250), outline=(215, 215, 215))
    d.rounded_rectangle((175, 150, 625, 200), radius=14, fill=(235, 236, 236), outline=(205, 205, 205))
    d.arc((210, 60, 590, 330), 200, 340, fill=(120, 125, 130), width=8)
    badge(d, 400, 560, label(d, (205, 260, 595, 500), name, band))
    return img


def draw_canister(name, band):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (190, 690, 610, 745))
    d = ImageDraw.Draw(img)
    body = (236, 238, 240)
    d.rounded_rectangle((210, 170, 590, 715), radius=40, fill=body, outline=(205, 208, 210))
    d.rounded_rectangle((420, 90, 570, 190), radius=30, fill=body, outline=(205, 208, 210))
    d.rounded_rectangle((450, 115, 540, 165), radius=18, fill=BG)
    d.rounded_rectangle((250, 120, 330, 180), radius=10, fill=band)
    badge(d, 400, 580, label(d, (230, 270, 570, 520), name, band))
    return img


def draw_can(name, band):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (190, 680, 610, 740))
    d = ImageDraw.Draw(img)
    metal = (200, 204, 208)
    d.rectangle((210, 200, 590, 680), fill=metal)
    d.ellipse((210, 640, 590, 720), fill=metal)
    d.ellipse((210, 160, 590, 240), fill=(220, 223, 226), outline=(170, 174, 178), width=4)
    d.ellipse((240, 172, 560, 228), outline=(170, 174, 178), width=3)
    badge(d, 400, 570, label(d, (210, 280, 590, 540), name, band))
    return img


def draw_spray(name, band):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (250, 700, 550, 750))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((270, 190, 530, 720), radius=36, fill=(225, 228, 231))
    d.rounded_rectangle((320, 120, 480, 200), radius=20, fill=(60, 66, 72))
    d.rectangle((380, 80, 420, 125), fill=(60, 66, 72))
    d.rectangle((420, 88, 520, 104), fill=(60, 66, 72))
    badge(d, 400, 600, label(d, (270, 270, 530, 560), name, band))
    return img


def draw_roll(name, band):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (140, 640, 660, 710))
    d = ImageDraw.Draw(img)
    face = (232, 234, 236)
    d.rectangle((210, 170, 590, 660), fill=face)
    d.ellipse((210, 610, 590, 710), fill=face)
    d.ellipse((210, 120, 590, 220), fill=(244, 245, 246), outline=(200, 203, 206), width=3)
    for r in range(30, 180, 26):
        d.ellipse((400 - r, 170 - r * 0.26, 400 + r, 170 + r * 0.26), outline=(210, 212, 215), width=2)
    d.ellipse((370, 160, 430, 180), fill=(120, 110, 95))
    badge(d, 400, 560, label(d, (210, 270, 590, 520), name, band))
    return img


def draw_part(name, band):
    """Коробка с этикеткой — мелкие детали и товары, которых нет на фотобанке."""
    img = Image.new("RGB", (SIZE, SIZE), BG)
    shadow(img, (150, 650, 650, 720))
    d = ImageDraw.Draw(img)
    kraft = (205, 170, 125)
    d.polygon([(160, 250), (520, 250), (640, 170), (280, 170)], fill=(222, 190, 146))
    d.polygon([(520, 250), (640, 170), (640, 600), (520, 690)], fill=darker(kraft, 30))
    d.rectangle((160, 250, 520, 690), fill=kraft)
    d.rectangle((310, 250, 370, 330), fill=(232, 205, 165))
    badge(d, 340, 605, label(d, (180, 340, 500, 590), name, band))
    return img


DRAW = {"bag": draw_bag, "bucket": draw_bucket, "canister": draw_canister, "can": draw_can, "spray": draw_spray,
        "roll": draw_roll, "part": draw_part}


def save(img, path):
    img.convert("RGB").save(path, "JPEG", quality=85, optimize=True, progressive=True)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    meta_path = CACHE / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    credits, large = {}, {}
    for sku, (name, section, _group) in sorted(products().items()):
        kind = concept(sku)
        choice = CHOICES.get(kind, 0)
        if not kind.startswith("draw:") and choice:
            hit = candidate(meta, kind, choice)
            if hit["id"] not in large:
                with Image.open(io.BytesIO(fetch(hit["large"]))) as src:
                    large[hit["id"]] = ImageOps.fit(ImageOps.exif_transpose(src).convert("RGB"), (SIZE, SIZE),
                                                    Image.LANCZOS)
            save(large[hit["id"]], OUT / f"{sku}.jpg")
            credits[sku] = {"source": "Pixabay", "id": hit["id"], "page": hit["page"], "author": hit["user"]}
        else:
            painter = DRAW[kind.split(":", 1)[1]] if kind.startswith("draw:") else draw_part
            save(painter(name, BANDS.get(section, INK)), OUT / f"{sku}.jpg")
            credits[sku] = {"source": "рисунок (1c/tools/product_images.py)"}
    (OUT / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    photos = sum(1 for c in credits.values() if c["source"] == "Pixabay")
    print(f"{OUT}: {len(credits)} картинок, из них фото {photos}, рисунков {len(credits) - photos}")


def check():
    items = products()
    missing = [sku for sku in items if concept(sku) is None]
    used = {concept(s) for s in items}
    print(f"товаров {len(items)}, без правила {len(missing)}: {missing}")
    print(f"понятий без запроса: {used - set(PHOTO) - {c for c in used if c.startswith('draw:')}}; "
          f"запросов без товаров: {set(PHOTO) - used}")


if __name__ == "__main__":
    {"search": search, "retry": lambda: search(retry=True), "build": build, "check": check}[
        sys.argv[1] if len(sys.argv) > 1 else "check"]()


