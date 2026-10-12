import math
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Avg, Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from accounts.models import is_wholesale
from content.forms import ReviewForm
from content.models import Post, Review
from delivery.services import calc_data, fleet, fleet_with_prices

from .attrs import LABELS, facets
from .calc import calculator
from .companions import companions
from .models import Brand, Category, Product
from .templatetags.shop import rub
from .tree import cached_tree, find_node

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


def _filter_and_sort(request, qs, relevance=None):
    """Фильтры и сортировка из query string. Возвращает (queryset, состояние фильтров для шаблона).

    relevance — выражение «чем меньше, тем выше» для поиска: при сортировке по умолчанию идёт первым ключом.
    """
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

    # Бренды — из того, что осталось после остальных фильтров, с количеством товаров; выбранные отмечены.
    chosen = set(request.GET.getlist("brand"))
    state["brands"] = [
        {"slug": row["brand__slug"], "name": row["brand__name"], "count": row["n"],
         "checked": row["brand__slug"] in chosen}
        for row in qs.filter(brand__is_published=True).values("brand__slug", "brand__name")
        .annotate(n=Count("pk")).order_by("brand__name")
    ]
    if chosen:
        qs = qs.filter(brand__slug__in=chosen)

    # Свойства из наименований (фасовка, толщина, цвет…): ?f_pack=25 кг&f_pack=50 кг — «или» внутри свойства,
    # «и» между свойствами. Счётчики — по товарам, прошедшим остальные фильтры.
    picked = {key: set(request.GET.getlist(f"f_{key}")) for key in LABELS}
    picked = {key: values for key, values in picked.items() if values}
    state["facets"] = facets(list(qs.values_list("pk", "attrs")), picked)
    for key, values in picked.items():
        qs = qs.filter(**{f"attrs__{key}__in": sorted(values)})

    approved = Q(reviews__status=Review.Status.APPROVED)
    qs = qs.annotate(rating=Avg("reviews__rating", filter=approved), reviews_n=Count("reviews", filter=approved))

    ordering = SORTS[state["sort"]][1]
    if ordering is None:
        qs = _in_stock_first(qs)
        if relevance is not None:
            qs = qs.annotate(relevance=relevance).order_by("relevance", "out_of_stock", "name")
    else:
        qs = qs.order_by(*ordering)
    state["sorts"] = [(key, label) for key, (label, _) in SORTS.items()]
    state["active"] = (state["in_stock"] or state["price_min"] is not None or state["price_max"] is not None
                       or bool(chosen) or bool(picked))
    # «Сбросить фильтры» — оставляем только поиск и сортировку
    keep = {k: request.GET[k] for k in ("q", "sort") if request.GET.get(k)}
    state["reset_url"] = "?" + urlencode(keep) if keep else "?"
    return qs, state


def _page(request, qs):
    return Paginator(qs, PER_PAGE).get_page(request.GET.get("page"))


# Подсказки поиска на первом экране: самые частые запросы покупателей стройматериалов
POPULAR_QUERIES = ("Цемент", "Кирпич", "Профнастил", "Металлочерепица", "Поликарбонат", "Ламинат", "Плиточный клей",
                   "Смеситель")


def home(request):
    in_stock = Product.objects.published().filter(stock__gt=0, price_retail__gt=0).select_related("category")
    # Витрина главной — это картинки: товары с фото, по одному из группы, чтобы лента была разнообразной.
    # Порядок — по «обороту» остатка (штука × цена): сверху типичные покупки, а не самая дешёвая мелочь.
    with_photo = sorted(in_stock.exclude(thumb="")[:400], key=lambda p: (-p.stock * p.price_retail, p.name))
    products = _one_per_group(with_photo, 12) or list(_in_stock_first(in_stock)[:12])
    return render(request, "catalog/home.html", {
        "products": products,
        "trucks": fleet_with_prices(),
        "popular_queries": POPULAR_QUERIES,
        "promos": Post.objects.active_promos()[:3],
        "posts": Post.objects.published().exclude(kind=Post.Kind.PROMO)[:3],
        "brands": _brands_with_products()[:12],
    })


def _root_id(p):
    return (p.category.parent_id or p.category_id) if p.category_id else None


def _one_per_group(products, n):
    """По одному товару из каждой группы, по кругу разделов: цемент, смеситель, ламинат, … вместо 12 мешков."""
    by_root = {}
    seen_groups = set()
    for p in products:
        if p.category_id not in seen_groups:
            seen_groups.add(p.category_id)
            by_root.setdefault(_root_id(p), []).append(p)
    queues = list(by_root.values())
    picked = []
    while queues and len(picked) < n:
        for q in list(queues):
            picked.append(q.pop(0))
            if not q:
                queues.remove(q)
            if len(picked) == n:
                break
    return picked


def _brands_with_products():
    return (Brand.objects.filter(is_published=True)
            .annotate(count=Count("products", filter=Q(products__is_published=True)))
            .filter(count__gt=0))


def brand_list(request):
    return render(request, "catalog/brand_list.html", {"brands": _brands_with_products()})


def brand(request, slug):
    item = get_object_or_404(Brand, slug=slug, is_published=True)
    qs = Product.objects.published().filter(brand=item).select_related("category")
    qs, filters = _filter_and_sort(request, qs)
    return render(request, "catalog/brand.html", {"brand": item, "page": _page(request, qs), "filters": filters})


def catalog_root(request):
    return render(request, "catalog/catalog_root.html")


def category(request, slug):
    current = get_object_or_404(Category, slug=slug, is_published=True)
    tree = cached_tree()
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
    item = get_object_or_404(Product.objects.select_related("category__parent", "brand"), slug=slug, is_published=True)
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
    # Форма отзыва с ошибками возвращается сюда редиректом — введённое берём из сессии.
    saved = request.session.pop("review_form", None)
    review_form = ReviewForm(saved["data"]) if saved and saved.get("product") == item.pk else ReviewForm()
    reviews = item.reviews.approved()
    delivery = None
    if item.weight_kg > 0 and item.can_buy:
        delivery = {**calc_data(), "product": {"kg": float(item.weight_kg), "m3": float(item.volume_m3)}}
    return render(request, "catalog/product.html", {
        "product": item,
        "breadcrumbs": [*item.category.ancestors(), item.category] if item.category_id else [],
        "related": related,
        "companions": companions(item),
        "calc": calculator(item) if item.can_buy else None,
        "delivery": delivery if delivery and delivery["zones"] else None,
        "trucks": trucks,
        "reviews": reviews,
        "rating": item.reviews.summary(),
        "review_form": review_form,
    })


def _search_terms(query):
    return [t for t in query.lower().split() if len(t) >= 2]


def _search_qs(terms):
    """(товары по словам запроса, выражение релевантности или None)."""
    qs = Product.objects.published().select_related("category")
    if not terms:
        return qs.none(), None
    for term in terms:
        qs = qs.filter(search_text__contains=term)
    # Название начинается с запроса — выше всех; запрос с начала слова — ниже; вхождение в середину слова — в конце.
    # search_text хранится в нижнем регистре: SQLite не умеет регистронезависимо сравнивать кириллицу.
    first = terms[0]
    relevance = Case(
        When(search_text__startswith=first, then=Value(0)),
        When(search_text__contains=" " + first, then=Value(1)),
        default=Value(2), output_field=IntegerField(),
    )
    return qs, relevance


def search_suggest(request):
    """Подсказки под строкой поиска: разделы и товары. Пустой запрос — частые запросы."""
    query = request.GET.get("q", "").strip()[:100]
    terms = _search_terms(query)
    if not terms:
        return JsonResponse({"q": query, "popular": POPULAR_QUERIES, "categories": [], "products": [], "total": 0})
    qs, relevance = _search_qs(terms)
    total = qs.count()
    products = qs.annotate(relevance=relevance).order_by("relevance", "-stock", "name")[:6]

    # Разделы — по основе слова: «штукатурка» находит «Штукатурки», «смеситель» — «Смесители»
    stems = [t[:max(4, len(t) - 2)] for t in terms]
    categories = []
    stack = list(cached_tree())
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        words = node.name.lower().split()
        if all(any(w.startswith(stem) for w in words) for stem in stems):
            categories.append({"name": node.name, "url": node.get_absolute_url(), "count": node.count})
    categories.sort(key=lambda c: -c["count"])

    wholesale = is_wholesale(request.user)
    return JsonResponse({
        "q": query,
        "total": total,
        "all_url": f"{reverse('catalog:search')}?{urlencode({'q': query})}",
        "categories": categories[:3],
        "products": [{
            "title": p.title, "url": p.get_absolute_url(), "price": rub(p.price_for(wholesale)) if p.can_buy else "",
            "unit": p.unit, "image": p.list_image.url if p.list_image else "", "in_stock": p.in_stock,
        } for p in products],
    })


def search(request):
    query = request.GET.get("q", "").strip()[:100]
    qs, relevance = _search_qs(_search_terms(query))
    qs, filters = _filter_and_sort(request, qs, relevance)
    return render(request, "catalog/search.html", {
        "query": query,
        "page": _page(request, qs),
        "filters": filters,
    })
