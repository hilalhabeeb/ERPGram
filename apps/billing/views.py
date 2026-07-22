"""Accounting pages: invoices, payments, receivables.

Gated twice like the manpower module — the tenant must be in a domain that has
billing, and the user must hold the permission.
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import has_permission, require_permission
from apps.billing import services
from apps.billing.forms import (
    BILLING_SETUP_FORMS,
    InvoiceForm,
    InvoiceLineForm,
    InvoiceTermsForm,
    PaymentForm,
)
from apps.billing.models import Invoice, Service
from apps.core.domains import MANPOWER
from apps.core.permissions import MANAGE_BILLING_SETUP, MANAGE_INVOICES, RECORD_PAYMENTS
from apps.ui.services import paginate


def _require_billing(request: HttpRequest) -> None:
    if getattr(request.tenant, "domain", None) != MANPOWER:
        raise Http404("billing is not enabled for this tenant")


def _get_invoice(request: HttpRequest, pk) -> Invoice:
    return get_object_or_404(
        Invoice.objects.filter(tenant=request.tenant)
        .select_related("sponsor", "placement", "corrects")
        .prefetch_related("lines__service", "payments"),
        pk=pk,
    )


# --- invoices ----------------------------------------------------------------


def invoice_list(request: HttpRequest) -> HttpResponse:
    _require_billing(request)
    tenant = request.tenant
    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "")

    queryset = services.invoices_for(tenant, search=search, state=state)
    page, sort_key, direction = paginate(
        request,
        queryset,
        allowed_sorts={"number": "number", "issued": "issue_date", "due": "due_date"},
        default_sort="issued",
    )

    context = {
        "page_title": _("Invoices"),
        "breadcrumb": [_("Invoices")],
        "columns": [
            {"key": "number", "label": _("Number"), "sortable": True},
            {"key": "sponsor", "label": _("Sponsor"), "sortable": False},
            {
                "key": "issued",
                "label": _("Issued"),
                "sortable": True,
                "css": "hidden lg:table-cell",
            },
            {"key": "due", "label": _("Due"), "sortable": True},
            {"key": "total", "label": _("Total"), "sortable": False},
            {"key": "state", "label": _("Status"), "sortable": False},
        ],
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "search": search,
        "state": state,
        "stats": services.billing_summary(tenant),
        "form": InvoiceForm(tenant=tenant),
        "can_manage": has_permission(request, MANAGE_INVOICES),
    }
    if request.htmx and request.htmx.target == "invoices-table":
        return render(request, "billing/_invoices_table.html", context)
    return render(request, "billing/invoice_list.html", context)


def invoice_detail(request: HttpRequest, pk) -> HttpResponse:
    _require_billing(request)
    invoice = _get_invoice(request, pk)
    tenant = request.tenant
    services_qs = Service.objects.filter(tenant=tenant, is_active=True)

    # The items grid is an Alpine child table: it needs the price list and the
    # current lines as JSON to edit in place. Money fields go over as strings so
    # the Arabic locale never turns a decimal point into a comma in transit.
    services_data = [
        {
            "id": str(service.id),
            "name": service.name,
            "code": service.code,
            "rate": str(service.default_rate),
            "taxable": service.is_taxable,
            "description": service.description or service.name,
        }
        for service in services_qs
    ]
    lines_data = [
        {
            "service": str(line.service_id) if line.service_id else "",
            "description": line.description,
            "quantity": str(line.quantity),
            "rate": str(line.rate),
        }
        for line in invoice.lines.all()
    ]
    grid_config = {
        "currency": tenant.currency,
        "defaultTax": str(tenant.default_tax_rate),
        "discount": str(invoice.discount),
    }

    return render(
        request,
        "billing/invoice_detail.html",
        {
            "page_title": invoice.number or _("Draft invoice"),
            "breadcrumb": [_("Invoices"), invoice.number or _("Draft")],
            "invoice": invoice,
            "lines": invoice.lines.all(),
            "payments": invoice.payments.all(),
            "terms_form": InvoiceTermsForm(instance=invoice, tenant=request.tenant),
            "payment_form": PaymentForm(tenant=request.tenant),
            "header_form": InvoiceForm(instance=invoice, tenant=request.tenant),
            "services": services_qs,
            "services_data": services_data,
            "lines_data": lines_data,
            "grid_config": grid_config,
            "can_manage": has_permission(request, MANAGE_INVOICES),
            "can_pay": has_permission(request, RECORD_PAYMENTS),
        },
    )


@require_POST
def invoice_create(request: HttpRequest) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    form = InvoiceForm(request.POST, tenant=request.tenant)
    if form.is_valid():
        data = dict(form.cleaned_data)
        invoice = services.create_invoice(
            tenant=request.tenant, user=request.user, sponsor=data.pop("sponsor"), **data
        )
        messages.success(request, _("Draft invoice created."))
        return redirect("billing:invoice_detail", pk=invoice.pk)
    messages.error(request, _("Please correct the errors and try again."))
    return redirect("billing:invoice_list")


def _guard_editable(request: HttpRequest, invoice: Invoice) -> HttpResponse | None:
    try:
        services.assert_editable(invoice)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("billing:invoice_detail", pk=invoice.pk)
    return None


@require_POST
def invoice_update(request: HttpRequest, pk, section: str) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    invoice = _get_invoice(request, pk)
    if blocked := _guard_editable(request, invoice):
        return blocked

    form_class = {"header": InvoiceForm, "terms": InvoiceTermsForm}.get(section)
    if form_class is None:
        raise Http404("unknown invoice section")

    form = form_class(request.POST, instance=invoice, tenant=request.tenant)
    if form.is_valid():
        form.save()
        messages.success(request, _("Changes saved."))
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("billing:invoice_detail", pk=invoice.pk)


@require_POST
def invoice_lines_save(request: HttpRequest, pk) -> HttpResponse:
    """Save the whole items grid in one post.

    The grid edits rows in place and submits the entire table as JSON, the way
    a Frappe child table saves with its parent — not row-by-row. Each row is put
    through ``InvoiceLineForm`` so the server, not the browser, decides the tax
    and defaults; a blank row (no service chosen) is dropped rather than rejected.
    """
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    invoice = _get_invoice(request, pk)
    if blocked := _guard_editable(request, invoice):
        return blocked

    try:
        rows = json.loads(request.POST.get("lines") or "[]")
    except json.JSONDecodeError:
        rows = None
    if not isinstance(rows, list):
        messages.error(request, _("Could not read the items. Please try again."))
        return redirect("billing:invoice_detail", pk=invoice.pk)

    cleaned: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not row.get("service"):
            continue  # a blank row is a removed row, not an error
        form = InvoiceLineForm(
            {
                "service": row.get("service") or "",
                "description": row.get("description") or "",
                "quantity": row.get("quantity") or "",
                "rate": row.get("rate") or "",
            },
            tenant=request.tenant,
        )
        if form.is_valid():
            cleaned.append(form.cleaned_data)
        else:
            first_error = next(iter(form.errors.values()))[0]
            messages.error(
                request,
                _("Row %(n)d: %(error)s") % {"n": index, "error": first_error},
            )
            return redirect("billing:invoice_detail", pk=invoice.pk)

    services.replace_invoice_lines(invoice, lines=cleaned, user=request.user)
    messages.success(request, _("Items saved."))
    return redirect("billing:invoice_detail", pk=invoice.pk)


@require_POST
def invoice_issue(request: HttpRequest, pk) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    invoice = _get_invoice(request, pk)
    try:
        services.issue_invoice(invoice, user=request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, _("Invoice %(number)s issued.") % {"number": invoice.number})
    return redirect("billing:invoice_detail", pk=invoice.pk)


@require_POST
def invoice_cancel(request: HttpRequest, pk) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    invoice = _get_invoice(request, pk)
    try:
        services.cancel_invoice(invoice, user=request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, _("Invoice cancelled."))
    return redirect("billing:invoice_detail", pk=invoice.pk)


@require_POST
def invoice_credit(request: HttpRequest, pk) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    invoice = _get_invoice(request, pk)
    try:
        note = services.create_credit_note(
            invoice, user=request.user, reason=request.POST.get("reason", "")
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("billing:invoice_detail", pk=invoice.pk)
    messages.success(request, _("Credit note drafted. Review it, then issue it."))
    return redirect("billing:invoice_detail", pk=note.pk)


@require_POST
def payment_add(request: HttpRequest, pk) -> HttpResponse:
    _require_billing(request)
    require_permission(request, RECORD_PAYMENTS)
    invoice = _get_invoice(request, pk)

    form = PaymentForm(request.POST, tenant=request.tenant)
    if form.is_valid():
        try:
            services.record_payment(invoice, user=request.user, **form.cleaned_data)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, _("Payment recorded."))
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("billing:invoice_detail", pk=invoice.pk)


def invoice_print(request: HttpRequest, pk) -> HttpResponse:
    _require_billing(request)
    invoice = _get_invoice(request, pk)
    return render(
        request,
        "billing/invoice_print.html",
        {"invoice": invoice, "lines": invoice.lines.all()},
    )


# --- receivables -------------------------------------------------------------


def receivables(request: HttpRequest) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    data = services.receivables(request.tenant)
    return render(
        request,
        "billing/receivables.html",
        {
            "page_title": _("Receivables"),
            "breadcrumb": [_("Invoices"), _("Receivables")],
            **data,
        },
    )


def sponsor_statement(request: HttpRequest, sponsor_pk) -> HttpResponse:
    _require_billing(request)
    require_permission(request, MANAGE_INVOICES)
    from apps.manpower.models import Sponsor

    sponsor = get_object_or_404(Sponsor.objects.filter(tenant=request.tenant), pk=sponsor_pk)
    return render(
        request,
        "billing/statement.html",
        services.sponsor_statement(request.tenant, sponsor),
    )


# --- setup -------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def setup(request: HttpRequest, section: str = "services") -> HttpResponse:
    """Services price list and terms templates."""
    _require_billing(request)
    require_permission(request, MANAGE_BILLING_SETUP)

    if section not in BILLING_SETUP_FORMS:
        raise Http404("unknown setup section")

    model, form_class, label = BILLING_SETUP_FORMS[section]
    tenant = request.tenant

    editing_id = request.POST.get("id") or request.GET.get("edit")
    instance = (
        model.all_tenants.filter(tenant=tenant, pk=editing_id).first() if editing_id else None
    )

    if request.method == "POST":
        if request.POST.get("archive") and instance is not None:
            instance.is_active = not instance.is_active
            instance.updated_by = request.user
            instance.save(update_fields=["is_active", "updated_by", "updated_at"])
            messages.success(request, _("Changes saved."))
            return redirect("billing:setup_section", section=section)

        form = form_class(request.POST, instance=instance, tenant=tenant)
        if form.is_valid():
            record = form.save(commit=False)
            record.tenant = tenant
            if instance is None:
                record.created_by = request.user
            record.updated_by = request.user
            record.save()
            messages.success(request, _("Changes saved."))
            return redirect("billing:setup_section", section=section)
        messages.error(request, _("Please correct the errors and try again."))
    else:
        form = form_class(instance=instance, tenant=tenant)

    return render(
        request,
        "billing/setup.html",
        {
            "page_title": _("Billing setup"),
            "breadcrumb": [_("Billing setup"), label],
            "section": section,
            "section_label": label,
            "sections": [(key, value[2]) for key, value in BILLING_SETUP_FORMS.items()],
            "rows": model.objects.filter(tenant=tenant),
            "form": form,
            "editing": instance,
        },
    )
