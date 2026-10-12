import io

import pytest
from django.core.management import call_command

from catalog.models import Product


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())


@pytest.mark.django_db
class TestSecurityAndSeo:
    def test_csp_on_storefront_not_admin(self, client, settings):
        settings.DEBUG = False
        r = client.get("/delivery/")
        assert "script-src 'self'" in r["Content-Security-Policy"]
        assert "frame-src https://yandex.ru" in r["Content-Security-Policy"]
        assert "camera=()" in r["Permissions-Policy"]
        assert "Content-Security-Policy" not in client.get("/admin/login/")

    def test_no_inline_handlers_or_styles(self, client, demo):
        """Строгий CSP не пропустит встроенные обработчики и style= — их не должно быть в разметке витрины."""
        product = Product.objects.published().first()
        for url in ["/", "/catalog/", "/delivery/", "/contacts/", product.get_absolute_url(), "/cart/"]:
            body = client.get(url).content.decode()
            assert " onclick=" not in body and " onsubmit=" not in body and ' style="' not in body, url

    def test_canonical_and_open_graph(self, client, demo):
        product = Product.objects.get(sku="ЦМ-500-50")
        body = client.get(product.get_absolute_url() + "?utm_source=x").content.decode()
        assert f'<link rel="canonical" href="http://testserver{product.get_absolute_url()}">' in body
        assert '<meta property="og:type" content="product">' in body
        page2 = client.get("/search/?q=а&page=2").content.decode()
        assert 'href="http://testserver/search/?page=2"' in page2


@pytest.mark.django_db
class TestHealthz:
    def test_never_then_ok_then_stale(self, client, settings):
        from datetime import timedelta

        from django.utils import timezone
        from rest_framework.test import APIClient

        from exchange.models import ExchangeContact

        assert client.get("/healthz/").json() == {"status": "ok", "db": True,
                                                  "exchange": {"status": "never", "last_seen_at": None}}
        settings.EXCHANGE_TOKEN = "t"
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Token t")
        api.get("/api/v1/ping/")
        assert client.get("/healthz/").json()["exchange"]["status"] == "ok"
        ExchangeContact.objects.update(last_seen_at=timezone.now() - timedelta(hours=2))
        assert client.get("/healthz/").json()["exchange"]["status"] == "stale"

    def test_wrong_token_is_not_contact(self, client, settings):
        from rest_framework.test import APIClient
        settings.EXCHANGE_TOKEN = "t"
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Token wrong")
        api.get("/api/v1/ping/")
        assert client.get("/healthz/").json()["exchange"]["status"] == "never"


def test_logging_to_file(tmp_path, monkeypatch):
    """LOG_DIR включает файл с ротацией; конфиг логирования применяется без ошибок."""
    import importlib
    import logging.config

    import config.settings as settings_module
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    reloaded = importlib.reload(settings_module)
    try:
        logging.config.dictConfig(reloaded.LOGGING)
        assert reloaded.LOGGING["handlers"]["file"]["filename"].endswith("site.log")
        assert "mail_admins" in reloaded.LOGGING["loggers"]["django.request"]["handlers"]
    finally:
        monkeypatch.delenv("LOG_DIR")
        logging.config.dictConfig(importlib.reload(settings_module).LOGGING)


@pytest.mark.django_db(transaction=True)
def test_backup_sqlite_and_media(tmp_path, settings):
    from django.db import connection
    if connection.vendor != "sqlite":
        pytest.skip("копия SQLite")
    settings.BACKUP_DIR = str(tmp_path / "backups")
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    (tmp_path / "media" / "products" / "a.webp").write_bytes(b"img")
    for _ in range(3):
        call_command("backup", "--keep", "2", stdout=io.StringIO())
    copies = sorted((tmp_path / "backups").iterdir())
    assert len(copies) == 2
    assert (copies[-1] / "db.sqlite3").stat().st_size > 0 and (copies[-1] / "media.zip").exists()


def test_lead_files_not_public(client, settings, tmp_path, db):
    """Файлы заявок (сметы) не отдаются по прямой ссылке, фото товаров — отдаются."""
    import importlib

    from django.urls import clear_url_caches

    import config.urls

    settings.MEDIA_ROOT = tmp_path
    settings.SERVE_MEDIA = True
    (tmp_path / "leads" / "2026" / "10").mkdir(parents=True)
    (tmp_path / "leads" / "2026" / "10" / "smeta.pdf").write_bytes(b"%PDF")
    (tmp_path / "products").mkdir()
    (tmp_path / "products" / "a.webp").write_bytes(b"img")
    importlib.reload(config.urls)
    clear_url_caches()
    try:
        assert client.get("/media/leads/2026/10/smeta.pdf").status_code == 404
        assert client.get("/media/products/a.webp").status_code == 200
    finally:
        importlib.reload(config.urls)
        clear_url_caches()


def test_healthz_exempt_from_https_redirect(client, settings, db):
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    assert client.get("/healthz/").status_code == 200
    assert client.get("/delivery/").status_code == 301


@pytest.mark.django_db
def test_admin_home_dashboard_and_lists(client):
    """Главная админки: табло с тем, что ждёт действия, разделы с числами; списки со статусами открываются."""
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from content.models import Review
    from crm.models import Client, Deal
    from exchange.models import ExchangeContact

    admin_user = get_user_model().objects.create_superuser("boss", "boss@example.com", "pass")
    c = Client.objects.create(name="Иван")
    Deal.objects.create(client=c, title="Ждёт", created_at=timezone.now())
    ExchangeContact.objects.create(last_seen_at=timezone.now())
    client.force_login(admin_user)
    r = client.get("/admin/")
    html = r.content.decode()
    assert r.status_code == 200 and "ht-tablo" in html and 'href="/crm/' in html
    assert "Ждут ответа в CRM" in html and "Обмен с 1С" in html and "только что" in html
    assert '<b class="ht-tablo__num">1</b>' in html   # одно обращение ждёт ответа
    assert Review.objects.count() == 0 and "все разобраны" in html
    for url in ("/admin/orders/order/", "/admin/crm/deal/", "/admin/accounts/profile/", "/admin/content/review/"):
        assert client.get(url).status_code == 200, url
