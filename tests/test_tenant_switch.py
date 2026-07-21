"""Switching tenants updates the session and the data the user sees."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.core.tenant import activate_tenant
from apps.tenancy.models import Company
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_in_two_tenants():
    user = UserFactory(email="multi@example.test")
    tenant_a = TenantFactory(name="Alpha", slug="alpha")
    tenant_b = TenantFactory(name="Beta", slug="beta")
    MembershipFactory(user=user, tenant=tenant_a, is_default=True)
    MembershipFactory(user=user, tenant=tenant_b, is_default=False)

    # Alpha has two companies, Beta has one — so the dashboard counts differ.
    with activate_tenant(tenant_a.id):
        Company.objects.create(tenant=tenant_a, name="A1")
        Company.objects.create(tenant=tenant_a, name="A2")
    with activate_tenant(tenant_b.id):
        Company.objects.create(tenant=tenant_b, name="B1")

    return user, tenant_a, tenant_b


def _company_stat(response) -> int:
    groups = response.context["stat_groups"]
    stats = {s.key: s.value for group in groups for s in group["stats"]}
    return stats["companies"]


def test_switch_changes_session_and_visible_data(client, user_in_two_tenants):
    user, tenant_a, tenant_b = user_in_two_tenants
    client.force_login(user)

    # Select tenant A.
    client.post(reverse("accounts:select_tenant"), {"tenant_id": str(tenant_a.id)})
    resp = client.get(reverse("ui:dashboard"))
    assert client.session["tenant_id"] == str(tenant_a.id)
    assert _company_stat(resp) == 2

    # Switch to tenant B via the shell switcher.
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant_b.id)})
    resp = client.get(reverse("ui:dashboard"))
    assert client.session["tenant_id"] == str(tenant_b.id)
    assert _company_stat(resp) == 1


def test_cannot_switch_to_a_tenant_you_do_not_belong_to(client, user_in_two_tenants):
    user, _tenant_a, _tenant_b = user_in_two_tenants
    outsider_tenant = TenantFactory(name="Gamma", slug="gamma")
    client.force_login(user)

    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(outsider_tenant.id)})
    assert client.session.get("tenant_id") != str(outsider_tenant.id)
