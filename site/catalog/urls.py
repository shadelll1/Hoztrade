from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog_root, name="root"),
    path("catalog/<slug:slug>/", views.category, name="category"),
    path("product/<slug:slug>/", views.product, name="product"),
    path("search/", views.search, name="search"),
    path("brands/", views.brand_list, name="brands"),
    path("brands/<slug:slug>/", views.brand, name="brand"),
]
