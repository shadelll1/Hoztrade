from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from content.models import Post

from .models import Brand, Category, Product


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return ["catalog:home", "catalog:root", "catalog:brands", "content:news", "content:promos", "content:advice",
                "pages:delivery", "pages:payment", "pages:b2b", "pages:returns", "pages:about", "pages:contacts",
                "orders:order_list"]

    def location(self, item):
        return reverse(item)


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Category.objects.filter(is_published=True).order_by("pk")

    def lastmod(self, obj):
        return obj.updated_at


class ProductSitemap(Sitemap):
    changefreq = "daily"  # цены и остатки приходят из 1С
    priority = 0.8

    def items(self):
        return Product.objects.published().order_by("pk")

    def lastmod(self, obj):
        return obj.updated_at


class BrandSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Brand.objects.filter(is_published=True).order_by("pk")


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Post.objects.published().order_by("pk")

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {"static": StaticSitemap, "categories": CategorySitemap, "products": ProductSitemap,
            "brands": BrandSitemap, "posts": PostSitemap}
