from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.static import serve

from catalog.sitemaps import SITEMAPS
from pages.views import robots_txt

admin.site.site_header = "Хозтрейд — управление сайтом"
admin.site.site_title = "Хозтрейд"

urlpatterns = [
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("exchange.urls")),
    path("account/", include("accounts.urls")),
    path("", include("orders.urls")),
    path("", include("pages.urls")),
    path("", include("catalog.urls")),
]

if settings.SERVE_MEDIA:
    urlpatterns.insert(0, re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}))
