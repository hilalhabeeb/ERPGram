"""Domain gating and public sign-up.

The domain axis answers "does this feature exist for this customer?", which is
separate from permissions ("may this user use it?"). These tests pin both the
gating and the fact that a manpower permission cannot leak into another domain.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Membership, Role
from apps.accounts.permissions import permissions_for
from apps.accounts.services import ensure_system_roles
from apps.core.domains import GENERAL, MANPOWER
from apps.core.permissions import (
    MANAGE_STRUCTURE,
    MANAGE_WORKERS,
    clean_codenames,
    codenames_for_domain,
)
from apps.manpower.models import Occupation, Worker
from apps.tenancy.models import Tenant
from apps.ui.navigation import nav_for
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _sign_in(client, tenant, *, is_owner=True, role=None):
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=is_owner, is_default=True, role=role)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


# --- gating ------------------------------------------------------------------


def test_manpower_pages_are_absent_for_another_domain(client):
    tenant = TenantFactory(domain=GENERAL)
    ensure_system_roles(tenant)
    _sign_in(client, tenant)

    # 404, not 403: the module does not exist for this tenant, so confirming the
    # URL is a real endpoint would be misleading.
    assert client.get(reverse("manpower:worker_list")).status_code == 404
    assert client.get(reverse("manpower:sponsor_list")).status_code == 404
    assert client.get(reverse("manpower:setup")).status_code == 404


def test_manpower_pages_are_present_for_a_manpower_tenant(client):
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    _sign_in(client, tenant)

    assert client.get(reverse("manpower:worker_list")).status_code == 200
    assert client.get(reverse("manpower:sponsor_list")).status_code == 200


def test_rail_hides_manpower_entries_outside_the_domain():
    everything = codenames_for_domain(MANPOWER)

    manpower_keys = {item.key for item in nav_for(everything, MANPOWER)}
    general_keys = {item.key for item in nav_for(everything, GENERAL)}

    assert {"workers", "sponsors"} <= manpower_keys
    assert not ({"workers", "sponsors", "manpower_setup"} & general_keys)
    # the shared core is present in both
    assert {"dashboard", "companies", "profile"} <= general_keys


def test_owner_of_another_domain_does_not_hold_manpower_permissions():
    tenant = TenantFactory(domain=GENERAL)
    roles = ensure_system_roles(tenant)
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=True, role=roles["owner"])

    held = permissions_for(user, tenant)
    assert MANAGE_STRUCTURE in held
    assert MANAGE_WORKERS not in held


def test_a_role_cannot_grant_a_permission_from_another_domain():
    """Even if the codename is written straight into the stored JSON."""
    tenant = TenantFactory(domain=GENERAL)
    role = Role.objects.create(
        tenant=tenant, name="Sneaky", slug="sneaky", permissions=[MANAGE_WORKERS]
    )
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=False, role=role)

    assert permissions_for(user, tenant) == frozenset()


def test_clean_codenames_drops_other_domain_permissions():
    assert clean_codenames([MANAGE_STRUCTURE, MANAGE_WORKERS], GENERAL) == [MANAGE_STRUCTURE]
    assert MANAGE_WORKERS in clean_codenames([MANAGE_WORKERS], MANPOWER)


# --- sign-up -----------------------------------------------------------------


def test_signup_creates_tenant_owner_roles_and_domain_defaults(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "organisation": "Pearl Manpower",
            "domain": MANPOWER,
            "full_name": "Aisha Owner",
            "email": "aisha@pearl.test",
            "password": "a-strong-pass-42",
        },
    )
    assert response.status_code == 302

    tenant = Tenant.objects.get(name="Pearl Manpower")
    assert tenant.domain == MANPOWER

    membership = Membership.objects.get(tenant=tenant)
    assert membership.is_owner is True
    assert membership.user.email == "aisha@pearl.test"

    # roles exist so the owner has something to assign from day one
    assert tenant.roles.filter(slug="owner").exists()
    # and the manpower module is usable immediately rather than showing empty
    # dropdowns — these are RLS tables, so this also proves the insert path.
    assert Occupation.all_tenants.filter(tenant=tenant).count() > 0


def test_signup_rejects_a_duplicate_email(client):
    existing = UserFactory(email="taken@example.test")
    response = client.post(
        reverse("accounts:signup"),
        {
            "organisation": "Second Org",
            "domain": MANPOWER,
            "full_name": "Someone Else",
            "email": existing.email,
            "password": "another-strong-1",
        },
    )
    assert response.status_code == 200
    assert not Tenant.objects.filter(name="Second Org").exists()


def test_signup_slugs_do_not_collide(client):
    for index in range(2):
        client.post(
            reverse("accounts:signup"),
            {
                "organisation": "Gulf Agency",
                "domain": MANPOWER,
                "full_name": f"Owner {index}",
                "email": f"owner{index}@gulf.test",
                "password": "a-strong-pass-42",
            },
        )
        client.logout()

    slugs = list(Tenant.objects.filter(name="Gulf Agency").values_list("slug", flat=True))
    assert len(slugs) == 2
    assert len(set(slugs)) == 2


def test_signup_is_reachable_without_logging_in(client):
    assert client.get(reverse("accounts:signup")).status_code == 200


def test_a_general_tenant_gets_no_manpower_defaults(client):
    client.post(
        reverse("accounts:signup"),
        {
            "organisation": "Plain Co",
            "domain": GENERAL,
            "full_name": "Plain Owner",
            "email": "plain@co.test",
            "password": "a-strong-pass-42",
        },
    )
    tenant = Tenant.objects.get(name="Plain Co")
    assert Occupation.all_tenants.filter(tenant=tenant).count() == 0
    assert Worker.all_tenants.filter(tenant=tenant).count() == 0
