"""Товарные картинки 299 демо-товаров: единый «студийный» вид — товар на белом фоне с мягкой тенью, 1000×1000.

Два источника:
  * фото со стоков (Pixabay Content License, Openverse CC0/PD) — для изделий, которые там есть в нормальном виде
    (смесители, инструмент, крепёж). Фон вырезается нейросетью ISNet (onnxruntime, модель — в .image-cache),
    товар ставится в кадр по общим правилам;
  * рисунки (packshot_items, packshot_goods) — для фасовки и материалов, которых на стоках нет: мешки, вёдра,
    листы, трубы, профиль, кровля, печное литьё. Этикетка — текст из названия товара, без чужих логотипов.

Результат — 1c/demo-images/<артикул>.jpg и credits.json. В 1С: «Сайт» → «Загрузить картинки товаров из папки».

Окружение (одно на инструменты картинок): python -m venv 1c/tools/.venv-images,
pip install onnxruntime pillow numpy; модель isnet-general-use.onnx — в 1c/tools/.image-cache/models.

  python 1c/tools/product_images.py                 — все товары
  python 1c/tools/product_images.py ЦМ- ПН-С8       — только артикулы с такими началами
  python 1c/tools/product_images.py --sheet out.jpg — плюс контрольный лист всех картинок
"""
import io
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import packshot_goods as g
import packshot_items as it

TOOLS = Path(__file__).resolve().parent
OUT = TOOLS.parent / "demo-images"
CACHE = TOOLS / ".image-cache"
SIZE = 1000

# ---------------------------------------------------------------------------------------------------------
# Что рисуем или чьё фото берём. Артикул (регулярное выражение, первое совпадение) -> действие.
# ("photo", "понятие:код"[, кадр[, стереть]]) — кандидат из листов stock_search.py; кадр (x0, y0, x1, y1) — часть
# снимка в долях ширины/высоты, стереть — прямоугольники (в долях кадра), которые убрать из маски товара;
# иначе — функция рисунка (sku, name) -> Image.

RAL = {"3005": "#5e2129", "6005": "#1f4a36", "8017": "#45322e", "ОЦ": "#b9c0c7"}
PC = {"П": "#e2f0f7", "Б": "#c69c5d", "З": "#8fcf9a", "С": "#7fb3e6"}


def kg_of(name):
    m = re.search(r"(\d+(?:[,.]\d+)?)\s*кг", name)
    return float(m.group(1).replace(",", ".")) if m else 25


def mm(name, n=0):
    return [float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:,\d+)?)", name)][n]


def pc_color(sku):
    m = re.search(r"\d+([ПБЗС])", sku)
    return PC[m.group(1)] if m else PC["П"]


RULES = [
    # Фасовка
    (r"^(ГР-БК|ШП-ШР|КРС-)", lambda s, n: it.bucket(n)),
    (r"^ГИ-МБ", lambda s, n: it.bucket(n, white_lid=False, color="#2b2e33")),
    (r"^(ГР-ГП|ГР-CT17|АС-|ГИ-ПР)", lambda s, n: it.canister(n)),
    (r"^ЭМ-", lambda s, n: it.paint_can(n)),
    (r"^ПН-(МП|МБ|ОЧ)", lambda s, n: it.aerosol(n, color={"ПН-МП": "#e8590c", "ПН-МБ": "#f08c00",
                                                       "ПН-ОЧ": "#5f3dc4"}[s[:5]], straw=s.startswith("ПН-МБ"))),
    (r"^(ГМ-СС|ГМ-СУ|ГМ-АК|КЛ-ЖГ)", lambda s, n: it.cartridge(n)),
    (r"^(ГМ-75|ГМ-СД|ИЗ-)", lambda s, n: it.roll(n, color="#eef1f4")),
    (r"^(ГИ-ЛН|ЛН-ПИ)", lambda s, n: it.tape_roll(n, color="#9aa3ad" if s.startswith("ГИ") else "#e9ecef")),
    (r"^ЛН-СРП", lambda s, n: it.tape_roll(n, color="#f1f3f5", mesh=True)),
    (r"^(ЦМ|ПБ-|КС-|ПС-|КРЗ|ЩБ|ШТ-|ШП-|КЛ-(CM|Ю)|НП-|ГИ-ОБ|ПЛ-СП|ПЛ-ГЛ|ЗТ-)", lambda s, n: it.bag(n, kg_of(n))),
    # Кладка
    (r"^КР-П-", lambda s, n: g.bricks("#a9472a")),
    (r"^КР-О-175", lambda s, n: g.bricks("#b9532e")),
    (r"^КР-О-Ж", lambda s, n: g.bricks("#d7b36a")),
    (r"^КР-О-К", lambda s, n: g.bricks("#6e4430")),
    (r"^КР-С-", lambda s, n: g.bricks("#e4e1d8", size=(0.25, 0.088, 0.12))),
    (r"^ГБ-", lambda s, n: g.blocks("aerated", (0.6, 0.3, mm(n, 3) / 1000))),
    (r"^ПБЛ-", lambda s, n: g.blocks("foam", (0.6, 0.3, 0.2))),
    (r"^КЕБ-", lambda s, n: g.blocks("keramzit", (0.39, 0.188, 0.19))),
    (r"^ПГП-80В", lambda s, n: g.blocks("pgp-green", (0.667, 0.5, 0.08))),
    (r"^ПГП-", lambda s, n: g.blocks("pgp", (0.667, 0.5, 0.08))),
    (r"^ПЛ-ША", lambda s, n: g.fireclay_bricks()),
    # Пиломатериалы и листы
    (r"^БРС-", lambda s, n: g.lumber((0.03, 0.04), 1.6, 6)),
    (r"^БР-50", lambda s, n: g.lumber((0.05, 0.05), 1.6, 4)),
    (r"^БР-", lambda s, n: g.lumber((mm(n, 0) / 1000, mm(n, 1) / 1000), 1.6, 3)),
    (r"^ДС-", lambda s, n: g.lumber((mm(n, 1) / 1000, mm(n, 0) / 1000), 1.6, 4)),
    (r"^ВГ-", lambda s, n: g.paneling()),
    (r"^ФН-", lambda s, n: g.sheet_stack("plywood", 1.525, 1.525, mm(n, 2) / 1000 * 3, 5)),
    (r"^ОСП-", lambda s, n: g.sheet_stack("osb", 2.5, 1.25, mm(n, 1) / 1000 * 2, 5)),
    (r"^ГКЛВ", lambda s, n: g.sheet_stack("gklv")),
    (r"^ГКЛО", lambda s, n: g.sheet_stack("gklo")),
    (r"^ГКЛ-", lambda s, n: g.sheet_stack("gkl")),
    (r"^ПП-", lambda s, n: g.sheet_stack("xps", 1.2, 0.6, 0.05 if "50" in s else 0.04, 6)),
    (r"^ППС", lambda s, n: g.sheet_stack("eps", 1.0, 1.0, 0.05, 5)),
    (r"^МВ-", lambda s, n: g.wool_pack(n, "#dfe9d8")),
    (r"^УТ-ФЛ", lambda s, n: g.foil_roll(n)),
    # Кровля
    (r"^ПН-С8-", lambda s, n: g.corrugated(RAL[s.split("-")[-1]] if s.split("-")[-1] in RAL else RAL["3005"], "c8")),
    (r"^ПН-С20-", lambda s, n: g.corrugated(RAL[s.split("-")[-1]], "c20")),
    (r"^МЧ-М-(045|8017)", lambda s, n: g.corrugated(RAL["8017"], "tile")),
    (r"^МЧ-М-", lambda s, n: g.corrugated(RAL[s.split("-")[-1]], "tile")),
    (r"^ОН-2000-З", lambda s, n: g.corrugated("#2f4a2e", "ondulin")),
    (r"^ОН-2000-К", lambda s, n: g.corrugated("#7a2a24", "ondulin")),
    (r"^ОН-2000", lambda s, n: g.corrugated("#5a3e2b", "ondulin")),
    (r"^ОН-КН", lambda s, n: g.ridge("#5a3e2b")),
    (r"^ОН-ГВ", lambda s, n: g.hanger_pack(n)),
    (r"^КР-СК-6005", lambda s, n: g.roof_screws(RAL["6005"])),
    (r"^КР-СК-", lambda s, n: g.roof_screws(RAL["3005"])),
    (r"^ВД-Ж", lambda s, n: g.gutter("#4a3426", "gutter")),
    (r"^ВД-Т", lambda s, n: g.gutter("#4a3426", "pipe")),
    # Профиль для ГКЛ
    (r"^ПР-ПП", lambda s, n: g.metal_profile("pp")),
    (r"^ПР-ПН-50", lambda s, n: g.metal_profile("pn50")),
    (r"^ПР-ПН", lambda s, n: g.metal_profile("pn")),
    (r"^ПР-ПС", lambda s, n: g.metal_profile("ps")),
    (r"^(ПР-ПДВ|ПР-КРБ|ПЛТ-УГ)", lambda s, n: g.hanger_pack(n)),
    (r"^КР-ГКЛ", ("photo", "wood-screws:a3")),
    # Сантехника
    (r"^ТР-PP-", lambda s, n: g.pipe("#f1f3f5", mm(n, 1) / 1000 * 1.4, 1.3, socket=False, count=5)),
    (r"^ТР-К-", lambda s, n: g.pipe("#9aa0a6", mm(n, 0) / 1000 * 0.45 + 0.012, 1.3 if "-1" not in s[6:] else 0.8)),
    (r"^ТР-МП", lambda s, n: g.pipe_coil()),
    (r"^ФТ-У-", lambda s, n: g.elbow("#f1f3f5", 0.04, 90, sockets=False)),
    (r"^ФТ-МФ", lambda s, n: g.coupling("#f1f3f5")),
    (r"^ФТ-ТР", lambda s, n: g.tee("#9aa0a6")),
    (r"^ФТ-ОТ-.*-45", lambda s, n: g.elbow("#9aa0a6", 0.055, 45)),
    (r"^ФТ-ОТ-", lambda s, n: g.elbow("#9aa0a6", 0.055, 87)),
    (r"^КШ-", lambda s, n: g.ball_valve(0.5 if "12" in s else 0.8)),
    (r"^ПВ-ГБ", ("photo", "flex-hose:b1")),
    (r"^СМ-К-05", ("photo", "faucet-kitchen:b2")),
    (r"^СМ-К-", ("photo", "faucet-kitchen:b5")),
    (r"^СМ-(В|ТС)-", ("photo", "faucet-bath:c1")),
    (r"^СМ-Р-", ("photo", "faucet-sink:a1")),
    (r"^(СМ-Д|ДШ-ЛК)", ("photo", "shower:a1")),
    (r"^ДШ-ШЛ", ("photo", "shower-hose:b5")),
    (r"^ВН-ПР", lambda s, n: g.water_heater(flow=True)),
    (r"^ВН-", lambda s, n: g.water_heater(mm(n, 0))),
    (r"^СФ-УН", lambda s, n: g.toilet()),
    (r"^СФ-РК", lambda s, n: g.sink()),
    (r"^СФ-ПД", lambda s, n: g.sink(pedestal=True)),
    (r"^СФ-ВН", lambda s, n: g.bathtub()),
    (r"^СФ-СФ", lambda s, n: g.siphon()),
    (r"^СФ-ИНС", lambda s, n: g.installation()),
    (r"^РД-(БМ|АЛ)", lambda s, n: g.radiator(int(re.search(r"(\d+) секц", n).group(1)))),
    (r"^РД-КМ", lambda s, n: g.mayevsky()),
    (r"^РД-НС", ("photo", "pump:b1")),
    (r"^РД-БК", lambda s, n: g.expansion_tank()),
    # Полы
    (r"^ЛМ-33-ДН", lambda s, n: g.laminate_pack("oak", 8, n)),
    (r"^ЛМ-(32|ВЛ)-ДС", lambda s, n: g.laminate_pack("oak-grey", 8, n)),
    (r"^ЛМ-34-ОР", lambda s, n: g.laminate_pack("walnut", 12, n)),
    (r"^ЛМ-32-ДБ", lambda s, n: g.laminate_pack("oak-white", 8, n)),
    (r"^ЛМ-32-ДМ", lambda s, n: g.laminate_pack("oak-honey", 8, n)),
    (r"^ЛМ-32-ЯС", lambda s, n: g.laminate_pack("ash", 8, n)),
    (r"^ЛМ-33-ДД", lambda s, n: g.laminate_pack("smoked", 8, n)),
    (r"^ЛМ-33-ОТ", lambda s, n: g.laminate_pack("walnut-dark", 10, n)),
    (r"^ЛМ-33-СС", lambda s, n: g.laminate_pack("pine", 10, n)),
    (r"^ЛМ-34-ДС", lambda s, n: g.laminate_pack("scandi", 12, n)),
    (r"^ЛМ-34-ВН", lambda s, n: g.laminate_pack("wenge", 12, n)),
    (r"^ЛМ-ВЛ-БТ", lambda s, n: g.laminate_pack("concrete", 8, n)),
    (r"^ПД-ХВ", lambda s, n: g.underlay("board")),
    (r"^ПД-ПРБ", lambda s, n: g.underlay("cork", n)),
    (r"^ПД-", lambda s, n: g.underlay("xps", n)),
    (r"^ПЛТ-58-ДН", lambda s, n: g.baseboard("oak")),
    (r"^ПЛТ-58-ДС", lambda s, n: g.baseboard("oak-grey")),
    (r"^ПЛТ-58-ВН", lambda s, n: g.baseboard("wenge")),
    (r"^ПРГ-30", lambda s, n: g.threshold()),
    (r"^ПРГ-РУ", lambda s, n: g.threshold(wood="oak")),
    (r"^ЛН-Б-ДС", lambda s, n: g.linoleum(g.wood_tex("oak-honey"))),
    (r"^ЛН-Б-ПС", lambda s, n: g.linoleum(g.tile_tex())),
    (r"^ЛН-ПК", lambda s, n: g.linoleum(g.wood_tex("oak"))),
    (r"^ЛН-К", lambda s, n: g.linoleum(g.photo_tex("concrete") or g.proc_tex("paper-grey"))),
    # Поликарбонат
    (r"^ПК-С-", lambda s, n: g.sheet_stack("polycarbonate", 2.1, 3.0, mm(n, 0) / 1000 * 2, 5, pc_color(s))),
    (r"^ПК-М-", lambda s, n: g.mono_polycarbonate(PC["Б"] if s.endswith("Б") else "#e6f3fa")),
    (r"^ПК-НП", lambda s, n: g.pc_profile("hp")),
    (r"^ПК-UP", lambda s, n: g.pc_profile("up")),
    (r"^ПК-ТШ", lambda s, n: g.thermo_washers()),
    (r"^ТП-", lambda s, n: g.greenhouse(int(s.split("-")[-1]) // 2 + 2)),
    # Печное литьё и дымоходы
    (r"^ПЛ-ДТ\d?С?$", lambda s, n: g.stove_door(glass="стекл" in n)),
    (r"^ПЛ-ДПР", lambda s, n: g.stove_door(small=True)),
    (r"^ПЛ-ДП", lambda s, n: g.stove_door(small=True, vent=True)),
    (r"^ПЛ-(РД|РУ)", lambda s, n: g.grate((mm(n, 1) / 1000, mm(n, 2) / 1000))),
    (r"^ПЛ-П2", lambda s, n: g.stove_plate(2)),
    (r"^ПЛ-П1", lambda s, n: g.stove_plate(1)),
    (r"^ПЛ-ЗВ", lambda s, n: g.damper()),
    (r"^ПЛ-ВК", lambda s, n: g.damper(round_lid=True)),
    (r"^ПЛ-ДШ", lambda s, n: g.oven_box()),
    (r"^ПЛ-ШН", lambda s, n: g.rope_coil()),
    (r"^ДМ-СЭ", lambda s, n: g.sandwich("pipe")),
    (r"^ДМ-КЛ", lambda s, n: g.sandwich("elbow")),
    (r"^ДМ-ТР", lambda s, n: g.sandwich("tee")),
    (r"^ДМ-ЗН", lambda s, n: g.sandwich("cap")),
    (r"^ДМ-ХМ", lambda s, n: g.sandwich("clamp")),
    # Крепёж
    (r"^КР-СД", ("photo", "wood-screws:a4")),
    (r"^КР-СМ", ("photo", "metal-screws:a4")),
    (r"^КР-ДГ", ("photo", "wall-plugs:b9")),
    (r"^КР-ДР", ("photo", "wall-plugs:a4")),
    (r"^КР-АБ", lambda s, n: g.anchor_bolt()),
    (r"^КР-ГВ", ("photo", "nails:c2")),
    (r"^КР-УГ", lambda s, n: g.angle_bracket()),
    (r"^КР-ЛП", lambda s, n: g.perforated_strip()),
    (r"^КР-ХТ", ("photo", "pipe-clamp:a1")),
    (r"^КР-ШП", lambda s, n: g.threaded_rod()),
    # Инструмент
    (r"^ИН-ШП-100", ("photo", "putty-knife:a1")),
    (r"^ИН-ШП-", lambda s, n: g.facade_spatula(mm(n, 0) / 1000)),
    (r"^ИН-УР", ("photo", "level:a1")),
    (r"^ИН-ТЧ", ("photo", "wheelbarrow:a10")),
    (r"^ИН-КЛ", lambda s, n: g.trowel()),
    (r"^ИН-ПР-", lambda s, n: g.straightedge()),
    (r"^ИН-ВЛ", ("photo", "paint-roller:c5")),
    (r"^ИН-КС", ("photo", "paint-brush:a4")),
    (r"^ИН-ВД", lambda s, n: g.bucket_plain()),
    (r"^ИН-РЛ", ("photo", "tape-measure:a7")),
    (r"^ИН-НЖ", ("photo", "utility-knife:a3")),
    (r"^ИН-ЛП", lambda s, n: g.shovel()),
    (r"^ИН-ПРЧ", ("photo", "gloves:c5")),
    (r"^ИН-МКС", lambda s, n: g.mixer_paddle()),
    (r"^ЭИ-ДШ", ("photo", "drill:a1")),
    (r"^ЭИ-ПФ", ("photo", "hammer-drill:b2", (0.0, 0.0, 0.74, 1.0), [(0.765, 0.64, 1.0, 1.0), (0.72, 0.8, 1.0, 1.0)])),  # без перчаток
    (r"^ЭИ-УШМ", ("photo", "grinder:a2")),
    (r"^ЭИ-ЛБ", ("photo", "jigsaw:a1")),
    (r"^ЭИ-МКС", lambda s, n: g.mixer_tool()),
    (r"^ЭИ-КР", lambda s, n: g.cutting_discs()),
]


def products():
    """Артикул -> название из демо-каталога сайта."""
    sys.path.insert(0, str(TOOLS.parents[1] / "site"))
    from catalog.demo_data import CATALOG
    from catalog.demo_data_extra import EXTRA

    result = {}
    for source in (CATALOG, EXTRA):
        for groups in source.values():
            for rows in groups.values():
                for row in rows:
                    result.setdefault(row[1], row[0])
    return result


def rule(sku):
    for pattern, action in RULES:
        if re.search(pattern, sku):
            return action
    return None


# ---------------------------------------------------------------------------------------------------------
# Фото: вырезание фона и постановка в кадр

_session = None


def cutout_mask(img):
    """Маска товара 0..255 по ISNet (вход 1024×1024, нормировка как в rembg)."""
    global _session
    if _session is None:
        import onnxruntime as ort
        _session = ort.InferenceSession(str(CACHE / "models" / "isnet-general-use.onnx"),
                                        providers=["CPUExecutionProvider"])
    inp = _session.get_inputs()[0]
    x = np.asarray(img.convert("RGB").resize((1024, 1024), Image.BILINEAR), dtype=np.float32) / 255.0
    x = ((x - 0.5) / 1.0).transpose(2, 0, 1)[None]
    y = _session.run(None, {inp.name: x})[0][0, 0]
    y = (y - y.min()) / (y.max() - y.min() + 1e-6)
    y = np.clip((y - 0.12) / 0.76, 0, 1)            # убираем полупрозрачный «туман» вокруг товара
    return Image.fromarray((y * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)


def stage(rgba, fill=0.8):
    """Товар с альфа-каналом -> кадр 1000×1000: по центру, с полями, мягкая тень на полу."""
    bbox = rgba.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    item = rgba.crop(bbox)
    scale = SIZE * fill / max(item.size)
    item = item.resize((max(1, int(item.width * scale)), max(1, int(item.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (SIZE, SIZE), "white")
    x = (SIZE - item.width) // 2
    y = (SIZE - item.height) // 2 - int(SIZE * 0.02)
    # Тень: силуэт нижней трети, сплющенный и размытый
    alpha = np.asarray(item.getchannel("A"), dtype=np.float32) / 255
    shadow = Image.new("L", (SIZE, SIZE), 0)
    foot = Image.fromarray((alpha * 255).astype(np.uint8)).resize((item.width, max(1, item.height // 9)))
    shadow.paste(foot, (x, y + item.height - foot.height // 2))
    shadow = shadow.filter(ImageFilter.GaussianBlur(SIZE * 0.022))
    sh = np.asarray(shadow, dtype=np.float32) / 255 * 0.28
    base = np.asarray(canvas, dtype=np.float32) * (1 - sh[..., None])
    canvas = Image.fromarray(base.astype(np.uint8))
    canvas.paste(item.convert("RGB"), (x, y), item.getchannel("A"))
    return canvas


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Hoztrade-catalog/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def photo(ref, crop=None, erase=()):
    """«понятие:код» -> (картинка, сведения об источнике). crop — часть снимка в долях (x0, y0, x1, y1),
    erase — прямоугольники в долях кадра, которые не относятся к товару."""
    concept, code = ref.split(":")
    meta = json.loads((CACHE / "stock" / "meta.json").read_text(encoding="utf-8"))
    hit = meta[concept][code[0]][int(code[1:]) - 1]
    path = CACHE / "stock" / "large" / f"{concept}-{code}.jpg"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch(hit["large"]))
    with Image.open(path) as src:
        src = ImageOps.exif_transpose(src).convert("RGB")
        if crop:
            w, h = src.size
            src = src.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
        src.thumbnail((1600, 1600), Image.LANCZOS)
        rgba = src.copy()
        mask = cutout_mask(src)
        for x0, y0, x1, y1 in erase:
            ImageDraw.Draw(mask).rectangle((x0 * src.width, y0 * src.height, x1 * src.width, y1 * src.height), fill=0)
        rgba.putalpha(mask)
    credit = {k: hit[k] for k in ("source", "page", "author", "license")}
    return stage(rgba), credit


# ---------------------------------------------------------------------------------------------------------

def build(prefixes=()):
    OUT.mkdir(exist_ok=True)
    credits_path = OUT / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() and prefixes else {}
    textures = json.loads((CACHE / "textures" / "credits.json").read_text(encoding="utf-8")) \
        if (CACHE / "textures" / "credits.json").exists() else {}
    missing = []
    for sku, name in products().items():
        if prefixes and not sku.startswith(tuple(prefixes)):
            continue
        action = rule(sku)
        if action is None:
            missing.append(sku)
            continue
        if isinstance(action, tuple):
            img, credit = photo(*action[1:])
            credits[sku] = {"kind": "photo", **credit}
        else:
            img = action(sku, name)
            credits[sku] = {"kind": "drawing", "note": "рисунок (1c/tools/packshot*.py)"}
        img.convert("RGB").save(OUT / f"{sku}.jpg", quality=90, optimize=True, progressive=True)
        print(sku, credits[sku]["kind"], flush=True)
    credits["_textures"] = textures
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    if missing:
        print("Нет правила:", ", ".join(missing))


def contact_sheet(out, per_row=10, cell=200):
    files = sorted(p for p in OUT.glob("*.jpg"))
    rows = math.ceil(len(files) / per_row)
    sheet = Image.new("RGB", (per_row * cell, rows * (cell + 18)), "white")
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    for i, p in enumerate(files):
        x, y = (i % per_row) * cell, (i // per_row) * (cell + 18)
        with Image.open(p) as img:
            sheet.paste(img.resize((cell - 4, cell - 4)), (x + 2, y + 2))
        d.text((x + 4, y + cell - 2), p.stem, font=f, fill="black")
    sheet.save(out, quality=82)


if __name__ == "__main__":
    args = sys.argv[1:]
    sheet_out = None
    if "--sheet" in args:
        i = args.index("--sheet")
        sheet_out = args[i + 1]
        args = args[:i] + args[i + 2:]
    build(args)
    if sheet_out:
        contact_sheet(sheet_out)
