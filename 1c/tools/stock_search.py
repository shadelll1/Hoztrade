"""Кандидаты фото со стоков для товаров-предметов и листы для выбора.

Источники: Pixabay (Pixabay Content License, ключ — 1c/tools/.pixabay-key) и Openverse (только CC0 и Public
Domain — без обязательного указания автора). По каждому понятию — три ряда по 10 снимков:
  a — Pixabay с фильтром «белый фон» (такие снимки чище всего вырезаются),
  b — Pixabay без фильтра,
  c — Openverse.
Выбор записывается в product_images.CHOICES кодом вида "a3".

  python 1c/tools/stock_search.py [понятие ...]   — без аргументов: все понятия из STOCK
"""
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

TOOLS = Path(__file__).resolve().parent
CACHE = TOOLS / ".image-cache" / "stock"
PER_ROW = 10
THUMB = 150

# Понятие -> (запрос Pixabay, запрос Openverse). Запросы — про предмет целиком, а не про стройку вокруг него.
STOCK = {
    "brick-red": ("red brick", "red clay brick"),
    "brick-white": ("white brick", "silicate brick"),
    "brick-yellow": ("yellow brick", "yellow brick"),
    "fire-brick": ("fire brick", "refractory brick"),
    "beam": ("wooden beam", "lumber beam"),
    "board": ("wooden boards", "lumber planks"),
    "batten": ("wooden slats", "wooden battens"),
    "pp-pipe": ("plastic pipe", "pvc pipe"),
    "sewer-pipe": ("pvc pipe", "drain pipe pvc"),
    "pp-fitting": ("pipe fitting", "pipe fittings plastic"),
    "sewer-fitting": ("pvc elbow", "pvc fitting"),
    "pipe-coil": ("pipe coil", "hose coil"),
    "ball-valve": ("ball valve", "brass valve"),
    "flex-hose": ("braided hose", "flexible hose"),
    "faucet-kitchen": ("kitchen faucet", "kitchen faucet"),
    "faucet-kitchen-black": ("black faucet", "black kitchen faucet"),
    "faucet-bath": ("bath faucet", "bathtub faucet"),
    "faucet-sink": ("bathroom faucet", "bathroom faucet"),
    "shower": ("shower head", "shower head"),
    "shower-hose": ("shower hose", "shower hose"),
    "toilet": ("toilet", "toilet bowl"),
    "sink": ("bathroom sink", "washbasin"),
    "bathtub": ("bathtub", "bathtub"),
    "siphon": ("sink drain pipe", "sink trap"),
    "pump": ("circulation pump", "circulator pump"),
    "expansion-tank": ("expansion tank", "expansion vessel"),
    "radiator": ("radiator", "heating radiator"),
    "greenhouse": ("greenhouse frame", "greenhouse frame"),
    "stove-door": ("stove door", "cast iron stove door"),
    "grate": ("fire grate", "cast iron grate"),
    "stove-top": ("cast iron stove", "cast iron stove top"),
    "chimney": ("chimney pipe", "stainless steel chimney"),
    "wood-screws": ("screws", "wood screws"),
    "roof-screws": ("roofing screws", "self drilling screws"),
    "metal-screws": ("self tapping screws", "metal screws"),
    "wall-plugs": ("wall plugs", "plastic anchors"),
    "anchor": ("anchor bolt", "anchor bolt"),
    "nails": ("nails", "steel nails"),
    "bracket": ("angle bracket", "metal bracket"),
    "perforated-tape": ("perforated metal", "perforated strap"),
    "pipe-clamp": ("pipe clamp", "pipe clamp"),
    "threaded-rod": ("threaded rod", "threaded rod"),
    "putty-knife": ("putty knife", "putty knife"),
    "level": ("spirit level", "spirit level"),
    "wheelbarrow": ("wheelbarrow", "wheelbarrow"),
    "trowel": ("trowel", "brick trowel"),
    "straightedge": ("aluminum ruler", "aluminum straightedge"),
    "paint-roller": ("paint roller", "paint roller"),
    "paint-brush": ("paint brush", "paintbrush"),
    "tape-measure": ("tape measure", "tape measure"),
    "utility-knife": ("utility knife", "box cutter"),
    "shovel": ("shovel", "spade shovel"),
    "gloves": ("work gloves", "work gloves"),
    "bucket": ("bucket", "plastic bucket"),
    "mixer-paddle": ("paint mixer", "mixing paddle drill"),
    "drill": ("cordless drill", "cordless drill"),
    "hammer-drill": ("hammer drill", "rotary hammer"),
    "grinder": ("angle grinder", "angle grinder"),
    "jigsaw": ("jigsaw tool", "jigsaw power tool"),
    "mixer": ("mixer drill", "paddle mixer"),
    "cutting-disc": ("cutting disc", "abrasive cutting wheel"),
    "spray-foam": ("spray can", "aerosol can"),
    "caulk": ("caulking gun", "caulk tube"),
}


def fetch(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "Hoztrade-catalog/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def pixabay(query, white):
    key = (TOOLS / ".pixabay-key").read_text(encoding="utf-8-sig").strip()
    params = {"key": key, "q": query, "image_type": "photo", "per_page": PER_ROW, "safesearch": "true"}
    if white:
        params["colors"] = "white"
    hits = json.loads(fetch("https://pixabay.com/api/?" + urllib.parse.urlencode(params)))["hits"]
    return [{"source": "Pixabay", "id": h["id"], "page": h["pageURL"], "author": h["user"], "license": "Pixabay",
             "thumb": h["webformatURL"], "large": h["largeImageURL"], "size": [h["imageWidth"], h["imageHeight"]]}
            for h in hits[:PER_ROW]]


def openverse(query):
    params = {"q": query, "license": "cc0,pdm", "page_size": PER_ROW, "mature": "false"}
    hits = json.loads(fetch("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)))["results"]
    return [{"source": f"Openverse ({h.get('provider', '')})", "id": h["id"], "page": h["foreign_landing_url"],
             "author": h.get("creator") or "", "license": h["license"].upper(), "thumb": h.get("thumbnail") or h["url"],
             "large": h["url"], "size": [h.get("width"), h.get("height")]} for h in hits[:PER_ROW]]


def font(size):
    return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)


def search(names):
    CACHE.mkdir(parents=True, exist_ok=True)
    meta_path = CACHE / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    for name in names:
        px_query, ov_query = STOCK[name]
        rows = {}
        for row, call in (("a", lambda: pixabay(px_query, True)), ("b", lambda: pixabay(px_query, False)),
                          ("c", lambda: openverse(ov_query))):
            try:
                rows[row] = call()
            except Exception as error:  # noqa: BLE001 — один упавший источник не должен останавливать поиск
                print(f"  {name}/{row}: {error}")
                rows[row] = []
            time.sleep(1.0)  # Pixabay — 100 запросов в минуту, Openverse анонимно — ещё меньше
        meta[name] = rows
        sheet(name, rows)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, {k: len(v) for k, v in rows.items()}, flush=True)


def sheet(name, rows):
    label = 26
    img = Image.new("RGB", (PER_ROW * (THUMB + 4), 30 + 3 * (THUMB + label)), "white")
    d = ImageDraw.Draw(img)
    d.text((4, 4), f"{name}: {' / '.join(STOCK[name])}", font=font(18), fill="black")
    for r, row in enumerate("abc"):
        y = 30 + r * (THUMB + label)
        for i, hit in enumerate(rows.get(row, [])):
            x = i * (THUMB + 4)
            try:
                with Image.open(io.BytesIO(fetch(hit["thumb"]))) as thumb:
                    img.paste(ImageOps.pad(thumb.convert("RGB"), (THUMB, THUMB), color=(235, 235, 235)), (x, y + label))
            except Exception:  # noqa: BLE001 — превью недоступно, клетка остаётся пустой
                continue
            d.text((x + 2, y + 4), f"{row}{i + 1}", font=font(16), fill=(200, 0, 0))
    img.save(CACHE / f"{name}.jpg", quality=82)


if __name__ == "__main__":
    search(sys.argv[1:] or list(STOCK))
