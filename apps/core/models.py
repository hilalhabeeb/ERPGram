"""Reusable abstract model base classes.

Every business table in later modules inherits ``TenantScopedModel`` so that
tenant isolation is enforced by construction — both by the default manager
(application layer) and by the Postgres RLS policy attached via
``apps.core.db.enable_rls`` (database layer).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.tenant import get_current_tenant_id


class TimeStampedModel(models.Model):
    """Adds created/updated timestamps and audit-user foreign keys."""

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("updated by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    """Non-guessable UUID primary key, shared by tenant-facing tables."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TenantManager(models.Manager):
    """Default manager: transparently filters to the request's active tenant.

    When no tenant is bound (anonymous request, shell without a bound tenant),
    the queryset returns nothing rather than leaking every row. Use the
    ``all_tenants`` manager for admin screens and background jobs.
    """

    def get_queryset(self) -> models.QuerySet:
        qs = super().get_queryset()
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class TenantScopedModel(UUIDPrimaryKeyModel, TimeStampedModel):
    """Abstract base for every tenant-owned table.

    * ``objects`` — tenant-filtered (application layer, layer 1).
    * ``all_tenants`` — unfiltered escape hatch for admin/jobs.

    Pair with ``apps.core.db.enable_rls`` in a migration to add the matching
    database-layer policy (layer 2).
    """

    tenant = models.ForeignKey(
        "tenancy.Tenant",
        verbose_name=_("tenant"),
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
    )

    objects = TenantManager()
    all_tenants = models.Manager()

    class Meta:
        abstract = True

    # NOTE: concrete subclasses that define their own Meta must set
    #   base_manager_name = "all_tenants"
    # so internal/related-object queries (cascade deletes, reverse relations)
    # use the unfiltered manager. Abstract Meta options do not propagate to a
    # child that declares its own Meta. The database RLS layer still constrains
    # whatever those queries touch.
