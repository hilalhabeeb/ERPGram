"""Placements: the operational record and the agreement.

Money lives on invoices now — see tests/test_invoicing.py.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db.models import ProtectedError
from django.urls import reverse

from apps.accounts.services import ensure_system_roles
from apps.core.domains import MANPOWER
from apps.core.tenant import activate_tenant
from apps.manpower import services
from apps.manpower.models import Country, Occupation, Placement, Sponsor, Worker
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def agency():
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
        fields = {
            "full_name": "Test Worker",
            "nationality": Country.objects.get(iso_code="ID"),
            "occupation": Occupation.objects.filter(tenant=tenant).first(),
            "experience_years": 4,
        }
        fields.update(overrides)
        return services.create_worker(tenant=tenant, user=user, **fields)


def _sponsor(tenant, user):
    with activate_tenant(tenant.id):
        return services.create_sponsor(
            tenant=tenant, user=user, name="Test Sponsor", national_id="800112233"
        )


def _placement(tenant, user, worker=None, sponsor=None):
    with activate_tenant(tenant.id):
        return services.create_placement(
            tenant=tenant,
            user=user,
            sponsor=sponsor or _sponsor(tenant, user),
            worker=worker or _worker(tenant, user),
        )


# --- route ------------------------------------------------------------------


def test_route_follows_where_the_worker_is(agency):
    user = UserFactory()
    overseas = _worker(agency, user, location=Worker.Location.OVERSEAS)
    local = _worker(agency, user, full_name="Local", location=Worker.Location.IN_COUNTRY)

    assert _placement(agency, user, worker=overseas).route == Placement.Route.OVERSEAS
    assert _placement(agency, user, worker=local).route == Placement.Route.TRANSFER


def test_transfer_pipeline_skips_travel_and_medical(agency):
    user = UserFactory()
    local = _worker(agency, user, location=Worker.Location.IN_COUNTRY)
    placement = _placement(agency, user, worker=local)

    labels = [str(step["label"]) for step in placement.milestones]
    assert "Travel" not in labels
    assert "Medical" not in labels
    assert "Visa transferred" in labels


def test_worker_and_occupation_are_snapshotted(agency):
    """The signed agreement must keep saying what was agreed."""
    user = UserFactory()
    worker = _worker(agency, user, full_name="Original Name")
    placement = _placement(agency, user, worker=worker)

    with activate_tenant(agency.id):
        services.update_worker(worker, user=user, full_name="Corrected Name")
        placement.refresh_from_db()

    assert placement.worker_name == "Original Name"


# --- pipeline and worker availability ---------------------------------------


def test_confirming_reserves_the_worker(agency):
    user = UserFactory()
    worker = _worker(agency, user)
    placement = _placement(agency, user, worker=worker)

    with activate_tenant(agency.id):
        services.set_placement_status(placement, user=user, status=Placement.Status.CONFIRMED)
        worker.refresh_from_db()

    assert worker.availability == Worker.Availability.RESERVED


def test_delivering_places_the_worker_and_sets_the_contract(agency):
    user = UserFactory()
    worker = _worker(agency, user, location=Worker.Location.OVERSEAS)
    placement = _placement(agency, user, worker=worker)

    with activate_tenant(agency.id):
        services.set_placement_status(placement, user=user, status=Placement.Status.DELIVERED)
        placement.refresh_from_db()
        worker.refresh_from_db()

    assert worker.availability == Worker.Availability.PLACED
    # Delivered means the worker is now here, on the sponsor's visa.
    assert worker.location == Worker.Location.IN_COUNTRY
    assert placement.contract_start == placement.delivered_on
    assert placement.contract_end == services.add_months(placement.contract_start, 24)


def test_cancelling_frees_the_worker_again(agency):
    user = UserFactory()
    worker = _worker(agency, user)
    placement = _placement(agency, user, worker=worker)

    with activate_tenant(agency.id):
        services.set_placement_status(placement, user=user, status=Placement.Status.CONFIRMED)
        services.set_placement_status(placement, user=user, status=Placement.Status.CANCELLED)
        worker.refresh_from_db()

    assert worker.availability == Worker.Availability.AVAILABLE


def test_add_months_clamps_to_the_end_of_a_short_month():
    assert services.add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert services.add_months(dt.date(2026, 7, 19), 24) == dt.date(2028, 7, 19)


# --- access and isolation ---------------------------------------------------


def test_only_available_workers_are_offered(agency, client):
    from apps.manpower.forms import PlacementForm

    user = _sign_in(client, agency)
    available = _worker(agency, user, full_name="Free Worker")
    taken = _worker(agency, user, full_name="Busy Worker")

    with activate_tenant(agency.id):
        taken.availability = Worker.Availability.PLACED
        taken.save()
        offered = {w.pk for w in PlacementForm(tenant=agency).fields["worker"].queryset}

    assert available.pk in offered
    assert taken.pk not in offered


def test_placement_of_another_tenant_404s(client, agency):
    _sign_in(client, agency)

    other = TenantFactory(domain=MANPOWER)
    services.ensure_tenant_defaults(other)
    foreign = _placement(other, UserFactory())

    assert client.get(reverse("manpower:placement_detail", args=[foreign.pk])).status_code == 404
    assert client.get(reverse("manpower:placement_print", args=[foreign.pk])).status_code == 404


def test_agreement_and_biodata_documents_render(client, agency):
    user = _sign_in(client, agency)
    worker = _worker(agency, user)
    placement = _placement(agency, user, worker=worker)

    agreement = client.get(reverse("manpower:placement_print", args=[placement.pk]))
    assert agreement.status_code == 200
    assert placement.reference in agreement.content.decode()

    cv = client.get(reverse("manpower:worker_cv", args=[worker.pk]))
    assert cv.status_code == 200
    assert worker.full_name in cv.content.decode()


def test_sponsors_are_protected_from_deletion(agency):
    """A placement is a business record; its parties must not vanish."""
    user = UserFactory()
    sponsor = _sponsor(agency, user)
    _placement(agency, user, sponsor=sponsor)

    with activate_tenant(agency.id), pytest.raises(ProtectedError):
        Sponsor.objects.filter(pk=sponsor.pk).delete()
