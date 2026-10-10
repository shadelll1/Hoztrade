from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Profile

DEMO_PASSWORD = "hoztrade-demo"

# Покупатели для демонстрации: частное лицо и подтверждённая компания с оптовыми ценами.
# ИНН выдуманный, но с верной контрольной суммой.
ACCOUNTS = [
    {"email": "demo@hoztrade.local", "name": "Иван Покупатель", "phone": "+79001112233"},
    {"email": "snab@hoztrade.local", "name": "Ольга Снабженец", "phone": "+79002223344",
     "company": "ООО «СтройМонтаж» (демо)", "inn": "2128000008", "wholesale": Profile.Wholesale.APPROVED},
]


class Command(BaseCommand):
    help = "Создать демо-покупателей (частное лицо и компания с оптовыми ценами). Повторный запуск не дублирует"

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
        self.stdout.write(self.style.SUCCESS("Демо-покупатели готовы (пароль — в README)"))
