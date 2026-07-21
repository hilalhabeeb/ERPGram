"""Invoicing and receivables.

Kept apart from ``apps.manpower`` on purpose: an invoice is a financial record
with its own rules, not a view over an operational one.

Why the split matters in practice:

* One placement can need several invoices — a deposit on signing and a balance
  on delivery is the normal payment term in this trade.
* A replacement or refund needs a **credit note** against an issued invoice.
* GCC VAT expects issued invoices to be sequentially numbered and **immutable**.
  A placement keeps changing (pipeline dates, status); a tax document must not.
* Plenty of billing has no placement at all — a visa renewal, a medical only,
  an attestation.

The customer is currently ``manpower.Sponsor``. That is an honest coupling for
today; when a second industry needs billing, introduce a customer abstraction
rather than pretending this one is already generic.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantScopedModel

TWO_DP = Decimal("0.01")
THREE_DP = Decimal("0.001")


class Service(TenantScopedModel):
    """A billable service with a default rate — the agency's price list.

    Rates are defaults, not rules: an invoice line copies the rate and can then
    be edited, so changing the price list never rewrites past invoices.
    """

    code = models.CharField(_("code"), max_length=30, blank=True)
    name = models.CharField(_("name"), max_length=150)
    description = models.CharField(_("description"), max_length=250, blank=True)
    default_rate = models.DecimalField(
        _("default rate"), max_digits=12, decimal_places=3, default=0
    )
    is_taxable = models.BooleanField(
        _("taxable"),
        default=True,
        help_text=_("Pass-through costs such as air tickets are usually not taxed."),
    )
    # Reserved for a future general ledger; unused today but cheap to carry.
    income_account = models.CharField(_("income account"), max_length=60, blank=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")
        ordering = ["sort_order", "name"]
        base_manager_name = "all_tenants"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_service_tenant_name"),
        ]

    def __str__(self) -> str:
        return self.name


class TermsTemplate(TenantScopedModel):
    """Reusable terms and conditions text.

    Chosen on a document and then **copied onto it**. Amending the template must
    never rewrite terms on a document a sponsor has already signed.
    """

    class Applies(models.TextChoices):
        BOTH = "both", _("Agreements and invoices")
        PLACEMENT = "placement", _("Agreements only")
        INVOICE = "invoice", _("Invoices only")

    name = models.CharField(_("name"), max_length=150)
    body = models.TextField(_("terms"))
    applies_to = models.CharField(
        _("applies to"), max_length=20, choices=Applies.choices, default=Applies.BOTH
    )
    is_default = models.BooleanField(
        _("use by default"),
        default=False,
        help_text=_("Pre-selected on new documents."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("terms template")
        verbose_name_plural = _("terms templates")
        ordering = ["-is_default", "name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Invoice(TenantScopedModel):
    """A bill (or credit note) issued to a sponsor.

    A draft is freely editable. **Issuing assigns the number and locks it**;
    after that the only corrections are cancelling an unpaid invoice or raising
    a credit note against it. That is what makes the numbering trustworthy.
    """

    class Kind(models.TextChoices):
        INVOICE = "invoice", _("Invoice")
        CREDIT_NOTE = "credit_note", _("Credit note")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ISSUED = "issued", _("Issued")
        CANCELLED = "cancelled", _("Cancelled")

    number = models.CharField(
        _("number"),
        max_length=30,
        blank=True,
        help_text=_("Assigned when the invoice is issued."),
    )
    kind = models.CharField(_("type"), max_length=20, choices=Kind.choices, default=Kind.INVOICE)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    sponsor = models.ForeignKey(
        "manpower.Sponsor",
        verbose_name=_("sponsor"),
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    placement = models.ForeignKey(
        "manpower.Placement",
        verbose_name=_("placement"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        help_text=_("Optional — not all billing comes from a placement."),
    )
    # A credit note points at what it corrects.
    corrects = models.ForeignKey(
        "self",
        verbose_name=_("corrects"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credit_notes",
    )

    # Snapshots, so the document keeps saying what it said when issued.
    sponsor_name = models.CharField(_("billed to"), max_length=200, blank=True)
    sponsor_national_id = models.CharField(_("national ID / CPR"), max_length=40, blank=True)

    issue_date = models.DateField(_("issue date"), null=True, blank=True)
    due_date = models.DateField(_("due date"), null=True, blank=True)
    payment_terms = models.CharField(_("payment terms"), max_length=200, blank=True)
    terms = models.TextField(_("terms and conditions"), blank=True)
    notes = models.TextField(_("notes"), blank=True)

    discount = models.DecimalField(
        _("discount"),
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-issue_date", "-created_at"]
        base_manager_name = "all_tenants"
        constraints = [
            # Drafts have no number yet, so only issued numbers must be unique.
            models.UniqueConstraint(
                fields=["tenant", "number"],
                condition=models.Q(number__gt=""),
                name="uniq_invoice_tenant_number",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "status", "issue_date"])]

    def __str__(self) -> str:
        return self.number or _("Draft invoice")

    # --- state ---

    @property
    def is_locked(self) -> bool:
        """Issued documents are read-only; correct them with a credit note."""
        return self.status != self.Status.DRAFT

    @property
    def sign(self) -> int:
        """Credit notes reduce what is owed."""
        return -1 if self.kind == self.Kind.CREDIT_NOTE else 1

    # --- money ---
    # Derived from the lines. A stored total is one edit away from disagreeing
    # with the document it is printed on.

    @property
    def subtotal(self) -> Decimal:
        return sum((line.amount for line in self.lines.all()), Decimal("0")).quantize(THREE_DP)

    @property
    def taxable_base(self) -> Decimal:
        base = sum((line.amount for line in self.lines.all() if line.is_taxable), Decimal("0"))
        return max(base - self.discount, Decimal("0")).quantize(THREE_DP)

    @property
    def tax_amount(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines.all()), Decimal("0")).quantize(THREE_DP)

    @property
    def total(self) -> Decimal:
        return (self.subtotal - self.discount + self.tax_amount).quantize(THREE_DP)

    @property
    def amount_paid(self) -> Decimal:
        return sum((p.amount for p in self.payments.all()), Decimal("0")).quantize(THREE_DP)

    @property
    def balance_due(self) -> Decimal:
        if self.status == self.Status.CANCELLED:
            return Decimal("0.000")
        return (self.total - self.amount_paid).quantize(THREE_DP)

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.ISSUED and self.balance_due <= 0

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        return bool(
            self.status == self.Status.ISSUED
            and self.due_date
            and self.balance_due > 0
            and self.due_date < timezone.localdate()
        )

    @property
    def payment_state(self) -> str:
        """One word for the list view: what is happening with the money."""
        if self.status != self.Status.ISSUED:
            return self.status
        if self.balance_due <= 0:
            return "paid"
        if self.amount_paid > 0:
            return "part_paid"
        return "unpaid"


class InvoiceLine(TenantScopedModel):
    """One priced line. Quantity x rate, with its own tax rate.

    ``tax_rate`` sits on the line rather than the invoice because GCC rates
    differ by country (Bahrain 10, Saudi 15, UAE 5) and some lines — an air
    ticket recharged at cost — are not taxed at all.
    """

    invoice = models.ForeignKey(
        Invoice, verbose_name=_("invoice"), on_delete=models.CASCADE, related_name="lines"
    )
    service = models.ForeignKey(
        Service,
        verbose_name=_("service"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lines",
    )
    description = models.CharField(_("description"), max_length=250)
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    rate = models.DecimalField(_("rate"), max_digits=12, decimal_places=3, default=0)
    is_taxable = models.BooleanField(_("taxable"), default=True)
    tax_rate = models.DecimalField(
        _("tax rate %"), max_digits=5, decimal_places=2, default=Decimal("10.00")
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("invoice line")
        verbose_name_plural = _("invoice lines")
        ordering = ["sort_order", "id"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return f"{self.description} x{self.quantity}"

    @property
    def amount(self) -> Decimal:
        return (self.quantity * self.rate).quantize(THREE_DP)

    @property
    def tax_amount(self) -> Decimal:
        if not self.is_taxable:
            return Decimal("0.000")
        return (self.amount * self.tax_rate / Decimal("100")).quantize(THREE_DP)

    @property
    def total(self) -> Decimal:
        return (self.amount + self.tax_amount).quantize(THREE_DP)


class Payment(TenantScopedModel):
    """Money received against an invoice.

    Separate rows rather than a single ``amount_paid`` field: a deposit and a
    balance are two events with two dates, and the ledger has to show both.
    """

    class Method(models.TextChoices):
        CASH = "cash", _("Cash")
        TRANSFER = "transfer", _("Bank transfer")
        CARD = "card", _("Card")
        CHEQUE = "cheque", _("Cheque")
        OTHER = "other", _("Other")

    invoice = models.ForeignKey(
        Invoice, verbose_name=_("invoice"), on_delete=models.PROTECT, related_name="payments"
    )
    received_on = models.DateField(_("received on"))
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    method = models.CharField(
        _("method"), max_length=20, choices=Method.choices, default=Method.CASH
    )
    reference = models.CharField(_("reference"), max_length=100, blank=True)
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-received_on", "-created_at"]
        base_manager_name = "all_tenants"
        indexes = [models.Index(fields=["tenant", "received_on"])]

    def __str__(self) -> str:
        return f"{self.amount} on {self.received_on}"
