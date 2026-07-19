"""Accounts: custom User, Membership (user↔tenant), and the login-attempt log."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager

LOCALE_CHOICES = [("en", _("English")), ("ar", _("العربية"))]


class User(AbstractBaseUser, PermissionsMixin):
    """Email-as-username custom user. Created in the first migration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email address"))
    full_name = models.CharField(_("full name"), max_length=200)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    # FileField (not ImageField) keeps Pillow out of the dependency set while
    # still storing an uploaded avatar. See README / step-1 notes.
    avatar = models.FileField(_("avatar"), upload_to="avatars/", blank=True, null=True)
    locale = models.CharField(_("locale"), max_length=8, choices=LOCALE_CHOICES, default="en")

    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff"), default=False)

    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    last_login_at = models.DateTimeField(_("last login at"), null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            # True case-insensitive uniqueness at the database level.
            models.UniqueConstraint(Lower("email"), name="user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        return self.full_name or self.email

    @property
    def initials(self) -> str:
        source = (self.full_name or self.email).strip()
        parts = [p for p in source.split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return source[:2].upper()


class Membership(models.Model):
    """Links a user to a tenant. A user may belong to several tenants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        verbose_name=_("tenant"),
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    is_default = models.BooleanField(_("default tenant"), default=False)
    is_owner = models.BooleanField(_("owner"), default=False)
    joined_at = models.DateTimeField(_("joined at"), default=timezone.now)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="uniq_user_tenant"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.tenant_id}"


class LoginAttempt(models.Model):
    """Append-only log of login attempts; backs the DB lockout counter."""

    id = models.BigAutoField(primary_key=True)
    email = models.CharField(_("email"), max_length=254)
    ip_address = models.GenericIPAddressField(_("ip address"), null=True, blank=True)
    successful = models.BooleanField(_("successful"), default=False)
    created_at = models.DateTimeField(_("created at"), default=timezone.now)

    class Meta:
        verbose_name = _("login attempt")
        verbose_name_plural = _("login attempts")
        indexes = [models.Index(fields=["email", "created_at"])]

    def __str__(self) -> str:
        return f"{self.email} @ {self.created_at:%Y-%m-%d %H:%M} ({'ok' if self.successful else 'fail'})"

    @classmethod
    def recent_failures(cls, email: str, window_minutes: int) -> int:
        since = timezone.now() - timedelta(minutes=window_minutes)
        return cls.objects.filter(
            email__iexact=email, successful=False, created_at__gte=since
        ).count()
