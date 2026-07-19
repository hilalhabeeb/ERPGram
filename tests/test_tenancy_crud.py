"""Organisation-structure CRUD: permissions, isolation, archiving, tree safety."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.core.tenant import activate_tenant
from apps.tenancy import services
from apps.tenancy.forms import DepartmentForm
from apps.tenancy.models import Branch, Company, Department
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _sign_in(client, *, is_owner: bool):
    """Log a user in and make their tenant the active one."""
    user = UserFactory()
    membership = MembershipFactory(user=user, is_owner=is_owner, is_default=True)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(membership.tenant_id)})
    return user, membership.tenant


def _make_structure(tenant, user):
    """A company -> branch -> department chain owned by `tenant`."""
    with activate_tenant(tenant.id):
        company = services.create_company(tenant=tenant, user=user, name="Acme Co")
        branch = services.create_branch(company=company, user=user, name="Head office")
        department = services.create_department(branch=branch, user=user, name="Finance")
    return company, branch, department


# --- permissions -------------------------------------------------------------


def test_member_can_view_but_not_create_companies(client):
    user, tenant = _sign_in(client, is_owner=False)

    assert client.get(reverse("tenancy:company_list")).status_code == 200

    resp = client.post(reverse("tenancy:company_create"), {"name": "Sneaky Ltd"})
    assert resp.status_code == 403
    with activate_tenant(tenant.id):
        assert not Company.objects.filter(name="Sneaky Ltd").exists()


def test_owner_can_create_a_company(client):
    user, tenant = _sign_in(client, is_owner=True)

    resp = client.post(reverse("tenancy:company_create"), {"name": "Acme Co"})
    assert resp.status_code == 302

    with activate_tenant(tenant.id):
        company = Company.objects.get(name="Acme Co")
    # roadmap #3: the audit columns are actually populated
    assert company.created_by_id == user.id
    assert company.updated_by_id == user.id


def test_member_does_not_see_write_actions(client):
    _sign_in(client, is_owner=False)
    body = client.get(reverse("tenancy:company_list")).content.decode()
    assert "open-modal-company" not in body


# --- tenant isolation --------------------------------------------------------


def test_company_of_another_tenant_is_not_reachable(client):
    _, tenant_a = _sign_in(client, is_owner=True)

    other_user = UserFactory()
    tenant_b = TenantFactory(name="Beta", slug="beta")
    company_b, branch_b, _dept = _make_structure(tenant_b, other_user)

    # Guessing tenant B's UUID must 404, not leak.
    assert client.get(reverse("tenancy:company_detail", args=[company_b.pk])).status_code == 404
    assert (
        client.get(reverse("tenancy:branch_detail", args=[company_b.pk, branch_b.pk])).status_code
        == 404
    )
    # ...and archiving it must not work either.
    assert client.post(reverse("tenancy:company_archive", args=[company_b.pk])).status_code == 404

    # Re-read under tenant B's own context: with no tenant bound, the RLS policy
    # itself hides the row, so this needs activate_tenant to see anything at all.
    with activate_tenant(tenant_b.id):
        assert Company.objects.get(pk=company_b.pk).is_active is True


def test_company_list_shows_only_the_active_tenants_rows(client):
    user, tenant_a = _sign_in(client, is_owner=True)
    _make_structure(tenant_a, user)

    other_user = UserFactory()
    tenant_b = TenantFactory(name="Beta", slug="beta")
    with activate_tenant(tenant_b.id):
        services.create_company(tenant=tenant_b, user=other_user, name="Beta Secret Co")

    body = client.get(reverse("tenancy:company_list")).content.decode()
    assert "Acme Co" in body
    assert "Beta Secret Co" not in body


def test_department_parent_choices_cannot_leak_another_tenant(client):
    """The FK dropdown is where another tenant's names would become visible."""
    user, tenant_a = _sign_in(client, is_owner=True)
    _company_a, branch_a, dept_a = _make_structure(tenant_a, user)

    other_user = UserFactory()
    tenant_b = TenantFactory(name="Beta", slug="beta")
    _company_b, _branch_b, dept_b = _make_structure(tenant_b, other_user)

    with activate_tenant(tenant_a.id):
        form = DepartmentForm(branch=branch_a)
        choices = list(form.fields["parent"].queryset)

    assert dept_a in choices
    assert dept_b not in choices


# --- department tree safety --------------------------------------------------


def test_department_cannot_be_its_own_parent(client):
    user, tenant = _sign_in(client, is_owner=True)
    _company, branch, department = _make_structure(tenant, user)

    with activate_tenant(tenant.id):
        form = DepartmentForm(
            {"name": department.name, "parent": str(department.pk)},
            branch=branch,
            instance=department,
        )
        assert not form.is_valid()
        assert "parent" in form.errors


def test_department_cannot_be_moved_under_its_own_child(client):
    user, tenant = _sign_in(client, is_owner=True)
    _company, branch, parent = _make_structure(tenant, user)

    with activate_tenant(tenant.id):
        child = services.create_department(branch=branch, user=user, name="Payables", parent=parent)
        # Moving `parent` under `child` would create a cycle.
        form = DepartmentForm(
            {"name": parent.name, "parent": str(child.pk)}, branch=branch, instance=parent
        )
        assert not form.is_valid()
        assert "parent" in form.errors


def test_department_tree_returns_depth_for_nesting(client):
    user, tenant = _sign_in(client, is_owner=True)
    _company, branch, root = _make_structure(tenant, user)

    with activate_tenant(tenant.id):
        child = services.create_department(branch=branch, user=user, name="Payables", parent=root)
        grandchild = services.create_department(
            branch=branch, user=user, name="Invoices", parent=child
        )
        rows = services.department_tree(branch)

    assert [(r["department"].id, r["depth"]) for r in rows] == [
        (root.id, 0),
        (child.id, 1),
        (grandchild.id, 2),
    ]


# --- archiving ---------------------------------------------------------------


def test_archiving_a_company_cascades_to_branches_and_departments(client):
    user, tenant = _sign_in(client, is_owner=True)
    company, branch, department = _make_structure(tenant, user)

    resp = client.post(reverse("tenancy:company_archive", args=[company.pk]))
    assert resp.status_code == 302

    with activate_tenant(tenant.id):
        assert Company.objects.get(pk=company.pk).is_active is False
        assert Branch.objects.get(pk=branch.pk).is_active is False
        assert Department.objects.get(pk=department.pk).is_active is False


def test_archived_rows_are_hidden_until_explicitly_requested(client):
    user, tenant = _sign_in(client, is_owner=True)
    company, _branch, _dept = _make_structure(tenant, user)
    client.post(reverse("tenancy:company_archive", args=[company.pk]))

    # Assert on the row's link, not the name: the success toast also contains
    # the company name, which would make a name check pass for the wrong reason.
    row_link = reverse("tenancy:company_detail", args=[company.pk])

    assert row_link not in client.get(reverse("tenancy:company_list")).content.decode()
    archived = client.get(reverse("tenancy:company_list"), {"archived": "1"})
    assert row_link in archived.content.decode()


def test_archiving_never_deletes_rows(client):
    """Archive is the only removal path — the row must survive."""
    user, tenant = _sign_in(client, is_owner=True)
    company, _branch, _dept = _make_structure(tenant, user)

    client.post(reverse("tenancy:company_archive", args=[company.pk]))

    with activate_tenant(tenant.id):
        assert Company.all_tenants.filter(pk=company.pk).exists()


def test_restoring_a_company_does_not_resurrect_its_children(client):
    user, tenant = _sign_in(client, is_owner=True)
    company, branch, _dept = _make_structure(tenant, user)

    client.post(reverse("tenancy:company_archive", args=[company.pk]))
    client.post(reverse("tenancy:company_archive", args=[company.pk]))  # toggles back to restore

    with activate_tenant(tenant.id):
        assert Company.objects.get(pk=company.pk).is_active is True
        assert Branch.objects.get(pk=branch.pk).is_active is False


def test_member_cannot_archive(client):
    owner = UserFactory()
    tenant = TenantFactory(name="Alpha", slug="alpha")
    MembershipFactory(user=owner, tenant=tenant, is_owner=True)
    company, _branch, _dept = _make_structure(tenant, owner)

    member = UserFactory()
    MembershipFactory(user=member, tenant=tenant, is_owner=False, is_default=True)
    client.force_login(member)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})

    assert client.post(reverse("tenancy:company_archive", args=[company.pk])).status_code == 403
    with activate_tenant(tenant.id):
        assert Company.objects.get(pk=company.pk).is_active is True
