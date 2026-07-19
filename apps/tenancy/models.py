"""Tenancy: the Tenant and its organisational hierarchy.

``Tenant`` is the isolation boundary itself, so it is *not* tenant-scoped.
``Company``, ``Branch`` and ``Department`` inherit ``TenantScopedModel`` — each
carries its own ``tenant_id`` (denormalised down the tree) so that a single RLS
policy protects every level uniformly.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantScopedModel, TimeStampedModel


class Tenant(TimeStampedModel):
    """A customer organisation — the top-level isolation boundary."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    is_active = models.BooleanField(_("active"), default=True)
    timezone = models.CharField(_("timezone"), max_length=64, default="Asia/Bahrain")
    default_locale = models.CharField(_("default locale"), max_length=8, default="en")

    class Meta:
        verbose_name = _("tenant")
        verbose_name_plural = _("tenants")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Company(TenantScopedModel):
    """A legal company under a tenant."""

    name = models.CharField(_("name"), max_length=200)
    legal_name = models.CharField(_("legal name"), max_length=200, blank=True)
    registration_no = models.CharField(_("registration no."), max_length=100, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("company")
        verbose_name_plural = _("companies")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Branch(TenantScopedModel):
    """A branch of a company."""

    company = models.ForeignKey(
        Company, verbose_name=_("company"), on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(_("code"), max_length=40, blank=True)
    address = models.TextField(_("address"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("branch")
        verbose_name_plural = _("branches")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Department(TenantScopedModel):
    """A department within a branch; may nest via ``parent``."""

    branch = models.ForeignKey(
        Branch, verbose_name=_("branch"), on_delete=models.CASCADE, related_name="departments"
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("parent department"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(_("code"), max_length=40, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name
