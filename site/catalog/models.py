from decimal import Decimal

from django.db import models
from django.urls import reverse

from .attrs import labeled
from .attrs import parse as parse_attrs
from .text import make_slug


class Category(models.Model):
    """Группа каталога. Приходит из 1С (группа справочника «Номенклатура»)."""

    ext_id = models.UUIDField("ID в 1С", unique=True, null=True, blank=True)
    parent = models.ForeignKey(
        "self", verbose_name="Родитель", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="children",
    )
    name = models.CharField("Наименование", max_length=150)
    slug = models.SlugField("Адрес", max_length=170, unique=True, allow_unicode=False)
    sort = models.PositiveIntegerField("Порядок", default=500)
    is_published = models.BooleanField("Опубликована", default=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name, Category, suffix=str(self.ext_id or "")[:8])
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:category", args=[self.slug])

    def ancestors(self):
        """Цепочка родителей от корня — для хлебных крошек."""
        chain, node = [], self.parent
        while node is not None and node not in chain:
            chain.insert(0, node)
            node = node.parent
        return chain

    def descendant_ids(self):
        """ID этой категории и всех вложенных (опубликованных)."""
        ids, frontier = [self.pk], [self.pk]
        while frontier:
            frontier = list(
                Category.objects.filter(parent_id__in=frontier, is_published=True)
                .values_list("pk", flat=True)
            )
            ids.extend(frontier)
        return ids


class Brand(models.Model):
    """Производитель. Ведётся на сайте; товары из 1С привязываются к нему по названию (поле «Варианты написания»)."""

    name = models.CharField("Название", max_length=100, unique=True)
    slug = models.SlugField("Адрес", max_length=120, unique=True)
    aliases = models.CharField(
        "Варианты написания", max_length=300, blank=True,
        help_text="Через запятую, как бренд пишется в названиях товаров: «Кнауф, Knauf»",
    )
    description = models.TextField("Описание", blank=True)
    logo = models.ImageField("Логотип", upload_to="brands/", blank=True)
    website = models.URLField("Сайт производителя", blank=True)
    sort = models.PositiveIntegerField("Порядок", default=500)
    is_published = models.BooleanField("Опубликован", default=True)

    class Meta:
        verbose_name = "Бренд"
        verbose_name_plural = "Бренды"
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name, Brand)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:brand", args=[self.slug])

    def spellings(self):
        """Все написания бренда в нижнем регистре: название и варианты."""
        names = [self.name, *self.aliases.split(",")]
        return [n.strip().lower() for n in names if n.strip()]


class ProductQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)


class Product(models.Model):
    """Товар. Учётные поля (цены, остатки, вес) приходят из 1С, контентные (описание, фото) ведутся на сайте."""

    ext_id = models.UUIDField("ID в 1С", unique=True, null=True, blank=True)
    category = models.ForeignKey(
        Category, verbose_name="Категория", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="products",
    )
    brand = models.ForeignKey(
        Brand, verbose_name="Бренд", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="products",
    )
    sku = models.CharField("Артикул", max_length=50, blank=True)
    name = models.CharField("Наименование", max_length=150)
    full_name = models.CharField("Полное наименование", max_length=500, blank=True)
    slug = models.SlugField("Адрес", max_length=200, unique=True, allow_unicode=False)
    unit = models.CharField("Единица", max_length=25, default="шт")
    weight_kg = models.DecimalField("Вес, кг", max_digits=12, decimal_places=3, default=Decimal("0"))
    volume_m3 = models.DecimalField("Объём, м³", max_digits=12, decimal_places=4, default=Decimal("0"))
    price_retail = models.DecimalField("Цена", max_digits=14, decimal_places=2, default=Decimal("0"))
    price_wholesale = models.DecimalField(
        "Цена для юрлиц", max_digits=14, decimal_places=2, null=True, blank=True,
    )
    stock = models.DecimalField("Остаток", max_digits=14, decimal_places=3, default=Decimal("0"))

    # Нижний регистр названия и артикула: SQLite не умеет регистронезависимый поиск по кириллице.
    search_text = models.TextField(editable=False, blank=True, db_index=False)
    # Свойства для фильтров и характеристик: {"pack": "25 кг", "thick": "8 мм"} — из наименования (catalog/attrs.py).
    attrs = models.JSONField("Свойства", default=dict, blank=True, editable=False)

    description = models.TextField("Описание", blank=True)
    image = models.ImageField("Фото", upload_to="products/", blank=True)
    # Миниатюра для списков; делается из фото автоматически (catalog/images.py).
    thumb = models.ImageField("Миниатюра", upload_to="products/thumbs/", blank=True, editable=False)
    # Версия фото из 1С (присылает 1С). Пусто — фото загружено на сайте вручную, обмен его не трогает.
    image_1c = models.CharField("Версия фото из 1С", max_length=100, blank=True, editable=False)

    is_published = models.BooleanField("Опубликован", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]
        indexes = [models.Index(fields=["is_published", "category"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name, Product, suffix=str(self.ext_id or "")[:8])
        self.search_text = " ".join([self.name, self.full_name, self.sku]).lower()
        self.attrs = parse_attrs(self.title)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = [*kwargs["update_fields"], "search_text", "attrs"]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:product", args=[self.slug])

    @property
    def title(self):
        return self.full_name or self.name

    @property
    def attr_list(self):
        """[(подпись, значение)] свойств — для таблицы характеристик."""
        return labeled(self.attrs or {})

    @property
    def list_image(self):
        """Картинка для списков: миниатюра, а если её нет (старое фото) — само фото."""
        return self.thumb or self.image

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def can_buy(self):
        return self.price_retail > 0

    def price_for(self, wholesale=False):
        """Цена для покупателя: оптовая — подтверждённым компаниям, если она есть, иначе розничная."""
        if wholesale and self.price_wholesale:
            return self.price_wholesale
        return self.price_retail
