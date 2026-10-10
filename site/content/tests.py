import io
import json
import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.brands import assign_brands
from catalog.models import Brand, Product
from content.models import Post, Review
from orders.notifications import notify


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())
    call_command("load_demo_content", stdout=io.StringIO())


def review_data(**extra):
    data = {"name": "Иван (тест)", "rating": "5", "text": "Хорошая штукатурка, легла ровно", "consent": "on"}
    data.update(extra)
    return data


@pytest.mark.django_db
class TestPosts:
    def test_lists_and_detail(self, client, demo):
        assert client.get("/news/").status_code == 200
        promos = client.get("/promo/").context["page"].object_list
        assert promos and all(p.kind == "promo" for p in promos)
        post = Post.objects.get(slug="skolko-gazobloka-nuzhno-na-dom")
        body = client.get(post.get_absolute_url()).content.decode()
        assert post.title in body and '"@type":"Article"' in body

    def test_hidden_posts(self, client, demo):
        draft = Post.objects.create(title="Черновик", lead="-", body="-", is_published=False)
        future = Post.objects.create(title="Завтра", lead="-", body="-",
                                     published_at=timezone.now() + timedelta(days=1))
        expired = Post.objects.create(title="Прошла", lead="-", body="-", kind=Post.Kind.PROMO,
                                      promo_until=timezone.localdate() - timedelta(days=1))
        assert client.get(draft.get_absolute_url()).status_code == 404
        assert client.get(future.get_absolute_url()).status_code == 404
        assert expired not in client.get("/promo/").context["page"].object_list
        assert "акция завершилась" in client.get(expired.get_absolute_url()).content.decode()

    def test_home_blocks(self, client, demo):
        r = client.get("/")
        assert r.context["promos"] and r.context["posts"] and r.context["brands"]
        assert all(p.kind != "promo" for p in r.context["posts"])


@pytest.mark.django_db
class TestReviews:
    def product(self):
        return Product.objects.get(sku="ШТ-ВС-30")

    def test_review_goes_to_moderation(self, client, demo):
        product = self.product()
        r = client.post(f"/product/{product.slug}/review/", review_data())
        assert r.status_code == 302 and r["Location"].endswith("#reviews")
        review = Review.objects.get()
        assert review.status == Review.Status.NEW and review.product == product
        page = client.get(product.get_absolute_url())
        assert not page.context["reviews"] and page.context["rating"]["count"] == 0

        review.status = Review.Status.APPROVED
        review.save()
        page = client.get(product.get_absolute_url())
        body = page.content.decode()
        assert list(page.context["reviews"]) == [review]
        assert '"aggregateRating"' in body and '"ratingValue":"5.0"' in body

    def test_invalid_review_keeps_input(self, client, demo):
        product = self.product()
        client.post(f"/product/{product.slug}/review/", review_data(rating="", text="Очень хорошая смесь"))
        form = client.get(product.get_absolute_url()).context["review_form"]
        assert "rating" in form.errors and form.data["text"] == "Очень хорошая смесь"
        assert not Review.objects.exists()

    def test_spam_and_throttle(self, client, demo):
        product = self.product()
        client.post(f"/product/{product.slug}/review/", review_data(website="http://spam"))
        assert not Review.objects.exists()
        for _ in range(7):
            client.post(f"/product/{product.slug}/review/", review_data())
        assert Review.objects.count() == 5

    def test_summary(self, demo):
        product = self.product()
        for rating, status in [(5, "approved"), (4, "approved"), (1, "rejected")]:
            Review.objects.create(product=product, name="x", rating=rating, text="текст отзыва", status=status)
        assert product.reviews.summary() == {"count": 2, "rating": 4.5}


@pytest.mark.django_db
class TestBrands:
    def test_matching_by_name_and_alias(self, demo):
        assert Product.objects.get(sku="ГКЛ-125").brand.name == "Knauf"          # «Кнауф» в названии
        assert Product.objects.get(sku="ШТ-ВС-30").brand.name == "Волма"
        assert Product.objects.get(sku="МВ-РЛ-50").brand.name == "Технониколь"   # вариант «Роклайт»
        assert Product.objects.get(sku="ЦМ-500-50").brand is None

    def test_word_boundary(self, db):
        Brand.objects.create(name="Волма")
        p = Product.objects.create(name="Смесь Волмакс 25 кг")
        assert assign_brands() == 0 and Product.objects.get(pk=p.pk).brand is None

    def test_brand_pages(self, client, demo):
        brand = Brand.objects.get(name="Knauf")
        r = client.get("/brands/")
        assert brand in r.context["brands"]
        page = client.get(brand.get_absolute_url())
        assert page.status_code == 200 and page.context["page"].paginator.count >= 3

    def test_import_from_1c_assigns_brand(self, db, settings):
        settings.EXCHANGE_TOKEN = "t"
        Brand.objects.create(name="Ceresit", aliases="Церезит")
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Token t")
        pid = str(uuid.uuid4())
        api.post("/api/v1/catalog/", {"products": [{"id": pid, "name": "Клей Церезит CM 11 25 кг"}]}, format="json")
        assert Product.objects.get(ext_id=pid).brand.name == "Ceresit"


@pytest.mark.django_db
def test_info_pages_and_sitemap(client, demo):
    for url in ["/about/", "/payment/", "/cookies/", "/contacts/"]:
        assert client.get(url).status_code == 200, url
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "/news/skolko-gazobloka-nuzhno-na-dom/" in sitemap and "/brands/" in sitemap


class TestTelegram:
    def test_disabled_without_settings(self, settings):
        settings.TELEGRAM_BOT_TOKEN = ""
        settings.MANAGERS = []
        assert notify("Тема", "Текст") is None

    def test_sends_message(self, settings):
        settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID, settings.MANAGERS = "123:abc", "-100", []
        with mock.patch("urllib.request.urlopen") as urlopen:
            notify("Новый заказ", "Иван, +79001234567").join(5)
        request = urlopen.call_args[0][0]
        assert request.full_url == "https://api.telegram.org/bot123:abc/sendMessage"
        assert json.loads(request.data)["text"] == "Новый заказ\nИван, +79001234567"

    def test_failure_is_logged_not_raised(self, settings, caplog):
        settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID, settings.MANAGERS = "123:abc", "-100", []
        with mock.patch("urllib.request.urlopen", side_effect=OSError("нет сети")):
            notify("Тема", "Текст").join(5)
        assert "Telegram" in caplog.text
