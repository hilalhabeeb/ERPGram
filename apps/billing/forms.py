"""Billing forms. Tenant-owned choice lists are always scoped explicitly."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.billing.models import Invoice, InvoiceLine, Payment, Service, TermsTemplate
from apps.manpower.forms import TenantScopedModelForm


class InvoiceForm(TenantScopedModelForm):
    """Header of a draft invoice.

    ``sponsor`` is scoped in ``__init__`` rather than through ``tenant_fields``
    because Sponsor lives in the manpower app and importing it at module level
    would make billing and manpower import each other.
    """

    class Meta:
        model = Invoice
        fields = ["sponsor", "issue_date", "due_date", "payment_terms", "discount", "notes"]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.manpower.models import Sponsor

        self.fields["sponsor"].queryset = Sponsor.objects.filter(
            tenant=self.tenant, is_active=True
        ).order_by("name")


class InvoiceTermsForm(TenantScopedModelForm):
    """Terms on an invoice, optionally filled from a template."""

    terms_template = forms.ModelChoiceField(
        label=_("Insert terms template"),
        queryset=TermsTemplate.objects.none(),
        required=False,
    )

    class Meta:
        model = Invoice
        fields = ["terms"]
        widgets = {"terms": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["terms_template"].queryset = TermsTemplate.objects.filter(
            tenant=self.tenant, is_active=True
        ).exclude(applies_to=TermsTemplate.Applies.PLACEMENT)

    def clean(self):
        cleaned = super().clean()
        template = cleaned.get("terms_template")
        if template and not (cleaned.get("terms") or "").strip():
            cleaned["terms"] = template.body
        cleaned.pop("terms_template", None)
        return cleaned


class InvoiceLineForm(TenantScopedModelForm):
    """One invoice line — always a registered service.

    Every line must reference a Service (the item master), the way ERPNext
    requires an Item. Anything you want to bill has to exist as a service first,
    so the price list stays the single source of truth and nothing is invented
    ad hoc on an invoice. The rate, description and tax fill in from the service
    and can be adjusted on the line without touching the master.
    """

    tenant_fields = {"service": Service}

    class Meta:
        model = InvoiceLine
        fields = ["service", "description", "quantity", "rate", "is_taxable", "tax_rate"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].required = True
        self.fields["service"].empty_label = _("Choose a service…")
        # Rate/description/tax are optional on the form: a blank line inherits
        # them from the chosen service in clean().
        for name in ("description", "rate", "tax_rate", "is_taxable"):
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        service = cleaned.get("service")
        if service is None:
            return cleaned
        if not (cleaned.get("description") or "").strip():
            cleaned["description"] = service.description or service.name
        if cleaned.get("rate") in (None, ""):
            cleaned["rate"] = service.default_rate
        # Taxability is a property of the item, not a per-line choice — a
        # checkbox cannot tell "unchecked" from "not sent", so it would default a
        # taxable service to untaxed. The service decides; the rate defaults to
        # the tenant's rate and stays adjustable.
        cleaned["is_taxable"] = service.is_taxable
        if service.is_taxable:
            if cleaned.get("tax_rate") in (None, ""):
                cleaned["tax_rate"] = self.tenant.default_tax_rate
        else:
            cleaned["tax_rate"] = Decimal("0.00")
        return cleaned


class PaymentForm(TenantScopedModelForm):
    class Meta:
        model = Payment
        fields = ["received_on", "amount", "method", "reference", "notes"]
        widgets = {"received_on": forms.DateInput(attrs={"type": "date"})}


class ServiceForm(TenantScopedModelForm):
    class Meta:
        model = Service
        fields = ["name", "code", "description", "default_rate", "is_taxable", "sort_order"]


class TermsTemplateForm(TenantScopedModelForm):
    class Meta:
        model = TermsTemplate
        fields = ["name", "body", "applies_to", "is_default"]
        widgets = {"body": forms.Textarea(attrs={"rows": 8})}


BILLING_SETUP_FORMS = {
    "services": (Service, ServiceForm, _("Services")),
    "terms": (TermsTemplate, TermsTemplateForm, _("Terms templates")),
}
