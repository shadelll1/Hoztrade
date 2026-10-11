"""Резервная копия сайта: база и загруженные файлы (фото товаров, файлы заявок) в BACKUP_DIR.

SQLite копируется штатным backup API (безопасно на работающем сайте), PostgreSQL — утилитой pg_dump
(должна быть в PATH). Хранятся последние --keep копий. Запускать по расписанию: раз в сутки.
"""
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Резервная копия базы и media в BACKUP_DIR"

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=14, help="сколько последних копий хранить")
        parser.add_argument("--no-media", action="store_true", help="только база")

    def handle(self, *args, keep, no_media, **options):
        root = Path(settings.BACKUP_DIR)
        root.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        target, n = root / stamp, 1
        while target.exists():          # несколько копий в одну секунду
            n += 1
            target = root / f"{stamp}-{n}"
        target.mkdir()

        db = connection.settings_dict
        if connection.vendor == "sqlite":
            connection.ensure_connection()      # копируем через то же соединение, что и сайт
            dest = sqlite3.connect(target / "db.sqlite3")
            with dest:
                connection.connection.backup(dest)
            dest.close()
        elif connection.vendor == "postgresql":
            if not shutil.which("pg_dump"):
                raise CommandError("pg_dump не найден в PATH — установите клиент PostgreSQL")
            env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
            cmd = ["pg_dump", "--format=custom", "--no-owner", f"--file={target / 'db.dump'}",
                   f"--host={db.get('HOST') or 'localhost'}", f"--port={db.get('PORT') or 5432}",
                   f"--username={db.get('USER')}", db["NAME"]]
            subprocess.run(cmd, env=env, check=True)  # noqa: S603 — аргументы из настроек, не от пользователя
        else:
            raise CommandError(f"Резервная копия базы {connection.vendor} не поддерживается")

        if not no_media and Path(settings.MEDIA_ROOT).exists():
            shutil.make_archive(str(target / "media"), "zip", settings.MEDIA_ROOT)

        backups = sorted(p for p in root.iterdir() if p.is_dir())
        for old in backups[:-keep] if keep > 0 else []:
            shutil.rmtree(old)
        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        kept = min(len(backups), keep)
        self.stdout.write(self.style.SUCCESS(f"Копия: {target} ({size // 1024} КБ), хранится копий: {kept}"))
