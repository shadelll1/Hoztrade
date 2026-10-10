from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from catalog.models import Product
from orders.notifications import notify
from orders.views import _throttled

from .forms import ReviewForm
from .models import Post

PER_PAGE = 12

KIND_TITLES = {
    None: "Акции, новости и советы",
    Post.Kind.PROMO: "Акции",
    Post.Kind.NEWS: "Новости",
    Post.Kind.ADVICE: "Советы строителям",
}


def post_list(request, kind=None):
    posts = Post.objects.published()
    if kind:
        posts = posts.filter(kind=kind)
        if kind == Post.Kind.PROMO:
            posts = Post.objects.active_promos()
    page = Paginator(posts, PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "content/post_list.html", {
        "page": page, "kind": kind, "title": KIND_TITLES[kind], "kinds": Post.Kind,
    })


def post_detail(request, slug):
    post = get_object_or_404(Post.objects.published(), slug=slug)
    more = Post.objects.published().filter(kind=post.kind).exclude(pk=post.pk)[:3]
    return render(request, "content/post_detail.html", {"post": post, "more": more})


@require_POST
def review_create(request, slug):
    product = get_object_or_404(Product.objects.published(), slug=slug)
    form = ReviewForm(request.POST)
    anchor = product.get_absolute_url() + "#reviews"
    if not form.is_valid():
        # Форма на странице товара; ошибки показываем там же, введённое не теряем.
        request.session["review_form"] = {"data": request.POST.dict(), "product": product.pk}
        messages.error(request, "Отзыв не отправлен: проверьте поля формы.")
        return redirect(anchor)
    if _throttled(request, "review"):
        messages.error(request, "Слишком много отзывов подряд. Попробуйте позже.")
        return redirect(anchor)
    review = form.save(commit=False)
    review.product = product
    review.save()
    notify(f"Новый отзыв на «{product.name}» ({review.rating}★)",
           f"{review.name}: {review.text}\n"
           f"{request.build_absolute_uri(reverse('admin:content_review_change', args=[review.pk]))}")
    messages.success(request, "Спасибо за отзыв! Он появится на сайте после проверки.")
    return redirect(anchor)
