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
