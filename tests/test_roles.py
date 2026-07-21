"""Roles and permissions: enforcement, scoping, and the anti-lockout guarantee."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Membership, Role
from apps.accounts.permissions import permissions_for
from apps.accounts.services import create_role, ensure_system_roles, update_role
from apps.core.permissions import (
    ALL_CODENAMES,
    MANAGE_MEMBERS,
    MANAGE_ORGANIZATION,
    MANAGE_ROLES,
    MANAGE_STRUCTURE,
    clean_codenames,
    codenames_for_domain,
)
from apps.core.tenant import activate_tenant
from apps.tenancy import services as tenancy_services
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _tenant_with_roles():
    tenant = TenantFactory()
    roles = ensure_system_roles(tenant)
    return tenant, roles


def _sign_in(client, tenant, *, role=None, is_owner=False):
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=is_owner, is_default=True, role=role)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


# --- the core rules ----------------------------------------------------------


def test_owner_holds_every_permission_regardless_of_role():
    """The anti-lockout guarantee: ownership cannot be revoked by editing roles."""
    tenant, roles = _tenant_with_roles()
    user = UserFactory()
    # Deliberately give the owner the empty Member role.
    MembershipFactory(user=user, tenant=tenant, is_owner=True, role=roles["member"])

    assert permissions_for(user, tenant) == codenames_for_domain(tenant.domain)


def test_membership_without_a_role_holds_nothing():
    tenant, _roles = _tenant_with_roles()
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=False, role=None)

    assert permissions_for(user, tenant) == frozenset()


def test_role_permissions_are_granted():
    tenant, _roles = _tenant_with_roles()
    role = create_role(tenant=tenant, name="Structure editor", permissions=[MANAGE_STRUCTURE])
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=False, role=role)

    assert permissions_for(user, tenant) == frozenset({MANAGE_STRUCTURE})


def test_unknown_codenames_in_stored_json_are_ignored():
    """Roles are JSON, so a stale value must not grant anything."""
    tenant, _roles = _tenant_with_roles()
    role = create_role(tenant=tenant, name="Odd", permissions=[MANAGE_STRUCTURE])
    Role.objects.filter(pk=role.pk).update(
        permissions=[MANAGE_STRUCTURE, "tenancy.delete_everything"]
    )
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=False, role=role)

    assert permissions_for(user, tenant) == frozenset({MANAGE_STRUCTURE})


def test_a_user_has_no_permissions_in_a_tenant_they_do_not_belong_to():
    tenant_a, roles_a = _tenant_with_roles()
    tenant_b, _roles_b = _tenant_with_roles()
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant_a, is_owner=True, role=roles_a["owner"])

    assert permissions_for(user, tenant_b) == frozenset()


def test_clean_codenames_drops_unknown_and_keeps_catalogue_order():
    assert clean_codenames([MANAGE_MEMBERS, "nope", MANAGE_STRUCTURE]) == [
        MANAGE_STRUCTURE,
        MANAGE_MEMBERS,
    ]


# --- enforcement through the views -------------------------------------------


def test_structure_permission_gates_company_creation(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["member"])

    assert client.post(reverse("tenancy:company_create"), {"name": "Nope Ltd"}).status_code == 403

    with activate_tenant(tenant.id):
        assert not tenancy_services.companies_for(tenant).filter(name="Nope Ltd").exists()


def test_a_non_owner_with_the_permission_can_create_a_company(client):
    """The whole point: access no longer requires ownership."""
    tenant, _roles = _tenant_with_roles()
    editor = create_role(tenant=tenant, name="Structure editor", permissions=[MANAGE_STRUCTURE])
    _sign_in(client, tenant, role=editor)

    assert client.post(reverse("tenancy:company_create"), {"name": "Acme Co"}).status_code == 302

    with activate_tenant(tenant.id):
        assert tenancy_services.companies_for(tenant).filter(name="Acme Co").exists()


def test_organization_settings_require_their_own_permission(client):
    tenant, _roles = _tenant_with_roles()
    structure_only = create_role(
        tenant=tenant, name="Structure editor", permissions=[MANAGE_STRUCTURE]
    )
    _sign_in(client, tenant, role=structure_only)

    # Holding one permission must not imply another.
    assert client.get(reverse("ui:settings_organization")).status_code == 403


def test_roles_page_requires_manage_roles(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["member"])
    assert client.get(reverse("ui:settings_roles")).status_code == 403


def test_owner_can_open_the_roles_page(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["owner"], is_owner=True)
    assert client.get(reverse("ui:settings_roles")).status_code == 200


def test_rail_only_lists_reachable_entries(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["member"])

    resp = client.get(reverse("ui:settings_profile"))
    keys = {item.key for item in resp.context["nav_items"]}

    assert "organization" not in keys
    assert {"dashboard", "companies", "profile", "users"} <= keys


# --- role management ---------------------------------------------------------


def test_the_owner_role_cannot_be_weakened(client):
    """Owners have implicit full access; a weakened Owner role would be a lie."""
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["owner"], is_owner=True)

    client.post(
        reverse("ui:settings_roles"),
        {"role_id": str(roles["owner"].pk), "name": "Owner", "permissions": []},
    )

    roles["owner"].refresh_from_db()
    assert set(roles["owner"].permissions) == set(ALL_CODENAMES)


def test_creating_a_role_stores_only_known_permissions(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["owner"], is_owner=True)

    client.post(
        reverse("ui:settings_roles"),
        {"name": "Auditor", "permissions": [MANAGE_ORGANIZATION, "made.up"]},
    )

    role = Role.objects.get(tenant=tenant, name="Auditor")
    assert role.permissions == [MANAGE_ORGANIZATION]
    assert role.is_system is False


def test_system_roles_cannot_be_renamed():
    tenant, roles = _tenant_with_roles()
    update_role(roles["member"], name="Hacked", permissions=[MANAGE_MEMBERS])

    roles["member"].refresh_from_db()
    assert roles["member"].name == "Member"
    assert roles["member"].permissions == [MANAGE_MEMBERS]


def test_role_slugs_are_unique_per_tenant():
    tenant, _roles = _tenant_with_roles()
    first = create_role(tenant=tenant, name="Auditor", permissions=[])
    second = create_role(tenant=tenant, name="Auditor", permissions=[])

    assert first.slug != second.slug


def test_changing_a_role_changes_access_immediately(client):
    tenant, _roles = _tenant_with_roles()
    role = create_role(tenant=tenant, name="Helper", permissions=[])
    _sign_in(client, tenant, role=role)

    assert client.post(reverse("tenancy:company_create"), {"name": "A"}).status_code == 403

    update_role(role, name="Helper", permissions=[MANAGE_STRUCTURE])

    assert client.post(reverse("tenancy:company_create"), {"name": "A"}).status_code == 302


def test_member_role_assignment_is_scoped_to_the_tenant(client):
    """A role from another tenant must not be assignable."""
    tenant_a, roles_a = _tenant_with_roles()
    tenant_b, _roles_b = _tenant_with_roles()
    foreign_role = create_role(tenant=tenant_b, name="Foreign", permissions=[MANAGE_ROLES])

    _sign_in(client, tenant_a, role=roles_a["owner"], is_owner=True)
    target = UserFactory()
    membership = MembershipFactory(user=target, tenant=tenant_a, is_owner=False, role=None)

    client.post(
        reverse("ui:member_role_update", args=[membership.pk]), {"role": str(foreign_role.pk)}
    )

    membership.refresh_from_db()
    assert membership.role is None
    assert permissions_for(target, tenant_a) == frozenset()


def test_an_owners_role_cannot_be_changed_away(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["owner"], is_owner=True)

    other_owner = UserFactory()
    membership = MembershipFactory(
        user=other_owner, tenant=tenant, is_owner=True, role=roles["owner"]
    )

    client.post(reverse("ui:member_role_update", args=[membership.pk]), {"role": ""})

    membership.refresh_from_db()
    assert membership.role_id == roles["owner"].pk
    assert permissions_for(other_owner, tenant) == codenames_for_domain(tenant.domain)


def test_invites_never_grant_ownership(client):
    tenant, roles = _tenant_with_roles()
    _sign_in(client, tenant, role=roles["owner"], is_owner=True)

    client.post(
        reverse("ui:settings_users"),
        {"full_name": "New Person", "email": "new@example.test", "role": str(roles["owner"].pk)},
    )

    membership = Membership.objects.get(user__email="new@example.test", tenant=tenant)
    assert membership.is_owner is False
    # They do get the chosen role's permissions, just not implicit ownership.
    assert membership.role_id == roles["owner"].pk
