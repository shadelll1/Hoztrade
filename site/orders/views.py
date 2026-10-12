from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalog.models import Product

from . import emails
from .cart import Cart
from .forms import CheckoutForm, LeadForm
from .models import Lead, Order, OrderItem
from .notifications import notify

THROTTLE_LIMIT = 5          # отправок форм
THROTTLE_WINDOW = 10 * 60   # за 10 минут с одного IP


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def _throttled(request, scope):
    """Не больше THROTTLE_LIMIT отправок формы за окно с одного адреса."""
    key = f"throttle:{scope}:{_client_ip(request)}"
    count = cache.get(key, 0)
    if count >= THROTTLE_LIMIT:
        return True
    cache.set(key, count + 1, THROTTLE_WINDOW)
    return False


def _qty(value, default=1):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _wants_json(request):
    return request.headers.get("x-requested-with") == "fetch"


def cart_detail(request):
    return render(request, "orders/cart.html", {"cart": Cart(request)})


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product.objects.published(), pk=product_id, price_retail__gt=0)
    cart = Cart(request)
    cart.add(product, _qty(request.POST.get("quantity"), 1) or 1)
    if _wants_json(request):
        return _cart_json(cart, product)
    messages.success(request, f"«{product.name}» в корзине")
    return redirect(_safe_next(request) or reverse("orders:cart"))


def _cart_json(cart, product):
    """Ответ для кнопок «В корзину» и счётчиков в карточках: сколько этого товара в корзине и итог."""
    return JsonResponse({"count": cart.count, "total": str(cart.total), "quantity": cart.quantity(product)})


def _safe_next(request):
    """Адрес возврата из формы — только внутри сайта."""
    target = request.POST.get("next") or ""
    return target if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}) else ""


@require_POST
def cart_update(request, product_id):
    """Задать количество товара в корзине (0 — убрать). Из корзины и из счётчика в карточке товара."""
    product = get_object_or_404(Product, pk=product_id)
    cart = Cart(request)
    cart.set(product, _qty(request.POST.get("quantity"), 0))
    if _wants_json(request):
        return _cart_json(cart, product)
    return redirect(_safe_next(request) or reverse("orders:cart"))


@require_POST
def cart_remove(request, product_id):
    Cart(request).remove(product_id)
    return redirect("orders:cart")


def checkout(request):
    cart = Cart(request)
    if not cart.lines:
        return redirect("orders:cart")

    form = CheckoutForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        if _throttled(request, "checkout"):
            messages.error(request, "Слишком много заказов подряд. Позвоните нам, пожалуйста.")
            return redirect("orders:checkout")
        order = _create_order(request, form, cart)
        cart.clear()
        emails.order_created(order, request)
        admin_url = request.build_absolute_uri(reverse("admin:orders_order_change", args=[order.pk]))
        _notify(f"Новый заказ {order.number} на {order.total} ₽", f"{order.name}, {order.phone}\n{admin_url}")
        return redirect(order.get_absolute_url() + "?new=1")

    quotes = cart.delivery_quotes
    zones = [{"radio": radio, "quote": quotes.get(int(str(radio.data["value"])))} for radio in form["zone"]]
    return render(request, "orders/checkout.html", {"cart": cart, "form": form, "zones": zones,
                                                    "company_profile": form.wholesale_profile})


@transaction.atomic
def _create_order(request, form, cart):
    order = form.save(commit=False)
    if order.delivery == Order.Delivery.PICKUP:
        order.pickup_store = form.cleaned_data.get("store") or ""
    if request.user.is_authenticated:
        order.user = request.user
    profile = form.wholesale_profile
    if profile is not None:
        order.customer_type = Order.CustomerType.COMPANY
        order.company = profile.company
        order.inn = profile.inn
    order.price_type = Order.PriceType.WHOLESALE if cart.wholesale else Order.PriceType.RETAIL
    order.total = cart.total
    order.weight_kg = cart.weight
    order.volume_m3 = cart.volume
    if order.delivery == Order.Delivery.TRUCK:
        _apply_delivery(order, cart)
    order.save()
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order, product=line.product, product_ext_id=line.product.ext_id, sku=line.product.sku,
            name=line.product.title, unit=line.product.unit, price=line.price,
            quantity=line.quantity, amount=line.amount,
        )
        for line in cart.lines
    ])
    return order


def _apply_delivery(order, cart):
    """Машина, рейсы и стоимость доставки по тарифу зоны. Без тарифа — только машина по весу, цену назовёт менеджер."""
    quote = cart.delivery_quotes.get(order.zone_id) if order.zone_id else None
    if quote is not None:
        truck, trips = quote.truck, quote.trips
        order.delivery_cost = quote.cost
    else:
        truck, trips = cart.truck
    if truck is not None:
        order.truck_t = truck.capacity_t
        order.truck_name = truck.name
        order.trips = trips


def order_detail(request, token):
    order = get_object_or_404(Order.objects.prefetch_related("items"), token=token)
    return render(request, "orders/order.html", {"order": order, "just_created": request.GET.get("new") == "1"})


def order_list(request):
    """Заказ по списку: текст и/или файл сметы."""
    form = LeadForm(request.POST or None, request.FILES or None, kind=Lead.Kind.LIST)
    if request.method == "POST" and form.is_valid():
        if _throttled(request, "lead"):
            messages.error(request, "Слишком много заявок подряд. Позвоните нам, пожалуйста.")
            return redirect("orders:order_list")
        lead = form.save(commit=False)
        lead.kind = Lead.Kind.LIST
        lead.save()
        _notify(f"Заказ по списку от {lead.name}", f"{lead.phone}\n{lead.text}")
        messages.success(request, "Заявка принята. Менеджер соберёт заказ и перезвонит.")
        return redirect("orders:order_list")
    return render(request, "orders/order_list.html", {"form": form})


@require_POST
def callback(request):
    form = LeadForm(request.POST, kind=Lead.Kind.CALLBACK)
    ok = form.is_valid() and not _throttled(request, "lead")
    if ok:
        lead = form.save(commit=False)
        lead.kind = Lead.Kind.CALLBACK
        lead.save()
        _notify(f"Обратный звонок: {lead.name}", lead.phone)
    if _wants_json(request):
        return JsonResponse({"ok": ok, "errors": form.errors if not ok else {}}, status=200 if ok else 400)
    if ok:
        messages.success(request, "Спасибо! Перезвоним в рабочее время.")
    else:
        messages.error(request, "Проверьте имя и телефон.")
    return redirect(request.POST.get("next") or "/")


def _notify(subject, body):
    notify(subject, body)
