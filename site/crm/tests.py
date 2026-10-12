import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Profile
from catalog.models import Product
from crm import reports, services
from crm.models import Activity, Client, Deal, Task
from orders.models import Lead, Order

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def setup(settings):
    settings.EXCHANGE_TOKEN = TOKEN
    cache.clear()


@pytest.fixture
def demo(db):
    call_command("load_demo_catalog", stdout=io.StringIO())


def staff(username, group):
    user = get_user_model().objects.create_user(username, f"{username}@example.com", "pass", is_staff=True,
                                                first_name=username.capitalize())
    user.groups.add(Group.objects.get(name=group))
    return user


@pytest.fixture
def manager(db):
    return staff("maria", "Менеджеры")


@pytest.fixture
def head(db):
    return staff("sergey", "Руководители")


def make_order(client, phone="8 900 111-22-33", name="Иван"):
    cement = Product.objects.get(sku="ЦМ-500-50")
    client.post(f"/cart/add/{cement.pk}/", {"quantity": 2})
    client.post("/checkout/", {"customer_type": "person", "name": name, "phone": phone, "email": "",
                               "delivery": "pickup", "store": "", "zone": "", "address": "", "consent": "on",
                               "comment": ""})
    return Order.objects.latest("pk")


@pytest.mark.django_db
class TestDealsAppearThemselves:
    def test_order_creates_client_and_deal(self, client, demo):
        order = make_order(client)
        deal = order.deal
        assert deal.source == Deal.Source.ORDER and deal.stage == Deal.Stage.NEW
        assert deal.amount == order.grand_total and deal.client.phone == "+79001112233"
        assert deal.activities.filter(kind=Activity.Kind.SYSTEM).exists()

    def test_same_phone_same_client(self, client, demo):
        make_order(client, phone="+7 (900) 111-22-33")
        client.post("/callback/", {"name": "Иван", "phone": "89001112233", "consent": "on"})
        assert Client.objects.count() == 1
        assert Client.objects.get().deals.count() == 2
        assert Lead.objects.get().deal.source == Deal.Source.CALLBACK

    def test_order_list_lead_with_file(self, client, db):
        client.post("/order-list/", {"name": "Пётр", "phone": "+79005556677", "text": "Цемент 10 мешков",
                                     "consent": "on", "attachment": SimpleUploadedFile("смета.txt", b"x")})
        deal = Lead.objects.get().deal
        assert deal.source == Deal.Source.LIST and "Цемент 10 мешков" in deal.activities.first().text

    def test_status_from_1c_moves_stage_forward_only(self, client, demo):
        order = make_order(client)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {TOKEN}")

        def status(value):
            api.post("/api/v1/orders/status/", {"orders": [{"id": order.pk, "status": value, "status_text": "",
                                                            "ext_number": "", "total": "900.00"}]}, format="json")
            return Deal.objects.get(order=order)

        assert status("accepted").stage == Deal.Stage.ORDER
        assert str(status("accepted").amount) == "900.00"   # итог из 1С — сумма обращения
        deal = status("done")
        assert deal.stage == Deal.Stage.WON and deal.closed_at
        assert status("confirmed").stage == Deal.Stage.WON   # назад не откатывается

    def test_wholesale_request_and_approval(self, client, db):
        user = get_user_model().objects.create_user("b@example.com", "b@example.com", "x")
        profile = Profile.objects.create(user=user, phone="+79007778899")
        profile.company, profile.inn, profile.wholesale = "ООО Ромашка", "7707083893", Profile.Wholesale.PENDING
        profile.save()
        deal = Deal.objects.get(profile=profile)
        assert deal.source == Deal.Source.B2B and deal.client.company == "ООО Ромашка"
        profile.wholesale = Profile.Wholesale.APPROVED
        profile.save()
        assert Deal.objects.get(pk=deal.pk).stage == Deal.Stage.WON

    def test_backfill_is_idempotent(self, client, demo):
        make_order(client)
        Deal.objects.all().delete()
        assert services.backfill()["orders"] == 1
        assert services.backfill()["orders"] == 0
        assert Deal.objects.count() == 1


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_goes_to_login(self, client):
        r = client.get("/crm/")
        assert r.status_code == 302 and r["Location"].startswith("/admin/login/")

    def test_customer_has_no_access(self, client):
        user = get_user_model().objects.create_user("c@example.com", "c@example.com", "x")
        client.force_login(user)
        assert client.get("/crm/").status_code == 403
        assert client.get("/crm/clients/").status_code == 403

    def test_manager_and_head(self, client, manager, head):
        client.force_login(manager)
        r = client.get("/crm/")
        assert r.status_code == 200 and "no-cache" in r["Cache-Control"]
        assert client.get("/crm/reports/").status_code == 403   # отчёты — руководителям
        client.force_login(head)
        assert client.get("/crm/reports/").status_code == 200

    def test_lead_file_only_in_crm(self, client, manager, db):
        lead = Lead.objects.create(kind="list", name="П", phone="+79005556677",
                                   attachment=SimpleUploadedFile("смета.txt", b"secret"))
        assert client.get(f"/crm/lead-file/{lead.pk}/").status_code == 302
        client.force_login(manager)
        r = client.get(f"/crm/lead-file/{lead.pk}/")
        assert r.status_code == 200 and b"".join(r.streaming_content) == b"secret"

    def test_robots_hide_crm(self, client, db):
        assert "Disallow: /crm/" in client.get("/robots.txt").content.decode()


@pytest.mark.django_db
class TestWork:
    def test_move_on_board_touches_and_assigns(self, client, demo, manager):
        deal = make_order(client).deal
        client.force_login(manager)
        r = client.post(f"/crm/deal/{deal.pk}/move/", {"stage": "contact"}, HTTP_X_REQUESTED_WITH="fetch")
        assert r.json() == {"ok": True, "stage": "contact", "label": "Связались"}
        deal.refresh_from_db()
        assert deal.manager == manager and deal.first_touch_at
        client.post(f"/crm/deal/{deal.pk}/move/", {"stage": "lost", "reason": "Дорого"},
                    HTTP_X_REQUESTED_WITH="fetch")
        deal.refresh_from_db()
        assert deal.stage == "lost" and deal.lost_reason == "Дорого" and deal.closed_at

    def test_note_task_and_done(self, client, demo, manager):
        deal = make_order(client).deal
        client.force_login(manager)
        client.post(deal.get_absolute_url(), {"action": "note", "kind": "call", "text": "Обсудили доставку"})
        due = timezone.localtime() - timedelta(hours=1)
        client.post(deal.get_absolute_url(), {"action": "task", "task-title": "Перезвонить",
                                              "task-due_at": due.strftime("%Y-%m-%dT%H:%M"),
                                              "task-assignee": manager.pk})
        task = Task.objects.get()
        assert task.deal == deal and task.is_overdue
        r = client.get("/crm/")
        assert r.context["nav_overdue"] == 1
        card = next(d for col in r.context["columns"] for d in col["deals"] if d.pk == deal.pk)
        assert card.has_overdue
        client.post(f"/crm/tasks/{task.pk}/done/", HTTP_X_REQUESTED_WITH="fetch")
        task.refresh_from_db()
        assert task.done_at and deal.activities.filter(kind="call", text="Обсудили доставку").exists()

    def test_manual_deal_and_client_search(self, client, manager, db):
        client.force_login(manager)
        r = client.post("/crm/deal/new/", {"name": "Олег", "phone": "8 (900) 222-33-44", "source": "phone",
                                           "title": "Газобетон на баню", "amount": "45000"})
        deal = Deal.objects.get()
        assert r["Location"] == deal.get_absolute_url() and deal.manager == manager
        assert client.get("/crm/clients/", {"q": "2223344"}).context["page"].object_list[0].name == "Олег"
        assert [d.pk for c in client.get("/crm/", {"q": "Олег"}).context["columns"] for d in c["deals"]] == [deal.pk]

    def test_reminders_once(self, manager, db, settings):
        settings.SITE_URL = "https://example.com"
        client_ = Client.objects.create(name="Иван", phone="+79001112233")
        deal = Deal.objects.create(client=client_, title="Счёт")
        Task.objects.create(deal=deal, client=client_, title="Отправить счёт", assignee=manager,
                            due_at=timezone.now() + timedelta(minutes=5))
        Task.objects.create(deal=deal, client=client_, title="Позже", assignee=manager,
                            due_at=timezone.now() + timedelta(days=1))
        call_command("crm_remind", stdout=io.StringIO())
        call_command("crm_remind", stdout=io.StringIO())
        assert len(mail.outbox) == 1 and "Отправить счёт" in mail.outbox[0].subject
        assert f"https://example.com{deal.get_absolute_url()}" in mail.outbox[0].body


@pytest.mark.django_db
def test_reports_numbers(head):
    c = Client.objects.create(name="Иван")
    now = timezone.now()
    Deal.objects.create(client=c, title="1", stage=Deal.Stage.WON, amount=1000, manager=head,
                        first_touch_at=now, created_at=now - timedelta(minutes=30))
    Deal.objects.create(client=c, title="2", stage=Deal.Stage.LOST, source=Deal.Source.CALLBACK,
                        lost_reason="Дорого")
    Deal.objects.create(client=c, title="3", stage=Deal.Stage.NEW, source=Deal.Source.CALLBACK)
    r = reports.build(30)
    assert r["total"] == 3 and r["won"] == 1 and r["won_sum"] == 1000 and r["conv"] == 50
    assert r["response"] == "30 мин" and r["reasons"] == [("Дорого", 1)]
    assert {row["label"]: row["n"] for row in r["by_source"]} == {"Обратный звонок": 2, "Другое": 1}
    assert r["funnel"][0]["n"] == 3 and r["funnel"][-1]["n"] == 1


@pytest.mark.django_db
def test_board_summary_and_waiting_filter(client, manager):
    c = Client.objects.create(name="Иван")
    now = timezone.now()
    old = Deal.objects.create(client=c, title="Ждёт давно", created_at=now - timedelta(hours=3))
    Deal.objects.create(client=c, title="Свежее", created_at=now - timedelta(minutes=5))
    Deal.objects.create(client=c, title="Ответили", stage=Deal.Stage.CONTACT, amount=5000, manager=manager,
                        first_touch_at=now)
    Deal.objects.create(client=c, title="Продано", stage=Deal.Stage.WON, amount=7000, closed_at=now,
                        first_touch_at=now)
    Task.objects.create(client=c, title="Перезвонить", assignee=manager, due_at=now - timedelta(hours=1))
    client.force_login(manager)
    r = client.get("/crm/")
    s = r.context["summary"]
    assert (s["wait"], s["wait_long"], s["overdue"], s["open"], s["open_sum"]) == (2, 1, 1, 3, 5000)
    assert s["won"] == 1 and s["won_sum"] == 7000 and s["wait_oldest"] == old.created_at
    card = next(d for col in r.context["columns"] for d in col["deals"] if d.pk == old.pk)
    assert card.wait_level == "alert"
    contact = next(col for col in r.context["columns"] if col["stage"] == "contact")
    assert contact["share"] == 100.0
    waiting = [d.title for col in client.get("/crm/", {"only": "wait"}).context["columns"] for d in col["deals"]]
    assert sorted(waiting) == ["Ждёт давно", "Свежее"]


@pytest.mark.django_db
def test_reports_compare_with_previous_period(head):
    c = Client.objects.create(name="Иван")
    now = timezone.now()
    Deal.objects.create(client=c, title="Раньше", stage=Deal.Stage.WON, amount=1000,
                        created_at=now - timedelta(days=40))
    for title in ("1", "2"):
        Deal.objects.create(client=c, title=title, stage=Deal.Stage.WON, amount=1500, created_at=now)
    r = reports.build(30)
    assert r["compare"]["won_sum"] == {"text": "+200 %", "good": True, "up": True}
    assert r["compare"]["total"]["text"] == "+100 %"
    assert r["compare"]["response"] is None   # первых ответов нет — сравнивать не с чем
    assert r["funnel"][0]["step"] is None and r["funnel"][1]["step"] == 100


def test_monogram():
    from crm.templatetags.crm import monogram
    assert monogram("Сергей Иванов") == "СИ"
    assert monogram("ООО «СтройМонтаж» (демо)") == "СМ"
    assert monogram("ИП Васильев") == "ВА"
    assert monogram("") == "?"
