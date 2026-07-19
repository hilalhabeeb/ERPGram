"""Tenancy business logic. Views orchestrate; these functions decide."""

from __future__ import annotations

from apps.tenancy.models import Tenant


def update_organization(
    tenant: Tenant,
    *,
    name: str,
    timezone: str,
    default_locale: str,
) -> Tenant:
    """Update a tenant's organisation-level settings and persist."""
    tenant.name = name.strip()
    tenant.timezone = timezone
    tenant.default_locale = default_locale
    tenant.save(update_fields=["name", "timezone", "default_locale", "updated_at"])
    return tenant
