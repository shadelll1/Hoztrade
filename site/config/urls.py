from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Хозтрейд — управление сайтом"
admin.site.site_title = "Хозтрейд"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("exchange.urls")),
    path("", include("orders.urls")),
    path("", include("pages.urls")),
    path("", include("catalog.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
