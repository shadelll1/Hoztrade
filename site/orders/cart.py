"""Корзина в сессии: {product_id: количество}. Цены и остатки всегда берутся из базы, не из сессии."""
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property

from django.conf import settings

from accounts.models import is_wholesale
from catalog.models import Product

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
            self._lines = [Line(products[int(pk)], int(q), self.wholesale) for pk, q in self.data.items() if int(pk) in products]
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
    def truck(self):
        """Наименьшая машина, которая увезёт корзину по весу, т. None — тяжелее самой большой."""
        weight_t = self.weight / 1000
        for capacity in settings.TRUCK_CAPACITIES_T:
            if weight_t <= Decimal(str(capacity)):
                return capacity
        return None

    @property
    def has_over_stock(self):
        return any(line.over_stock for line in self.lines)
