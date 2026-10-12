"""Рисунки самих изделий: листы, плиты, блоки, пиломатериалы, кровля, трубы, профиль, отопление, печное литьё,
дымоходы, теплицы, ламинат, линолеум. Фото-текстуры — из .image-cache/textures (texture_search.py),
без них — процедурные.
"""
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from packshot import (Material, Quad, Scene, arc_path, box, disk, extrude, grid_surface, lathe, orient,
                      ring_disk, rounded_prism, transform, tube)
from packshot_items import font, hexrgb, label, paper, scheme, seed_of

TEX = Path(__file__).resolve().parent / ".image-cache" / "textures"


# ---------------------------------------------------------------------------------------------------------
# Текстуры

def noise(size, scale, seed, octaves=3):
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = max(2, int(size / scale * (2 ** o)))
        small = rng.random((n, n)).astype(np.float32)
        big = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC),
                         dtype=np.float32) / 255
        out += amp * big
        total += amp
        amp *= 0.5
    return out / total


def tint(gray, color, contrast=1.0):
    c = np.array(hexrgb(color) if isinstance(color, str) else color, dtype=np.float32)
    g = (gray - 0.5) * contrast + 0.5
    return Image.fromarray(np.clip(g[..., None] * 2 * c, 0, 255).astype(np.uint8))


@lru_cache(maxsize=64)
def photo_tex(name, size=1024):
    """Квадратный фрагмент из середины фото-текстуры (или None)."""
    path = TEX / f"{name}.jpg"
    if not path.exists():
        return None
    with Image.open(path) as img:
        img = img.convert("RGB")
        side = int(min(img.size) * 0.8)
        cx, cy = img.width // 2, img.height // 2
        crop = img.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2))
        return crop.resize((size, size), Image.LANCZOS)


# Подкраска фото: (яркость, насыщенность, оттенок RGB-множителем)
WOOD_TONE = {"smoked": (0.62, 0.55, (1.0, 0.97, 0.94)), "wenge": (0.55, 0.8, (1.0, 0.95, 0.9)),
             "walnut-dark": (0.8, 1.0, (1.0, 0.96, 0.92)), "oak-honey": (1.0, 1.15, (1.0, 0.96, 0.82))}


def wood_tex(kind="pine", size=1024, along="x"):
    """Древесина: фото, если есть, иначе — процедурные волокна. along — вдоль какой оси текстуры волокна."""
    img = photo_tex(kind) or photo_tex("pine")
    if img is not None and kind in WOOD_TONE:
        bright, sat, mul = WOOD_TONE[kind]
        a = np.asarray(img, dtype=np.float32)
        gray = a.mean(2, keepdims=True)
        a = (gray + (a - gray) * sat) * bright * np.array(mul, dtype=np.float32)
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if img is None:
        base = {"pine": "#d8b07a", "oak": "#c19a6b", "walnut": "#7a5236", "wenge": "#4a3326"}.get(kind, "#d2a774")
        y = np.linspace(0, 1, size, dtype=np.float32)[:, None]
        n = noise(size, 64, seed_of(kind), 4)
        grain = 0.5 + 0.25 * np.sin((y * 40 + n * 6) * math.pi) + 0.15 * (noise(size, 8, seed_of(kind) + 1) - 0.5)
        img = tint(np.repeat(grain, size, 1) if grain.shape[1] == 1 else grain, base, 0.6)
    # Волокна в фото могут идти как угодно: выбираем ориентацию по градиентам
    a = np.asarray(img.convert("L"), dtype=np.float32)
    gx = np.abs(np.diff(a, axis=1)).mean()
    gy = np.abs(np.diff(a, axis=0)).mean()
    vertical_grain = gx > gy          # волокна вертикальны, если яркость сильнее меняется по горизонтали
    if (along == "x") == vertical_grain:
        img = img.rotate(90, expand=True)
    return img


def proc_tex(kind, size=512, seed=1):
    if kind == "cast-iron":
        n = noise(size, 6, seed, 3)
        return tint(0.42 + 0.12 * (n - 0.5), "#3a3d41", 1.0)
    if kind == "galvanized":
        n = noise(size, 30, seed, 2)
        spots = noise(size, 4, seed + 3, 1)
        return tint(0.5 + 0.18 * (n - 0.5) + 0.06 * (spots - 0.5), "#c3c9cf", 1.0)
    if kind == "aerated":
        n = noise(size, 50, seed, 2)
        rng = np.random.default_rng(seed)
        img = tint(0.5 + 0.06 * (n - 0.5), "#e6e4dd", 1.0)
        d = ImageDraw.Draw(img)
        for _ in range(size * 3):
            x, y = rng.integers(0, size, 2)
            r = rng.uniform(0.6, 2.2)
            g = int(rng.uniform(170, 205))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(g, g - 2, g - 6))
        return img
    if kind == "fireclay":
        n = noise(size, 40, seed, 3)
        rng = np.random.default_rng(seed)
        img = tint(0.5 + 0.1 * (n - 0.5), "#e2c79b", 1.0)
        d = ImageDraw.Draw(img)
        for _ in range(size * 2):
            x, y = rng.integers(0, size, 2)
            r = rng.uniform(0.5, 1.8)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(150, 110, 70))
        return img
    if kind == "foam":
        rng = np.random.default_rng(seed)
        img = Image.new("RGB", (size, size), (246, 246, 244))
        d = ImageDraw.Draw(img)
        for _ in range(size * 4):
            x, y = rng.integers(0, size, 2)
            r = rng.uniform(3, 7)
            g = int(rng.uniform(232, 250))
            d.ellipse((x - r, y - r, x + r, y + r), outline=(g - 14, g - 14, g - 16), fill=(g, g, g - 2))
        return img
    if kind == "gypsum":
        n = noise(size, 40, seed, 2)
        return tint(0.5 + 0.05 * (n - 0.5), "#f0efea", 1.0)
    if kind == "paper-grey":
        n = noise(size, 20, seed, 2)
        return tint(0.5 + 0.04 * (n - 0.5), "#c9ccce", 1.0)
    raise ValueError(kind)


def tex_mat(img, spec=0.15, shine=20, ambient=0.34, **kw):
    return Material(texture=img, spec=spec, shine=shine, ambient=ambient, **kw)


def scene_render(quads, yaw=-35, pitch=26, **kw):
    return Scene(yaw=yaw, pitch=pitch).add(quads).render(**kw)


# ---------------------------------------------------------------------------------------------------------
# Листы и плиты

def sheet_stack(kind, w=1.2, l=2.5, t=0.0125, n=6, color=None):
    """Стопка листов. kind: gkl, gklv, gklo, plywood, osb, eps, xps, polycarbonate, xps-green."""
    scale = 1 / max(w, l)
    w, l = w * scale, l * scale
    t = max(t * scale * 2.2, 0.012)
    quads = []
    if kind in ("gkl", "gklv", "gklo"):
        face = {"gkl": "#c9ccce", "gklv": "#9fc79a", "gklo": "#e3b6c0"}[kind]
        top = tex_mat(tint(noise(512, 60, 3, 2) * 0.03 + 0.485, face, 1.0), spec=0.08)
        edge = Material({"gkl": "#e9e6df", "gklv": "#d9e8d4", "gklo": "#f0dde1"}[kind], spec=0.05)
        for i in range(n):
            dx = (i % 3 - 1) * 0.004
            quads += box(-w / 2 + dx, i * t, -l, w / 2 + dx, (i + 1) * t * 0.97, 0, edge, uvmats={"top": top})
    elif kind == "plywood":
        top = tex_mat(wood_tex("plywood") if photo_tex("plywood") else wood_tex("pine"), spec=0.1)
        edge_img = Image.new("RGB", (512, 64), (226, 196, 150))
        d = ImageDraw.Draw(edge_img)
        for k in range(0, 64, 8):
            d.rectangle((0, k, 512, k + 3), fill=(196, 160, 112))
        edge = tex_mat(edge_img, spec=0.05)
        for i in range(n):
            quads += box(-w / 2, i * t, -l, w / 2, (i + 1) * t * 0.97, 0, edge,
                         uvmats={"top": top, "front": edge, "right": edge, "left": edge})
    elif kind == "osb":
        img = photo_tex("osb") or tint(noise(512, 10, 7, 4), "#c8a165", 1.4)
        top = tex_mat(img, spec=0.08)
        edge = Material("#b88f55", spec=0.05)
        for i in range(n):
            quads += box(-w / 2, i * t, -l, w / 2, (i + 1) * t * 0.97, 0, edge, uvmats={"top": top})
    elif kind == "eps":
        foam = tex_mat(proc_tex("foam"), spec=0.05, ambient=0.4)
        for i in range(n):
            quads += box(-w / 2, i * t, -l, w / 2, (i + 1) * t * 0.985, 0, foam,
                         uvmats={"top": foam, "front": foam, "right": foam, "left": foam})
    elif kind in ("xps", "xps-green"):
        c = color or ("#f08a24" if kind == "xps" else "#7fbf6a")
        mat = Material(c, spec=0.18, shine=30, ambient=0.36)
        for i in range(n):
            # Г-образная кромка — ступенька по краю
            quads += box(-w / 2, i * t, -l, w / 2 - 0.012, (i + 1) * t * 0.98, 0, mat)
            quads += box(w / 2 - 0.012, i * t, -l, w / 2, i * t + t * 0.5, 0, mat)
        band = Material("#2b3a55", spec=0.2)
        for zc in (-l * 0.25, -l * 0.75):
            quads += box(-w / 2 - 0.004, -0.003, zc - 0.03, w / 2 + 0.004, n * t + 0.004, zc + 0.03, band,
                         faces=("front", "top", "right", "left"))
    elif kind == "polycarbonate":
        c = color or "#dbeef7"
        lines = Image.new("RGB", (1024, 1024), hexrgb(c))
        d = ImageDraw.Draw(lines)
        dark = tuple(int(v * 0.86) for v in hexrgb(c))
        for x in range(0, 1024, 18):
            d.line((x, 0, x, 1024), fill=dark, width=2)
        top = tex_mat(lines, spec=0.9, shine=150, ambient=0.42)
        cells = Image.new("RGB", (1024, 64), hexrgb(c))
        d = ImageDraw.Draw(cells)
        for x in range(0, 1024, 18):
            d.rectangle((x + 3, 6, x + 15, 58), fill=tuple(int(v * 0.72) for v in hexrgb(c)))
        edge = tex_mat(cells, spec=0.6, shine=80)
        t = max(t, 0.03)
        for i in range(n):
            quads += box(-w / 2, i * t, -l, w / 2, (i + 1) * t * 0.96, 0, Material(c, spec=0.6, shine=100),
                         uvmats={"top": top, "front": edge, "right": edge})
        quads = transform(quads, move=(0, 0, l / 2))
        return scene_render(quads, yaw=-30, pitch=20)
    quads = transform(quads, move=(0, 0, l / 2))
    return scene_render(quads, yaw=-38, pitch=30)


def mono_polycarbonate(color="#e6f3fa", n=4):
    """Монолитный поликарбонат: гладкие прозрачные листы с плёнкой и наклейкой."""
    w, l, t = 0.66, 1.0, 0.012
    quads = []
    glass = Material(color, spec=1.0, shine=200, ambient=0.45)
    film = Material("#eef3f6", spec=0.4, shine=40, ambient=0.42)
    for i in range(n):
        quads += box(-w / 2, i * t, -l / 2, w / 2, (i + 1) * t * 0.9, l / 2, glass)
    quads += box(-w / 2 + 0.03, n * t * 0.9 + 0.0005, -l / 2 + 0.03, w / 2 - 0.03, n * t * 0.9 + 0.001, l / 2 - 0.03, film,
                 faces=("top",))
    return scene_render(quads, yaw=-38, pitch=30)


def blocks(kind, dims=(0.6, 0.2, 0.3), n=3):
    """Стеновые блоки: aerated (газобетон), foam (пеноблок), keramzit, pgp (пазогребневая), brick."""
    L, H, D = dims
    s = 1 / max(L, D * 2, H * 2)
    L, H, D = L * s, H * s, D * s
    quads = []
    if kind in ("aerated", "foam"):
        tex = tex_mat(proc_tex("aerated", seed=3 if kind == "aerated" else 5), spec=0.04, ambient=0.36)
        for i, (x, y, z) in enumerate([(0, 0, 0), (L + 0.02, 0, 0), (L * 0.5 + 0.01, H + 0.005, 0)][:n]):
            quads += box(x - L, y, z - D, x, y + H, z, tex, uvmats={k: tex for k in ("top", "front", "right", "left")})
        quads = transform(quads, move=(L / 2, 0, D / 2))
    elif kind == "keramzit":
        mat = tex_mat(tint(noise(512, 6, 11, 3), "#9a9c98", 1.6), spec=0.03)
        hole = Material("#3c3e3c", spec=0.0, ambient=0.2)
        for x0 in (0.0, L + 0.02):
            quads += box(x0 - L / 2, 0, -D / 2, x0 + L / 2, H, D / 2, mat, uvmats={k: mat for k in ("top", "front", "right")})
            for k in range(3):
                hx = x0 - L / 2 + L * (0.18 + 0.32 * k)
                quads += box(hx - L * 0.11, H + 0.0005, -D * 0.32, hx + L * 0.11, H + 0.001, D * 0.32, hole, faces=("top",))
    elif kind in ("pgp", "pgp-green"):
        c = "#f3f2ee" if kind == "pgp" else "#cfe6cf"
        mat = Material(c, spec=0.06, ambient=0.38)
        for i, x0 in enumerate((0.0, L + 0.015)):
            quads += box(x0 - L / 2, 0, -D / 2, x0 + L / 2, H, D / 2, mat)
            quads += box(x0 - L / 2 + 0.02, H, -D * 0.18, x0 + L / 2 - 0.02, H + 0.03, D * 0.18, mat)   # гребень
    return scene_render(quads, yaw=-36, pitch=26)


def bricks(color="#b5532f", count=6, hollow=False, size=(0.25, 0.065, 0.12)):
    """Кирпичи: небольшая кладка-стопка. Фактура — фото кирпича (если есть) с подкраской под цвет."""
    L, H, D = size
    n = noise(512, 40, 5, 3) * 0.6 + noise(512, 4, 6, 1) * 0.4
    img = tint(0.5 + (n - 0.5) * 0.16, color, 1.0)
    mat = tex_mat(img, spec=0.05, ambient=0.34)
    quads = []
    layout = [(0, 0, 0), (L + 0.008, 0, 0), (L / 2 + 0.004, H + 0.004, 0), (0, 0, -D - 0.008),
              (L + 0.008, 0, -D - 0.008), (L / 2 + 0.004, H + 0.004, -D - 0.008)][:count]
    for x, y, z in layout:
        quads += box(x - L / 2, y, z - D, x + L / 2, y + H, z, mat, uvmats={k: mat for k in ("top", "front", "right", "left")})
    return scene_render(quads, yaw=-34, pitch=24)


# ---------------------------------------------------------------------------------------------------------
# Пиломатериалы

def lumber(section=(0.1, 0.1), length=1.6, count=3, kind="pine", planed=False, profile=None):
    """Брус, доска, брусок: штабель из нескольких штук; торец — годичные кольца."""
    a, b = section
    s = 0.22 / max(a * 3, b * 3, 0.22)
    a, b = a * s * 1.6, b * s * 1.6
    side = tex_mat(wood_tex("pine" if kind == "pine" else kind, along="x"), spec=0.12 if planed else 0.05)
    end_img = Image.new("RGB", (512, 512), (214, 176, 120))
    d = ImageDraw.Draw(end_img)
    rng = np.random.default_rng(int(a * 1000))
    cx, cy = rng.uniform(150, 360, 2)
    for r in range(700, 0, -11):
        tone = (198, 156, 100) if (r // 11) % 2 else (222, 186, 132)
        d.ellipse((cx - r, cy - r * 0.95, cx + r, cy + r * 0.95), outline=tone, width=5)
    end = tex_mat(end_img.filter(ImageFilter.GaussianBlur(1.2)), spec=0.03)
    quads = []
    positions = {1: [(0, 0)], 2: [(0, 0), (a + 0.006, 0)], 3: [(0, 0), (a + 0.006, 0), (a / 2, b + 0.004)],
                 4: [(0, 0), (a + 0.006, 0), (0, b + 0.004), (a + 0.006, b + 0.004)],
                 6: [(i * (a + 0.006), j * (b + 0.004)) for j in range(2) for i in range(3)]}[count]
    for x, y in positions:
        uv = {"top": side, "right": side, "left": side, "front": end, "back": end}
        quads += box(x, y, -length / 2, x + a, y + b, length / 2, side, uvmats=uv)
    quads = transform(quads, rot=("y", 62))
    return scene_render(quads, yaw=-30, pitch=24)


def paneling(count=4):
    """Вагонка «штиль»: профиль с пазом и гребнем, вытянутый вдоль длины."""
    w, t = 0.096, 0.014
    prof = [(0, 0), (w, 0), (w, t * 0.35), (w + 0.008, t * 0.35), (w + 0.008, t * 0.65), (w, t * 0.65), (w, t),
            (0.004, t), (0, t - 0.004)]
    side = tex_mat(wood_tex("pine", along="y"), spec=0.15, shine=25)
    endc = Material("#dcb98a", spec=0.05)
    quads = []
    for i in range(count):
        quads += transform(extrude(prof, 1.2, side, cap_mat=endc, uvmat=side), move=(i * (w + 0.002) - 0.2, 0, 0.6))
    quads = transform(quads, rot=("y", 55))
    return scene_render(quads, yaw=-25, pitch=40)


# ---------------------------------------------------------------------------------------------------------
# Кровля

def corrugated(color, kind="c8", sheets=3):
    """Профнастил (c8, c20), металлочерепица (tile), ондулин (ondulin): лист в перспективе, 2–3 штуки стопкой."""
    width, length = 1.15, 1.6
    if kind in ("c8", "c20"):
        h = 0.012 if kind == "c8" else 0.03
        pitch = 0.115 if kind == "c8" else 0.137
        prof = []
        x = 0.0
        while x < width:
            prof += [(x, 0), (x + pitch * 0.18, 0), (x + pitch * 0.32, h), (x + pitch * 0.68, h), (x + pitch * 0.82, 0)]
            x += pitch
        prof.append((x, 0))
        face = Material(color, spec=0.55, shine=70, metal=False, ambient=0.33, double=True)
        quads = []
        for i in range(sheets):
            quads += transform(extrude(prof, length, face, closed=False), move=(-width / 2, i * (h + 0.006), length / 2))
    elif kind == "ondulin":
        prof = [(x, 0.018 * (1 - math.cos(2 * math.pi * x / 0.095))) for x in np.linspace(0, 0.95, 220)]
        face = Material(color, spec=0.15, shine=20, ambient=0.33, double=True)
        quads = []
        for i in range(sheets):
            quads += transform(extrude(prof, length * 1.1, face, closed=False), move=(-0.47, i * 0.008, length / 2))
    else:   # металлочерепица: волна поперёк + ступенька каждые 0.35
        face = Material(color, spec=0.6, shine=80, ambient=0.33, double=True)

        def fn(u, v):
            x = u * width
            z = -v * length
            wave = 0.034 * (1 - math.cos(2 * math.pi * x / 0.185)) / 2
            step = ((v * length) % 0.35) / 0.35
            y = wave + 0.04 * (step ** 2.2) - (0.012 if step > 0.94 else 0)
            return (x - width / 2, y, z + length / 2)
        quads = grid_surface(fn, 180, 120, face)
    return scene_render(quads, yaw=-30, pitch=34)


def ridge(color):
    prof = [(0.016 * math.sin(math.pi * i / 30) - 0.12 + 0.24 * i / 30, 0.12 - abs(0.12 - 0.24 * i / 30) * 0.9)
            for i in range(31)]
    face = Material(color, spec=0.15, shine=20, double=True)
    quads = extrude(prof, 1.0, face, closed=False)
    return scene_render(transform(quads, move=(0, 0, 0.5)), yaw=-40, pitch=26)


def gutter(color, kind="gutter"):
    """Водосток: полукруглый желоб или круглая труба."""
    c = Material(color, spec=0.5, shine=60, double=True)
    if kind == "gutter":
        prof = [(0.0625 * math.cos(a), -0.0625 * math.sin(a)) for a in np.linspace(0, math.pi, 60)]
        prof = [(0.07, 0.004)] + prof + [(-0.07, 0.004)]
        quads = extrude(prof, 0.6, c, closed=False)
    else:
        quads = tube([(0, 0, 0.3), (0, 0, -0.3)], 0.045, c, 64, closed_ends=False)
        quads += [Quad(q.p[::-1], Material("#4a3a2e", spec=0.05, double=True)) for q in tube([(0, 0, 0.3), (0, 0, -0.3)], 0.044, c, 64, closed_ends=False)]
    return scene_render(transform(quads, move=(0, 0, 0.3) if kind == "gutter" else (0, 0, 0)), yaw=-50, pitch=26)


# ---------------------------------------------------------------------------------------------------------
# Сантехника: трубы, фитинги, отопление

def pipe(color="#f1f3f5", r=0.04, length=1.4, socket=True, stripe=None, count=3):
    body = Material(color, spec=0.45, shine=60, ambient=0.36)
    inner = Material("#5b6168", spec=0.1, ambient=0.25)
    quads = []
    length = min(length, r * 18)          # кадр — по длине: длинная тонкая труба превращается в линию
    for i in range(count):
        dz = i * (r * 2.4)
        q = tube([(-length / 2, 0, dz), (length / 2, 0, dz)], r, body, 72, closed_ends=False)
        quads += q
        quads += transform(ring_disk(r * 0.82, r, 0, body, 72), rot=("z", -90), move=(length / 2, 0, dz))
        quads += transform(disk(r * 0.82, -0.001, inner, 72), rot=("z", -90), move=(length / 2, 0, dz))
        if socket:
            quads += tube([(-length / 2 - r * 1.8, 0, dz), (-length / 2 + 0.002, 0, dz)], r * 1.18, body, 72)
        if stripe:
            quads += tube([(-length / 2, 0.0, dz + 0.0), (length / 2, 0, dz)], r * 1.003, Material(stripe), 72,
                          closed_ends=False)[:2]
    return scene_render(transform(quads, rot=("y", 30)), yaw=-25, pitch=22)


def elbow(color, r=0.055, angle=90, sockets=True):
    body = Material(color, spec=0.45, shine=60, ambient=0.36)
    R = r * 2.2
    path = arc_path(-R, 0, R, 0, angle, 40)
    quads = tube(path, r, body, 64)
    if sockets:
        p0 = np.array(path[0])
        quads += tube([p0 - (0, 0.02, 0), p0 - (0, r * 1.6, 0)], r * 1.17, body, 64)
        a = math.radians(angle)
        p1 = np.array(path[-1])
        d = np.array([-math.sin(a), math.cos(a), 0])
        quads += tube([p1 + d * 0.02, p1 + d * r * 1.6], r * 1.17, body, 64)
    return scene_render(quads, yaw=-30, pitch=20)


def tee(color, r=0.055, branch_angle=45):
    body = Material(color, spec=0.45, shine=60, ambient=0.36)
    quads = tube([(-0.25, 0, 0), (0.25, 0, 0)], r, body, 64)
    a = math.radians(branch_angle)
    end = (0.22 * math.cos(a), 0.22 * math.sin(a), 0)
    quads += tube([(0, 0, 0), end], r * 0.98, body, 64)
    for p, q in (((-0.25, 0, 0), (-0.33, 0, 0)), ((0.25, 0, 0), (0.33, 0, 0))):
        quads += tube([p, q], r * 1.17, body, 64)
    quads += tube([end, (end[0] + 0.08 * math.cos(a), end[1] + 0.08 * math.sin(a), 0)], r * 1.17, body, 64)
    return scene_render(quads, yaw=-30, pitch=20)


def coupling(color, r=0.03):
    body = Material(color, spec=0.45, shine=60, ambient=0.36)
    quads = tube([(-0.03, 0, 0), (0.03, 0, 0)], r, body, 64, closed_ends=False)
    quads += tube([(-0.034, 0, 0), (-0.03, 0, 0)], r * 1.04, body, 64, closed_ends=False)
    quads += tube([(0.03, 0, 0), (0.034, 0, 0)], r * 1.04, body, 64, closed_ends=False)
    quads += transform(ring_disk(r * 0.72, r * 1.04, 0, body, 64), rot=("z", -90), move=(0.034, 0, 0))
    quads += transform(disk(r * 0.72, -0.001, Material("#7d848c"), 64), rot=("z", -90), move=(0.034, 0, 0))
    return scene_render(transform(quads, rot=("y", -35)), yaw=-25, pitch=24)


def pipe_coil(color="#f4f5f6"):
    body = Material(color, spec=0.4, shine=50, ambient=0.36)
    path = []
    for i in range(14 * 40):
        a = 2 * math.pi * i / 40
        rr = 0.3 + 0.012 * (i // 40) * 0.25
        path.append((rr * math.cos(a), 0.016 * (i // 40) + 0.0004 * (i % 40), rr * math.sin(a)))
    quads = tube(path, 0.009, body, 16)
    band = Material("#2b8a3e", spec=0.2)
    for ang in (0, 120, 240):
        a = math.radians(ang)
        quads += box(0.27, -0.005, -0.015, 0.34, 0.235, 0.015, band, faces=("front", "top", "right", "left"))
        quads = quads[:-4] + transform(quads[-4:], rot=("y", ang))
    return scene_render(quads, yaw=-20, pitch=40)


def water_heater(liters=80, flow=False):
    white = Material("#f5f6f7", spec=0.5, shine=80, ambient=0.37)
    panel = Material("#2f3338", spec=0.6, shine=90)
    chrome = Material("#cfd4da", spec=1.0, shine=140, metal=True)
    if flow:
        quads = rounded_prism(0.32, 0.12, 0.48, 0.04, white, bevel=0.02)
        quads += box(-0.09, 0.27, 0.061, 0.09, 0.34, 0.064, panel, faces=("front",))
        quads += box(-0.06, 0.29, 0.064, 0.0, 0.32, 0.066, Material("#39d353", emissive=0.6), faces=("front",))
        for x in (-0.08, 0.08):
            quads += tube([(x, 0.0, 0.0), (x, -0.08, 0.0)], 0.011, chrome, 24)
        return scene_render(quads, yaw=-25, pitch=14)
    h = 0.42 + 0.5 * liters / 100
    r = 0.2
    prof = [(0.0, 0.0), (r * 0.6, 0.004), (r * 0.92, 0.03), (r, 0.08), (r, h - 0.06), (r * 0.94, h - 0.02), (r * 0.6, h),
            (0.0, h + 0.004)]
    quads = lathe(prof, white, 160)
    quads += box(-0.06, h * 0.12, r - 0.005, 0.06, h * 0.12 + 0.11, r + 0.025, panel)
    quads += box(-0.035, h * 0.12 + 0.05, r + 0.025, 0.01, h * 0.12 + 0.08, r + 0.027, Material("#3b82f6", emissive=0.5),
                 faces=("front",))
    for x in (-0.07, 0.07):
        quads += tube([(x, 0.01, 0.06), (x, -0.07, 0.06)], 0.012, chrome, 24)
    return scene_render(quads, yaw=-25, pitch=12)


def radiator(sections=8, kind="bimetal"):
    white = Material("#f6f7f8", spec=0.6, shine=90, ambient=0.37)
    quads = []
    w = 0.08
    for i in range(sections):
        x = i * w
        quads += transform(rounded_prism(w * 0.86, 0.075, 0.56, 0.02, white, bevel=0.012), move=(x, 0, 0))
        quads += transform(rounded_prism(w * 0.5, 0.05, 0.5, 0.012, Material("#e8eaec", spec=0.3)), move=(x, 0.03, -0.01))
    quads += tube([(-w / 2, 0.06, 0), (sections * w - w / 2, 0.06, 0)], 0.022, white, 32)
    quads += tube([(-w / 2, 0.5, 0), (sections * w - w / 2, 0.5, 0)], 0.022, white, 32)
    chrome = Material("#cfd4da", spec=1.0, shine=140, metal=True)
    quads += tube([(-w / 2 - 0.035, 0.5, 0), (-w / 2, 0.5, 0)], 0.018, chrome, 24)
    return scene_render(transform(quads, move=(-sections * w / 2, 0, 0)), yaw=-30, pitch=14)


def mayevsky():
    brass = Material("#d4af6a", spec=0.9, shine=110, metal=True, ambient=0.3)
    chrome = Material("#d5d9de", spec=1.0, shine=140, metal=True)
    quads = lathe([(0.04, 0), (0.04, 0.05), (0.052, 0.05), (0.052, 0.09), (0.03, 0.09), (0.03, 0.16), (0.0, 0.165)], brass, 64)
    quads += lathe([(0.012, 0.165), (0.012, 0.21), (0.0, 0.212)], chrome, 32)
    quads += box(-0.004, 0.2, -0.03, 0.004, 0.206, 0.03, chrome)
    return scene_render(quads, yaw=-25, pitch=24)


def expansion_tank(color="#d63031"):
    red = Material(color, spec=0.6, shine=80, ambient=0.35)
    prof = [(0.0, 0.0), (0.12, 0.01), (0.17, 0.05), (0.18, 0.1), (0.18, 0.32), (0.17, 0.37), (0.12, 0.41), (0.0, 0.42)]
    quads = lathe(prof, red, 120)
    brass = Material("#c9a35d", spec=0.9, shine=110, metal=True)
    quads += lathe([(0.03, 0.42), (0.03, 0.46), (0.022, 0.46), (0.022, 0.5), (0.0, 0.5)], brass, 48)
    return scene_render(quads, yaw=-25, pitch=18)


# ---------------------------------------------------------------------------------------------------------
# Металлический профиль и мелкие изделия

def metal_profile(kind="pp", count=3):
    """ПП 60×27 (С-образный с отбортовкой), ПН (П-образный), ПС (стоечный)."""
    gal = tex_mat(proc_tex("galvanized", seed=4), spec=0.7, shine=90, metal=True, double=True)
    t = 0.0015
    if kind == "pp":
        prof = [(-0.03, 0.027), (-0.03, 0.0), (0.03, 0.0), (0.03, 0.027)]
        lip = 0.004
        prof = [(-0.03 + lip, 0.027)] + prof + [(0.03 - lip, 0.027)]
    elif kind == "pn":
        prof = [(-0.014, 0.027), (-0.014, 0.0), (0.014, 0.0), (0.014, 0.027)]
    elif kind == "ps":
        prof = [(-0.019, 0.05), (-0.025, 0.05), (-0.025, 0.0), (0.025, 0.0), (0.025, 0.05), (0.019, 0.05)]
    else:   # pn50
        prof = [(-0.025, 0.04), (-0.025, 0.0), (0.025, 0.0), (0.025, 0.04)]
    quads = []
    for i in range(count):
        quads += transform(extrude(prof, 0.6, gal, closed=False, uvmat=gal), move=(i * 0.075, 0, 0.3))
    del t
    return scene_render(transform(quads, rot=("y", 40)), yaw=-25, pitch=34)


def hanger_pack(name):
    """Коробка с мелкими изделиями (подвесы, крабы, термошайбы, гвозди): картонная коробка с этикеткой."""
    lab = paper(label(name, 700, 520, "small"), 5, seed_of(name))
    kraft = tex_mat(tint(noise(512, 30, 2, 2) * 0.1 + 0.45, "#c79f6b", 1.0), spec=0.06)
    lab_m = tex_mat(lab, spec=0.1)
    quads = box(-0.2, 0, -0.14, 0.2, 0.22, 0.14, kraft, uvmats={"front": lab_m, "top": kraft, "right": kraft})
    tape = Material("#d9c6a3", spec=0.3)
    quads += box(-0.205, 0.2205, -0.03, 0.205, 0.2215, 0.03, tape, faces=("top",))
    return scene_render(quads, yaw=-30, pitch=26)


def thermo_washers(count=7):
    clear = Material("#cfe9f6", spec=0.9, shine=120, ambient=0.42)
    cap = Material("#9ccde6", spec=0.7, shine=90)
    steel = Material("#b8bfc6", spec=0.9, shine=110, metal=True)
    quads = []
    rng = np.random.default_rng(3)
    for i in range(count):
        x, z = rng.uniform(-0.18, 0.18, 2)
        q = lathe([(0.0, 0.0), (0.035, 0.0), (0.035, 0.006), (0.028, 0.012), (0.012, 0.016), (0.0, 0.017)], clear, 48)
        q += lathe([(0.0, 0.016), (0.014, 0.016), (0.012, 0.024), (0.0, 0.025)], cap, 32)
        q += lathe([(0.0035, -0.06), (0.0035, 0.025), (0.0, 0.026)], steel, 12)
        quads += transform(q, rot=("x", rng.uniform(-20, 20)), move=(x, 0.06, z))
    return scene_render(quads, yaw=-25, pitch=40)


# ---------------------------------------------------------------------------------------------------------
# Поликарбонат: профили

def pc_profile(kind="hp", color="#d8edf7"):
    clear = Material(color, spec=0.9, shine=130, ambient=0.44, double=True)
    if kind == "hp":        # соединительный НП: Н-образный
        prof = [(-0.02, 0.02), (-0.02, 0.0), (0.02, 0.0), (0.02, 0.02)]
        quads = []
        for dy in (0.0, 0.012):
            quads += transform(extrude([(-0.02, 0.006), (-0.02, 0.0), (0.02, 0.0), (0.02, 0.006)], 0.4, clear, closed=False),
                               move=(0, dy, 0.2))
        quads += transform(extrude([(0, 0), (0, 0.012)], 0.4, clear, closed=False), move=(0, 0, 0.2))
        del prof
    else:                   # торцевой UP
        quads = extrude([(-0.008, 0.012), (-0.008, 0.0), (0.012, 0.0), (0.012, 0.012)], 0.4, clear, closed=False)
        quads = transform(quads, move=(0, 0, 0.2))
    quads += transform(quads, move=(0.06, 0, 0))
    return scene_render(transform(quads, rot=("y", 40)), yaw=-25, pitch=34)


def greenhouse(length=4):
    green = Material("#2f8a3e", spec=0.4, shine=50, ambient=0.34)
    quads = []
    n = length + 1
    for i in range(n):
        z = -i * 0.5
        path = [(1.5 * math.cos(math.radians(a)), 1.9 * math.sin(math.radians(a)), z) for a in np.linspace(0, 180, 30)]
        quads += tube(path, 0.03, green, 8)
    for a in (0, 35, 70, 90, 110, 145, 180):
        x, y = 1.5 * math.cos(math.radians(a)), 1.9 * math.sin(math.radians(a))
        quads += tube([(x, y, 0), (x, y, -(n - 1) * 0.5)], 0.025, green, 8)
    quads += tube([(-1.5, 0, 0), (1.5, 0, 0)], 0.03, green, 8)
    return scene_render(transform(quads, move=(0, 0, (n - 1) * 0.25)), yaw=-38, pitch=18, shadow=0.25)


# ---------------------------------------------------------------------------------------------------------
# Печное литьё и дымоходы

def cast_iron():
    return tex_mat(proc_tex("cast-iron", seed=9), spec=0.25, shine=30, ambient=0.3)


def stove_plate(burners=2):
    ci = cast_iron()
    w = 0.71 if burners == 2 else 0.41
    d = 0.41 if burners == 2 else 0.34
    quads = box(-w / 2, 0, -d / 2, w / 2, 0.03, d / 2, ci, uvmats={"top": ci, "front": ci, "right": ci})
    for k in range(burners):
        cx = (-w / 4 if burners == 2 else 0) + k * w / 2
        for rr, hh in ((0.13, 0.034), (0.1, 0.037), (0.07, 0.04), (0.04, 0.043)):
            ring = lathe([(rr, 0.03), (rr, hh), (rr - 0.008, hh), (rr - 0.008, 0.03)], ci, 96)
            quads += transform(ring, move=(cx, 0, 0))
        quads += transform(disk(0.032, 0.043, ci, 64), move=(cx, 0, 0))
    return scene_render(quads, yaw=-30, pitch=38)


def stove_door(glass=False, small=False, vent=False):
    ci = cast_iron()
    W, H = (0.25, 0.21) if not small else (0.14, 0.14)
    quads = box(-W / 2 - 0.03, 0, -0.01, W / 2 + 0.03, H + 0.06, 0.0, ci, uvmats={"front": ci})       # рамка
    quads += box(-W / 2, 0.03, 0.0, W / 2, H + 0.03, 0.025, ci, uvmats={"front": ci, "right": ci, "top": ci})
    if glass:
        quads += box(-W / 2 + 0.04, 0.07, 0.025, W / 2 - 0.04, H - 0.01, 0.0265,
                     Material("#1d2024", spec=1.2, shine=200, ambient=0.2), faces=("front",))
    else:
        for i in range(3):
            quads += box(-W / 2 + 0.03, 0.06 + i * H / 3.2, 0.025, W / 2 - 0.03, 0.07 + i * H / 3.2, 0.03, ci)
    if vent:
        quads += box(-0.04, 0.07, 0.025, 0.04, 0.1, 0.035, ci)
    steel = Material("#2a2c2f", spec=0.6, shine=60)
    quads += box(W / 2 - 0.02, H / 2, 0.025, W / 2 + 0.07, H / 2 + 0.02, 0.045, steel)                 # ручка
    for y in (0.05, H):
        quads += tube([(-W / 2 - 0.025, y, 0.012), (-W / 2 - 0.025, y + 0.03, 0.012)], 0.008, steel, 16)
    return scene_render(quads, yaw=-28, pitch=10)


def grate(size=(0.3, 0.25)):
    ci = cast_iron()
    W, D = size
    quads = []
    quads += box(-W / 2, 0, -D / 2, W / 2, 0.03, -D / 2 + 0.02, ci)
    quads += box(-W / 2, 0, D / 2 - 0.02, W / 2, 0.03, D / 2, ci)
    bars = int(W / 0.03)
    for i in range(bars):
        x = -W / 2 + (i + 0.5) * W / bars
        quads += box(x - 0.008, 0, -D / 2 + 0.02, x + 0.008, 0.03, D / 2 - 0.02, ci)
    return scene_render(quads, yaw=-30, pitch=42)


def damper(round_lid=False):
    ci = cast_iron()
    if round_lid:   # вьюшка: плита с круглым отверстием и крышка
        quads = box(-0.17, 0, -0.17, 0.17, 0.015, 0.17, ci, uvmats={"top": ci})
        quads += lathe([(0.11, 0.015), (0.11, 0.035), (0.0, 0.04)], ci, 96)
        quads += box(-0.02, 0.04, -0.005, 0.02, 0.06, 0.005, ci)
        return scene_render(quads, yaw=-30, pitch=38)
    quads = box(-0.17, 0, -0.08, 0.17, 0.018, 0.08, ci, uvmats={"top": ci})
    quads += box(-0.07, 0.018, -0.06, 0.24, 0.026, 0.06, ci, uvmats={"top": ci})
    quads += box(0.24, 0.0, -0.012, 0.27, 0.05, 0.012, ci)
    return scene_render(quads, yaw=-30, pitch=34)


def oven_box():
    steel = Material("#2c2f33", spec=0.5, shine=60, ambient=0.3)
    quads = box(-0.17, 0, -0.22, 0.17, 0.3, 0.22, steel)
    quads += box(-0.15, 0.03, 0.22, 0.15, 0.27, 0.235, steel)
    quads += box(0.06, 0.13, 0.235, 0.14, 0.16, 0.25, Material("#d4d7db", spec=1.0, shine=140, metal=True))
    return scene_render(quads, yaw=-30, pitch=18)


def fireclay_bricks(count=3, size=(0.23, 0.065, 0.114)):
    mat = tex_mat(proc_tex("fireclay", seed=4), spec=0.04)
    L, H, D = size
    quads = []
    for x, y, z in [(0, 0, 0), (L + 0.008, 0, 0), (L / 2, H + 0.004, 0)][:count]:
        quads += box(x - L / 2, y, z - D, x + L / 2, y + H, z, mat, uvmats={k: mat for k in ("top", "front", "right", "left")})
    return scene_render(quads, yaw=-34, pitch=24)


def rope_coil(color="#f1efe8"):
    body = tex_mat(tint(noise(256, 3, 7, 2), color, 0.6), spec=0.1)
    path = []
    for i in range(8 * 48):
        a = 2 * math.pi * i / 48
        rr = 0.12 + 0.022 * (i / 48)
        path.append((rr * math.cos(a), 0.012 * math.sin(a * 3) * 0.2, rr * math.sin(a)))
    return scene_render(tube(path, 0.011, Material(color, spec=0.1), 14), yaw=-20, pitch=55)


def sandwich(kind="pipe"):
    steel = Material("#d9dde1", spec=1.1, shine=160, metal=True, ambient=0.3)
    wool = Material("#f2e7c9", spec=0.02, ambient=0.4)
    inner = Material("#aeb4ba", spec=0.6, shine=80, metal=True)
    R, r = 0.1, 0.058
    quads = []

    def end_cap(at, rot):
        q = ring_disk(r, R * 0.98, 0, wool, 96) + ring_disk(r * 0.96, r, 0.0005, inner, 96)
        return transform(q, rot=rot, move=at)

    if kind == "pipe":
        quads += tube([(0, 0, 0), (0, 0.9, 0)], R, steel, 128, closed_ends=False)
        quads += end_cap((0, 0.9, 0), None)
        quads += tube([(0, 0.9, 0), (0, 0.95, 0)], r, inner, 96, closed_ends=False)
        return scene_render(transform(quads, rot=("z", -55)), yaw=-30, pitch=24)
    if kind == "elbow":
        path = arc_path(-0.25, 0, 0.25, 0, 90, 36)
        quads += tube(path, R, steel, 96, closed_ends=False)
        quads += end_cap((0, 0, 0), ("z", 180))
        return scene_render(quads, yaw=-30, pitch=20)
    if kind == "tee":
        quads += tube([(0, -0.3, 0), (0, 0.3, 0)], R, steel, 96, closed_ends=False)
        quads += tube([(0, 0, 0), (0, 0, 0.32)], R * 0.98, steel, 96, closed_ends=False)
        quads += end_cap((0, 0.3, 0), None)
        quads += end_cap((0, 0, 0.32), ("x", 90))
        return scene_render(quads, yaw=-35, pitch=18)
    if kind == "cap":
        quads += tube([(0, 0, 0), (0, 0.25, 0)], R, steel, 96, closed_ends=False)
        quads += lathe([(0.24, 0.36), (0.0, 0.47)], steel, 128)
        quads += lathe([(0.0, 0.355), (0.24, 0.36)], Material("#b9bfc5", spec=0.6, shine=80, metal=True), 128)
        for a in (0, 120, 240):
            x, z = 0.09 * math.cos(math.radians(a)), 0.09 * math.sin(math.radians(a))
            quads += tube([(x, 0.25, z), (x * 1.6, 0.36, z * 1.6)], 0.006, steel, 8)
        return scene_render(quads, yaw=-30, pitch=18)
    # хомут обжимной
    quads += lathe([(R * 1.02, 0), (R * 1.02, 0.05), (R * 1.0, 0.05), (R * 1.0, 0)], steel, 128)
    quads += box(R * 0.95, 0.0, -0.02, R * 1.25, 0.05, -0.005, steel)
    quads += box(R * 0.95, 0.0, 0.005, R * 1.25, 0.05, 0.02, steel)
    quads += tube([(R * 1.15, 0.025, -0.04), (R * 1.15, 0.025, 0.04)], 0.006, Material("#9aa0a6", spec=0.8, metal=True), 12)
    return scene_render(quads, yaw=-30, pitch=40)


# ---------------------------------------------------------------------------------------------------------
# Напольные покрытия

def laminate_pack(wood="oak", thick=8, name=""):
    """Пачка ламината в плёнке + две доски сверху веером."""
    face = wood_tex(wood, along="x")
    plank_m = tex_mat(face, spec=0.35, shine=40)
    core = Material("#d8c3a0", spec=0.05)
    lab = paper(label(name or "Ламинат", 900, 260, "small"), 3, seed_of(name or wood))
    pack_top = tex_mat(face, spec=0.6, shine=90)
    side = tex_mat(lab, spec=0.4, shine=60)
    L, W = 0.9, 0.26
    H = 0.1 + thick * 0.003
    quads = box(-L / 2, 0, -W / 2, L / 2, H, W / 2, Material("#cfc3ad", spec=0.4),
                uvmats={"top": pack_top, "front": side})
    for i, (dx, rot) in enumerate(((0.05, 8), (-0.02, -6))):
        p = box(-L / 2, 0, -W / 2, L / 2, 0.009, W / 2, core, uvmats={"top": plank_m})
        quads += transform(p, rot=("y", rot), move=(dx, H + 0.001 + i * 0.0095, 0.05 + i * 0.12))
    return scene_render(quads, yaw=-28, pitch=32)


def baseboard(wood="oak", count=3):
    face = tex_mat(wood_tex(wood, along="y"), spec=0.3, shine=40)
    prof = [(0, 0), (0.018, 0), (0.018, 0.012), (0.012, 0.03), (0.006, 0.05), (0.003, 0.058), (0, 0.058)]
    quads = []
    for i in range(count):
        quads += transform(extrude(prof, 0.5, face, cap_mat=Material("#d9d2c4"), uvmat=face), move=(i * 0.03, 0, 0.25))
    return scene_render(transform(quads, rot=("y", 50)), yaw=-25, pitch=24)


def threshold(color="#c9ced4", wood=None):
    mat = tex_mat(wood_tex(wood, along="y"), spec=0.3) if wood else Material(color, spec=0.9, shine=120, metal=True)
    prof = [(-0.015, 0), (0.015, 0), (0.012, 0.004), (0.0, 0.006), (-0.012, 0.004)]
    quads = transform(extrude(prof, 0.3, mat, cap_mat=Material(color, spec=0.8, metal=True), uvmat=mat if wood else None),
                      move=(0, 0, 0.15))
    holes = Material("#5b6168", spec=0.2)
    for z in (-0.1, 0.0, 0.1):
        quads += disk(0.0025, 0.0062, holes, 16, cx=0, cz=z)
    return scene_render(transform(quads, rot=("y", 50)), yaw=-25, pitch=40)


def linoleum(tex_img, width=3.0):
    """Рулон линолеума лёжа, конец полотна раскатан на полу."""
    face = tex_mat(tex_img, spec=0.25, shine=30, double=True)
    back = Material("#e7e2d6", spec=0.05)
    R, L = 0.16, 1.4
    quads = tube([(-L / 2, R, 0), (L / 2, R, 0)], R, back, 96)
    # раскатанное полотно с текстурой
    quads += [Quad([(-L / 2, 0.001, 0.0), (L / 2, 0.001, 0.0), (L / 2, 0.001, 0.8), (-L / 2, 0.001, 0.8)], face,
                   [(0, 0), (1, 0), (1, 0.6), (0, 0.6)])]
    # верхний виток с лицевой стороной
    arc = []
    for i in range(48):
        a = math.radians(-90 + 360 * i / 48 * 0.5)
        arc.append(a)
    for i in range(len(arc) - 1):
        a0, a1 = arc[i], arc[i + 1]
        p = [(-L / 2, R + R * math.sin(a0) * 1.01, R * math.cos(a0) * 1.01), (L / 2, R + R * math.sin(a0) * 1.01, R * math.cos(a0) * 1.01),
             (L / 2, R + R * math.sin(a1) * 1.01, R * math.cos(a1) * 1.01), (-L / 2, R + R * math.sin(a1) * 1.01, R * math.cos(a1) * 1.01)]
        quads.append(Quad(p[::-1], face, [(0, 0.6 + 0.4 * i / 47), (1, 0.6 + 0.4 * i / 47), (1, 0.6 + 0.4 * (i + 1) / 47),
                                          (0, 0.6 + 0.4 * (i + 1) / 47)][::-1]))
    quads = orient(quads, (0, R, 0)) if False else quads
    return scene_render(quads, yaw=-30, pitch=34)


def underlay(kind="xps", name=""):
    if kind == "board":     # хвойная подложка: пачка плит
        mat = tex_mat(tint(noise(512, 4, 5, 3), "#9a6b3c", 1.5), spec=0.04)
        quads = []
        for i in range(6):
            quads += box(-0.4, i * 0.022, -0.3, 0.4, (i + 1) * 0.021, 0.3, mat, uvmats={"top": mat, "front": mat, "right": mat})
        return scene_render(quads, yaw=-34, pitch=30)
    from packshot_items import roll
    color = {"xps": "#d9ead3", "xps2": "#cfe2f3", "cork": "#c69c6d"}.get(kind, "#e5e5e5")
    return roll(name or "Подложка", color=color, r=0.17, h=0.55)


# ---------------------------------------------------------------------------------------------------------
# Санфаянс: внутренняя чаша — рисунком на верхней грани (ортографический вид сверху под углом это позволяет)

def basin_texture(w, h, rim=0.08, color=(246, 247, 248), drain=True, oval=True):
    """Верх раковины/ванны: бортик и затенённая чаша с бликом и сливом."""
    W, H = 1024, int(1024 * h / w)
    img = Image.new("RGB", (W, H), color)
    m = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(m)
    r = int(min(W, H) * rim)
    if oval:
        md.ellipse((r, r, W - r, H - r), fill=255)
    else:
        md.rounded_rectangle((r, r, W - r, H - r), radius=int(min(W, H) * 0.25), fill=255)
    # затенение чаши: темнее у дальнего (верхнего) края и по периметру
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H / 2
    d = np.sqrt(((xx - cx) / (W / 2 - r)) ** 2 + ((yy - cy) / (H / 2 - r)) ** 2)
    shade = 0.78 + 0.18 * (1 - np.clip(d, 0, 1)) ** 0.6 - 0.12 * (1 - yy / H)
    base = np.array(color, dtype=np.float32)
    bowl = np.clip(base[None, None] * shade[..., None], 0, 255).astype(np.uint8)
    img.paste(Image.fromarray(bowl), (0, 0), m.filter(ImageFilter.GaussianBlur(3)))
    dd = ImageDraw.Draw(img)
    if drain:
        dr = int(min(W, H) * 0.035)
        dd.ellipse((cx - dr, cy + H * 0.12 - dr, cx + dr, cy + H * 0.12 + dr), fill=(196, 200, 205), outline=(150, 155, 160), width=3)
    return img


def toilet():
    white = Material("#f7f8f9", spec=0.7, shine=110, ambient=0.38)
    quads = []
    # чаша: «тело вращения», сплюснутое по ширине
    bowl = lathe([(0.11, 0.0), (0.13, 0.015), (0.115, 0.1), (0.15, 0.26), (0.19, 0.36), (0.2, 0.4)], white, 120)
    quads += transform(bowl, rot=np.diag([0.85, 1.0, 1.3]), move=(0, 0, 0.06))
    seat = Material("#fbfbfc", spec=0.6, shine=90, ambient=0.4)
    lid = lathe([(0.0, 0.4), (0.2, 0.4), (0.205, 0.415), (0.19, 0.43), (0.0, 0.432)], seat, 120)
    quads += transform(lid, rot=np.diag([0.86, 1.0, 1.3]), move=(0, 0, 0.06))
    quads += box(-0.14, 0.0, -0.26, 0.14, 0.41, -0.12, white)               # задняя часть с бачком на полке
    tank = rounded_prism(0.4, 0.17, 0.36, 0.04, white, bevel=0.02)
    quads += transform(tank, move=(0, 0.41, -0.22))
    chrome = Material("#d5d9de", spec=1.1, shine=150, metal=True)
    quads += transform(lathe([(0.025, 0), (0.025, 0.012), (0.0, 0.014)], chrome, 48), move=(0, 0.77, -0.22))
    return scene_render(quads, yaw=-35, pitch=18)


def sink(pedestal=False):
    white = Material("#f7f8f9", spec=0.7, shine=110, ambient=0.38)
    quads = []
    if pedestal:
        quads += lathe([(0.11, 0.0), (0.12, 0.02), (0.08, 0.1), (0.07, 0.45), (0.1, 0.64), (0.0, 0.645)], white, 120)
        return scene_render(transform(quads, rot=np.diag([1.0, 1.0, 0.8])), yaw=-30, pitch=14)
    top = tex_mat(basin_texture(0.6, 0.45, 0.07), spec=0.7, shine=110, ambient=0.38)
    quads += rounded_prism(0.6, 0.45, 0.16, 0.02, white, bevel=0.0, top_mat=None)
    quads = [q for q in quads if not (q.p[:, 1].min() > 0.159)]    # убираем крышку — её заменит чаша
    quads += [Quad([(-0.3, 0.16, 0.225), (0.3, 0.16, 0.225), (0.3, 0.16, -0.225), (-0.3, 0.16, -0.225)], top,
                   [(0, 1), (1, 1), (1, 0), (0, 0)])]
    chrome = Material("#d5d9de", spec=1.1, shine=150, metal=True)
    quads += transform(lathe([(0.012, 0), (0.012, 0.004), (0.0, 0.005)], chrome, 24), move=(0, 0.16, -0.17))
    return scene_render(quads, yaw=-30, pitch=34)


def bathtub():
    white = Material("#f7f8f9", spec=0.75, shine=120, ambient=0.38)
    L, W, H = 1.7, 0.7, 0.42
    quads = rounded_prism(L, W, H, 0.06, white, bevel=0.02)
    quads = [q for q in quads if q.p[:, 1].min() < H - 0.001]
    top = tex_mat(basin_texture(L, W, 0.06, oval=False), spec=0.75, shine=120, ambient=0.38)
    quads += [Quad([(-L / 2, H, W / 2), (L / 2, H, W / 2), (L / 2, H, -W / 2), (-L / 2, H, -W / 2)], top,
                   [(0, 1), (1, 1), (1, 0), (0, 0)])]
    leg = Material("#c9ced4", spec=0.9, shine=120, metal=True)
    for x in (-L / 2 + 0.15, L / 2 - 0.15):
        for z in (-W / 2 + 0.12, W / 2 - 0.12):
            quads += transform(lathe([(0.02, -0.08), (0.02, 0.0), (0.0, 0.001)], leg, 24), move=(x, 0, z))
    return scene_render(quads, yaw=-30, pitch=30)


def installation():
    """Инсталляция: стальная рама и бачок."""
    frame = Material("#c9ced4", spec=0.7, shine=90, metal=True)
    blue = Material("#2d6cdf", spec=0.4, shine=60)
    quads = []
    for x in (-0.22, 0.22):
        quads += box(x - 0.02, 0, -0.02, x + 0.02, 1.12, 0.02, frame)
    for y in (0.05, 0.42, 1.08):
        quads += box(-0.24, y, -0.02, 0.24, y + 0.04, 0.02, frame)
    quads += rounded_prism(0.36, 0.09, 0.42, 0.03, blue, bevel=0.01)
    quads = quads[:-0] if False else quads
    quads[-len(rounded_prism(0.36, 0.09, 0.42, 0.03, blue, bevel=0.01)):] = transform(
        rounded_prism(0.36, 0.09, 0.42, 0.03, blue, bevel=0.01), move=(0, 0.62, 0.02))
    white = Material("#f1f3f5", spec=0.4)
    quads += tube([(0, 0.42, 0.04), (0, 0.32, 0.2)], 0.045, white, 32)
    return scene_render(quads, yaw=-30, pitch=12)


# ---------------------------------------------------------------------------------------------------------
# Арматура и крепёж

def ball_valve(size=0.5):
    brass = Material("#d8b46c", spec=1.0, shine=120, metal=True, ambient=0.3)
    red = Material("#d63031", spec=0.5, shine=60)
    s = 1 + size * 0.4
    quads = tube([(-0.12 * s, 0, 0), (0.12 * s, 0, 0)], 0.045 * s, brass, 6)       # шестигранники по краям
    quads += tube([(-0.07 * s, 0, 0), (0.07 * s, 0, 0)], 0.055 * s, brass, 48)
    quads += lathe([(0.025 * s, 0.05 * s), (0.025 * s, 0.09 * s), (0.0, 0.092 * s)], brass, 32)
    quads += box(-0.02 * s, 0.085 * s, -0.012 * s, 0.2 * s, 0.1 * s, 0.012 * s, red)
    return scene_render(quads, yaw=-30, pitch=22)


def thread_rod(r, length, mat, pitch=None, seg=10):
    """Резьба: стержень и винтовая нить вдоль оси Y."""
    pitch = pitch or r * 0.9
    quads = lathe([(r * 0.85, 0), (r * 0.85, length), (0, length + 1e-4)], mat, 32)
    turns = int(length / pitch)
    path = [(r * 0.88 * math.cos(t), pitch * t / (2 * math.pi), r * 0.88 * math.sin(t))
            for t in np.linspace(0, turns * 2 * math.pi, turns * seg)]
    quads += tube(path, r * 0.16, mat, 8, closed_ends=False)
    return quads


def roof_screws(color="#2f4a2e", count=4):
    steel = Material("#c4cad0", spec=0.9, shine=110, metal=True)
    paint = Material(color, spec=0.5, shine=60)
    rubber = Material("#1d1f22", spec=0.2)
    quads = []
    for i, (x, z, rx) in enumerate([(-0.12, 0.05, 70), (0.0, -0.06, 82), (0.12, 0.04, 75), (0.24, -0.04, 88)][:count]):
        q = thread_rod(0.024, 0.32, steel)
        q += transform(lathe([(0.012, -0.03), (0.02, 0.0), (0.0, 0.0)], steel, 16), move=(0, 0, 0))
        q += tube([(0, 0.32, 0), (0, 0.345, 0)], 0.05, rubber, 48)
        q += tube([(0, 0.345, 0), (0, 0.355, 0)], 0.052, steel, 48)
        q += tube([(0, 0.355, 0), (0, 0.4, 0)], 0.04, paint, 6)
        quads += transform(q, rot=("x", rx), move=(x, 0.05, z))
    return scene_render(quads, yaw=-25, pitch=40)


def anchor_bolt():
    steel = Material("#c9ced4", spec=0.9, shine=110, metal=True)
    sleeve = Material("#b6bcc2", spec=0.7, shine=80, metal=True)
    quads = thread_rod(0.03, 0.55, steel)
    quads += lathe([(0.036, 0.05), (0.036, 0.4), (0.0, 0.401)], sleeve, 48)
    quads += tube([(0, 0.4, 0), (0, 0.41, 0)], 0.06, steel, 48)
    quads += tube([(0, 0.41, 0), (0, 0.46, 0)], 0.05, steel, 6)
    return scene_render(transform(quads, rot=("z", -60)), yaw=-25, pitch=30)


def threaded_rod():
    steel = Material("#c9ced4", spec=0.9, shine=110, metal=True)
    quads = thread_rod(0.03, 0.6, steel, pitch=0.02, seg=12)
    for y in (0.08, 0.5):     # гайки
        quads += tube([(0, y, 0), (0, y + 0.035, 0)], 0.055, steel, 6)
    return scene_render(transform(quads, rot=("z", -60)), yaw=-25, pitch=30)


def angle_bracket(count=2):
    gal = tex_mat(proc_tex("galvanized", seed=6), spec=0.8, shine=90, metal=True)
    holes = Material("#4a4f55", spec=0.1, ambient=0.2)
    quads = []
    for i in range(count):
        q = box(0, 0, 0, 0.09, 0.004, 0.065, gal, uvmats={"top": gal})
        q += box(0, 0, 0, 0.004, 0.09, 0.065, gal, uvmats={"right": gal})
        for a in (0.025, 0.05, 0.075):
            for b in (0.02, 0.045):
                q += disk(0.004, 0.0045, holes, 16, cx=a, cz=b)
        q += box(0.004, 0.004, 0.028, 0.03, 0.03, 0.036, gal)   # ребро жёсткости
        quads += transform(q, rot=("y", -20 * i), move=(i * 0.11, 0, -i * 0.04))
    return scene_render(quads, yaw=-40, pitch=26)


def perforated_strip():
    gal = proc_tex("galvanized", seed=8, size=512)
    d = ImageDraw.Draw(gal)
    for x in range(16, 512, 32):
        d.ellipse((x - 7, 256 - 7, x + 7, 256 + 7), fill=(70, 74, 80))
    mat = tex_mat(gal, spec=0.8, shine=90, metal=True)
    plain = Material("#c3c9cf", spec=0.8, shine=90, metal=True)
    quads = lathe([(0.14, 0), (0.14, 0.02)], plain, 120) + lathe([(0.1, 0.02), (0.1, 0.0)], plain, 120)
    quads += ring_disk(0.1, 0.14, 0.02, plain, 120)
    mat.double = True
    quads += [Quad([(0.0, 0.001, 0.14), (0.45, 0.001, 0.14), (0.45, 0.001, 0.115), (0.0, 0.001, 0.115)],
                   mat, [(0, 0.35), (1, 0.35), (1, 0.65), (0, 0.65)])]
    return scene_render(quads, yaw=-25, pitch=45)


# ---------------------------------------------------------------------------------------------------------
# Ручной инструмент без фото

def trowel():
    steel = Material("#cdd2d8", spec=1.0, shine=130, metal=True, double=True)
    wood = tex_mat(wood_tex("lumber", along="y"), spec=0.2)
    blade = [Quad([(0, 0, 0), (0.18, 0, -0.1), (0.18, 0, 0.1)], steel)]
    quads = blade + tube([(0.02, 0.0, 0.0), (0.0, 0.05, 0.0), (-0.03, 0.06, 0.0)], 0.006, steel, 12)
    quads += lathe([(0.012, 0), (0.016, 0.02), (0.016, 0.1), (0.012, 0.12), (0.0, 0.121)], wood, 32) and \
        transform(lathe([(0.012, 0), (0.016, 0.02), (0.016, 0.1), (0.012, 0.12), (0.0, 0.121)], Material("#b07a45", spec=0.2), 32),
                  rot=("z", 90), move=(-0.03, 0.06, 0))
    return scene_render(quads, yaw=-30, pitch=40)


def facade_spatula(width=0.45):
    steel = Material("#d4d8dd", spec=1.0, shine=140, metal=True, double=True)
    handle = Material("#2b2f33", spec=0.4, shine=50)
    accent = Material("#f2b705", spec=0.4, shine=50)
    quads = box(-width / 2, 0, -0.06, width / 2, 0.002, 0.06, steel)
    quads += box(-width * 0.3, 0.002, -0.02, width * 0.3, 0.012, 0.02, accent)        # держатель полотна
    quads += transform(rounded_prism(0.16, 0.034, 0.05, 0.014, handle, bevel=0.008), move=(0, 0.012, 0))
    quads += tube([(-0.07, 0.012, 0), (-0.07, 0.04, 0)], 0.008, handle, 12)
    quads += tube([(0.07, 0.012, 0), (0.07, 0.04, 0)], 0.008, handle, 12)
    return scene_render(quads, yaw=-30, pitch=34)


def straightedge(length=2.0):
    alu = Material("#cfd4da", spec=0.9, shine=110, metal=True)
    prof = [(0, 0), (0.1, 0), (0.1, 0.006), (0.06, 0.018), (0.04, 0.018), (0.0, 0.006)]
    quads = transform(extrude(prof, 1.6, alu, cap_mat=alu), move=(-0.05, 0, 0.8))
    cap = Material("#2b2f33", spec=0.3)
    quads += box(-0.052, -0.001, 0.8, 0.052, 0.02, 0.83, cap)
    return scene_render(transform(quads, rot=("y", 60)), yaw=-25, pitch=34)


def shovel():
    steel = Material("#5a6068", spec=0.7, shine=70, metal=True, double=True)
    wood = Material("#c99a62", spec=0.2, shine=20)

    def blade(u, v):
        w = 0.11 * (1 - 0.55 * v ** 2.5)
        x = (u - 0.5) * 2 * w
        y = -v * 0.3
        z = 0.025 * (1 - (2 * u - 1) ** 2)
        return (x, y, z)
    quads = grid_surface(blade, 24, 24, steel)
    quads += tube([(0, 0.0, 0.01), (0, 0.08, 0.01)], 0.022, steel, 24)
    quads += tube([(0, 0.08, 0.01), (0, 1.15, 0.01)], 0.018, wood, 24)
    return scene_render(transform(quads, rot=("z", -40)), yaw=-25, pitch=24)


def bucket_plain(color="#2f3338"):
    from packshot_items import lathe as _lathe   # noqa: F401 — тот же lathe
    body = Material(color, spec=0.3, shine=40, ambient=0.34, double=True)
    prof = [(0.13, 0.0), (0.135, 0.01), (0.165, 0.3), (0.172, 0.31), (0.172, 0.32)]
    quads = lathe(prof, body, 120)
    quads += disk(0.13, 0.006, Material("#25282c"), 64)
    handle = Material("#9aa0a6", spec=0.7, metal=True)
    quads += tube(arc_path(0, 0.26, 0.18, 200, 340, 30, z=0.0), 0.005, handle, 12)
    return scene_render(quads, yaw=-20, pitch=30)


def mixer_paddle():
    steel = Material("#c9ced4", spec=0.9, shine=110, metal=True)
    quads = tube([(0, 0, 0), (0, 0.55, 0)], 0.008, steel, 16)
    path = [(0.05 * math.cos(t), -0.12 * t / (4 * math.pi), 0.05 * math.sin(t)) for t in np.linspace(0, 4 * math.pi, 120)]
    quads += tube(path, 0.006, steel, 10)
    return scene_render(transform(quads, rot=("z", -55)), yaw=-25, pitch=30)


def cutting_discs(count=3, color="#2d6cdf"):
    disc = tex_mat(tint(noise(256, 3, 3, 2), "#3a3d41", 1.4), spec=0.3)
    lab = Image.new("RGB", (512, 512), (58, 61, 65))
    d = ImageDraw.Draw(lab)
    d.ellipse((96, 96, 416, 416), fill=hexrgb(color))
    d.ellipse((216, 216, 296, 296), fill=(210, 214, 218))
    d.text((256, 150), "125", font=font(56), fill="white", anchor="mm")
    top = tex_mat(ImageOps.mirror(lab), spec=0.3)
    quads = []
    for i in range(count):
        q = lathe([(0.125, 0), (0.125, 0.006)], disc, 96)
        seg = 96
        for k in range(seg):
            t0, t1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
            p = [(0, 0.006, 0), (0.125 * math.sin(t0), 0.006, 0.125 * math.cos(t0)), (0.125 * math.sin(t1), 0.006, 0.125 * math.cos(t1))]
            uv = [(0.5, 0.5), (0.5 + 0.49 * math.sin(t0), 0.5 - 0.49 * math.cos(t0)), (0.5 + 0.49 * math.sin(t1), 0.5 - 0.49 * math.cos(t1))]
            q.append(Quad(p, top, uv))
        quads += transform(q, move=(i * 0.03, i * 0.008, -i * 0.02))
    return scene_render(quads, yaw=-25, pitch=40)


def wool_pack(name, color="#f2c94c"):
    """Упаковка минваты/утеплителя в плёнке: скруглённая «подушка» с принтом."""
    lab = paper(label(name, 800, 520, "small", base="#ffffff"), 4, seed_of(name))
    film = Material(color, spec=0.6, shine=70, ambient=0.36)
    lab_m = tex_mat(lab, spec=0.6, shine=70)
    quads = rounded_prism(1.0, 0.6, 0.5, 0.08, film, lab_m, (0.12, 0.88, 0.12, 0.88), bevel=0.05, rows=20, cols=20)
    return scene_render(quads, yaw=-30, pitch=22)


def foil_roll(name):
    from packshot_items import roll
    return roll(name, color="#d9dde1", r=0.17, h=0.5)


def tile_tex(color=(196, 199, 202)):
    """Линолеум «плитка»: квадраты с лёгкой разницей тона и швами."""
    img = Image.new("RGB", (1024, 1024), (150, 153, 156))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(5)
    for i in range(8):
        for j in range(8):
            k = rng.uniform(0.92, 1.05)
            c = tuple(int(v * k) for v in color)
            d.rectangle((i * 128 + 2, j * 128 + 2, i * 128 + 126, j * 128 + 126), fill=c)
    n = (noise(1024, 30, 9, 3) - 0.5) * 18
    a = np.asarray(img, dtype=np.float32) + n[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def mixer_tool():
    """Строительный миксер: корпус с двигателем, две рукоятки, насадка."""
    body = Material("#2b8a3e", spec=0.5, shine=60, ambient=0.34)
    black = Material("#25282c", spec=0.4, shine=50, ambient=0.3)
    steel = Material("#c9ced4", spec=0.9, shine=110, metal=True)
    quads = transform(rounded_prism(0.16, 0.13, 0.3, 0.05, body, bevel=0.02), move=(0, 0.25, 0))
    quads += transform(lathe([(0.05, 0), (0.05, 0.08), (0.0, 0.081)], black, 48), move=(0, 0.17, 0))
    for side in (-1, 1):
        quads += tube([(side * 0.08, 0.42, 0), (side * 0.2, 0.44, 0), (side * 0.22, 0.32, 0), (side * 0.08, 0.3, 0)],
                      0.018, black, 16)
    quads += tube([(0, 0.17, 0), (0, -0.25, 0)], 0.008, steel, 16)
    path = [(0.05 * math.cos(t), -0.25 - 0.1 * t / (4 * math.pi), 0.05 * math.sin(t)) for t in np.linspace(0, 4 * math.pi, 100)]
    quads += tube(path, 0.006, steel, 10)
    return scene_render(quads, yaw=-30, pitch=16)


def siphon():
    """Бутылочный сифон: решётка выпуска, трубка, «бутылка», отвод в канализацию."""
    white = Material("#f4f5f6", spec=0.55, shine=80, ambient=0.38)
    chrome = Material("#d5d9de", spec=1.1, shine=150, metal=True)
    quads = transform(lathe([(0.0, 0.0), (0.045, 0.0), (0.045, 0.01), (0.0, 0.011)], chrome, 64), move=(0, 0.46, 0))
    quads += tube([(0, 0.46, 0), (0, 0.3, 0)], 0.018, white, 32)
    quads += lathe([(0.0, 0.08), (0.045, 0.085), (0.05, 0.11), (0.05, 0.3), (0.042, 0.33), (0.02, 0.34), (0.0, 0.341)], white, 96)
    quads += lathe([(0.0, 0.05), (0.04, 0.05), (0.042, 0.085), (0.0, 0.086)], Material("#e3e6e9", spec=0.4), 64)
    quads += tube([(0.0, 0.25, 0.0), (0.12, 0.25, 0.0), (0.2, 0.2, 0.0), (0.24, 0.12, 0.0)], 0.02, white, 32)
    quads += tube([(0.24, 0.13, 0.0), (0.24, 0.02, 0.0)], 0.026, white, 32)
    return scene_render(quads, yaw=-30, pitch=14)
