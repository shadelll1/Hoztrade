"""Кабинет менеджера: воронка обращений, карточки обращения и клиента, задачи, отчёты."""
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, Max, Min, OuterRef, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from orders.models import Lead

from . import reports, services
from .forms import ClientForm, DealEditForm, NewDealForm, NoteForm, TaskForm
from .models import Activity, Client, Deal, Task

BOARD_CLOSED_DAYS = 14   # выполненные и отказы на доске — за последние две недели


def crm_view(view):
    """Только сотрудникам с правом «Работа в CRM»; страницы с персональными данными не кэшируются."""
    @wraps(view)
    @never_cache
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("admin:login"))
        if not services.can_use(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def _wants_json(request):
    return request.headers.get("x-requested-with") == "fetch"


def _back(request, default):
    """Адрес возврата из формы — только внутри сайта."""
    target = request.POST.get("next") or ""
    ok = url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()})
    return target if ok else reverse(default)


def _page(request, template, context):
    """Счётчики в боковом меню: мои просроченные задачи и новые обращения без менеджера."""
    now = timezone.now()
    context.update({
        "nav_overdue": Task.objects.filter(assignee=request.user, done_at__isnull=True, due_at__lt=now).count(),
        "nav_new": Deal.objects.filter(stage=Deal.Stage.NEW, manager__isnull=True).count(),
        "can_report": services.can_report(request.user),
        "stages": Deal.Stage.choices,
    })
    return render(request, template, context)


def _deals():
    now = timezone.now()
    overdue = Task.objects.filter(deal=OuterRef("pk"), done_at__isnull=True, due_at__lt=now)
    return (Deal.objects.select_related("client", "manager")
            .annotate(next_task=Min("tasks__due_at", filter=Q(tasks__done_at__isnull=True)),
                      has_overdue=Exists(overdue)))


@crm_view
def board(request):
    who = request.GET.get("who", "all")
    source = request.GET.get("source", "")
    q = request.GET.get("q", "").strip()
    qs = _deals()
    if who == "me":
        qs = qs.filter(manager=request.user)
    elif who == "none":
        qs = qs.filter(manager__isnull=True)
    if source in Deal.Source.values:
        qs = qs.filter(source=source)
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        match = (Q(client__name__icontains=q) | Q(client__company__icontains=q) | Q(title__icontains=q)
                 | Q(client__email__icontains=q))
        if len(digits) >= 4:
            match |= Q(client__phone__contains=digits[-10:])
            match |= Q(pk=int(digits)) if len(digits) <= 6 else Q()
        qs = qs.filter(match)
    since = timezone.now() - timedelta(days=BOARD_CLOSED_DAYS)
    qs = qs.filter(Q(stage__in=Deal.OPEN) | Q(closed_at__gte=since))

    columns = []
    deals = list(qs.order_by("-created_at")[:600])
    for value, label in Deal.Stage.choices:
        items = [d for d in deals if d.stage == value]
        columns.append({"stage": value, "label": label, "deals": items,
                        "sum": sum((d.amount for d in items), 0), "closed": value in Deal.CLOSED})
    return _page(request, "crm/board.html", {
        "columns": columns, "who": who, "source": source, "q": q, "sources": Deal.Source.choices,
        "closed_days": BOARD_CLOSED_DAYS, "who_choices": [("all", "Все"), ("me", "Мои"), ("none", "Без менеджера")],
    })


@crm_view
def deal_detail(request, pk):
    deal = get_object_or_404(_deals().select_related("order", "lead", "profile__user"), pk=pk)
    note_form, task_form = NoteForm(), TaskForm(user=request.user, prefix="task")
    edit_form = DealEditForm(instance=deal, prefix="deal")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "note":
            note_form = NoteForm(request.POST)
            if note_form.is_valid():
                services.log(deal, note_form.cleaned_data["text"], note_form.cleaned_data["kind"], author=request.user)
                services.touch(deal, request.user)
                return redirect(deal.get_absolute_url())
        elif action == "task":
            task_form = TaskForm(request.POST, user=request.user, prefix="task")
            if task_form.is_valid():
                task = task_form.save(commit=False)
                task.deal, task.client, task.created_by = deal, deal.client, request.user
                task.save()
                services.log(deal, f"Задача «{task.title}» на {timezone.localtime(task.due_at):%d.%m %H:%M}",
                             Activity.Kind.TASK, author=request.user)
                services.touch(deal, request.user)
                return redirect(deal.get_absolute_url())
        elif action == "edit":
            old_manager = deal.manager
            edit_form = DealEditForm(request.POST, instance=deal, prefix="deal")
            if edit_form.is_valid():
                deal = edit_form.save()
                if deal.manager != old_manager:
                    name = deal.manager.get_full_name() or deal.manager.username if deal.manager else "никто"
                    services.log(deal, f"Ответственный: {name}", author=request.user)
                messages.success(request, "Сохранено")
                return redirect(deal.get_absolute_url())
        elif action == "stage":
            stage = request.POST.get("stage")
            if stage in Deal.Stage.values:
                services.set_stage(deal, stage, author=request.user, reason=request.POST.get("reason", "").strip())
            return redirect(deal.get_absolute_url())

    activities = deal.activities.select_related("author")
    tasks = deal.tasks.select_related("assignee").order_by("done_at", "due_at")
    other_deals = deal.client.deals.exclude(pk=deal.pk).order_by("-created_at")[:6]
    return _page(request, "crm/deal.html", {
        "deal": deal, "activities": activities, "tasks": tasks, "other_deals": other_deals,
        "note_form": note_form, "task_form": task_form, "edit_form": edit_form,
        "items": deal.order.items.all() if deal.order_id else [],
    })


@crm_view
@require_POST
def deal_move(request, pk):
    """Перетаскивание на доске: новый этап. JSON для доски, редирект — без JS."""
    deal = get_object_or_404(Deal, pk=pk)
    stage = request.POST.get("stage")
    if stage not in Deal.Stage.values:
        return JsonResponse({"ok": False}, status=400)
    services.set_stage(deal, stage, author=request.user, reason=request.POST.get("reason", "").strip())
    if _wants_json(request):
        return JsonResponse({"ok": True, "stage": deal.stage, "label": deal.get_stage_display()})
    return redirect(_back(request, "crm:board"))


@crm_view
def deal_new(request):
    form = NewDealForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            client = services.find_or_create_client(data["name"], data["phone"], data["email"], data["company"])
            deal = Deal.objects.create(client=client, source=data["source"], title=data["title"],
                                       amount=data["amount"] or 0, manager=request.user,
                                       first_touch_at=timezone.now())
            services.log(deal, f"Обращение заведено вручную: {deal.get_source_display().lower()}"
                         + (f". {data['text']}" if data["text"] else ""), author=request.user)
        return redirect(deal.get_absolute_url())
    return _page(request, "crm/deal_new.html", {"form": form})


@crm_view
def tasks(request):
    who = request.GET.get("who", "me")
    qs = Task.objects.select_related("deal__client", "client", "assignee")
    if who == "me":
        qs = qs.filter(assignee=request.user)
    now = timezone.localtime()
    day_end = now.replace(hour=23, minute=59, second=59)
    open_qs = qs.filter(done_at__isnull=True).order_by("due_at")
    groups = [
        ("overdue", "Просрочено", open_qs.filter(due_at__lt=now)),
        ("today", "Сегодня", open_qs.filter(due_at__gte=now, due_at__lte=day_end)),
        ("later", "Дальше", open_qs.filter(due_at__gt=day_end)[:100]),
        ("done", "Выполнено за неделю", qs.filter(done_at__gte=now - timedelta(days=7)).order_by("-done_at")[:50]),
    ]
    return _page(request, "crm/tasks.html", {"groups": groups, "who": who})


@crm_view
@require_POST
def task_done(request, pk):
    task = get_object_or_404(Task.objects.select_related("deal"), pk=pk)
    if task.done_at is None:
        task.done_at = timezone.now()
        task.save(update_fields=["done_at"])
        client = task.client or (task.deal.client if task.deal_id else None)
        if client is not None:
            services.log(task.deal, f"Выполнено: {task.title}", Activity.Kind.TASK, author=request.user, client=client)
        if task.deal_id:
            services.touch(task.deal, request.user)
    if _wants_json(request):
        return JsonResponse({"ok": True})
    return redirect(_back(request, "crm:tasks"))


@crm_view
def clients(request):
    q = request.GET.get("q", "").strip()
    qs = Client.objects.annotate(
        deals_n=Count("deals", distinct=True),
        won_sum=Sum("deals__amount", filter=Q(deals__stage=Deal.Stage.WON)),
        last_at=Max("deals__created_at"),
    )
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        match = Q(name__icontains=q) | Q(company__icontains=q) | Q(email__icontains=q) | Q(inn=q)
        if len(digits) >= 4:
            match |= Q(phone__contains=digits[-10:])
        qs = qs.filter(match)
    page = Paginator(qs.order_by("-last_at", "name"), 50).get_page(request.GET.get("page"))
    return _page(request, "crm/clients.html", {"page": page, "q": q})


@crm_view
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form, note_form = ClientForm(instance=client), NoteForm()
    if request.method == "POST":
        if request.POST.get("action") == "edit":
            form = ClientForm(request.POST, instance=client)
            if form.is_valid():
                form.save()
                messages.success(request, "Сохранено")
                return redirect(client.get_absolute_url())
        elif request.POST.get("action") == "note":
            note_form = NoteForm(request.POST)
            if note_form.is_valid():
                Activity.objects.create(client=client, kind=note_form.cleaned_data["kind"],
                                        text=note_form.cleaned_data["text"], author=request.user)
                return redirect(client.get_absolute_url())
    deals = client.deals.select_related("manager", "order").order_by("-created_at")
    won = deals.filter(stage=Deal.Stage.WON).aggregate(n=Count("pk"), s=Sum("amount"))
    first_at = deals.aggregate(first=Min("created_at"))["first"]
    return _page(request, "crm/client.html", {
        "client": client, "form": form, "note_form": note_form, "deals": deals, "won": won, "first_at": first_at,
        "activities": client.activities.select_related("author", "deal")[:80],
        "tasks": client.tasks.filter(done_at__isnull=True).select_related("assignee").order_by("due_at"),
    })


@crm_view
def report(request):
    if not services.can_report(request.user):
        raise PermissionDenied
    days = request.GET.get("days", "30")
    days = int(days) if days in ("7", "30", "90", "365") else 30
    return _page(request, "crm/reports.html", {"r": reports.build(days), "days": days,
                                               "periods": [(7, "7 дней"), (30, "30 дней"), (90, "90 дней"),
                                                           (365, "Год")]})


@crm_view
def lead_file(request, pk):
    """Файл заявки (смета, фото списка) — персональные данные: только сотрудникам, не по прямой ссылке media/."""
    lead = get_object_or_404(Lead, pk=pk)
    if not lead.attachment:
        raise Http404
    return FileResponse(lead.attachment.open("rb"), as_attachment=True,
                        filename=lead.attachment.name.rsplit("/", 1)[-1])

