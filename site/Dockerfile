# Сайт «Хозтрейд» для Linux-сервера: gunicorn за обратным прокси (Caddy в deploy/docker-compose.yml).
# Debian trixie: его postgresql-client 17 снимает копии с PostgreSQL 16 из docker-compose (pg_dump не старше сервера)
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Клиент PostgreSQL — для manage.py backup (pg_dump)
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Статика собирается в образ (whitenoise отдаёт её сам); секреты при сборке не нужны — подставляем заглушки
RUN SECRET_KEY=build EXCHANGE_TOKEN=build python manage.py collectstatic --noinput \
    && mkdir -p /app/media /app/logs /app/backups /app/data \
    && chown -R app:app /app/media /app/logs /app/backups /app/data

# Без DATABASE_URL (образ запущен без compose) — SQLite в папке, куда пользователь app может писать;
# docker-compose подставляет PostgreSQL
ENV DATABASE_URL=sqlite:////app/data/db.sqlite3

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4)"

# Миграции при каждом запуске (идемпотентны), затем gunicorn: 3 процесса по 4 потока
CMD ["sh", "-c", "python manage.py migrate --noinput && (python manage.py crm_sync || true) && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 4 --timeout 60 --access-logfile - --forwarded-allow-ips='*'"]
