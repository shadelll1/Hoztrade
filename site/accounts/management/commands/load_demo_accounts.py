from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from accounts.models import Profile

DEMO_PASSWORD = "hoztrade-demo"  # noqa: S105 — демо-учётки для локальной проверки, не для боевого сайта

# Покупатели для демонстрации: частное лицо и подтверждённая компания с оптовыми ценами.
# ИНН выдуманный, но с верной контрольной суммой.
ACCOUNTS = [
    {"email": "demo@hoztrade.local", "name": "Иван Покупатель", "phone": "+79001112233"},
    {"email": "snab@hoztrade.local", "name": "Ольга Снабженец", "phone": "+79002223344",
     "company": "ООО «СтройМонтаж» (демо)", "inn": "2128000008", "wholesale": Profile.Wholesale.APPROVED},
]

# Сотрудники для CRM (/crm/): вход через /admin/login/, группы — из миграции crm.0002_groups.
STAFF = [
    {"email": "manager@hoztrade.local", "first": "Мария", "last": "Менеджер", "group": "Менеджеры"},
    {"email": "head@hoztrade.local", "first": "Сергей", "last": "Руководитель", "group": "Руководители"},
]


class Command(BaseCommand):
    help = ("Создать демо-покупателей (частное лицо и компания с оптовыми ценами) и сотрудников CRM. "
            "Повторный запуск не дублирует")

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEMO_PASSWORD)

    def handle(self, *args, password, **options):
        User = get_user_model()
        for data in ACCOUNTS:
            user, created = User.objects.get_or_create(username=data["email"], defaults={
                "email": data["email"], "first_name": data["name"]})
            if created:
                user.set_password(password)
                user.save()
            Profile.objects.update_or_create(user=user, defaults={
                "phone": data["phone"], "company": data.get("company", ""), "inn": data.get("inn", ""),
                "wholesale": data.get("wholesale", Profile.Wholesale.NONE)})
            self.stdout.write(f"{'создан' if created else 'уже есть'}: {data['email']}")
        for data in STAFF:
            user, created = User.objects.get_or_create(username=data["email"], defaults={
                "email": data["email"], "first_name": data["first"], "last_name": data["last"], "is_staff": True})
            if created:
                user.set_password(password)
                user.save()
            group = Group.objects.filter(name=data["group"]).first()
            if group:
                user.groups.add(group)
            self.stdout.write(f"{'создан' if created else 'уже есть'}: {data['email']} ({data['group']})")
        self.stdout.write(self.style.SUCCESS("Демо-покупатели и сотрудники CRM готовы (пароль — в README)"))
