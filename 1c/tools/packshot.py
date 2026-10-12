"""Мини-рендер товарных «рисунков» для товаров без подходящего фото: мешки, вёдра, листы, трубы, профили, литьё.

Объект собирается из четырёхугольников в 3D, проецируется ортографически (вид 3/4 сверху, как на студийной
съёмке), закрашивается по модели освещения «студия» (основной свет сверху слева, заполняющий справа,
светлое небо сверху, блик) и рисуется от дальних граней к ближним. Этикетки и текстуры (дерево, OSB)
натягиваются на грани аффинным преобразованием. Сверху — мягкая контактная тень на белом полу.

Только PIL и numpy: рисуется в 2× размере и уменьшается — края получаются сглаженными.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1000          # итоговая картинка, квадрат
SS = 2               # сглаживание: рисуем в SS раз крупнее
FILL = 0.78          # доля кадра под объект (по большей стороне)

# Свет в системе камеры (x вправо, y вверх, z к зрителю)
KEY = np.array([-0.45, 0.75, 0.55])
KEY = KEY / np.linalg.norm(KEY)
FILL_LIGHT = np.array([0.7, 0.25, 0.65])
FILL_LIGHT = FILL_LIGHT / np.linalg.norm(FILL_LIGHT)
VIEW = np.array([0.0, 0.0, 1.0])


def srgb(c):
    """'#rrggbb' или (r, g, b) 0..255 -> линейный RGB 0..1."""
    if isinstance(c, str):
        c = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    return (np.array(c, dtype=float) / 255.0) ** 2.2


def to_u8(lin):
    return np.clip(np.power(np.clip(lin, 0, None), 1 / 2.2) * 255 + 0.5, 0, 255).astype(np.uint8)


class Material:
    def __init__(self, color="#cccccc", spec=0.25, shine=40, texture=None, metal=False, ambient=0.32,
                 double=False, emissive=0.0):
        self.color = srgb(color)
        self.spec = spec
        self.shine = shine
        self.texture = texture          # PIL RGB — натягивается по UV
        self.metal = metal              # блик окрашен цветом металла
        self.ambient = ambient
        self.double = double            # тонкая поверхность: видна с обеих сторон
        self.emissive = emissive
        self._tex_lin = None

    def tex_lin(self):
        if self._tex_lin is None and self.texture is not None:
            self._tex_lin = (np.asarray(self.texture.convert("RGB"), dtype=np.float32) / 255.0) ** 2.2
        return self._tex_lin


class Quad:
    __slots__ = ("p", "mat", "uv")

    def __init__(self, p, mat, uv=None):
        self.p = np.asarray(p, dtype=float)   # 4×3 (или 3×3 — треугольник)
        self.mat = mat
        self.uv = None if uv is None else np.asarray(uv, dtype=float)


class Scene:
    def __init__(self, yaw=-32, pitch=22):
        self.quads = []
        y, x = math.radians(yaw), math.radians(pitch)
        ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
        rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
        self.rot = rx @ ry

    def add(self, quads):
        self.quads.extend(quads)
        return self

    # --- рендер ---------------------------------------------------------------------------------------
    def render(self, size=SIZE, fill=FILL, shadow=0.42, lift=0.0):
        big = size * SS
        cam = [(q, q.p @ self.rot.T) for q in self.quads]
        allpts = np.concatenate([c[:, :2] for _, c in cam])
        lo, hi = allpts.min(0), allpts.max(0)
        span = max(hi[0] - lo[0], (hi[1] - lo[1]) * 1.0)
        scale = big * fill / span
        cx, cy = (lo + hi) / 2

        # Пол — чуть ниже самой нижней точки объекта (в мире); тень кладём на него
        ground = min(q.p[:, 1].min() for q in self.quads) - lift

        def screen(c):
            return np.stack([(c[:, 0] - cx) * scale + big / 2, -(c[:, 1] - cy) * scale + big / 2 + big * 0.03], 1)

        # Тень: проекция всех граней на пол сверху
        shadow_mask = Image.new("L", (big, big), 0)
        sd = ImageDraw.Draw(shadow_mask)
        for q in self.quads:
            fp = q.p.copy()
            fp[:, 1] = ground
            pts = screen(fp @ self.rot.T)
            sd.polygon([tuple(v) for v in pts], fill=255)

        color = np.ones((big, big, 3), dtype=np.float32)          # белый пол, линейный
        img = Image.new("RGB", (big, big), (255, 255, 255))
        if shadow:
            soft = np.asarray(shadow_mask.filter(ImageFilter.GaussianBlur(big * 0.035)), dtype=np.float32) / 255
            tight = np.asarray(shadow_mask.filter(ImageFilter.GaussianBlur(big * 0.008)), dtype=np.float32) / 255
            dark = 1 - shadow * (0.55 * soft + 0.45 * tight)
            color *= dark[..., None]
        img = Image.fromarray(to_u8(color))

        order = sorted(cam, key=lambda qc: qc[1][:, 2].mean())
        draw = ImageDraw.Draw(img)
        for q, c in order:
            n = np.cross(c[1] - c[0], c[2] - c[0])
            if len(c) == 4:
                n = n + np.cross(c[2] - c[0], c[3] - c[0])
            norm = np.linalg.norm(n)
            if norm < 1e-12:
                continue
            n = n / norm
            if n[2] <= 0:
                if not q.mat.double:
                    continue
                n = -n
            pts = screen(c)
            shade, spec = self._light(n, q.mat)
            if q.uv is not None and q.mat.texture is not None:
                self._textured(img, pts, q, shade, spec)
            else:
                rgb = tuple(int(v) for v in to_u8(q.mat.color * shade + spec))
                poly = [tuple(v) for v in pts]
                draw.polygon(poly, fill=rgb, outline=rgb)
        return img.resize((size, size), Image.LANCZOS)

    def _light(self, n, m):
        diff = max(0.0, float(n @ KEY)) * 0.78 + max(0.0, float(n @ FILL_LIGHT)) * 0.22
        sky = m.ambient * (0.75 + 0.35 * n[1])
        shade = sky + diff * (1 - m.ambient * 0.6) + m.emissive
        h = (KEY + VIEW) / np.linalg.norm(KEY + VIEW)
        s = m.spec * max(0.0, float(n @ h)) ** m.shine
        h2 = (FILL_LIGHT + VIEW) / np.linalg.norm(FILL_LIGHT + VIEW)
        s += m.spec * 0.35 * max(0.0, float(n @ h2)) ** m.shine
        spec = (m.color * 1.6 if m.metal else np.ones(3)) * s
        return shade, spec

    def _textured(self, img, pts, q, shade, spec):
        x0, y0 = np.floor(pts.min(0)).astype(int) - 1
        x1, y1 = np.ceil(pts.max(0)).astype(int) + 1
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h <= 0:
            return
        tex = q.mat.texture
        tw, th = tex.size
        # Аффинное отображение экран -> текстура по трём вершинам
        src = q.uv[:3] * [tw - 1, th - 1]
        dst = pts[:3] - [x0, y0]
        a = np.array([[dst[0][0], dst[0][1], 1], [dst[1][0], dst[1][1], 1], [dst[2][0], dst[2][1], 1]])
        try:
            cu = np.linalg.solve(a, src[:, 0])
            cv = np.linalg.solve(a, src[:, 1])
        except np.linalg.LinAlgError:
            return
        patch = tex.transform((w, h), Image.AFFINE, (*cu, *cv), resample=Image.BILINEAR)
        lin = (np.asarray(patch, dtype=np.float32) / 255.0) ** 2.2
        out = Image.fromarray(to_u8(lin * shade + spec))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon([tuple(v) for v in pts - [x0, y0]], fill=255, outline=255)
        img.paste(out, (int(x0), int(y0)), mask)


# ---------------------------------------------------------------------------------------------------------
# Построители сеток. Обход вершин — против часовой стрелки при взгляде снаружи.

def box(x0, y0, z0, x1, y1, z1, mat, faces="all", uvmats=None):
    """Параллелепипед. uvmats: {'front'|'top'|'right'|'left'|'back'|'bottom': Material с текстурой}."""
    uvmats = uvmats or {}
    v = {
        "front": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        "back": [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],
        "right": [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],
        "left": [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
        "top": [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)],
        "bottom": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
    }
    uv = [(0, 1), (1, 1), (1, 0), (0, 0)]
    out = []
    for name, pts in v.items():
        if faces != "all" and name not in faces:
            continue
        m = uvmats.get(name, mat)
        out.append(Quad(pts, m, uv if m.texture is not None else None))
    return out


def lathe(profile, mat, seg=144, uvmat=None, uv_range=None, a0=0.0, a1=2 * math.pi):
    """Тело вращения вокруг оси Y. profile — [(r, y), ...] снизу вверх.
    uvmat/uv_range=(i0, i1): этикетка на поясе между точками профиля i0..i1 (развёртка по углу)."""
    out = []
    for i in range(len(profile) - 1):
        (r0, y0), (r1, y1) = profile[i], profile[i + 1]
        labeled = uvmat is not None and uv_range and uv_range[0] <= i < uv_range[1]
        for k in range(seg):
            t0 = a0 + (a1 - a0) * k / seg
            t1 = a0 + (a1 - a0) * (k + 1) / seg
            p = [(r0 * math.sin(t0), y0, r0 * math.cos(t0)), (r0 * math.sin(t1), y0, r0 * math.cos(t1)),
                 (r1 * math.sin(t1), y1, r1 * math.cos(t1)), (r1 * math.sin(t0), y1, r1 * math.cos(t0))]
            if labeled:
                i0, i1 = uv_range
                ya, yb = profile[i0][1], profile[i1][1]
                u0, u1 = k / seg, (k + 1) / seg
                v0 = 1 - (y0 - ya) / (yb - ya)
                v1 = 1 - (y1 - ya) / (yb - ya)
                out.append(Quad(p, uvmat, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]))
            else:
                out.append(Quad(p, mat))
    return out


def disk(r, y, mat, seg=144, down=False, cx=0.0, cz=0.0):
    out = []
    for k in range(seg):
        t0, t1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        p = [(cx, y, cz), (cx + r * math.sin(t0), y, cz + r * math.cos(t0)), (cx + r * math.sin(t1), y, cz + r * math.cos(t1))]
        if down:
            p = p[::-1]
        out.append(Quad(p, mat))
    return out


def ring_disk(r_in, r_out, y, mat, seg=144, down=False):
    out = []
    for k in range(seg):
        t0, t1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        p = [(r_in * math.sin(t0), y, r_in * math.cos(t0)), (r_out * math.sin(t0), y, r_out * math.cos(t0)),
             (r_out * math.sin(t1), y, r_out * math.cos(t1)), (r_in * math.sin(t1), y, r_in * math.cos(t1))]
        out.append(Quad(p[::-1] if down else p, mat))
    return out


def transform(quads, rot=None, move=(0, 0, 0), scale=1.0):
    """Поворот (матрица 3×3 или (ось, градусы)), масштаб и сдвиг набора граней."""
    if isinstance(rot, tuple):
        rot = rotation(*rot)
    out = []
    for q in quads:
        p = q.p * scale
        if rot is not None:
            p = p @ rot.T
        out.append(Quad(p + np.asarray(move, dtype=float), q.mat, q.uv))
    return out


def rotation(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def extrude(poly, length, mat, cap_mat=None, uvmat=None, closed=True):
    """Призма: 2D-контур poly [(x, y), ...] в плоскости XY, вытянутый по Z от 0 до -length.
    closed=False — открытый профиль (лист, швеллер без торцов). uvmat — текстура вдоль длины на боковых гранях."""
    out = []
    n = len(poly)
    rng = range(n) if closed else range(n - 1)
    total = sum(math.dist(poly[i], poly[(i + 1) % n]) for i in rng)
    acc = 0.0
    for i in rng:
        (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
        seg = math.dist(poly[i], poly[(i + 1) % n])
        p = [(xa, ya, 0), (xa, ya, -length), (xb, yb, -length), (xb, yb, 0)]
        if uvmat is not None:
            u0, u1 = acc / total, (acc + seg) / total
            out.append(Quad(p, uvmat, [(u0, 1), (u0, 0), (u1, 0), (u1, 1)]))
        else:
            out.append(Quad(p, mat))
        acc += seg
    if closed and cap_mat is not None:
        cx = sum(x for x, _ in poly) / n
        cy = sum(y for _, y in poly) / n
        for i in range(n):
            (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
            out.append(Quad([(cx, cy, 0), (xa, ya, 0), (xb, yb, 0)], cap_mat))
            out.append(Quad([(cx, cy, -length), (xb, yb, -length), (xa, ya, -length)], cap_mat))
    return out


def grid_surface(fn, nu, nv, mat, uvmat=None, uv_fn=None):
    """Поверхность по параметрам u, v ∈ [0, 1]: fn(u, v) -> (x, y, z). uv_fn(u, v) -> (s, t) | None."""
    pts = [[np.array(fn(i / nu, j / nv), dtype=float) for j in range(nv + 1)] for i in range(nu + 1)]
    out = []
    for i in range(nu):
        for j in range(nv):
            p = [pts[i][j], pts[i + 1][j], pts[i + 1][j + 1], pts[i][j + 1]]
            if uvmat is not None and uv_fn is not None:
                corners = [uv_fn(i / nu, j / nv), uv_fn((i + 1) / nu, j / nv), uv_fn((i + 1) / nu, (j + 1) / nv),
                           uv_fn(i / nu, (j + 1) / nv)]
                if all(c is not None for c in corners):
                    out.append(Quad(p, uvmat, corners))
                    continue
            out.append(Quad(p, mat))
    return out


def superquad(a, b, c, e1, e2, mat, nu=72, nv=48, uvmat=None, uv_fn=None):
    """Суперэллипсоид с полуосями a (x), b (y), c (z). e1, e2 < 1 — «скруглённый ящик» (канистра, упаковка).
    uv_fn(x, y, z, n) -> (s, t) | None — этикетка по положению точки (обычно на передней грани)."""
    def sp(w, e):
        return math.copysign(abs(w) ** e, w)

    def point(u, v):
        eta = -math.pi / 2 + math.pi * v
        om = -math.pi + 2 * math.pi * u
        return (a * sp(math.cos(eta), e1) * sp(math.sin(om), e2), b * sp(math.sin(eta), e1),
                c * sp(math.cos(eta), e1) * sp(math.cos(om), e2))

    def uvf(u, v):
        return uv_fn(*point(u, v)) if uv_fn else None

    return grid_surface(point, nu, nv, mat, uvmat, uvf if uv_fn else None)


def tube(path, r, mat, seg=48, closed_ends=True):
    """Труба радиуса r вдоль ломаной path [(x, y, z), ...]."""
    path = [np.asarray(p, dtype=float) for p in path]
    rings = []
    for i, p in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)])
        t = t / np.linalg.norm(t)
        ref = np.array([0, 1, 0]) if abs(t[1]) < 0.9 else np.array([1, 0, 0])
        a = np.cross(t, ref)
        a /= np.linalg.norm(a)
        b = np.cross(t, a)
        rings.append([p + r * (math.cos(2 * math.pi * k / seg) * a + math.sin(2 * math.pi * k / seg) * b)
                      for k in range(seg)])
    out = []
    for i in range(len(rings) - 1):
        for k in range(seg):
            k1 = (k + 1) % seg
            quad = [rings[i][k], rings[i + 1][k], rings[i + 1][k1], rings[i][k1]]
            n = np.cross(quad[1] - quad[0], quad[3] - quad[0])
            if n @ (quad[0] - path[i]) < 0:      # нормаль внутрь — разворачиваем обход
                quad = quad[::-1]
            out.append(Quad(quad, mat))
    if closed_ends:
        for ring, outward in ((rings[0], path[0] - path[1]), (rings[-1], path[-1] - path[-2])):
            c = sum(ring) / seg
            for k in range(seg):
                tri = [c, ring[k], ring[(k + 1) % seg]]
                if np.cross(tri[1] - tri[0], tri[2] - tri[0]) @ outward < 0:
                    tri = tri[::-1]
                out.append(Quad(tri, mat))
    return out


def arc_path(cx, cy, r, a0, a1, n=40, z=0.0, plane="xy"):
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        if plane == "xy":
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
        else:
            pts.append((cx + r * math.cos(a), z, cy + r * math.sin(a)))
    return pts



def orient(quads, center):
    """Разворачивает грани выпуклого тела нормалью наружу (от центра)."""
    c = np.asarray(center, dtype=float)
    out = []
    for q in quads:
        p = q.p
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if n @ (p.mean(0) - c) < 0:
            p = p[::-1]
            uv = None if q.uv is None else q.uv[::-1]
            out.append(Quad(p, q.mat, uv))
        else:
            out.append(q)
    return out


def rounded_prism(w, d, h, r, mat, label_mat=None, label_box=(0.1, 0.9, 0.1, 0.9), bevel=0.0, top_mat=None,
                  rows=24, cols=16, corner_seg=10):
    """Вертикальная призма со скруглёнными углами (вид сверху — скруглённый прямоугольник w×d), высота h.
    Передняя плоская грань (z = +d/2) разбита на клетки; этикетка — в прямоугольнике label_box
    (доли ширины передней грани u0, u1 и высоты v0, v1, снизу вверх). bevel — фаска сверху и снизу."""
    hw, hd = w / 2, d / 2
    pts = []   # от правого конца передней грани по кругу: правый-перед, правый-зад, левый-зад, левый-перед
    for cx, cz, a0 in ((hw - r, hd - r, 90), (hw - r, -hd + r, 0), (-hw + r, -hd + r, -90), (-hw + r, hd - r, 180)):
        for k in range(corner_seg + 1):
            a = math.radians(a0 - 90 * k / corner_seg)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    out = []
    y0, y1 = bevel, h - bevel
    n = len(pts)
    for i in range(n - 1):     # последнее ребро (левый-перед -> правый-перед) — передняя грань, она ниже
        (xa, za), (xb, zb) = pts[i], pts[i + 1]
        out.append(Quad([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)], mat))
    xl, xr = -hw + r, hw - r
    lu0, lu1, lv0, lv1 = label_box
    for i in range(cols):
        xa, xb = xl + (xr - xl) * i / cols, xl + (xr - xl) * (i + 1) / cols
        for j in range(rows):
            ya, yb = y0 + (y1 - y0) * j / rows, y0 + (y1 - y0) * (j + 1) / rows
            quad = [(xa, ya, hd), (xb, ya, hd), (xb, yb, hd), (xa, yb, hd)]
            ua, ub, va, vb = i / cols, (i + 1) / cols, j / rows, (j + 1) / rows
            inside = ua >= lu0 - 1e-9 and ub <= lu1 + 1e-9 and va >= lv0 - 1e-9 and vb <= lv1 + 1e-9
            if label_mat is not None and inside:
                su = [(u - lu0) / (lu1 - lu0) for u in (ua, ub)]
                sv = [1 - (v - lv0) / (lv1 - lv0) for v in (va, vb)]
                out.append(Quad(quad, label_mat, [(su[0], sv[0]), (su[1], sv[0]), (su[1], sv[1]), (su[0], sv[1])]))
            else:
                out.append(Quad(quad, mat))
    # фаски и крышки
    def ring(y, k):
        return [(x * (1 - k / hw), y, z * (1 - k / hd)) for x, z in pts]
    inset = bevel * 1.3
    for ya, yb in ((y1, h), (y0, 0.0)):
        ra, rb = ring(ya, 0), ring(yb, inset)
        for i in range(n):
            out.append(Quad([ra[i], ra[(i + 1) % n], rb[(i + 1) % n], rb[i]], mat))
        c = (0, yb, 0)
        for i in range(n):
            out.append(Quad([c, rb[i], rb[(i + 1) % n]], top_mat or mat))
    return orient(out, (0, h / 2, 0))
