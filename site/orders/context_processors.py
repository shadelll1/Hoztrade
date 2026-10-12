from .cart import Cart


def cart(request):
    """Значок корзины в шапке и количество каждого товара в корзине для счётчиков в карточках (без запроса к базе)."""
    current = Cart(request)
    return {"cart_count": current.count, "cart_qty": current.quantities()}
