"""Authentication and tenant-selection views. Thin — logic lives in services."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.forms import ActivateForm, LoginForm
from apps.accounts.services import (
    client_ip,
    is_locked_out,
    memberships_for,
    record_login_attempt,
    set_active_tenant,
    switch_tenant,
)
from apps.accounts.tokens import activation_token

User = get_user_model()


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("ui:dashboard")

    form = LoginForm(request.POST or None)
    next_url = request.GET.get("next") or request.POST.get("next", "")

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        ip = client_ip(request)

        if is_locked_out(email):
            messages.error(
                request, _("Too many failed attempts. Please try again in a few minutes.")
            )
        else:
            user = authenticate(request, username=email, password=password)
            record_login_attempt(email, ip, successful=user is not None)
            if user is not None:
                auth_login(request, user)
                user.last_login_at = timezone.now()
                user.save(update_fields=["last_login_at"])
                return _post_login_redirect(request, user, next_url)
            messages.error(request, _("Invalid email or password."))

    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def _post_login_redirect(request: HttpRequest, user, next_url: str) -> HttpResponse:
    memberships = memberships_for(user)
    if len(memberships) == 1:
        set_active_tenant(request, memberships[0])
        return redirect(next_url or "ui:dashboard")
    if len(memberships) > 1:
        return redirect("accounts:select_tenant")

    if user.is_staff:
        return redirect(reverse("admin:index"))
    messages.info(request, _("Your account is not linked to any organisation yet."))
    auth_logout(request)
    return redirect("accounts:login")


def logout_view(request: HttpRequest) -> HttpResponse:
    auth_logout(request)
    return redirect("accounts:login")


def select_tenant_view(request: HttpRequest) -> HttpResponse:
    memberships = memberships_for(request.user)

    if len(memberships) <= 1:
        if memberships:
            set_active_tenant(request, memberships[0])
        return redirect("ui:dashboard")

    if request.method == "POST":
        if switch_tenant(request, request.POST.get("tenant_id", "")):
            return redirect("ui:dashboard")
        messages.error(request, _("That organisation is not available."))

    return render(request, "accounts/select_tenant.html", {"memberships": memberships})


@require_POST
def switch_tenant_view(request: HttpRequest) -> HttpResponse:
    if not switch_tenant(request, request.POST.get("tenant_id", "")):
        messages.error(request, _("That organisation is not available."))
    if request.htmx:
        response = HttpResponse(status=204)
        response["HX-Redirect"] = reverse("ui:dashboard")
        return response
    return redirect("ui:dashboard")


def activate_view(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    user = _user_from_uidb64(uidb64)
    if user is None or not activation_token.check_token(user, token):
        return render(request, "accounts/activate_invalid.html", status=400)

    form = ActivateForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, _("Your account is ready. Please sign in."))
        return redirect("accounts:login")

    return render(request, "accounts/activate.html", {"form": form, "invitee": user})


def _user_from_uidb64(uidb64: str):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
