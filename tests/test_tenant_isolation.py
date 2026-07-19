"""Tenant isolation is enforced at both layers: ORM manager and Postgres RLS."""

from __future__ import annotations

from django.db import connection

from apps.core.tenant import set_current_tenant_id
from apps.tenancy.models import Company
from tests.conftest import set_db_tenant


def _raw_company_ids() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM tenancy_company")
        return {str(row[0]) for row in cursor.fetchall()}


def test_orm_manager_scopes_to_current_tenant(two_tenants, bind_tenant):
    a, b = two_tenants["a"], two_tenants["b"]
    ca, cb = two_tenants["company_a"], two_tenants["company_b"]

    with bind_tenant(a.id):
        ids = set(Company.objects.values_list("id", flat=True))
        assert ca.id in ids
        assert cb.id not in ids  # tenant A cannot see tenant B via the ORM

    with bind_tenant(b.id):
        ids = set(Company.objects.values_list("id", flat=True))
        assert cb.id in ids
        assert ca.id not in ids


def test_raw_sql_rls_blocks_cross_tenant(two_tenants):
    """Layer 2: even bypassing the ORM entirely, RLS hides other tenants' rows."""
    a, b = two_tenants["a"], two_tenants["b"]
    ca, cb = two_tenants["company_a"], two_tenants["company_b"]

    set_db_tenant(a.id)
    rows = _raw_company_ids()
    assert str(ca.id) in rows
    assert str(cb.id) not in rows  # DB refuses to return tenant B's row

    set_db_tenant(b.id)
    rows = _raw_company_ids()
    assert str(cb.id) in rows
    assert str(ca.id) not in rows


def test_escape_hatch_manager_still_bounded_by_db(two_tenants):
    """`all_tenants` skips the ORM filter, but the DB layer still constrains it."""
    a = two_tenants["a"]
    cb = two_tenants["company_b"]

    # No application contextvar bound: all_tenants returns an unfiltered queryset...
    set_current_tenant_id(None)
    set_db_tenant(a.id)  # ...but the connection is pinned to tenant A.
    ids = set(Company.all_tenants.values_list("id", flat=True))
    assert cb.id not in ids  # layer 2 holds even when layer 1 is bypassed


def test_rls_returns_nothing_for_unrelated_tenant(two_tenants):
    """A GUC pointing at a tenant with no rows yields an empty result, not a leak."""
    import uuid

    set_db_tenant(uuid.uuid4())
    assert _raw_company_ids() == set()
