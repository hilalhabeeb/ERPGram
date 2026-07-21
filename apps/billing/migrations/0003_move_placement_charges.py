"""Move money off the placement and onto invoices.

Placements used to carry their own charge lines and act as their own invoice.
Pricing now lives on ``billing.Invoice`` so that a placement can be billed more
than once, corrected by a credit note, and left alone once issued.

Each placement with charges becomes one invoice:

* charge types  -> services (the price list)
* charge lines  -> invoice lines
* a placement that was delivered gets an **issued** invoice with a number, so
  the sequence is continuous from day one; anything else becomes a draft
* ``amount_paid`` becomes a single payment, dated to the invoice

Nothing is deleted here — the old columns are dropped by the manpower migration
that depends on this one, so a rollback still has the data to go back to.
"""

import datetime as dt
from decimal import Decimal

from django.db import migrations

from apps.core.db import each_tenant


def _next_number(Invoice, tenant_id, year, counter):
    return f"INV-{year}-{counter:04d}"


def forwards(apps, schema_editor):
    # RLS applies to migrations too: with no app.tenant_id bound, every SELECT
    # returns nothing and this migration "succeeds" having moved nothing — which
    # is exactly what happened the first time it was written.
    for tenant_id in each_tenant(apps, schema_editor):
        _move_tenant(apps, tenant_id)


def _move_tenant(apps, tenant_id):
    Placement = apps.get_model("manpower", "Placement")
    ChargeType = apps.get_model("manpower", "ChargeType")
    Service = apps.get_model("billing", "Service")
    Invoice = apps.get_model("billing", "Invoice")
    InvoiceLine = apps.get_model("billing", "InvoiceLine")
    Payment = apps.get_model("billing", "Payment")

    services_by_key: dict[tuple, object] = {}
    for charge_type in ChargeType.objects.filter(tenant_id=tenant_id):
        service, _created = Service.objects.get_or_create(
            tenant_id=charge_type.tenant_id,
            name=charge_type.name,
            defaults={
                "default_rate": charge_type.default_amount,
                "is_taxable": charge_type.is_taxable,
                "sort_order": charge_type.sort_order,
                "is_active": charge_type.is_active,
            },
        )
        services_by_key[(charge_type.tenant_id, charge_type.name)] = service

    counters: dict[tuple, int] = {}

    for placement in Placement.objects.filter(tenant_id=tenant_id).order_by("created_at"):
        charges = list(placement.charges.all())
        if not charges:
            continue

        issue_date = placement.invoice_date or placement.agreed_on or dt.date.today()
        delivered = placement.status == "delivered"

        number = ""
        status = "draft"
        if delivered:
            key = (placement.tenant_id, issue_date.year)
            counters[key] = counters.get(key, 0) + 1
            number = _next_number(Invoice, placement.tenant_id, issue_date.year, counters[key])
            status = "issued"

        invoice = Invoice.objects.create(
            tenant_id=placement.tenant_id,
            number=number,
            kind="invoice",
            status=status,
            sponsor_id=placement.sponsor_id,
            placement_id=placement.id,
            sponsor_name=getattr(placement.sponsor, "name", ""),
            sponsor_national_id=getattr(placement.sponsor, "national_id", ""),
            issue_date=issue_date,
            due_date=issue_date + dt.timedelta(days=14),
            payment_terms=placement.payment_terms,
            terms=placement.terms,
            discount=placement.discount or Decimal("0"),
            created_by_id=placement.created_by_id,
            updated_by_id=placement.updated_by_id,
        )

        for order, charge in enumerate(charges):
            InvoiceLine.objects.create(
                tenant_id=placement.tenant_id,
                invoice_id=invoice.id,
                service=services_by_key.get((placement.tenant_id, charge.description)),
                description=charge.description,
                quantity=Decimal("1.00"),
                rate=charge.amount,
                is_taxable=charge.is_taxable,
                # The old model held one rate for the whole placement.
                tax_rate=placement.tax_rate or Decimal("10.00"),
                sort_order=charge.sort_order or order,
            )

        if placement.amount_paid and placement.amount_paid > 0 and status == "issued":
            Payment.objects.create(
                tenant_id=placement.tenant_id,
                invoice_id=invoice.id,
                received_on=issue_date,
                amount=placement.amount_paid,
                method="cash",
                notes="Migrated from placement",
            )


def backwards(apps, schema_editor):
    """Drop the generated billing rows; the placement columns still hold the data."""
    Invoice = apps.get_model("billing", "Invoice")
    Invoice.objects.filter(placement__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_rls"),
        ("manpower", "0005_rls_placements"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
