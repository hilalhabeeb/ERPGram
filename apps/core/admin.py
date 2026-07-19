"""Admin base classes.

The Django admin is our internal back office for seeding tenants and users. It
must see across *all* tenants, so tenant-scoped model admins query through the
``all_tenants`` manager rather than the tenant-filtered default.
"""

from __future__ import annotations

from django.contrib import admin
from django.db import models


class AllTenantsAdmin(admin.ModelAdmin):
    """ModelAdmin for ``TenantScopedModel`` subclasses — sees every tenant."""

    def get_queryset(self, request) -> models.QuerySet:
        return self.model.all_tenants.get_queryset()
