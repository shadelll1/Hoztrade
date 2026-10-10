from django.urls import path
from django.views.generic import TemplateView

app_name = "pages"


def page(template):
    return TemplateView.as_view(template_name=f"pages/{template}.html")


urlpatterns = [
    path("delivery/", page("delivery"), name="delivery"),
    path("b2b/", page("b2b"), name="b2b"),
    path("returns/", page("returns"), name="returns"),
    path("contacts/", page("contacts"), name="contacts"),
    path("privacy/", page("privacy"), name="privacy"),
]
