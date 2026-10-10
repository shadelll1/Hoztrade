"""Картинки демо-товаров для 1С: мешки цемента и смесей, нарисованные Pillow.

Пишет общий макет хт_ДемоКартинки (текстовый, JSON: артикул -> имя файла и картинка в base64).
Команда «Заполнить демо-каталог Хозтрейд» прикладывает картинки к номенклатуре, а обмен отправляет их
на сайт. Запуск: site\\.venv\\Scripts\\python.exe 1c\\tools\\make_demo_images.py
"""
import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "CommonTemplates" / "хт_ДемоКартинки" / "Ext" / "Template.txt"
FONTS = Path("C:/Windows/Fonts")
SIZE = 800

# артикул -> (имя файла, надпись крупно, подпись, вес, цвет мешка, цвет полосы)
BAGS = {
    "ЦМ-500-50": ("cement-m500.jpg", "ЦЕМЕНТ", "М500 Д0", "50 кг", (196, 200, 204), (21, 128, 61)),
    "ЦМ-400-50": ("cement-m400.jpg", "ЦЕМЕНТ", "М400 Д20", "50 кг", (205, 199, 188), (30, 79, 138)),
    "ПБ-300-40": ("peskobeton-m300.jpg", "ПЕСКОБЕТОН", "М300", "40 кг", (222, 214, 196), (180, 83, 9)),
    "КС-150-40": ("kladochnaya-m150.jpg", "КЛАДОЧНАЯ", "смесь М150", "40 кг", (214, 208, 200), (153, 27, 27)),
}


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def centered(draw, y, text, fnt, fill):
    w = draw.textlength(text, font=fnt)
    draw.text(((SIZE - w) / 2, y), text, font=fnt, fill=fill)


def bag(title, subtitle, weight, color, band):
    img = Image.new("RGB", (SIZE, SIZE), (246, 247, 245))

    # Мягкая тень под мешком
    shadow = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(shadow).ellipse((170, 690, 630, 745), fill=110)
    img.paste((150, 155, 150), (0, 0), shadow.filter(ImageFilter.GaussianBlur(18)))

    d = ImageDraw.Draw(img)
    body = (190, 120, 610, 715)
    d.rounded_rectangle(body, radius=46, fill=color)
    # Боковые складки и шов сверху
    shade = tuple(max(0, c - 22) for c in color)
    d.rounded_rectangle((190, 120, 222, 715), radius=20, fill=shade)
    d.rounded_rectangle((578, 120, 610, 715), radius=20, fill=shade)
    d.rectangle((210, 120, 590, 150), fill=tuple(max(0, c - 12) for c in color))
    for x in range(222, 580, 18):
        d.line((x, 136, x + 9, 136), fill=shade, width=3)

    # Цветная полоса с надписью
    d.rectangle((222, 250, 578, 410), fill=band)
    centered(d, 270, title, font("arialbd.ttf", 58 if len(title) < 9 else 46), (255, 255, 255))
    centered(d, 345, subtitle, font("arial.ttf", 40), (255, 255, 255))

    # Вес и «логотип» магазина
    d.rounded_rectangle((300, 470, 500, 560), radius=18, fill=(255, 255, 255))
    centered(d, 487, weight, font("arialbd.ttf", 48), (34, 40, 46))
    centered(d, 620, "ХОЗТРЕЙД", font("arialbd.ttf", 28), shade)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=86, optimize=True)
    return buf.getvalue()


def main():
    data = {}
    for sku, (filename, title, subtitle, weight, color, band) in BAGS.items():
        data[sku] = {"name": filename, "data": base64.b64encode(bag(title, subtitle, weight, color, band)).decode()}
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    # Макеты 1С — UTF-8 с BOM
    TEMPLATE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8-sig", newline="\r\n")
    print(f"{TEMPLATE}: {len(data)} картинок, {TEMPLATE.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
