from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from orders.forms import PHONE_HELP, AntiSpamMixin, inn_is_valid, normalize_phone

from .models import Profile

User = get_user_model()


class RegisterForm(AntiSpamMixin, forms.Form):
    """Регистрация покупателя. Email служит логином (username = email в нижнем регистре)."""

    name = forms.CharField(label="Имя", max_length=150,
                           widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(label="Телефон", max_length=20, widget=forms.TextInput(
        attrs={"type": "tel", "placeholder": PHONE_HELP, "autocomplete": "tel"}))
    password1 = forms.CharField(label="Пароль", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="Не короче 8 символов, не только цифры")
    password2 = forms.CharField(label="Пароль ещё раз", strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise ValidationError("Этот email уже зарегистрирован. Войдите или восстановите пароль.")
        return email

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Пароли не совпадают")
        elif p1:
            user = User(username=data.get("email") or "", email=data.get("email") or "",
                        first_name=data.get("name") or "")
            try:
                password_validation.validate_password(p1, user)
            except ValidationError as e:
                self.add_error("password1", e)
        return data

    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(username=data["email"], email=data["email"], password=data["password1"],
                                        first_name=data["name"])
        Profile.objects.create(user=user, phone=data["phone"])
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email",
                                                                             "autofocus": True}))

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class ProfileForm(forms.ModelForm):
    name = forms.CharField(label="Имя", max_length=150)

    class Meta:
        model = Profile
        fields = ["phone"]
        widgets = {"phone": forms.TextInput(attrs={"type": "tel", "placeholder": PHONE_HELP})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].initial = self.instance.user.first_name
        self.order_fields(["name", "phone"])

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def save(self, commit=True):
        profile = super().save(commit)
        profile.user.first_name = self.cleaned_data["name"]
        profile.user.save(update_fields=["first_name"])
        return profile


class WholesaleRequestForm(forms.ModelForm):
    """Заявка компании на оптовые цены. Менеджер проверяет ИНН и подтверждает в админке."""

    class Meta:
        model = Profile
        fields = ["company", "inn"]
        labels = {"company": "Организация или ИП"}
        widgets = {"company": forms.TextInput(attrs={"placeholder": "ООО «СтройМонтаж»"}),
                   "inn": forms.TextInput(attrs={"inputmode": "numeric"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True

    def clean_inn(self):
        inn = self.cleaned_data["inn"].strip()
        if not inn_is_valid(inn):
            raise ValidationError("Проверьте ИНН: 10 или 12 цифр, контрольная сумма не сходится")
        return inn
