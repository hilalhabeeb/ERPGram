"""Invoicing rules. Views orchestrate; these functions decide."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.billing.models import Invoice, InvoiceLine, Payment, Service, TermsTemplate
from apps.core.tenant import activate_tenant
from apps.tenancy.models import Tenant

DEFAULT_PAYMENT_DAYS = 14

# A starting price list, so a new agency can raise an invoice on day one.
# (name, code, rate, taxable)
DEFAULT_SERVICES = [
    ("Service fee", "SRV", Decimal("450.000"), True),
    ("Visa processing", "VISA", Decimal("150.000"), True),
    ("Medical examination", "MED", Decimal("40.000"), True),
    ("Air ticket", "TKT", Decimal("120.000"), False),
    ("Insurance", "INS", Decimal("25.000"), True),
    ("Agency margin", "MRG", Decimal("100.000"), True),
    ("Visa renewal", "RNW", Decimal("180.000"), True),
    ("Replacement fee", "RPL", Decimal("200.000"), True),
]

DEFAULT_TERMS = f"""1. The sponsor is responsible for the worker's residence permit and its renewal.
2. A replacement is offered once within three months if the worker is unable to continue.
3. Fees become non-refundable once the visa has been issued.
4. Payment is due within {DEFAULT_PAYMENT_DAYS} days of the invoice date."""


def ensure_billing_defaults(tenant: Tenant, *, user=None) -> None:
    """Starting services and a default terms template for a new tenant.

    Binds the tenant itself: these are RLS-protected tables and an insert with
    no ``app.tenant_id`` is rejected outright.
    """
    with activate_tenant(tenant.id), transaction.atomic():
        for order, (name, code, rate, taxable) in enumerate(DEFAULT_SERVICES):
            Service.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "code": code,
                    "default_rate": rate,
                    "is_taxable": taxable,
                    "sort_order": order,
                    "created_by": user,
                    "updated_by": user,
                },
            )
        TermsTemplate.all_tenants.get_or_create(
            tenant=tenant,
            name="Standard terms",
            defaults={
                "body": DEFAULT_TERMS,
                "is_default": True,
                "created_by": user,
                "updated_by": user,
            },
        )


# --- numbering ---------------------------------------------------------------


def next_invoice_number(tenant: Tenant, *, kind: str, on: dt.date) -> str:
    """``INV-2026-0001``, restarting each year.

    Numbers are only handed out at issue time and are never reused: a cancelled
    invoice keeps its number and is marked cancelled, so the sequence a tax
    inspector sees has no gaps and no duplicates.
    """
    prefix = "CN" if kind == Invoice.Kind.CREDIT_NOTE else "INV"
    stem = f"{prefix}-{on.year}-"
    last = (
        Invoice.all_tenants.filter(tenant=tenant, number__startswith=stem)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    counter = 0
    if last:
        try:
            counter = int(last.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            counter = 0
    return f"{stem}{counter + 1:04d}"


# --- queries -----------------------------------------------------------------


def invoices_for(
    tenant: Tenant, *, search: str = "", state: str = "", sponsor=None
) -> QuerySet[Invoice]:
    queryset = (
        Invoice.objects.filter(tenant=tenant)
        .select_related("sponsor", "placement")
        .prefetch_related("lines", "payments")
    )
    if sponsor is not None:
        queryset = queryset.filter(sponsor=sponsor)
    if search:
        queryset = queryset.filter(
            Q(number__icontains=search)
            | Q(sponsor_name__icontains=search)
            | Q(sponsor__name__icontains=search)
        )
    if state in {Invoice.Status.DRAFT, Invoice.Status.CANCELLED}:
        queryset = queryset.filter(status=state)
    elif state == "unpaid":
        queryset = queryset.filter(status=Invoice.Status.ISSUED)
    return queryset


def default_terms(tenant: Tenant, *, applies_to: str) -> TermsTemplate | None:
    return (
        TermsTemplate.objects.filter(tenant=tenant, is_active=True, is_default=True)
        .filter(Q(applies_to=applies_to) | Q(applies_to=TermsTemplate.Applies.BOTH))
        .first()
    )


# --- lifecycle ---------------------------------------------------------------


@transaction.atomic
def create_invoice(
    *, tenant: Tenant, user, sponsor, placement=None, services=None, **fields
) -> Invoice:
    """Open a draft invoice, optionally pre-filled from the price list."""
    terms = fields.pop("terms", None)
    if terms is None:
        template = default_terms(tenant, applies_to=TermsTemplate.Applies.INVOICE)
        terms = template.body if template else ""

    invoice = Invoice.objects.create(
        tenant=tenant,
        sponsor=sponsor,
        placement=placement,
        sponsor_name=sponsor.name,
        sponsor_national_id=sponsor.national_id,
        terms=terms,
        created_by=user,
        updated_by=user,
        **fields,
    )
    if services:
        for order, service in enumerate(services):
            add_line_from_service(invoice, service=service, user=user, sort_order=order)
    return invoice


def add_line_from_service(invoice: Invoice, *, service: Service, user=None, **overrides):
    """Copy a service onto the invoice. The rate is a starting point, not a rule."""
    values = {
        "description": service.name,
        "rate": service.default_rate,
        "is_taxable": service.is_taxable,
        "quantity": Decimal("1.00"),
    }
    values.update(overrides)
    return InvoiceLine.objects.create(
        tenant=invoice.tenant,
        invoice=invoice,
        service=service,
        created_by=user,
        updated_by=user,
        **values,
    )


def assert_editable(invoice: Invoice) -> None:
    """Guard every mutation. An issued document is evidence, not a draft."""
    if invoice.is_locked:
        raise ValidationError(_("This invoice has been issued. Raise a credit note to correct it."))


@transaction.atomic
def issue_invoice(invoice: Invoice, *, user, on: dt.date | None = None) -> Invoice:
    """Assign the number and lock the document."""
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError(_("Only a draft can be issued."))
    if not invoice.lines.exists():
        raise ValidationError(_("Add at least one line before issuing."))

    issued_on = on or invoice.issue_date or timezone.localdate()
    invoice.issue_date = issued_on
    invoice.due_date = invoice.due_date or issued_on + dt.timedelta(days=DEFAULT_PAYMENT_DAYS)
    invoice.number = next_invoice_number(invoice.tenant, kind=invoice.kind, on=issued_on)
    invoice.status = Invoice.Status.ISSUED
    # Re-snapshot: the sponsor may have been corrected while this was a draft.
    invoice.sponsor_name = invoice.sponsor.name
    invoice.sponsor_national_id = invoice.sponsor.national_id
    invoice.updated_by = user
    invoice.save()
    return invoice


@transaction.atomic
def cancel_invoice(invoice: Invoice, *, user) -> Invoice:
    """Cancel an issued invoice that has taken no money.

    The number is kept rather than freed — a reused number is exactly what the
    sequential-numbering rule exists to prevent.
    """
    if invoice.payments.exists():
        raise ValidationError(
            _("This invoice has payments against it. Raise a credit note instead.")
        )
    invoice.status = Invoice.Status.CANCELLED
    invoice.updated_by = user
    invoice.save(update_fields=["status", "updated_by", "updated_at"])
    return invoice


@transaction.atomic
def create_credit_note(invoice: Invoice, *, user, reason: str = "") -> Invoice:
    """A mirror of an issued invoice that cancels out what it charged."""
    if invoice.status != Invoice.Status.ISSUED:
        raise ValidationError(_("Only an issued invoice can be credited."))
    if invoice.kind == Invoice.Kind.CREDIT_NOTE:
        raise ValidationError(_("A credit note cannot be credited."))

    note = Invoice.objects.create(
        tenant=invoice.tenant,
        kind=Invoice.Kind.CREDIT_NOTE,
        sponsor=invoice.sponsor,
        placement=invoice.placement,
        corrects=invoice,
        sponsor_name=invoice.sponsor_name,
        sponsor_national_id=invoice.sponsor_national_id,
        notes=reason,
        created_by=user,
        updated_by=user,
    )
    for line in invoice.lines.all():
        InvoiceLine.objects.create(
            tenant=invoice.tenant,
            invoice=note,
            service=line.service,
            description=line.description,
            quantity=line.quantity,
            rate=line.rate,
            is_taxable=line.is_taxable,
            tax_rate=line.tax_rate,
            sort_order=line.sort_order,
            created_by=user,
            updated_by=user,
        )
    return note


@transaction.atomic
def record_payment(invoice: Invoice, *, user, **fields) -> Payment:
    if invoice.status != Invoice.Status.ISSUED:
        raise ValidationError(_("Only an issued invoice can take a payment."))
    return Payment.objects.create(
        tenant=invoice.tenant, invoice=invoice, created_by=user, updated_by=user, **fields
    )


# --- receivables -------------------------------------------------------------

AGING_BUCKETS = [(0, 30), (31, 60), (61, 90), (91, None)]


def receivables(tenant: Tenant) -> dict:
    """What is owed, and how old it is.

    Credit notes carry a negative sign so a sponsor's balance is what they
    actually owe, not a gross figure with corrections listed separately.
    """
    today = timezone.localdate()
    open_invoices = [
        invoice
        for invoice in Invoice.objects.filter(tenant=tenant, status=Invoice.Status.ISSUED)
        .select_related("sponsor")
        .prefetch_related("lines", "payments")
        if invoice.balance_due > 0
    ]

    buckets = {label: Decimal("0.000") for label, _range in _bucket_labels()}
    by_sponsor: dict = {}
    total = Decimal("0.000")

    for invoice in open_invoices:
        owed = invoice.balance_due * invoice.sign
        total += owed
        age = (today - (invoice.due_date or invoice.issue_date or today)).days
        buckets[_bucket_for(age)] += owed

        entry = by_sponsor.setdefault(
            invoice.sponsor_id,
            {"sponsor": invoice.sponsor, "total": Decimal("0.000"), "oldest_days": 0, "count": 0},
        )
        entry["total"] += owed
        entry["count"] += 1
        entry["oldest_days"] = max(entry["oldest_days"], age)

    return {
        "total": total,
        "buckets": buckets,
        "sponsors": sorted(by_sponsor.values(), key=lambda row: row["total"], reverse=True),
        "invoices": sorted(open_invoices, key=lambda i: i.due_date or today),
    }


def _bucket_labels():
    return [
        (_("Not yet due"), None),
        (_("1–30 days"), (0, 30)),
        (_("31–60 days"), (31, 60)),
        (_("61–90 days"), (61, 90)),
        (_("Over 90 days"), (91, None)),
    ]


def _bucket_for(age_days: int):
    if age_days < 0:
        return _("Not yet due")
    if age_days <= 30:
        return _("1–30 days")
    if age_days <= 60:
        return _("31–60 days")
    if age_days <= 90:
        return _("61–90 days")
    return _("Over 90 days")


def sponsor_statement(tenant: Tenant, sponsor) -> dict:
    """Every issued document for one sponsor, with a running balance."""
    documents = (
        Invoice.objects.filter(tenant=tenant, sponsor=sponsor)
        .exclude(status=Invoice.Status.DRAFT)
        .prefetch_related("lines", "payments")
        .order_by("issue_date", "number")
    )
    rows = []
    balance = Decimal("0.000")
    for invoice in documents:
        if invoice.status == Invoice.Status.CANCELLED:
            continue
        charged = invoice.total * invoice.sign
        balance += charged
        rows.append(
            {"invoice": invoice, "charged": charged, "paid": Decimal("0.000"), "balance": balance}
        )
        for payment in invoice.payments.all():
            balance -= payment.amount
            rows.append(
                {
                    "invoice": invoice,
                    "payment": payment,
                    "charged": Decimal("0.000"),
                    "paid": payment.amount,
                    "balance": balance,
                }
            )
    return {"rows": rows, "balance": balance, "sponsor": sponsor}


def billing_summary(tenant: Tenant) -> list[dict]:
    data = receivables(tenant)
    overdue = sum(
        (invoice.balance_due for invoice in data["invoices"] if invoice.is_overdue),
        Decimal("0.000"),
    )
    drafts = Invoice.objects.filter(tenant=tenant, status=Invoice.Status.DRAFT).count()
    return [
        {
            "key": "outstanding",
            "label": _("Outstanding"),
            "value": data["total"],
            "icon": "file-text",
        },
        {"key": "overdue", "label": _("Overdue"), "value": overdue, "icon": "alert-triangle"},
        {"key": "drafts", "label": _("Draft invoices"), "value": drafts, "icon": "pencil"},
    ]
