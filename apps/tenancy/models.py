"""Tenancy: the Tenant and its organisational hierarchy.

``Tenant`` is the isolation boundary itself, so it is *not* tenant-scoped.
``Company``, ``Branch`` and ``Department`` inherit ``TenantScopedModel`` — each
carries its own ``tenant_id`` (denormalised down the tree) so that a single RLS
policy protects every level uniformly.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.domains import GENERAL, domain_choices
from apps.core.models import TenantScopedModel, TimeStampedModel


class Tenant(TimeStampedModel):
    """A customer organisation — the top-level isolation boundary."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    is_active = models.BooleanField(_("active"), default=True)
    timezone = models.CharField(_("timezone"), max_length=64, default="Asia/Bahrain")
    default_locale = models.CharField(_("default locale"), max_length=8, default="en")
    # Printed on invoices. Gulf currencies are quoted to three decimals.
    currency = models.CharField(_("currency"), max_length=8, default="BHD")
    # Seller identity on a tax invoice. GCC VAT rules require the supplier's VAT
    # registration number on every tax invoice, so an invoice without it is not
    # a valid document — these feed the printed letterhead.
    legal_name = models.CharField(_("legal name"), max_length=200, blank=True)
    vat_number = models.CharField(_("VAT registration no."), max_length=40, blank=True)
    cr_number = models.CharField(_("CR number"), max_length=60, blank=True)
    address = models.TextField(_("address"), blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"), blank=True)
    # Default VAT rate applied to new taxable invoice lines. Bahrain 10, Saudi
    # 15, UAE 5 — editable per line, but this is what a new line starts from.
    default_tax_rate = models.DecimalField(
        _("default tax rate %"), max_digits=5, decimal_places=2, default=Decimal("10.00")
    )
    # Chosen at sign-up; decides which industry modules exist for this tenant.
    # See apps.core.domains — choices are resolved lazily so adding a domain
    # does not require a migration.
    domain = models.CharField(
        _("industry"),
        max_length=32,
        default=GENERAL,
        choices=domain_choices,
    )

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
