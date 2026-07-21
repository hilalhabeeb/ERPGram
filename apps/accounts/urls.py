"""Auth URLs (namespace ``accounts``). Kept out of the i18n URL prefix."""

from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from apps.accounts import signup, views
from apps.accounts.forms import StyledPasswordResetForm, StyledSetPasswordForm

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", signup.signup, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("select-tenant/", views.select_tenant_view, name="select_tenant"),
    path("switch-tenant/", views.switch_tenant_view, name="switch_tenant"),
    path("activate/<uidb64>/<token>/", views.activate_view, name="activate"),
    # --- password reset (Django's built-in views + our templates) ---
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
            form_class=StyledPasswordResetForm,
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            form_class=StyledSetPasswordForm,
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
