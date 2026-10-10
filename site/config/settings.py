"""Настройки сайта «Хозтрейд».

Всё, что отличается между разработкой и боевым режимом, берётся из переменных окружения
или файла .env рядом с manage.py (образец — .env.example).
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    HTTPS=(bool, False),
    SERVE_MEDIA=(bool, True),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
# Проверка здоровья внутри контейнера и сервера ходит на 127.0.0.1 по http
for _local in ("127.0.0.1", "localhost"):
    if _local not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_local)
# За обратным прокси с HTTPS: https://хозтрейд.рф,https://xn--d1abfjwnnv.xn--p1ai
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "rest_framework",
    "catalog",
    "orders",
    "delivery",
    "content",
    "pages",
    "exchange",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.security.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.context_processors.shop",
                "orders.context_processors.cart",
                "accounts.context_processors.account",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite по умолчанию; PostgreSQL — DATABASE_URL=postgres://user:pass@host:5432/db
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Резервные копии (manage.py backup): база и media
BACKUP_DIR = env("BACKUP_DIR", default=str(BASE_DIR / "backups"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:home"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

# Токен, с которым 1С обращается к API обмена
EXCHANGE_TOKEN = env("EXCHANGE_TOKEN")
# /healthz/ считает обмен вставшим, если 1С не обращалась дольше (обмен по расписанию — каждые 5 минут)
EXCHANGE_STALE_MINUTES = env.int("EXCHANGE_STALE_MINUTES", default=30)

# Данные компании для шапки, подвала и контактов
SITE_INFO = {
    "name": "Хозтрейд",
    "legal_name": "Группа компаний «Хозтрейд»",
    "city": "Чебоксары",
    "phone": "(8352) 22-33-77",
    "phone_href": "+78352223377",
    "email": "tpk21@mail.ru",
    "stores": [
        {"title": "Магазин на Машиностроителей", "address": "проезд Машиностроителей, 1, корп. 4"},
        {"title": "Склад на Складском", "address": "Складской проезд, 6, склад 41"},
        {"title": "Офис продаж", "address": "Складской проезд, 6, офис 108"},
    ],
}

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
# Почта одной строкой: EMAIL_URL=smtp+tls://user:password@smtp.yandex.ru:587 (включает SMTP-бэкенд)
if env("EMAIL_URL", default=""):
    vars().update(env.email_url("EMAIL_URL"))
EMAIL_TIMEOUT = 10
# Адрес сайта для ссылок в письмах (https://хозтрейд.рф); пусто — адрес из запроса
SITE_URL = env("SITE_URL", default="")
MANAGER_EMAILS = env.list("MANAGER_EMAILS", default=[])
MANAGERS = [("Менеджер", e) for e in MANAGER_EMAILS]
# Уведомления в Telegram (orders/notifications.py): оба значения пустые — выключено.
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", default="")
DEFAULT_FROM_EMAIL = SERVER_EMAIL = env("DEFAULT_FROM_EMAIL", default="shop@localhost")
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# Фото товаров и файлы заявок. В режиме разработки их отдаёт runserver, в боевом на одном компьютере —
# Django (SERVE_MEDIA=True); за nginx/CDN выключить и раздавать MEDIA_ROOT веб-сервером.
SERVE_MEDIA = DEBUG or env("SERVE_MEDIA")

if not DEBUG:
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# HTTPS=True — сайт в интернете за TLS (напрямую или за обратным прокси).
if env("HTTPS"):
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
else:
    # Локальный боевой режим (http://localhost) без TLS: проверки HTTPS в check --deploy к нему не относятся.
    SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W008", "security.W012", "security.W016"]

# Журналы: консоль всегда; LOG_DIR — ещё и файл site.log с ротацией (10 МБ × 5). Ошибки 500 в боевом
# режиме уходят письмом администраторам (ADMIN_EMAILS) — так Django делает по умолчанию.
ADMINS = [("Администратор", e) for e in env.list("ADMIN_EMAILS", default=[])]
LOG_DIR = env("LOG_DIR", default="")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR",
                        "filters": ["require_debug_false"]},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django.request": {"handlers": ["console", "mail_admins"], "level": "ERROR", "propagate": False},
    },
}
if LOG_DIR:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler", "formatter": "plain", "encoding": "utf-8",
        "filename": str(Path(LOG_DIR) / "site.log"), "maxBytes": 10 * 1024 * 1024, "backupCount": 5,
    }
    LOGGING["root"]["handlers"].append("file")
    LOGGING["loggers"]["django.request"]["handlers"].append("file")
