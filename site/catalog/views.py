import math
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404, render

from delivery.services import fleet

from .models import Category, Product
from .tree import build_tree, find_node

PER_PAGE = 24

SORTS = {
    "popular": ("По наличию", None),
    "price": ("Сначала дешевле", ("price_retail", "name")),
    "-price": ("Сначала дороже", ("-price_retail", "name")),
    "name": ("По названию", ("name",)),
}


def _in_stock_first(qs):
    return qs.annotate(
        out_of_stock=Case(When(stock__gt=0, then=Value(0)), default=Value(1), output_field=IntegerField())
    ).order_by("out_of_stock", "name")


def _decimal(value):
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _filter_and_sort(request, qs):
    """Фильтры и сортировка из query string. Возвращает (queryset, состояние фильтров для шаблона)."""
    state = {
        "in_stock": request.GET.get("in_stock") == "1",
        "price_min": _decimal(request.GET.get("price_min")),
        "price_max": _decimal(request.GET.get("price_max")),
        "sort": request.GET.get("sort") if request.GET.get("sort") in SORTS else "popular",
    }
    if state["in_stock"]:
        qs = qs.filter(stock__gt=0)
    if state["price_min"] is not None:
        qs = qs.filter(price_retail__gte=state["price_min"])
    if state["price_max"] is not None:
        qs = qs.filter(price_retail__lte=state["price_max"])

    ordering = SORTS[state["sort"]][1]
    qs = _in_stock_first(qs) if ordering is None else qs.order_by(*ordering)
    state["sorts"] = [(key, label) for key, (label, _) in SORTS.items()]
    state["active"] = state["in_stock"] or state["price_min"] is not None or state["price_max"] is not None
    return qs, state


def _page(request, qs):
    return Paginator(qs, PER_PAGE).get_page(request.GET.get("page"))


def home(request):
    in_stock = _in_stock_first(Product.objects.published().filter(stock__gt=0, price_retail__gt=0))
    return render(request, "catalog/home.html", {
        "products": in_stock.select_related("category")[:8],
        "trucks": fleet(),
    })


def catalog_root(request):
    return render(request, "catalog/catalog_root.html")


def category(request, slug):
    current = get_object_or_404(Category, slug=slug, is_published=True)
    tree = build_tree()
    node = find_node(tree, current.pk)

    qs = Product.objects.published().filter(category_id__in=current.descendant_ids()).select_related("category")
    qs, filters = _filter_and_sort(request, qs)
    return render(request, "catalog/category.html", {
        "category": current,
        "node": node,
        "breadcrumbs": current.ancestors(),
        "page": _page(request, qs),
        "filters": filters,
    })


def product(request, slug):
    item = get_object_or_404(Product.objects.select_related("category__parent"), slug=slug, is_published=True)
    related = (
        _in_stock_first(Product.objects.published().filter(category=item.category).exclude(pk=item.pk))
        .select_related("category")[:4]
        if item.category_id else []
    )
    # Сколько единиц товара помещается в каждую машину — по весу и, если известен, по объёму кузова.
    trucks = []
    if item.weight_kg > 0:
        for truck in fleet():
            fits = math.floor(truck.capacity_kg / item.weight_kg)
            if truck.volume_m3 > 0 and item.volume_m3 > 0:
                fits = min(fits, math.floor(truck.volume_m3 / item.volume_m3))
            trucks.append((truck, fits))
    return render(request, "catalog/product.html", {
        "product": item,
        "breadcrumbs": (item.category.ancestors() + [item.category]) if item.category_id else [],
        "related": related,
        "trucks": trucks,
    })


def search(request):
    query = request.GET.get("q", "").strip()[:100]
    terms = [t for t in query.lower().split() if len(t) >= 2]
    qs = Product.objects.published().select_related("category")
    if terms:
        for term in terms:
            qs = qs.filter(search_text__contains=term)
    else:
        qs = qs.none()
    qs, filters = _filter_and_sort(request, qs)
    return render(request, "catalog/search.html", {
        "query": query,
        "page": _page(request, qs),
        "filters": filters,
    })
