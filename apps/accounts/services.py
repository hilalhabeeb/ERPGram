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
from django.utils.text import slugify

from apps.accounts.models import LoginAttempt, Membership, Role
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


# --- roles -------------------------------------------------------------------


def roles_for(tenant: Tenant):
    """Every role defined in a tenant, system roles first."""
    return Role.objects.filter(tenant=tenant).order_by("-is_system", "name")


def default_member_role(tenant: Tenant) -> Role | None:
    """The role new invitees get unless one is chosen."""
    return Role.objects.filter(tenant=tenant, slug="member").first()


@transaction.atomic
def ensure_system_roles(tenant: Tenant) -> dict[str, Role]:
    """Create the built-in roles for a tenant if they are missing.

    Mirrors the 0004 data migration so newly created tenants (seed, back office)
    are never left without roles to assign.
    """
    from apps.core.permissions import ALL_CODENAMES

    specs = [
        ("owner", "Owner", sorted(ALL_CODENAMES)),
        ("member", "Member", []),
    ]
    roles: dict[str, Role] = {}
    for slug, name, permissions in specs:
        roles[slug], _created = Role.objects.get_or_create(
            tenant=tenant,
            slug=slug,
            defaults={"name": name, "permissions": permissions, "is_system": True},
        )
    return roles


@transaction.atomic
def create_role(*, tenant: Tenant, name: str, permissions: list[str]) -> Role:
    from apps.core.permissions import clean_codenames

    return Role.objects.create(
        tenant=tenant,
        name=name.strip(),
        slug=_unique_role_slug(tenant, name),
        permissions=clean_codenames(permissions),
        is_system=False,
    )


@transaction.atomic
def update_role(role: Role, *, name: str, permissions: list[str]) -> Role:
    """Rename a role and set its permissions.

    System roles keep their name (the UI depends on "Owner"/"Member" meaning
    what they say) but their permissions may still be tuned — except the owner
    role, which the caller must not weaken.
    """
    from apps.core.permissions import clean_codenames

    if not role.is_system:
        role.name = name.strip()
    role.permissions = clean_codenames(permissions)
    role.save(update_fields=["name", "permissions", "updated_at"])
    return role


def _unique_role_slug(tenant: Tenant, name: str) -> str:
    base = slugify(name)[:40] or "role"
    slug = base
    suffix = 2
    while Role.objects.filter(tenant=tenant, slug=slug).exists():
        slug = f"{base}-{suffix}"[:50]
        suffix += 1
    return slug


# --- invitations ------------------------------------------------------------


@transaction.atomic
def invite_member(
    *,
    tenant: Tenant,
    email: str,
    full_name: str,
    invited_by,
    role: Role | None = None,
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

    # Invitations never grant ownership: is_owner is the anti-lockout flag and is
    # only ever set by seeding or by an existing owner promoting someone.
    #
    # NOTE: Membership is a plain model, not TimeStampedModel — it has no
    # created_by/updated_by columns. Passing those raised FieldError and broke
    # every invitation until a test finally exercised this path; `invited_by`
    # is the field that actually exists.
    membership, _ = Membership.objects.get_or_create(
        user=user,
        tenant=tenant,
        defaults={"role": role, "invited_by": invited_by},
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
