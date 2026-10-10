from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalog.models import Product
from orders.cart import Cart
from orders.models import Order
from orders.views import _notify, _throttled

from .forms import LoginForm, ProfileForm, RegisterForm, WholesaleRequestForm
from .models import Profile


def _profile(user):
    """Профиль есть у всех, кто зарегистрировался на сайте; сотруднику из админки создаём при первом входе."""
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


def _safe_next(request, default):
    url = request.POST.get("next") or request.GET.get("next")
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return default


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _throttled(request, "register"):
            messages.error(request, "Слишком много регистраций подряд. Попробуйте позже.")
            return redirect("accounts:register")
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Готово! Заказы, оформленные под этой учётной записью, будут в личном кабинете.")
        return redirect(_safe_next(request, reverse("accounts:home")))
    return render(request, "accounts/register.html", {"form": form, "next": _safe_next(request, "")})


class SiteLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


@login_required
def home(request):
    profile = _profile(request.user)
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "accounts/home.html", {
        "profile": profile,
        "orders": orders,
        "wholesale_form": WholesaleRequestForm(instance=profile),
    })


@login_required
def profile_edit(request):
    profile = _profile(request.user)
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Контакты сохранены")
        return redirect("accounts:home")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
@require_POST
def wholesale_request(request):
    """Заявка на оптовые цены: реквизиты сохраняются, менеджер получает письмо и подтверждает в админке."""
    profile = _profile(request.user)
    if profile.is_wholesale:
        return redirect("accounts:home")
    form = WholesaleRequestForm(request.POST, instance=profile)
    if not form.is_valid():
        orders = Order.objects.filter(user=request.user).prefetch_related("items")
        return render(request, "accounts/home.html", {"profile": profile, "orders": orders,
                                                      "wholesale_form": form}, status=400)
    profile = form.save(commit=False)
    profile.wholesale = Profile.Wholesale.PENDING
    profile.wholesale_requested_at = timezone.now()
    profile.wholesale_comment = ""
    profile.save()
    _notify(f"Заявка на оптовые цены: {profile.company}",
            f"ИНН {profile.inn}, {request.user.email}, {profile.phone}\n"
            + request.build_absolute_uri(reverse("admin:accounts_profile_change", args=[profile.pk])))
    messages.success(request, "Заявка отправлена. Менеджер проверит компанию и откроет оптовые цены.")
    return redirect("accounts:home")


@login_required
@require_POST
def repeat_order(request, token):
    """Повтор заказа: товары, которые ещё продаются, кладутся в корзину по текущим ценам."""
    order = get_object_or_404(Order, token=token, user=request.user)
    ids = [i.product_id for i in order.items.all() if i.product_id]
    products = Product.objects.published().filter(pk__in=ids, price_retail__gt=0).in_bulk()
    cart = Cart(request)
    added = skipped = 0
    for item in order.items.all():
        product = products.get(item.product_id)
        if product is None:
            skipped += 1
            continue
        cart.add(product, max(1, int(item.quantity)))
        added += 1
    if added:
        text = f"В корзине товары из заказа {order.number}. Цены — актуальные на сегодня."
        if skipped:
            text += f" Не добавлено (больше не продаётся): {skipped}."
        messages.success(request, text)
    else:
        messages.error(request, "Товаров из этого заказа больше нет в продаже.")
    return redirect("orders:cart")
