"""Корзина в сессии: {product_id: количество}. Цены и остатки всегда берутся из базы, не из сессии."""
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property

from accounts.models import is_wholesale
from catalog.models import Product
from delivery import services as delivery

SESSION_KEY = "cart"
MAX_QTY = 100000


@dataclass
class Line:
    product: Product
    quantity: int
    wholesale: bool = False

    @property
    def price(self):
        return self.product.price_for(self.wholesale)

    @property
    def amount(self):
        return self.price * self.quantity

    @property
    def weight(self):
        return self.product.weight_kg * self.quantity

    @property
    def volume(self):
        return self.product.volume_m3 * self.quantity

    @property
    def over_stock(self):
        return self.quantity > self.product.stock


class Cart:
    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(SESSION_KEY) or {}
        self.user = getattr(request, "user", None)
        self._lines = None

    @cached_property
    def wholesale(self):
        """Подтверждённая компания покупает по оптовым ценам."""
        return is_wholesale(self.user)

    def _save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True
        self._lines = None
        for name in ("fleet", "truck", "delivery_quotes"):
            self.__dict__.pop(name, None)

    def add(self, product, quantity=1):
        current = int(self.data.get(str(product.pk), 0))
        self.set(product, current + quantity)

    def set(self, product, quantity):
        quantity = max(0, min(int(quantity), MAX_QTY))
        if quantity:
            self.data[str(product.pk)] = quantity
        else:
            self.data.pop(str(product.pk), None)
        self._save()

    def quantity(self, product):
        return int(self.data.get(str(product.pk), 0))

    def quantities(self):
        """{id товара: количество} — для счётчиков в карточках, без запроса к базе."""
        return {int(pk): int(q) for pk, q in self.data.items()}

    def remove(self, product_id):
        self.data.pop(str(product_id), None)
        self._save()

    def clear(self):
        self.data = {}
        self._save()

    @property
    def lines(self):
        """Строки корзины. Снятые с публикации и товары без цены выпадают."""
        if self._lines is None:
            ids = [int(pk) for pk in self.data]
            products = Product.objects.published().filter(pk__in=ids, price_retail__gt=0).in_bulk()
            self._lines = [Line(products[int(pk)], int(q), self.wholesale)
                           for pk, q in self.data.items() if int(pk) in products]
        return self._lines

    def __len__(self):
        return len(self.lines)

    @property
    def count(self):
        """Количество позиций (не штук) — для значка в шапке."""
        return len(self.data)

    @property
    def total(self):
        return sum((line.amount for line in self.lines), Decimal("0"))

    @property
    def weight(self):
        return sum((line.weight for line in self.lines), Decimal("0"))

    @property
    def volume(self):
        return sum((line.volume for line in self.lines), Decimal("0"))

    @cached_property
    def fleet(self):
        return delivery.fleet()

    @cached_property
    def truck(self):
        """(машина, рейсов): наименьшая машина автопарка, которая увезёт корзину; (None, 0) — автопарка нет."""
        return delivery.pick_truck(self.fleet, self.weight, self.volume)

    @cached_property
    def delivery_quotes(self):
        """Расчёт доставки корзины по всем зонам: {id зоны: Quote}."""
        return delivery.quotes(self.weight, self.volume, self.fleet)

    @property
    def delivery_from(self):
        """Самая дешёвая доставка — для подсказки в корзине."""
        return min(self.delivery_quotes.values(), key=lambda q: q.cost, default=None)

    @property
    def has_over_stock(self):
        return any(line.over_stock for line in self.lines)
