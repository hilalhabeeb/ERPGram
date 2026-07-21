"""`each_tenant` — the helper data migrations must use.

Written after a data migration read zero rows and reported success: RLS hides
tenant-scoped rows from migrations exactly as it does from requests, so a
migration with no tenant bound moves nothing and says nothing.
"""

from __future__ import annotations

import pytest
from django.db import connection

from apps.core.db import bind_tenant
from apps.core.domains import MANPOWER
from apps.core.tenant import activate_tenant
from apps.manpower import services
from apps.manpower.models import Occupation
from tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _FakeSchemaEditor:
    """`each_tenant` only needs the connection off the schema editor."""

    def __init__(self):
        self.connection = connection


class _FakeApps:
    """Stand-in for the migration's historical model registry."""

    def get_model(self, app_label, model_name):
        from django.apps import apps as real_apps

        return real_apps.get_model(app_label, model_name)


def _tenant_with_data(name: str):
    tenant = TenantFactory(domain=MANPOWER, name=name)
    services.ensure_tenant_defaults(tenant)
    return tenant


def test_unbound_reads_see_nothing():
    """The failure mode: no tenant bound means no rows, and no error."""
    _tenant_with_data("Alpha")

    bind_tenant(connection, None)
    assert Occupation.all_tenants.count() == 0


def test_each_tenant_binds_so_rows_are_visible():
    from apps.core.db import each_tenant

    first = _tenant_with_data("Alpha")
    second = _tenant_with_data("Beta")

    seen: dict = {}
    for tenant_id in each_tenant(_FakeApps(), _FakeSchemaEditor()):
        # Rows for *this* tenant must be readable while it is bound.
        seen[tenant_id] = Occupation.all_tenants.filter(tenant_id=tenant_id).count()

    assert seen[first.id] > 0
    assert seen[second.id] > 0


def test_each_tenant_leaves_the_connection_unbound():
    """So a later migration step does not silently inherit the last tenant."""
    from apps.core.db import each_tenant

    _tenant_with_data("Alpha")
    list(each_tenant(_FakeApps(), _FakeSchemaEditor()))

    assert Occupation.all_tenants.count() == 0


def test_each_tenant_can_write_for_the_bound_tenant():
    """Writes are the half that raises rather than silently doing nothing."""
    from apps.core.db import each_tenant

    tenant = _tenant_with_data("Alpha")

    for tenant_id in each_tenant(_FakeApps(), _FakeSchemaEditor()):
        if tenant_id == tenant.id:
            Occupation.all_tenants.create(tenant_id=tenant_id, name="Migration test")

    with activate_tenant(tenant.id):
        assert Occupation.objects.filter(name="Migration test").exists()
