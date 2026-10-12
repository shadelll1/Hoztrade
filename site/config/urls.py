from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_page
from django.views.static import serve

from catalog.sitemaps import SITEMAPS
from pages.views import healthz, robots_txt

admin.site.site_header = "Хозтрейд — управление сайтом"
admin.site.site_title = "Хозтрейд"

urlpatterns = [
    path("sitemap.xml", cache_page(60 * 60)(sitemap), {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots"),
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("exchange.urls")),
    path("account/", include("accounts.urls")),
    path("crm/", include("crm.urls")),
    path("", include("orders.urls")),
    path("", include("content.urls")),
    path("", include("pages.urls")),
    path("", include("catalog.urls")),
]

# Публичные загрузки: фото товаров, логотипы брендов, картинки публикаций. Файлы заявок (media/leads/) —
# персональные данные: их отдаёт только API обмена по токену, по прямой ссылке — 404.
PUBLIC_MEDIA = r"(?:products|brands|posts)/"
if settings.SERVE_MEDIA:
    urlpatterns.insert(
        0, re_path(rf"^media/(?P<path>{PUBLIC_MEDIA}.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    )
