from django.urls import path

from . import views
from .models import Post

app_name = "content"

urlpatterns = [
    path("news/", views.post_list, name="news"),
    path("promo/", views.post_list, {"kind": Post.Kind.PROMO}, name="promos"),
    path("advice/", views.post_list, {"kind": Post.Kind.ADVICE}, name="advice"),
    path("news/<slug:slug>/", views.post_detail, name="post"),
    path("product/<slug:slug>/review/", views.review_create, name="review"),
]
