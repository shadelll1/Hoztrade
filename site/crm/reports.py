"""Отчёты руководителю: обращения по источникам и менеджерам, конверсия, выручка, скорость первого ответа, воронка.

Графики — SVG с размерами в атрибутах (CSP запрещает встроенные стили); геометрия считается здесь.
"""
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.utils import timezone

from . import services
from .models import Activity, Deal, Task

STAGES = [s for s, _ in Deal.Stage.choices]
FUNNEL = [Deal.Stage.NEW, Deal.Stage.CONTACT, Deal.Stage.OFFER, Deal.Stage.ORDER, Deal.Stage.WON]


def _minutes(deals):
    values = [(d.first_touch_at - d.created_at).total_seconds() / 60 for d in deals
              if d.first_touch_at and d.first_touch_at >= d.created_at]
    return median(values) if values else None


def duration(minutes):
    """«35 мин», «4 ч 10 мин», «2 дн 3 ч»."""
    if minutes is None:
        return "—"
    minutes = round(minutes)
    if minutes < 60:
        return f"{minutes} мин"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} ч {rest} мин" if rest else f"{hours} ч"
    days, hours = divmod(hours, 24)
    return f"{days} дн {hours} ч" if hours else f"{days} дн"


def _conv(won, total):
    return round(100 * won / total) if total else 0


def _hbars(rows, key, width=78):
    """Горизонтальные столбики одной серии: длина в % ширины ячейки (до width %), справа — подпись значения.
    Проценты, а не viewBox: текст подписи не масштабируется вместе со столбиком."""
    top = max((r[key] for r in rows), default=0) or 1
    for r in rows:
        pct = round(width * float(r[key]) / float(top), 1) if r[key] else 0
        r["bar_w"] = f"{max(pct, 1.5)}%" if pct else ""
        r["label_x"] = f"{pct + 2}%" if pct else "0%"
    return rows


def _daily(deals, start, days):
    """Столбики по дням (или неделям для длинных периодов): геометрия для SVG 720×160."""
    step = 1 if days <= 31 else 7
    buckets = []
    day = start.date()
    end = timezone.localdate()
    while day <= end:
        buckets.append({"from": day, "n": 0})
        day += timedelta(days=step)
    for d in deals:
        idx = (timezone.localtime(d.created_at).date() - start.date()).days // step
        if 0 <= idx < len(buckets):
            buckets[idx]["n"] += 1
    w, h, pad = 720, 150, 22
    top = max((b["n"] for b in buckets), default=0)
    nice = max(1, top)
    slot = w / max(1, len(buckets))
    bar = min(24, max(4, slot * 0.6))
    radius = min(4, bar / 2)
    for i, b in enumerate(buckets):
        bh = 0 if not b["n"] else max(radius + 2, round((h - pad) * b["n"] / nice))
        x = round(i * slot + (slot - bar) / 2, 1)
        b.update(x=x, w=round(bar, 1), h=bh, y=h - bh, hit_x=round(i * slot, 1), hit_w=round(slot, 1),
                 label=b["from"].strftime("%d.%m") + ("" if step == 1 else "+"))
        # Столбик растёт от базовой линии, верх скруглён на 4px, низ прямой
        r = radius
        b["path"] = (f"M{x},{h} V{h - bh + r} Q{x},{h - bh} {x + r},{h - bh} H{round(x + bar - r, 1)} "
                     f"Q{round(x + bar, 1)},{h - bh} {round(x + bar, 1)},{h - bh + r} V{h} Z") if bh else ""
    ticks = [{"v": v, "y": round(h - (h - pad) * v / nice, 1)} for v in sorted({0, nice // 2, nice}) if nice]
    every = max(1, len(buckets) // 8)
    for i, b in enumerate(buckets):
        b["show_label"] = i % every == 0 or i == len(buckets) - 1
        b["lx"] = round(b["x"] + b["w"] / 2, 1)
    return {"bars": buckets, "ticks": ticks, "w": w, "h": h, "step": step, "top": top,
            "view": f"-30 -8 {w + 40} {h + 34}", "label_y": h + 18}


def build(days=30):
    now = timezone.now()
    start = timezone.localtime(now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = list(Deal.objects.filter(created_at__gte=start).select_related("manager"))
    won = [d for d in deals if d.stage == Deal.Stage.WON]
    lost = [d for d in deals if d.stage == Deal.Stage.LOST]
    won_sum = sum((d.amount for d in won), Decimal(0))

    by_source = []
    for value, label in Deal.Source.choices:
        items = [d for d in deals if d.source == value]
        if not items:
            continue
        w = [d for d in items if d.stage == Deal.Stage.WON]
        by_source.append({"label": label, "n": len(items), "won": len(w), "conv": _conv(len(w), len(items)),
                          "sum": sum((d.amount for d in w), Decimal(0))})
    by_source.sort(key=lambda r: -r["n"])
    _hbars(by_source, "n")

    overdue = {}
    for task in Task.objects.filter(done_at__isnull=True, due_at__lt=now).values("assignee_id"):
        overdue[task["assignee_id"]] = overdue.get(task["assignee_id"], 0) + 1
    by_manager = []
    people = {m.pk: m for m in services.managers()}
    for d in deals:
        if d.manager_id and d.manager_id not in people:
            people[d.manager_id] = d.manager
    for pk, user in people.items():
        items = [d for d in deals if d.manager_id == pk]
        if not items and not overdue.get(pk):
            continue
        w = [d for d in items if d.stage == Deal.Stage.WON]
        by_manager.append({"name": user.get_full_name() or user.username, "n": len(items), "won": len(w),
                           "conv": _conv(len(w), len(items)), "sum": sum((d.amount for d in w), Decimal(0)),
                           "response": duration(_minutes(items)), "overdue": overdue.get(pk, 0)})
    unassigned = [d for d in deals if not d.manager_id]
    if unassigned:
        by_manager.append({"name": "Без менеджера", "n": len(unassigned), "won": 0, "conv": 0, "sum": Decimal(0),
                           "response": "—", "overdue": 0, "muted": True})
    by_manager.sort(key=lambda r: (r.get("muted", False), -r["sum"], -r["n"]))
    _hbars(by_manager, "sum", width=55)

    # Воронка: сколько обращений периода дошло до этапа — по истории этапов и текущему этапу
    reached = {d.pk: {Deal.Stage.NEW, d.stage} for d in deals}
    for deal_id, stage in Activity.objects.filter(deal_id__in=reached, kind=Activity.Kind.STAGE).values_list(
            "deal_id", "stage"):
        if stage:
            reached[deal_id].add(stage)
    funnel = []
    for stage in FUNNEL:
        idx = STAGES.index(stage)
        n = sum(1 for d in deals if any(STAGES.index(s) >= idx for s in reached[d.pk] if s != Deal.Stage.LOST))
        funnel.append({"label": Deal.Stage(stage).label, "n": n, "share": _conv(n, len(deals))})
    _hbars(funnel, "n")

    reasons = {}
    for d in lost:
        key = d.lost_reason or "Причина не указана"
        reasons[key] = reasons.get(key, 0) + 1

    return {
        "start": start, "total": len(deals), "won": len(won), "won_sum": won_sum, "lost": len(lost),
        "conv": _conv(len(won), len(won) + len(lost)), "response": duration(_minutes(deals)),
        "open_now": Deal.objects.filter(stage__in=Deal.OPEN).count(),
        "overdue_now": sum(overdue.values()),
        "by_source": by_source, "by_manager": by_manager, "funnel": funnel,
        "reasons": sorted(reasons.items(), key=lambda kv: -kv[1])[:6],
        "daily": _daily(deals, start, days),
    }
