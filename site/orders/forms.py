import re

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Lead, Order

PHONE_HELP = "Например, +7 900 123-45-67"
MAX_UPLOAD_MB = 10
ALLOWED_UPLOADS = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".doc", ".docx", ".xls", ".xlsx", ".txt"}


def normalize_phone(value: str) -> str:
    """Любой российский номер -> +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValidationError("Укажите номер из 10 цифр после +7")
    return "+7" + digits


def inn_is_valid(inn: str) -> bool:
    """Проверка контрольных цифр ИНН (10 — организация, 12 — ИП/физлицо)."""
    if not inn.isdigit() or len(inn) not in (10, 12):
        return False
    digits = [int(c) for c in inn]

    def check(weights):
        return sum(w * d for w, d in zip(weights, digits)) % 11 % 10

    if len(inn) == 10:
        return check([2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
    return (check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[10]
            and check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[11])


class AntiSpamMixin(forms.Form):
    """Скрытое поле-ловушка: человек его не видит и не заполняет, бот заполняет."""

    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "tabindex": "-1", "autocomplete": "off", "class": "hp"}))
    consent = forms.BooleanField(
        label="Согласен на обработку персональных данных",
        error_messages={"required": "Без согласия мы не можем принять заявку"},
    )

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise ValidationError("spam")
        return ""


class CheckoutForm(AntiSpamMixin, forms.ModelForm):
    store = forms.ChoiceField(label="Пункт самовывоза", required=False)

    class Meta:
        model = Order
        fields = ["customer_type", "name", "phone", "email", "company", "inn",
                  "delivery", "address", "delivery_date", "comment"]
        widgets = {
            "customer_type": forms.RadioSelect,
            "delivery": forms.RadioSelect,
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "Подъезд, разгрузка, удобное время"}),
            "phone": forms.TextInput(attrs={"type": "tel", "placeholder": PHONE_HELP, "autocomplete": "tel"}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "address": forms.TextInput(attrs={"placeholder": "Город, улица, дом", "autocomplete": "street-address"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        stores = [s["address"] for s in settings.SITE_INFO["stores"]]
        self.fields["store"].choices = [(s, s) for s in stores]
        self.fields["store"].initial = stores[0]
        self.fields["phone"].help_text = ""

        # Вошедшему покупателю — контакты из профиля. Подтверждённая компания покупает только на себя:
        # реквизиты берутся из профиля, а не из формы, иначе оптовые цены можно было бы отдать кому угодно.
        self.wholesale_profile = None
        profile = getattr(user, "profile", None) if user is not None and user.is_authenticated else None
        if profile is not None:
            self.initial.setdefault("name", user.get_full_name())
            self.initial.setdefault("email", user.email)
            self.initial.setdefault("phone", profile.phone)
            if profile.is_wholesale:
                self.wholesale_profile = profile
                for name in ("customer_type", "company", "inn"):
                    del self.fields[name]
            elif profile.inn:
                self.initial.setdefault("customer_type", Order.CustomerType.COMPANY)
                self.initial.setdefault("company", profile.company)
                self.initial.setdefault("inn", profile.inn)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean(self):
        data = super().clean()
        if self.wholesale_profile is not None:
            pass  # реквизиты компании подставляет оформление заказа из профиля
        elif data.get("customer_type") == Order.CustomerType.COMPANY:
            if not data.get("company"):
                self.add_error("company", "Укажите организацию")
            inn = (data.get("inn") or "").strip()
            if not inn_is_valid(inn):
                self.add_error("inn", "Проверьте ИНН: 10 или 12 цифр, контрольная сумма не сходится")
            data["inn"] = inn
        else:
            data["company"] = ""
            data["inn"] = ""

        if data.get("delivery") == Order.Delivery.TRUCK:
            if not data.get("address"):
                self.add_error("address", "Укажите адрес доставки")
        else:
            data["address"] = ""
        return data


class LeadForm(AntiSpamMixin, forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["name", "phone", "email", "text", "attachment"]
        widgets = {
            "phone": forms.TextInput(attrs={"type": "tel", "placeholder": PHONE_HELP, "autocomplete": "tel"}),
            "text": forms.Textarea(attrs={"rows": 4, "placeholder": "Например: цемент М500 — 20 мешков, газоблок D500 — 3 поддона"}),
        }

    def __init__(self, *args, kind=Lead.Kind.LIST, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        if kind == Lead.Kind.CALLBACK:
            for name in ("email", "text", "attachment"):
                del self.fields[name]

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_attachment(self):
        f = self.cleaned_data.get("attachment")
        if not f:
            return f
        ext = "." + f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in ALLOWED_UPLOADS:
            raise ValidationError("Можно приложить PDF, фото, Word, Excel или текст")
        if f.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise ValidationError(f"Файл больше {MAX_UPLOAD_MB} МБ")
        return f

    def clean(self):
        data = super().clean()
        if self.kind == Lead.Kind.LIST and not data.get("text") and not data.get("attachment"):
            raise ValidationError("Напишите, что нужно, или приложите файл со сметой")
        return data
