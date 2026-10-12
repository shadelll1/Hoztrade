"""Товарные рисунки: упаковка с этикеткой и сами изделия, собранные из packshot.

build(sku, name) -> PIL.Image 1000×1000 на белом фоне или None, если для товара нет рисунка.
Этикетка — только текст из названия товара (тип, марка, вес) в собственном оформлении, без логотипов
производителей.
"""
import hashlib
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from packshot import (Material, Quad, Scene, arc_path, box, disk, extrude, grid_surface, lathe, ring_disk,
                      rotation, rounded_prism, superquad, transform, tube)

FONTS = Path("C:/Windows/Fonts")
TEXTURES = Path(__file__).resolve().parent / ".image-cache" / "textures"


# ---------------------------------------------------------------------------------------------------------
# Шрифты и текст

@lru_cache(maxsize=64)
def font(size, style="Bold Condensed"):
    f = ImageFont.truetype(str(FONTS / "bahnschrift.ttf"), size)
    f.set_variation_by_name(style)
    return f


def fit_font(draw, text, max_w, max_size, style="Bold Condensed", min_size=10):
    size = max_size
    while size > min_size:
        f = font(size, style)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return font(min_size, style)


def wrap_lines(draw, text, max_w, size, style, max_lines=3):
    """Перенос по словам под ширину; шрифт уменьшается, пока текст не влезет в max_lines строк."""
    words = text.split()
    while size > 12:
        f = font(size, style)
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=f) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines and all(draw.textlength(line, font=f) <= max_w for line in lines):
            return f, lines
        size -= 2
    return font(12, style), [text]


# Названия из двух слов, которые на упаковке — одним заголовком
TWO_WORD = {"наливной пол", "кладочная смесь", "смесь кладочная", "смесь печная", "стяжка пола", "пена монтажная",
            "клей жидкие", "краска водоэмульсионная", "краска интерьерная", "краска фасадная",
            "песок строительный", "песок кварцевый", "лента соединительная", "лента гидроизоляционная",
            "глина огнеупорная"}
AMOUNT = re.compile(r"(\d+(?:[,.]\d+)?\s*(?:кг|л|мл|м²|м|шт|мм|пар))\b", re.I)
ADJ = re.compile(r"(ая|ый|ой|ий|яя|ое|ые|ее)$")


def parse_name(name):
    """«Штукатурка гипсовая Кнауф Ротбанд 30 кг» -> ('ШТУКАТУРКА', 'гипсовая', 'Кнауф Ротбанд', '30 кг')."""
    amounts = AMOUNT.findall(name)
    amount = amounts[-1] if amounts else ""
    rest = name.replace(amount, "").strip(" ,") if amount else name
    words = rest.replace(", ", " ").split()
    title = words[0] if words else name
    i = 1
    if len(words) > 1 and f"{words[0]} {words[1]}".lower() in TWO_WORD:
        title, i = f"{words[0]} {words[1]}", 2
    desc = []
    while i < len(words) and ADJ.search(words[i].lower()) and words[i][0].islower():
        desc.append(words[i])
        i += 1
    model = " ".join(words[i:])
    return title.upper(), " ".join(desc), model, amount.replace(" ", "\u00a0")


# Цветовые схемы этикеток: (основной, тёмный, светлый фон)
SCHEMES = {
    "цемент": ("#3f4a57", "#232a33", "#eef0f2"),
    "пескобетон": ("#d0611f", "#7a3510", "#fbf1e8"),
    "кладочная": ("#9a4b2a", "#5a2a16", "#f7efe9"),
    "смесь": ("#9a4b2a", "#5a2a16", "#f7efe9"),
    "песок": ("#c79a3d", "#6d5216", "#faf5ea"),
    "керамзит": ("#8a5a3c", "#4b2f1d", "#f6efe9"),
    "щебень": ("#5b6470", "#2f353d", "#eff1f3"),
    "штукатурка": ("#1f5fae", "#123a6a", "#eef4fb"),
    "шпаклёвка": ("#16865a", "#0c4f35", "#ecf7f1"),
    "клей": ("#e0a10b", "#7a5600", "#fdf6e3"),
    "затирка": ("#6b4fa0", "#3c2a60", "#f3effa"),
    "наливной": ("#7a3fa0", "#45215c", "#f5eef9"),
    "стяжка": ("#7a3fa0", "#45215c", "#f5eef9"),
    "грунтовка": ("#0e7fa8", "#07465d", "#eaf6fa"),
    "грунт": ("#0e7fa8", "#07465d", "#eaf6fa"),
    "бетоноконтакт": ("#c23b5a", "#6e1d31", "#fbedf1"),
    "гидроизоляция": ("#14607a", "#0a3646", "#e9f3f6"),
    "мастика": ("#26292e", "#0e0f11", "#f0f0f0"),
    "праймер": ("#26292e", "#0e0f11", "#f0f0f0"),
    "краска": ("#2b7bd0", "#164a80", "#eef5fd"),
    "эмаль": ("#c0392b", "#6b1e16", "#fbeeed"),
    "грунт-эмаль": ("#55606b", "#2c3238", "#eff1f2"),
    "антисептик": ("#3a8a2e", "#1f4f18", "#eef7ec"),
    "огнебиозащита": ("#c24a1a", "#6c270c", "#fbefe9"),
    "герметик": ("#1e88c8", "#0f4c72", "#ebf5fb"),
    "пена": ("#e8590c", "#7c2e05", "#fdf0e8"),
    "очиститель": ("#5f3dc4", "#33207a", "#f1eefc"),
    "клей жидкие": ("#c92a2a", "#6e1414", "#fbeded"),
    "глина": ("#a0522d", "#5c2e18", "#f8efea"),
    "мембрана": ("#1971c2", "#0b3f70", "#eaf2fb"),
    "пароизоляция": ("#1971c2", "#0b3f70", "#eaf2fb"),
    "изоспан": ("#1971c2", "#0b3f70", "#eaf2fb"),
    "лента": ("#495057", "#212529", "#f1f3f5"),
    "подложка": ("#2f9e44", "#18582a", "#ecf8ef"),
    "утеплитель": ("#c2255c", "#6c1232", "#fbedf2"),
}


def scheme(name):
    low = name.lower()
    for key in sorted(SCHEMES, key=len, reverse=True):
        if low.startswith(key) or f" {key}" in f" {low}":
            return SCHEMES[key]
    digest = hashlib.md5(name.split()[0].encode()).digest()[0]
    palette = list(SCHEMES.values())
    return palette[digest % len(palette)]


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def label(name, w, h, kind="bag", base=None, frac=0.3):
    """Этикетка товара. kind влияет на раскладку: bag — во всю переднюю сторону мешка, band — опоясывающая
    этикетка ведра/банки (текст по центру развёртки), small — баллон, картридж."""
    main, dark, light = scheme(name)
    title, desc, model, amount = parse_name(name)
    bg = base or light
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)

    if kind == "band":
        # Развёртка цилиндра: к зрителю обращена середина (u = 0.5) — туда весь текст, колонкой шириной frac·w.
        cx = w // 2
        pw = int(w * frac)
        d.rectangle((0, 0, w, int(h * 0.24)), fill=main)
        d.rectangle((0, int(h * 0.24), w, int(h * 0.27)), fill=dark)
        d.polygon([(0, h), (0, int(h * 0.8)), (w, int(h * 0.66)), (w, h)], fill=main)
        f = fit_font(d, title, pw, int(h * 0.17))
        d.text((cx, int(h * 0.125)), title, font=f, fill="white", anchor="mm")
        sub = (desc + " " + model).strip()
        if sub:
            f2, lines = wrap_lines(d, sub, pw, int(h * 0.11), "Bold Condensed", 3)
            y = int(h * 0.36) + (0 if len(lines) > 1 else int(h * 0.04))
            for line in lines:
                d.text((cx, y), line, font=f2, fill=dark, anchor="mm")
                y += int(f2.size * 1.08)
        if amount:
            fa = fit_font(d, amount, int(pw * 0.8), int(h * 0.12))
            tw = d.textlength(amount, font=fa)
            ay = int(h * 0.84)
            box_ = (cx - tw / 2 - 16, ay - fa.size / 2 - 8, cx + tw / 2 + 16, ay + fa.size / 2 + 10)
            d.rounded_rectangle(box_, radius=10, fill="white")
            d.text((cx, ay + 1), amount, font=fa, fill=dark, anchor="mm")
        return img

    pad = int(w * 0.08)
    if kind == "small":
        d.rectangle((0, 0, w, int(h * 0.26)), fill=main)
        f = fit_font(d, title, w - 2 * pad, int(h * 0.14))
        d.text((w // 2, int(h * 0.13)), title, font=f, fill="white", anchor="mm")
        sub = (desc + " " + model).strip()
        f2, lines = wrap_lines(d, sub, w - 2 * pad, int(h * 0.075), "Bold Condensed", 3)
        y = int(h * 0.36)
        for line in lines:
            d.text((w // 2, y), line, font=f2, fill=dark, anchor="mm")
            y += int(f2.size * 1.1)
        d.polygon([(0, int(h * 0.78)), (w, int(h * 0.7)), (w, h), (0, h)], fill=main)
        if amount:
            fa = fit_font(d, amount, w - 2 * pad, int(h * 0.09))
            d.text((w // 2, int(h * 0.87)), amount, font=fa, fill="white", anchor="mm")
        return img

    # Мешок: верхняя плашка с типом, крупная марка, диагональ, вес в плашке снизу
    top = int(h * 0.2)
    d.rectangle((0, 0, w, top), fill=main)
    d.polygon([(0, top), (w, top), (w, top + int(h * 0.05)), (0, top + int(h * 0.11))], fill=dark)
    f = fit_font(d, title, w - 2 * pad, int(h * 0.12))
    d.text((w // 2, top // 2 + 4), title, font=f, fill="white", anchor="mm")
    y = top + int(h * 0.2)
    if desc:
        fd = fit_font(d, desc.upper(), w - 2 * pad, int(h * 0.055), "SemiBold Condensed")
        d.text((w // 2, y - int(h * 0.04)), desc.upper(), font=fd, fill=dark, anchor="mm")
    if model:
        fm, lines = wrap_lines(d, model, w - 2 * pad, int(h * 0.13), "Bold Condensed", 2)
        y += int(h * 0.04)
        for line in lines:
            d.text((w // 2, y), line, font=fm, fill=main, anchor="mm")
            y += int(fm.size * 1.0)
    # Полоса и пиктограммы применения
    band_y = int(h * 0.64)
    d.polygon([(0, band_y + int(h * 0.06)), (w, band_y - int(h * 0.02)), (w, band_y + int(h * 0.04)),
               (0, band_y + int(h * 0.12))], fill=main)
    for i in range(3):
        px = int(w * (0.28 + 0.22 * i))
        py = int(h * 0.79)
        d.ellipse((px - 26, py - 26, px + 26, py + 26), fill="white", outline=main, width=5)
        d.line((px - 12, py + 8, px + 12, py - 8), fill=main, width=5)
    if amount:
        fa = fit_font(d, amount, int(w * 0.5), int(h * 0.08))
        tw = d.textlength(amount, font=fa)
        bx = (w // 2 - tw / 2 - 22, int(h * 0.87), w // 2 + tw / 2 + 22, int(h * 0.87) + fa.size + 18)
        d.rounded_rectangle(bx, radius=14, fill=dark)
        d.text((w // 2, (bx[1] + bx[3]) / 2), amount, font=fa, fill="white", anchor="mm")
    return img


def paper(img, strength=10, seed=1):
    """Лёгкая фактура бумаги/пластика, чтобы этикетка не была «цифровой»."""
    rng = np.random.default_rng(seed)
    a = np.asarray(img, dtype=np.int16)
    noise = rng.normal(0, strength, a.shape[:2])[..., None]
    noise = np.asarray(Image.fromarray(np.clip(noise[..., 0] + 128, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(1.2)), dtype=np.int16)[..., None] - 128
    return Image.fromarray(np.clip(a + noise, 0, 255).astype(np.uint8))


def seed_of(text):
    return int(hashlib.md5(text.encode()).hexdigest()[:6], 16)


# ---------------------------------------------------------------------------------------------------------
# Упаковка

def bag(name, kg=25):
    """Клапанный бумажный мешок: «подушка» с видимым боком и складками у шва. Размер зависит от веса."""
    s = 0.8 + 0.2 * min(kg, 50) / 50
    W, H, D = 0.5 * s, 0.74 * s, 0.3 * s
    if kg <= 5:                       # мелкая фасовка — пакет пониже и тоньше
        W, H, D = 0.5, 0.6, 0.18
    lab = paper(label(name, 700, 1040, "bag"), 7, seed_of(name))
    front = Material(texture=lab, spec=0.14, shine=16, ambient=0.33)
    _, dark, light = scheme(name)
    plain = Material(light, spec=0.1, shine=16, ambient=0.33)
    rng = np.random.default_rng(seed_of(name))
    ph = rng.uniform(0, 6.28, 3)

    def shape(u, v, sign):
        taper = 1 - 0.07 * v                                   # к верху мешок чуть уже
        x = (u - 0.5) * W * taper
        sag = 0.02 * math.sin(math.pi * u) * (1 - v) ** 3       # низ слегка «осел»
        y = v * H - sag * H
        side = math.sin(math.pi * u) ** 0.5                     # выпуклый перёд, круглый бок
        vert = math.sin(math.pi * min(1.0, 0.04 + v * 0.98)) ** 0.55
        wr = 0.012 * math.sin(9 * u + ph[0]) * math.sin(7 * v + ph[1]) * (v ** 4 + (1 - v) ** 4)  # складки у швов
        z = sign * (D / 2 * side * vert + wr * D)
        return (x if sign > 0 else -x, y, z)

    quads = grid_surface(lambda u, v: shape(u, v, 1), 44, 52, front, front, lambda u, v: (u, 1 - v))
    quads += grid_surface(lambda u, v: shape(u, v, -1), 24, 26, plain)
    seam = Material(dark, spec=0.08, ambient=0.34)
    quads += box(-W / 2 * 0.9, H * 0.995, -0.01, W / 2 * 0.9, H + 0.022, 0.01, seam)
    return Scene(yaw=-34, pitch=16).add(quads).render()


def bucket(name, white_lid=True, color=None):
    """Пластиковое ведро с крышкой, опоясывающей этикеткой и ручкой."""
    main, dark, light = scheme(name)
    lab = paper(label(name, 1700, 620, "band", base="#ffffff", frac=0.27), 5, seed_of(name))
    body = Material(color or "#f4f5f6", spec=0.35, shine=60, ambient=0.36)
    lab_m = Material(texture=lab, spec=0.3, shine=60, ambient=0.36)
    prof = [(0.155, 0.0), (0.16, 0.012), (0.163, 0.04), (0.18, 0.33), (0.182, 0.345), (0.192, 0.35), (0.192, 0.375),
            (0.186, 0.38)]
    quads = lathe(prof, body, 160, lab_m, (2, 3), a0=-math.pi + math.radians(20), a1=math.pi + math.radians(20))
    lid = Material(color or ("#f7f7f7" if white_lid else main), spec=0.3, shine=50, ambient=0.38)
    quads += lathe([(0.186, 0.38), (0.19, 0.392), (0.17, 0.397), (0.0, 0.40)], lid, 160)
    handle = Material("#d9dbde", spec=0.5, shine=80)
    quads += tube(arc_path(0, 0.30, 0.205, 200, 340, 30, z=0.0), 0.006, handle, 12)
    return Scene(yaw=-20, pitch=24).add(quads).render()


def canister(name, color="#f2f3f4"):
    """Канистра: скруглённый корпус, ручка сверху, крышка; этикетка на лицевой стороне."""
    main, dark, light = scheme(name)
    lab = paper(label(name, 700, 800, "small"), 5, seed_of(name))
    body = Material(color, spec=0.35, shine=50, ambient=0.36)
    lab_m = Material(texture=lab, spec=0.3, shine=50, ambient=0.36)
    W, D, H = 0.36, 0.2, 0.5
    quads = rounded_prism(W, D, H, 0.05, body, lab_m, (0.0, 1.0, 0.1, 0.86), bevel=0.04, rows=30, cols=16)
    handle = Material(color, spec=0.35, shine=50, ambient=0.36)
    quads += tube([(0.0, H - 0.01, 0), (0.03, H + 0.075, 0), (0.15, H + 0.075, 0), (0.17, H - 0.01, 0)], 0.02,
                  handle, 24)
    cap = Material(main, spec=0.4, shine=60)
    quads += transform(lathe([(0.042, 0), (0.042, 0.055), (0.0, 0.057)], cap, 64), move=(-0.1, H - 0.01, 0))
    return Scene(yaw=-28, pitch=16).add(quads).render()


def paint_can(name, color=None):
    """Металлическая банка (эмаль) с опоясывающей этикеткой."""
    lab = paper(label(name, 1500, 560, "band", base="#ffffff", frac=0.3), 4, seed_of(name))
    metal = Material("#c9ced4", spec=0.9, shine=120, metal=True, ambient=0.3)
    lab_m = Material(texture=lab, spec=0.25, shine=60, ambient=0.36)
    prof = [(0.13, 0.0), (0.135, 0.008), (0.135, 0.02), (0.132, 0.03), (0.132, 0.2), (0.135, 0.21), (0.135, 0.225),
            (0.128, 0.228)]
    quads = lathe(prof, metal, 160, lab_m, (3, 4), a0=-math.pi + math.radians(20), a1=math.pi + math.radians(20))
    quads += ring_disk(0.105, 0.128, 0.228, metal)
    quads += disk(0.105, 0.222, Material("#b8bec5", spec=0.8, shine=90, metal=True))
    return Scene(yaw=-20, pitch=26).add(quads).render()


def aerosol(name, color="#e8590c", straw=False):
    """Аэрозольный баллон: пена, очиститель."""
    lab = paper(label(name, 1500, 1000, "band", base="#ffffff", frac=0.26), 4, seed_of(name))
    lab_m = Material(texture=lab, spec=0.45, shine=70, ambient=0.34)
    metal = Material("#d5d9de", spec=1.0, shine=140, metal=True, ambient=0.3)
    r = 0.075
    prof = [(r * 0.92, 0.0), (r, 0.01), (r, 0.03), (r, 0.33), (r * 0.96, 0.35), (r * 0.7, 0.375), (r * 0.35, 0.385),
            (r * 0.3, 0.39)]
    quads = lathe(prof, metal, 140, lab_m, (2, 3), a0=-math.pi + math.radians(20), a1=math.pi + math.radians(20))
    cap = Material(color, spec=0.45, shine=60, ambient=0.34)
    quads += transform(lathe([(0.025, 0), (0.03, 0.03), (0.024, 0.045), (0, 0.047)], cap, 64), move=(0, 0.39, 0))
    if straw:
        quads += tube([(0.0, 0.425, 0.0), (0.0, 0.43, 0.06), (0.0, 0.43, 0.19)], 0.006, Material("#f1f3f5", spec=0.4))
    return Scene(yaw=-20, pitch=14).add(quads).render()


def cartridge(name, color="#ffffff"):
    """Картридж герметика / жидких гвоздей."""
    lab = paper(label(name, 1300, 1000, "band", base="#ffffff", frac=0.26), 4, seed_of(name))
    lab_m = Material(texture=lab, spec=0.4, shine=60, ambient=0.35)
    body = Material(color, spec=0.4, shine=60, ambient=0.36)
    r = 0.05
    prof = [(r, 0.0), (r, 0.01), (r, 0.205), (r * 0.98, 0.215), (0.012, 0.225)]
    quads = lathe(prof, body, 120, lab_m, (1, 2), a0=-math.pi + math.radians(18), a1=math.pi + math.radians(18))
    nozzle = Material("#f1f3f5", spec=0.5, shine=60, ambient=0.4)
    quads += transform(lathe([(0.012, 0), (0.009, 0.06), (0.003, 0.12), (0, 0.121)], nozzle, 48), move=(0, 0.225, 0))
    quads += disk(r, 0.0, Material("#e9ecef"), 64, down=True)
    return Scene(yaw=-18, pitch=16).add(quads).render()


def roll(name, color=None, wrap=True, r=0.13, h=0.5):
    """Рулон стоя: мембраны, пароизоляция, подложка — с бумажным поясом-этикеткой."""
    main, dark, light = scheme(name)
    film = Material(color or light, spec=0.35, shine=50, ambient=0.36)
    lab = paper(label(name, 1500, 520, "band", base="#ffffff", frac=0.26), 4, seed_of(name))
    lab_m = Material(texture=lab, spec=0.2, shine=30, ambient=0.36)
    prof = [(r, 0.0), (r, h * 0.35), (r * 1.004, h * 0.35), (r * 1.004, h * 0.65), (r, h * 0.65), (r, h)]
    quads = lathe(prof, film, 150, lab_m if wrap else None, (2, 3) if wrap else None, a0=-math.pi + math.radians(20), a1=math.pi + math.radians(20))
    # Торец: витки рулона и картонная втулка
    rings = Image.new("RGB", (512, 512), "white")
    rd = ImageDraw.Draw(rings)
    base = np.array(hexrgb(color) if color else hexrgb(light))
    for k in range(60, 0, -1):
        t = k / 60
        shade = tuple(int(c) for c in base * (0.86 + 0.12 * ((k % 2) * 0.6 + 0.4 * t)))
        rd.ellipse((256 - 250 * t, 256 - 250 * t, 256 + 250 * t, 256 + 250 * t), fill=shade)
    rd.ellipse((256 - 70, 256 - 70, 256 + 70, 256 + 70), fill=(181, 140, 92))
    rd.ellipse((256 - 52, 256 - 52, 256 + 52, 256 + 52), fill=(70, 55, 40))
    top = Material(texture=rings, spec=0.15, ambient=0.38)
    seg = 120
    for k in range(seg):
        t0, t1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        p = [(0, h, 0), (r * math.sin(t0), h, r * math.cos(t0)), (r * math.sin(t1), h, r * math.cos(t1))]
        uv = [(0.5, 0.5), (0.5 + 0.49 * math.sin(t0), 0.5 - 0.49 * math.cos(t0)),
              (0.5 + 0.49 * math.sin(t1), 0.5 - 0.49 * math.cos(t1))]
        quads.append(Quad(p, top, uv))
    return Scene(yaw=-20, pitch=24).add(quads).render()


def tape_roll(name, color="#f1f3f5", mesh=False):
    """Лента в рулоне, лежит плашмя: серпянка, гидроизоляционная, соединительная."""
    main, dark, light = scheme(name)
    r, h = 0.16, 0.06
    side = Material(color, spec=0.25, shine=40, ambient=0.36)
    quads = lathe([(r, 0), (r, h)], side, 160)
    face = Image.new("RGB", (512, 512), "white")
    fd = ImageDraw.Draw(face)
    base = np.array(hexrgb(color))
    for k in range(40, 0, -1):
        t = 0.4 + 0.6 * k / 40
        shade = tuple(int(c) for c in base * (0.88 + 0.1 * (k % 2)))
        fd.ellipse((256 - 252 * t, 256 - 252 * t, 256 + 252 * t, 256 + 252 * t), fill=shade)
    fd.ellipse((256 - 100, 256 - 100, 256 + 100, 256 + 100), fill=(196, 160, 112))
    fd.ellipse((256 - 82, 256 - 82, 256 + 82, 256 + 82), fill="white")
    if mesh:
        for x in range(0, 512, 12):
            fd.line((x, 0, x, 512), fill=tuple(int(c * 0.9) for c in base), width=1)
    top = Material(texture=face, spec=0.15, ambient=0.38)
    seg = 120
    for k in range(seg):
        t0, t1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        p = [(0, h, 0), (r * math.sin(t0), h, r * math.cos(t0)), (r * math.sin(t1), h, r * math.cos(t1))]
        uv = [(0.5, 0.5), (0.5 + 0.49 * math.sin(t0), 0.5 - 0.49 * math.cos(t0)),
              (0.5 + 0.49 * math.sin(t1), 0.5 - 0.49 * math.cos(t1))]
        quads.append(Quad(p, top, uv))
    # бумажная этикетка-кружок на торце не видна — подпись на картонной втулке опускаем
    return Scene(yaw=-20, pitch=48).add(quads).render()
