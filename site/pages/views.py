from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.cache import cache_page

# Служебные разделы, корзина, личные страницы и результаты поиска — не для поисковиков.
DISALLOW = ["/admin/", "/api/", "/account/", "/cart/", "/checkout/", "/order/", "/search/"]


@cache_page(60 * 60)
def robots_txt(request):
    lines = ["User-agent: *"] + [f"Disallow: {path}" for path in DISALLOW]
    lines += ["", f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
