from .cart import Cart


def cart(request):
    """Количество позиций корзины для значка в шапке (без запроса к базе)."""
    return {"cart_count": Cart(request).count}
