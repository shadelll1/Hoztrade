"""Проверка исходников 1С: UTF-8 с BOM и переносы CRLF, как их пишет Конфигуратор.

Запуск: python 1c/tools/check_encoding.py [папка ...]   (по умолчанию 1c/src)
Код возврата 1, если есть файл без BOM или со смешанными переносами. ConfigDumpInfo.xml не проверяется.
"""
import sys
from pathlib import Path

EXTENSIONS = {".xml", ".bsl", ".txt", ".mxl"}
BOM = b"\xef\xbb\xbf"


def problems(path: Path):
    data = path.read_bytes()
    if not data.startswith(BOM):
        yield "нет BOM"
    lf, crlf = data.count(b"\n"), data.count(b"\r\n")
    if lf != crlf:
        yield f"переносы LF: {lf - crlf} из {lf}"
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        yield f"не UTF-8: {error}"


def main(roots):
    bad = checked = 0
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            if path.suffix.lower() not in EXTENSIONS or path.name == "ConfigDumpInfo.xml":
                continue
            checked += 1
            for problem in problems(path):
                print(f"{path}: {problem}")
                bad += 1
    print(f"Проверено файлов: {checked}, замечаний: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "src"
    sys.exit(main(sys.argv[1:] or [default]))
