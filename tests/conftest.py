"""Shared test fixtures."""

from __future__ import annotations

import pytest
from django.db import connection

from apps.core.tenant import reset_current_tenant_id, set_current_tenant_id
from apps.tenancy.models import Company
from tests.factories import TenantFactory


def set_db_tenant(tenant_id) -> None:
    """Set the Postgres ``app.tenant_id`` GUC for the current transaction."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])


@pytest.fixture(autouse=True)
def _clear_tenant_contextvar():
    """Ensure the tenant contextvar never leaks between tests (same thread)."""
    yield
    set_current_tenant_id(None)


@pytest.fixture
def bind_tenant():
    """Bind both isolation layers to a tenant id for the duration of a `with`."""
    from contextlib import contextmanager

    @contextmanager
    def _bind(tenant_id):
        token = set_current_tenant_id(str(tenant_id))
        set_db_tenant(tenant_id)
        try:
            yield
        finally:
            reset_current_tenant_id(token)

    return _bind


@pytest.fixture
def two_tenants(db, bind_tenant):
    """Two tenants, each owning one company row (inserted under its own GUC)."""
    tenant_a = TenantFactory(name="Alpha", slug="alpha")
    tenant_b = TenantFactory(name="Beta", slug="beta")

    with bind_tenant(tenant_a.id):
        company_a = Company.all_tenants.create(tenant=tenant_a, name="Alpha Co")
    with bind_tenant(tenant_b.id):
        company_b = Company.all_tenants.create(tenant=tenant_b, name="Beta Co")

    return {
        "a": tenant_a,
        "b": tenant_b,
        "company_a": company_a,
        "company_b": company_b,
    }
