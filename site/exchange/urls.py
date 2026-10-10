from django.urls import path

from . import views

app_name = "exchange"

urlpatterns = [
    path("ping/", views.PingView.as_view(), name="ping"),
    path("catalog/", views.CatalogUploadView.as_view(), name="catalog"),
]
