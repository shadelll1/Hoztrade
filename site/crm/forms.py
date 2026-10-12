from datetime import timedelta

from django import forms
from django.utils import timezone

from orders.forms import normalize_phone

from . import services
from .models import Activity, Client, Deal, Task


class ManagerChoice(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return user.get_full_name() or user.username


def _tomorrow_10():
    now = timezone.localtime()
    return (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)


class NoteForm(forms.Form):
    kind = forms.ChoiceField(label="Тип", choices=[(Activity.Kind.NOTE, "Заметка"), (Activity.Kind.CALL, "Звонок")],
                             initial=Activity.Kind.NOTE)
    text = forms.CharField(label="Текст", widget=forms.Textarea(attrs={"rows": 3}), max_length=4000)


class TaskForm(forms.ModelForm):
    assignee = ManagerChoice(label="Исполнитель", queryset=None)

    class Meta:
        model = Task
        fields = ["title", "due_at", "assignee"]
        widgets = {"due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = services.managers()
        if not self.is_bound:
            self.initial.setdefault("due_at", _tomorrow_10())
            if user is not None:
                self.initial.setdefault("assignee", user.pk)
        self.fields["title"].widget.attrs["placeholder"] = "Перезвонить, отправить счёт…"


class DealEditForm(forms.ModelForm):
    manager = ManagerChoice(label="Менеджер", queryset=None, required=False, empty_label="— не назначен —")

    class Meta:
        model = Deal
        fields = ["title", "amount", "manager"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = services.managers()
        self.fields["amount"].required = False

    def clean_amount(self):
        return self.cleaned_data.get("amount") or 0


class NewDealForm(forms.Form):
    """Обращение не с сайта: звонок, визит в магазин."""

    name = forms.CharField(label="Имя клиента", max_length=150)
    phone = forms.CharField(label="Телефон", max_length=20)
    email = forms.EmailField(label="Email", required=False)
    company = forms.CharField(label="Организация", max_length=250, required=False)
    source = forms.ChoiceField(label="Откуда", choices=[(Deal.Source.PHONE, "Звонок"), (Deal.Source.STORE, "Магазин"),
                                                        (Deal.Source.OTHER, "Другое")])
    title = forms.CharField(label="Что нужно", max_length=200)
    amount = forms.DecimalField(label="Сумма, ₽", required=False, min_value=0, max_digits=14, decimal_places=2)
    text = forms.CharField(label="Подробности", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "phone", "email", "company", "inn", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        return normalize_phone(phone) if phone else ""
