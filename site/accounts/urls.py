from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.SiteLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="catalog:home"), name="logout"),
    path("profile/", views.profile_edit, name="profile"),
    path("wholesale/", views.wholesale_request, name="wholesale"),
    path("orders/<uuid:token>/repeat/", views.repeat_order, name="repeat"),
    path("password/", auth_views.PasswordChangeView.as_view(
        template_name="accounts/password_change.html", success_url=reverse_lazy("accounts:password_changed")),
        name="password_change"),
    path("password/done/", auth_views.PasswordChangeDoneView.as_view(
        template_name="accounts/password_changed.html"), name="password_changed"),
    path("reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset.html", email_template_name="accounts/password_reset_email.txt",
        subject_template_name="accounts/password_reset_subject.txt",
        success_url=reverse_lazy("accounts:password_reset_sent")), name="password_reset"),
    path("reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_sent.html"), name="password_reset_sent"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html", success_url=reverse_lazy("accounts:login")),
        name="password_reset_confirm"),
]
