"""Invoicing: arithmetic, numbering, immutability, credit notes, receivables.

These are the rules that make the numbering trustworthy and the totals safe to
send to a customer, so they are pinned tightly.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.services import ensure_system_roles
from apps.billing import services as billing
from apps.billing.models import Invoice, Service
from apps.core.domains import MANPOWER
from apps.core.tenant import activate_tenant
from apps.manpower import services as manpower
from apps.manpower.models import Country, Occupation
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def agency():
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    manpower.ensure_reference_data()
    manpower.ensure_tenant_defaults(tenant)
    billing.ensure_billing_defaults(tenant)
    return tenant


def _sign_in(client, tenant):
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=True, is_default=True)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


def _sponsor(tenant, user, name="Test Sponsor"):
    with activate_tenant(tenant.id):
        return manpower.create_sponsor(tenant=tenant, user=user, name=name, national_id="800112233")


def _invoice(tenant, user, *, sponsor=None, lines=None):
    """A draft invoice with explicit lines, so the arithmetic is unambiguous."""
    with activate_tenant(tenant.id):
        invoice = billing.create_invoice(
            tenant=tenant, user=user, sponsor=sponsor or _sponsor(tenant, user)
        )
        for description, rate, taxable, tax_rate in lines or [
            ("Service fee", Decimal("100.000"), True, Decimal("10.00"))
        ]:
            invoice.lines.create(
                tenant=tenant,
                description=description,
                quantity=Decimal("1.00"),
                rate=rate,
                is_taxable=taxable,
                tax_rate=tax_rate,
            )
        invoice.refresh_from_db()
        return invoice


# --- arithmetic --------------------------------------------------------------


def test_tax_applies_per_line_not_per_invoice(agency):
    """GCC rates differ, and a recharged air ticket is not taxed at all."""
    user = UserFactory()
    invoice = _invoice(
        agency,
        user,
        lines=[
            ("Service fee", Decimal("100.000"), True, Decimal("10.00")),
            ("Air ticket", Decimal("50.000"), False, Decimal("10.00")),
            ("Saudi line", Decimal("100.000"), True, Decimal("15.00")),
        ],
    )
    with activate_tenant(agency.id):
        assert invoice.subtotal == Decimal("250.000")
        # 10 on the first line, none on the ticket, 15 on the third
        assert invoice.tax_amount == Decimal("25.000")
        assert invoice.total == Decimal("275.000")


def test_quantity_multiplies_the_rate(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        invoice = billing.create_invoice(tenant=agency, user=user, sponsor=_sponsor(agency, user))
        invoice.lines.create(
            tenant=agency,
            description="Monthly fee",
            quantity=Decimal("3.00"),
            rate=Decimal("50.000"),
            is_taxable=False,
        )
        invoice.refresh_from_db()
        assert invoice.subtotal == Decimal("150.000")


def test_discount_reduces_the_taxable_base(agency):
    user = UserFactory()
    invoice = _invoice(agency, user, lines=[("Fee", Decimal("200.000"), True, Decimal("10.00"))])
    with activate_tenant(agency.id):
        invoice.discount = Decimal("50.000")
        invoice.save()
        invoice.refresh_from_db()
        assert invoice.taxable_base == Decimal("150.000")


def test_balance_tracks_payments(agency):
    user = UserFactory()
    invoice = _invoice(agency, user, lines=[("Fee", Decimal("100.000"), False, Decimal("0"))])
    with activate_tenant(agency.id):
        billing.issue_invoice(invoice, user=user)
        assert invoice.balance_due == Decimal("100.000")

        billing.record_payment(
            invoice, user=user, received_on=dt.date(2026, 7, 1), amount=Decimal("40.000")
        )
        invoice.refresh_from_db()
        assert invoice.balance_due == Decimal("60.000")
        assert invoice.payment_state == "part_paid"

        billing.record_payment(
            invoice, user=user, received_on=dt.date(2026, 7, 5), amount=Decimal("60.000")
        )
        invoice.refresh_from_db()
        assert invoice.is_paid is True
        assert invoice.payment_state == "paid"


# --- numbering ---------------------------------------------------------------


def test_numbers_are_sequential_and_reset_each_year(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        first = billing.issue_invoice(_invoice(agency, user), user=user, on=dt.date(2026, 3, 1))
        second = billing.issue_invoice(_invoice(agency, user), user=user, on=dt.date(2026, 9, 1))
        next_year = billing.issue_invoice(_invoice(agency, user), user=user, on=dt.date(2027, 1, 5))

    assert first.number == "INV-2026-0001"
    assert second.number == "INV-2026-0002"
    assert next_year.number == "INV-2027-0001"


def test_a_draft_has_no_number(agency):
    user = UserFactory()
    assert _invoice(agency, user).number == ""


def test_numbers_do_not_collide_across_tenants(agency):
    user = UserFactory()
    other = TenantFactory(domain=MANPOWER)
    manpower.ensure_tenant_defaults(other)
    billing.ensure_billing_defaults(other)

    with activate_tenant(agency.id):
        mine = billing.issue_invoice(_invoice(agency, user), user=user, on=dt.date(2026, 3, 1))
    with activate_tenant(other.id):
        theirs = billing.issue_invoice(_invoice(other, user), user=user, on=dt.date(2026, 3, 1))

    # Same number, different tenants — the uniqueness constraint is per tenant.
    assert mine.number == theirs.number == "INV-2026-0001"


def test_cancelling_keeps_the_number_so_it_is_never_reused(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        first = billing.issue_invoice(_invoice(agency, user), user=user, on=dt.date(2026, 3, 1))
        billing.cancel_invoice(first, user=user)
        second = billing.issue_invoice(_invoice(agency, user), user=user, on=dt.date(2026, 3, 2))

    first.refresh_from_db()
    assert first.number == "INV-2026-0001"
    assert first.status == Invoice.Status.CANCELLED
    assert second.number == "INV-2026-0002"


# --- immutability ------------------------------------------------------------


def test_an_issued_invoice_cannot_be_edited(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        invoice = billing.issue_invoice(_invoice(agency, user), user=user)
        with pytest.raises(ValidationError):
            billing.assert_editable(invoice)


def test_an_empty_invoice_cannot_be_issued(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        empty = billing.create_invoice(tenant=agency, user=user, sponsor=_sponsor(agency, user))
        with pytest.raises(ValidationError):
            billing.issue_invoice(empty, user=user)


def test_an_invoice_with_payments_cannot_be_cancelled(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        invoice = billing.issue_invoice(_invoice(agency, user), user=user)
        billing.record_payment(
            invoice, user=user, received_on=dt.date(2026, 7, 1), amount=Decimal("10.000")
        )
        with pytest.raises(ValidationError):
            billing.cancel_invoice(invoice, user=user)


def test_editing_a_locked_invoice_through_the_view_is_refused(client, agency):
    user = _sign_in(client, agency)
    with activate_tenant(agency.id):
        invoice = billing.issue_invoice(_invoice(agency, user), user=user)
        line_count = invoice.lines.count()

    client.post(
        reverse("billing:invoice_line_add", args=[invoice.pk]),
        {"description": "Sneaky", "quantity": "1", "rate": "999", "tax_rate": "10"},
    )

    with activate_tenant(agency.id):
        invoice.refresh_from_db()
        assert invoice.lines.count() == line_count


# --- credit notes ------------------------------------------------------------


def test_a_credit_note_mirrors_the_invoice_and_offsets_it(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        invoice = billing.issue_invoice(
            _invoice(agency, user, lines=[("Fee", Decimal("100.000"), False, Decimal("0"))]),
            user=user,
        )
        note = billing.create_credit_note(invoice, user=user, reason="Worker returned")
        billing.issue_invoice(note, user=user)

        assert note.kind == Invoice.Kind.CREDIT_NOTE
        assert note.corrects_id == invoice.pk
        assert note.number.startswith("CN-")
        assert note.total == invoice.total
        # Credit notes reduce what is owed.
        assert note.sign == -1


def test_a_draft_cannot_be_credited(agency):
    user = UserFactory()
    with activate_tenant(agency.id), pytest.raises(ValidationError):
        billing.create_credit_note(_invoice(agency, user), user=user)


# --- price list --------------------------------------------------------------


def test_a_line_copies_the_service_rate_but_stays_editable(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        service = Service.objects.get(tenant=agency, name="Visa processing")
        invoice = billing.create_invoice(
            tenant=agency, user=user, sponsor=_sponsor(agency, user), services=[service]
        )
        line = invoice.lines.first()
        assert line.rate == service.default_rate

        # Changing the price list must not rewrite an existing line.
        service.default_rate = Decimal("999.000")
        service.save()
        line.refresh_from_db()
        assert line.rate != Decimal("999.000")


def test_placement_invoice_prefills_from_the_price_list(client, agency):
    user = _sign_in(client, agency)
    with activate_tenant(agency.id):
        worker = manpower.create_worker(
            tenant=agency,
            user=user,
            full_name="Worker",
            nationality=Country.objects.get(iso_code="ID"),
            occupation=Occupation.objects.filter(tenant=agency).first(),
        )
        placement = manpower.create_placement(
            tenant=agency, user=user, sponsor=_sponsor(agency, user), worker=worker
        )

    response = client.post(reverse("manpower:placement_invoice", args=[placement.pk]))
    assert response.status_code == 302

    with activate_tenant(agency.id):
        invoice = Invoice.objects.get(placement=placement)
        assert invoice.status == Invoice.Status.DRAFT
        assert invoice.lines.count() > 0
        assert invoice.sponsor_id == placement.sponsor_id


# --- receivables -------------------------------------------------------------


def test_receivables_totals_only_unpaid_issued_invoices(agency):
    user = UserFactory()
    with activate_tenant(agency.id):
        paid = billing.issue_invoice(
            _invoice(agency, user, lines=[("Fee", Decimal("100.000"), False, Decimal("0"))]),
            user=user,
        )
        billing.record_payment(
            paid, user=user, received_on=dt.date(2026, 7, 1), amount=Decimal("100.000")
        )
        billing.issue_invoice(
            _invoice(agency, user, lines=[("Fee", Decimal("60.000"), False, Decimal("0"))]),
            user=user,
        )
        _invoice(agency, user)  # a draft owes nothing

        data = billing.receivables(agency)

    assert data["total"] == Decimal("60.000")


def test_statement_runs_a_balance_across_documents_and_payments(agency):
    user = UserFactory()
    sponsor = _sponsor(agency, user, name="Statement Sponsor")
    with activate_tenant(agency.id):
        invoice = billing.issue_invoice(
            _invoice(
                agency,
                user,
                sponsor=sponsor,
                lines=[("Fee", Decimal("100.000"), False, Decimal("0"))],
            ),
            user=user,
        )
        billing.record_payment(
            invoice, user=user, received_on=dt.date(2026, 7, 2), amount=Decimal("30.000")
        )
        statement = billing.sponsor_statement(agency, sponsor)

    assert statement["balance"] == Decimal("70.000")


# --- isolation ---------------------------------------------------------------


def test_invoice_of_another_tenant_404s(client, agency):
    _sign_in(client, agency)
    other = TenantFactory(domain=MANPOWER)
    manpower.ensure_tenant_defaults(other)
    billing.ensure_billing_defaults(other)
    foreign = _invoice(other, UserFactory())

    assert client.get(reverse("billing:invoice_detail", args=[foreign.pk])).status_code == 404
    assert client.get(reverse("billing:invoice_print", args=[foreign.pk])).status_code == 404


def test_billing_is_absent_for_another_domain(client):
    from apps.core.domains import GENERAL

    tenant = TenantFactory(domain=GENERAL)
    ensure_system_roles(tenant)
    _sign_in(client, tenant)

    assert client.get(reverse("billing:invoice_list")).status_code == 404


def test_a_placement_with_only_a_draft_invoice_is_not_paid(agency):
    """A draft has not been billed, so it cannot make a placement look settled."""
    user = UserFactory()
    with activate_tenant(agency.id):
        worker = manpower.create_worker(
            tenant=agency,
            user=user,
            full_name="Worker",
            nationality=Country.objects.get(iso_code="ID"),
            occupation=Occupation.objects.filter(tenant=agency).first(),
        )
        placement = manpower.create_placement(
            tenant=agency, user=user, sponsor=_sponsor(agency, user), worker=worker
        )
        billing.create_invoice(
            tenant=agency,
            user=user,
            sponsor=placement.sponsor,
            placement=placement,
            services=list(Service.objects.filter(tenant=agency)[:2]),
        )
        placement.refresh_from_db()

        assert placement.invoiced_total == Decimal("0.000")
        assert placement.is_paid is False


# --- the screens actually render ---------------------------------------------
# Added after the invoice list 500'd while the whole suite was green: every test
# above either hit a 404 first or exercised services directly, so no test ever
# rendered these pages successfully.


def test_every_billing_page_renders(client, agency):
    user = _sign_in(client, agency)
    with activate_tenant(agency.id):
        draft = _invoice(agency, user)
        issued = billing.issue_invoice(_invoice(agency, user), user=user)
        sponsor = draft.sponsor

    pages = [
        reverse("billing:invoice_list"),
        reverse("billing:receivables"),
        reverse("billing:setup"),
        reverse("billing:setup_section", args=["terms"]),
        reverse("billing:invoice_detail", args=[draft.pk]),
        reverse("billing:invoice_detail", args=[issued.pk]),
        reverse("billing:invoice_print", args=[issued.pk]),
        reverse("billing:sponsor_statement", args=[sponsor.pk]),
    ]
    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, f"{url} returned {response.status_code}"


def test_placement_pages_render_after_the_billing_split(client, agency):
    user = _sign_in(client, agency)
    with activate_tenant(agency.id):
        worker = manpower.create_worker(
            tenant=agency,
            user=user,
            full_name="Worker",
            nationality=Country.objects.get(iso_code="ID"),
            occupation=Occupation.objects.filter(tenant=agency).first(),
        )
        placement = manpower.create_placement(
            tenant=agency, user=user, sponsor=_sponsor(agency, user), worker=worker
        )

    for url in [
        reverse("manpower:placement_list"),
        reverse("manpower:placement_detail", args=[placement.pk]),
        reverse("manpower:placement_print", args=[placement.pk]),
    ]:
        response = client.get(url)
        assert response.status_code == 200, f"{url} returned {response.status_code}"


# --- service master enforcement ----------------------------------------------


def test_a_line_requires_a_registered_service(agency):
    """Nothing is billed that is not in the price list."""
    from apps.billing.forms import InvoiceLineForm

    with activate_tenant(agency.id):
        form = InvoiceLineForm({"quantity": "1", "rate": "50"}, tenant=agency)
        assert not form.is_valid()
        assert "service" in form.errors


def test_a_line_inherits_rate_description_and_tax_from_the_service(agency):
    from apps.billing.forms import InvoiceLineForm

    with activate_tenant(agency.id):
        service = Service.objects.get(tenant=agency, name="Visa processing")
        # Only the service is supplied; everything else fills in.
        form = InvoiceLineForm({"service": str(service.pk), "quantity": "1"}, tenant=agency)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["rate"] == service.default_rate
        assert form.cleaned_data["description"] == (service.description or service.name)
        assert form.cleaned_data["tax_rate"] == agency.default_tax_rate


def test_a_non_taxable_service_forces_the_line_non_taxable(agency):
    from apps.billing.forms import InvoiceLineForm

    with activate_tenant(agency.id):
        ticket = Service.objects.get(tenant=agency, name="Air ticket")
        assert ticket.is_taxable is False
        # Even if the POST claims taxable, a non-taxable service wins.
        form = InvoiceLineForm(
            {"service": str(ticket.pk), "quantity": "1", "is_taxable": "on", "tax_rate": "10"},
            tenant=agency,
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["is_taxable"] is False
        assert form.cleaned_data["tax_rate"] == Decimal("0.00")


def test_new_lines_use_the_tenant_default_tax_rate(agency):
    from apps.tenancy.services import update_organization

    user = UserFactory()
    with activate_tenant(agency.id):
        update_organization(agency, default_tax_rate=Decimal("15.00"))
        service = Service.objects.get(tenant=agency, name="Service fee")
        invoice = billing.create_invoice(tenant=agency, user=user, sponsor=_sponsor(agency, user))
        line = billing.add_line_from_service(invoice, service=service, user=user)
        assert line.tax_rate == Decimal("15.00")


# --- payment guards ----------------------------------------------------------


def test_a_payment_cannot_exceed_the_balance(agency):
    user = UserFactory()
    invoice = _invoice(agency, user, lines=[("Fee", Decimal("100.000"), False, Decimal("0"))])
    with activate_tenant(agency.id):
        billing.issue_invoice(invoice, user=user)
        with pytest.raises(ValidationError):
            billing.record_payment(
                invoice, user=user, received_on=dt.date(2026, 7, 1), amount=Decimal("150.000")
            )
        # a payment up to the balance is fine
        billing.record_payment(
            invoice, user=user, received_on=dt.date(2026, 7, 1), amount=Decimal("100.000")
        )
        invoice.refresh_from_db()
        assert invoice.is_paid
