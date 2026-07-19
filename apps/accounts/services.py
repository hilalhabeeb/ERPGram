"""Accounts business logic: login rate-limiting, tenant switching, invitations.

All decisions live here so views stay thin and an API layer can be added later
without reimplementing rules.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import LoginAttempt, Membership
from apps.accounts.tokens import activation_token
from apps.tenancy.models import Tenant

User = get_user_model()


# --- login rate limiting ----------------------------------------------------


def is_locked_out(email: str) -> bool:
    """True when ``email`` has hit the failed-attempt ceiling in the window."""
    failures = LoginAttempt.recent_failures(email, settings.LOGIN_ATTEMPT_WINDOW_MINUTES)
    return failures >= settings.LOGIN_MAX_ATTEMPTS


def record_login_attempt(email: str, ip_address: str | None, *, successful: bool) -> None:
    LoginAttempt.objects.create(email=email, ip_address=ip_address, successful=successful)


def client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# --- tenant selection / switching -------------------------------------------


def memberships_for(user) -> list[Membership]:
    return list(
        Membership.objects.filter(user=user, tenant__is_active=True)
        .select_related("tenant")
        .order_by("-is_default", "tenant__name")
    )


def set_active_tenant(request: HttpRequest, membership: Membership) -> None:
    request.session[settings.SESSION_TENANT_KEY] = str(membership.tenant_id)


def switch_tenant(request: HttpRequest, tenant_id: str) -> bool:
    """Point the session at ``tenant_id`` iff the user is a member. Returns success."""
    membership = Membership.objects.filter(
        user=request.user, tenant_id=tenant_id, tenant__is_active=True
    ).first()
    if membership is None:
        return False
    set_active_tenant(request, membership)
    return True


# --- invitations ------------------------------------------------------------


@transaction.atomic
def invite_member(
    *,
    tenant: Tenant,
    email: str,
    full_name: str,
    invited_by,
    is_owner: bool = False,
) -> tuple[Membership, bool]:
    """Create (or reuse) a user and attach a membership to ``tenant``.

    New users are created inactive with an unusable password; they set their
    password via the activation link. Returns ``(membership, created_user)``.
    """
    email = User.objects.normalize_email(email)
    user = User.objects.filter(email__iexact=email).first()
    created_user = False
    if user is None:
        user = User(email=email, full_name=full_name, is_active=False)
        user.set_unusable_password()
        user.save()
        created_user = True

    membership, _ = Membership.objects.get_or_create(
        user=user,
        tenant=tenant,
        defaults={"is_owner": is_owner, "created_by": invited_by, "updated_by": invited_by},
    )
    return membership, created_user


def build_activation_url(request: HttpRequest, user) -> str:
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = activation_token.make_token(user)
    path = reverse("accounts:activate", kwargs={"uidb64": uidb64, "token": token})
    return request.build_absolute_uri(path)


def send_invitation_email(request: HttpRequest, user, tenant: Tenant) -> None:
    activation_url = build_activation_url(request, user)
    body = render_to_string(
        "accounts/email/invitation.txt",
        {"user": user, "tenant": tenant, "activation_url": activation_url},
    )
    send_mail(
        subject=f"You have been invited to {tenant.name}",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def activate_user(user, raw_password: str) -> None:
    user.set_password(raw_password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])
