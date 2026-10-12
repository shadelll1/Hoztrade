from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page, never_cache

from exchange.models import ExchangeContact

# Служебные разделы, корзина, личные страницы и результаты поиска — не для поисковиков.
DISALLOW = ["/admin/", "/api/", "/account/", "/cart/", "/checkout/", "/order/", "/search/", "/healthz/", "/crm/"]


@cache_page(60 * 60)
def robots_txt(request):
    lines = ["User-agent: *"] + [f"Disallow: {path}" for path in DISALLOW]
    lines += ["", f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@never_cache
def healthz(request):
    """Проверка для мониторинга: база отвечает (иначе 503) и давно ли 1С выходила на связь.

    exchange.status: ok — 1С обращалась не дольше EXCHANGE_STALE_MINUTES назад, stale — дольше (обмен встал:
    клиент 1С закрыт или нет связи), never — ещё ни разу. На код ответа не влияет: сайт работает и без 1С.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 — любая ошибка базы
        return JsonResponse({"status": "error", "db": False}, status=503)

    contact = ExchangeContact.objects.filter(pk=1).first()
    exchange = {"status": "never", "last_seen_at": None}
    if contact is not None:
        stale = timezone.now() - contact.last_seen_at > timedelta(minutes=settings.EXCHANGE_STALE_MINUTES)
        exchange = {"status": "stale" if stale else "ok",
                    "last_seen_at": timezone.localtime(contact.last_seen_at).isoformat()}
    return JsonResponse({"status": "ok", "db": True, "exchange": exchange})
