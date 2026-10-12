"""Фото-текстуры для рисунков (дерево, OSB, пробка, бетон, кирпич) с Pixabay и листы для выбора.

Выбранный кадр скачивается в 1c/tools/.image-cache/textures/<имя>.jpg (большой размер) командой
  python 1c/tools/texture_search.py fetch
по словарю CHOSEN. Без аргументов — поиск кандидатов и листы в .image-cache/textures/sheets/.
"""
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from stock_search import THUMB, fetch, font, pixabay

TOOLS = Path(__file__).resolve().parent
OUT = TOOLS / ".image-cache" / "textures"

QUERIES = {
    "pine": "pine wood texture",
    "oak": "oak wood texture",
    "oak-grey": "grey wood texture",
    "oak-white": "white wood texture",
    "oak-honey": "light oak wood texture",
    "walnut": "walnut wood texture",
    "walnut-dark": "dark wood texture",
    "ash": "ash wood grain",
    "wenge": "wenge wood",
    "scandi": "scandinavian oak floor",
    "smoked": "smoked oak",
    "concrete": "concrete texture",
    "osb": "osb texture",
    "plywood": "plywood texture",
    "cork": "cork texture",
    "endgrain": "wood end grain",
    "brick-red": "red brick texture",
    "linoleum-tile": "grey tiles texture",
    "galvanized": "galvanized steel texture",
    "lumber": "pine lumber",
}

# Имя текстуры -> номер кандидата (1..20: 1–10 — ряд a, 11–20 — ряд b), по листам
CHOSEN = {"pine": 17, "lumber": 3, "oak": 2, "oak-grey": 1, "oak-white": 16, "oak-honey": 12, "walnut": 14,
          "walnut-dark": 10, "wenge": 12, "ash": 20, "scandi": 2, "smoked": 15, "concrete": 19, "osb": 2,
          "plywood": 7, "cork": 4}


def search():
    sheets = OUT / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    meta_path = OUT / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    for name, query in QUERIES.items():
        hits = pixabay(query, False) + pixabay(query + " background", False)
        meta[name] = hits
        img = Image.new("RGB", (10 * (THUMB + 4), 30 + 2 * (THUMB + 24)), "white")
        d = ImageDraw.Draw(img)
        d.text((4, 4), f"{name}: {query}", font=font(18), fill="black")
        for i, hit in enumerate(hits[:20]):
            x, y = (i % 10) * (THUMB + 4), 30 + (i // 10) * (THUMB + 24)
            try:
                with Image.open(io.BytesIO(fetch(hit["thumb"]))) as t:
                    img.paste(ImageOps.fit(t.convert("RGB"), (THUMB, THUMB)), (x, y + 24))
            except Exception:  # noqa: BLE001 — превью недоступно
                continue
            d.text((x + 2, y + 2), str(i + 1), font=font(16), fill=(200, 0, 0))
        img.save(sheets / f"{name}.jpg", quality=82)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, len(hits), flush=True)
        time.sleep(1.2)


def download():
    meta = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    credits = {}
    for name, number in CHOSEN.items():
        hit = meta[name][number - 1]
        path = OUT / f"{name}.jpg"
        if not path.exists():
            path.write_bytes(fetch(hit["large"]))
        credits[name] = {k: hit[k] for k in ("source", "page", "author", "license")}
        print(name, path.stat().st_size)
    (OUT / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    download() if sys.argv[1:] == ["fetch"] else search()
