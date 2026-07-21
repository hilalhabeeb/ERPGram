"""Manpower masters: isolation, the M2M leak guard, references and filtering."""

from __future__ import annotations

import pytest
from django.db import connection
from django.urls import reverse

from apps.accounts.services import ensure_system_roles
from apps.core.domains import MANPOWER
from apps.core.tenant import activate_tenant
from apps.manpower import services
from apps.manpower.forms import WorkerForm
from apps.manpower.models import Country, Occupation, Skill, Worker
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def manpower_tenant():
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    services.ensure_reference_data()
    services.ensure_tenant_defaults(tenant)
    return tenant


def _sign_in(client, tenant):
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=True, is_default=True)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


def _worker(tenant, user, **overrides):
    with activate_tenant(tenant.id):
        occupation = Occupation.objects.filter(tenant=tenant).first()
        fields = {
            "full_name": "Test Worker",
            "nationality": Country.objects.get(iso_code="ID"),
            "occupation": occupation,
            "experience_years": 3,
        }
        fields.update(overrides)
        return services.create_worker(tenant=tenant, user=user, **fields)


# --- defaults ----------------------------------------------------------------


def test_tenant_defaults_are_created_and_idempotent(manpower_tenant):
    first = Occupation.all_tenants.filter(tenant=manpower_tenant).count()
    services.ensure_tenant_defaults(manpower_tenant)
    assert Occupation.all_tenants.filter(tenant=manpower_tenant).count() == first
    assert first >= 5


# --- references --------------------------------------------------------------


def test_worker_references_increment_per_tenant(manpower_tenant):
    user = UserFactory()
    first = _worker(manpower_tenant, user)
    second = _worker(manpower_tenant, user, full_name="Second Worker")

    assert first.reference == "W-0001"
    assert second.reference == "W-0002"


def test_references_restart_in_a_different_tenant(manpower_tenant):
    user = UserFactory()
    _worker(manpower_tenant, user)

    other = TenantFactory(domain=MANPOWER)
    services.ensure_tenant_defaults(other)
    other_worker = _worker(other, user)

    assert other_worker.reference == "W-0001"


# --- isolation ---------------------------------------------------------------


def test_workers_of_another_tenant_are_not_listed(client, manpower_tenant):
    user = _sign_in(client, manpower_tenant)
    _worker(manpower_tenant, user, full_name="Mine Worker")

    other = TenantFactory(domain=MANPOWER)
    services.ensure_tenant_defaults(other)
    _worker(other, UserFactory(), full_name="Other Worker")

    body = client.get(reverse("manpower:worker_list")).content.decode()
    assert "Mine Worker" in body
    assert "Other Worker" not in body


def test_worker_of_another_tenant_404s(client, manpower_tenant):
    _sign_in(client, manpower_tenant)

    other = TenantFactory(domain=MANPOWER)
    services.ensure_tenant_defaults(other)
    foreign = _worker(other, UserFactory())

    assert client.get(reverse("manpower:worker_detail", args=[foreign.pk])).status_code == 404


def test_worker_form_choices_are_scoped_to_the_tenant(manpower_tenant):
    other = TenantFactory(domain=MANPOWER)
    services.ensure_tenant_defaults(other)

    with activate_tenant(manpower_tenant.id):
        form = WorkerForm(tenant=manpower_tenant)
        occupation_ids = {o.pk for o in form.fields["occupation"].queryset}
        skill_ids = {s.pk for s in form.fields["skills"].queryset}

    foreign_occupations = set(
        Occupation.all_tenants.filter(tenant=other).values_list("pk", flat=True)
    )
    foreign_skills = set(Skill.all_tenants.filter(tenant=other).values_list("pk", flat=True))

    assert occupation_ids
    assert not (occupation_ids & foreign_occupations)
    assert not (skill_ids & foreign_skills)


def test_skills_from_another_tenant_cannot_be_attached(manpower_tenant):
    """The join table has no tenant column, so the service re-checks ownership."""
    user = UserFactory()
    other = TenantFactory(domain=MANPOWER)
    services.ensure_tenant_defaults(other)

    # Each read binds its own tenant: `SET LOCAL app.tenant_id` survives to the
    # end of the surrounding transaction, and in tests that is the whole test —
    # so without this the second lookup would still be scoped to `other`.
    with activate_tenant(other.id):
        foreign_skill = Skill.all_tenants.filter(tenant=other).first()
    with activate_tenant(manpower_tenant.id):
        own_skill = Skill.all_tenants.filter(tenant=manpower_tenant).first()
    assert foreign_skill is not None and own_skill is not None

    worker = _worker(manpower_tenant, user)
    with activate_tenant(manpower_tenant.id):
        services.update_worker(
            worker, user=user, skills=[foreign_skill, own_skill], full_name=worker.full_name
        )
        attached = set(worker.skills.values_list("pk", flat=True))

    assert own_skill.pk in attached
    assert foreign_skill.pk not in attached


# --- filtering ---------------------------------------------------------------


def test_worker_filters_narrow_the_list(manpower_tenant):
    user = UserFactory()
    with activate_tenant(manpower_tenant.id):
        housemaid = Occupation.objects.get(tenant=manpower_tenant, name="Housemaid")
        driver = Occupation.objects.get(tenant=manpower_tenant, name="Driver")

    _worker(manpower_tenant, user, full_name="Maid One", occupation=housemaid)
    _worker(
        manpower_tenant,
        user,
        full_name="Driver One",
        occupation=driver,
        location=Worker.Location.IN_COUNTRY,
    )

    with activate_tenant(manpower_tenant.id):
        by_occupation = services.workers_for(manpower_tenant, occupation=str(driver.pk))
        by_location = services.workers_for(manpower_tenant, location=Worker.Location.IN_COUNTRY)
        by_search = services.workers_for(manpower_tenant, search="Maid")

        assert [w.full_name for w in by_occupation] == ["Driver One"]
        assert [w.full_name for w in by_location] == ["Driver One"]
        assert [w.full_name for w in by_search] == ["Maid One"]


def test_archived_workers_are_hidden_by_default(manpower_tenant):
    user = UserFactory()
    worker = _worker(manpower_tenant, user, full_name="Gone Worker")

    with activate_tenant(manpower_tenant.id):
        services.set_worker_active(worker, user=user, is_active=False)
        visible = list(services.workers_for(manpower_tenant))
        everything = list(services.workers_for(manpower_tenant, include_archived=True))

    assert visible == []
    assert len(everything) == 1


def test_unbound_query_after_a_bound_one_returns_nothing_rather_than_erroring(
    manpower_tenant,
):
    """Regression: the RLS policy must tolerate an empty app.tenant_id.

    Once the GUC has been SET LOCAL on a connection, Postgres reports it as ''
    instead of NULL. Casting that straight to uuid raised
    "invalid input syntax for type uuid", turning an unbound query on a pooled
    connection into a 500 instead of an empty result.
    """
    _worker(manpower_tenant, UserFactory())

    # Set the GUC to '' explicitly: that is the state Postgres leaves behind on
    # a connection once SET LOCAL has been used, and it cannot be reproduced by
    # simply not binding a tenant inside a single test transaction.
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', '', true)")

    # Before the NULLIF guard this raised DataError instead of returning nothing.
    assert Worker.all_tenants.count() == 0
    assert list(Occupation.all_tenants.all()) == []


def test_worker_summary_counts_by_location_and_availability(manpower_tenant):
    user = UserFactory()
    _worker(manpower_tenant, user, location=Worker.Location.IN_COUNTRY)
    _worker(manpower_tenant, user, full_name="B", location=Worker.Location.OVERSEAS)
    _worker(
        manpower_tenant,
        user,
        full_name="C",
        availability=Worker.Availability.PLACED,
        location=Worker.Location.OVERSEAS,
    )

    with activate_tenant(manpower_tenant.id):
        summary = {row["key"]: row["value"] for row in services.worker_summary(manpower_tenant)}

    assert summary["in_country"] == 1
    assert summary["overseas"] == 2
    assert summary["placed"] == 1
    assert summary["available"] == 2
