"""Manpower pages: workers, sponsors and the setup lists.

Every view is gated twice — the tenant must be in the manpower domain, and the
user must hold the relevant permission. Reads are open to any member; writes
need the permission.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import has_permission, require_permission
from apps.billing import services as billing_services
from apps.billing.models import Service
from apps.core.domains import MANPOWER
from apps.core.permissions import (
    MANAGE_INVOICES,
    MANAGE_MANPOWER_SETUP,
    MANAGE_PLACEMENTS,
    MANAGE_SPONSORS,
    MANAGE_WORKERS,
)
from apps.manpower import services
from apps.manpower.forms import (
    SETUP_FORMS,
    PlacementAgreementForm,
    PlacementForm,
    PlacementPipelineForm,
    SponsorForm,
    WorkerForm,
)
from apps.manpower.models import Country, Occupation, Placement, Sponsor, Worker
from apps.ui.services import paginate


def _require_manpower(request: HttpRequest) -> None:
    """404 rather than 403 for tenants outside this industry.

    The feature does not exist for them, so revealing that the URL is a real
    endpoint would be misleading.
    """
    if getattr(request.tenant, "domain", None) != MANPOWER:
        raise Http404("manpower module is not enabled for this tenant")


# --- workers -----------------------------------------------------------------


def worker_list(request: HttpRequest) -> HttpResponse:
    _require_manpower(request)
    tenant = request.tenant

    filters = {
        "search": request.GET.get("q", "").strip(),
        "occupation": request.GET.get("occupation", ""),
        "nationality": request.GET.get("nationality", ""),
        "availability": request.GET.get("availability", ""),
        "location": request.GET.get("location", ""),
        "include_archived": request.GET.get("archived") == "1",
    }
    queryset = services.workers_for(tenant, **filters)

    page, sort_key, direction = paginate(
        request,
        queryset,
        allowed_sorts={
            "reference": "reference",
            "name": "full_name",
            "occupation": "occupation__name",
            "nationality": "nationality__name",
            "experience": "experience_years",
        },
        default_sort="reference",
    )

    context = {
        "page_title": _("Workers"),
        "breadcrumb": [_("Workers")],
        "columns": [
            {"key": "reference", "label": _("Ref"), "sortable": True},
            {"key": "name", "label": _("Worker"), "sortable": True},
            {"key": "occupation", "label": _("Occupation"), "sortable": True},
            {
                "key": "nationality",
                "label": _("Nationality"),
                "sortable": True,
                "css": "hidden lg:table-cell",
            },
            {
                "key": "experience",
                "label": _("Experience"),
                "sortable": True,
                "css": "hidden xl:table-cell",
            },
            {"key": "availability", "label": _("Availability"), "sortable": False},
            {"key": "location", "label": _("Location"), "sortable": False},
        ],
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "stats": services.worker_summary(tenant),
        "occupations": Occupation.objects.filter(tenant=tenant, is_active=True),
        "nationalities": Country.objects.filter(is_source=True),
        "availability_choices": Worker.Availability.choices,
        "location_choices": Worker.Location.choices,
        "filters": filters,
        "can_manage": has_permission(request, MANAGE_WORKERS),
    }
    if request.htmx and request.htmx.target == "workers-table":
        return render(request, "manpower/_workers_table.html", context)
    return render(request, "manpower/worker_list.html", context)


def worker_detail(request: HttpRequest, pk) -> HttpResponse:
    _require_manpower(request)
    worker = get_object_or_404(
        Worker.objects.filter(tenant=request.tenant).select_related(
            "nationality", "occupation", "agent", "accommodation"
        ),
        pk=pk,
    )
    return render(
        request,
        "manpower/worker_detail.html",
        {
            "page_title": worker.full_name,
            "breadcrumb": [_("Workers"), worker.full_name],
            "worker": worker,
            "documents": worker.documents.select_related("document_type"),
            "can_manage": has_permission(request, MANAGE_WORKERS),
        },
    )


@require_http_methods(["GET", "POST"])
def worker_form(request: HttpRequest, pk=None) -> HttpResponse:
    _require_manpower(request)
    require_permission(request, MANAGE_WORKERS)
    tenant = request.tenant

    worker = get_object_or_404(Worker.objects.filter(tenant=tenant), pk=pk) if pk else None
    form = WorkerForm(request.POST or None, request.FILES or None, instance=worker, tenant=tenant)

    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        skills = data.pop("skills", None)
        languages = data.pop("languages", None)
        if worker is None:
            saved = services.create_worker(
                tenant=tenant, user=request.user, skills=skills, languages=languages, **data
            )
            messages.success(request, _("%(name)s has been added.") % {"name": saved.full_name})
        else:
            saved = services.update_worker(
                worker, user=request.user, skills=skills, languages=languages, **data
            )
            messages.success(request, _("Changes saved."))
        return redirect("manpower:worker_detail", pk=saved.pk)

    return render(
        request,
        "manpower/worker_form.html",
        {
            "page_title": _("Edit worker") if worker else _("Add worker"),
            "breadcrumb": [_("Workers"), worker.full_name if worker else _("Add worker")],
            "form": form,
            "worker": worker,
        },
    )


@require_POST
def worker_archive(request: HttpRequest, pk) -> HttpResponse:
    _require_manpower(request)
    require_permission(request, MANAGE_WORKERS)
    worker = get_object_or_404(Worker.objects.filter(tenant=request.tenant), pk=pk)
    services.set_worker_active(worker, user=request.user, is_active=not worker.is_active)
    messages.success(
        request,
        _("%(name)s was restored.") % {"name": worker.full_name}
        if worker.is_active
        else _("%(name)s was archived.") % {"name": worker.full_name},
    )
    return redirect("manpower:worker_list")


# --- sponsors ----------------------------------------------------------------


def sponsor_list(request: HttpRequest) -> HttpResponse:
    _require_manpower(request)
    tenant = request.tenant
    search = request.GET.get("q", "").strip()
    include_archived = request.GET.get("archived") == "1"

    queryset = services.sponsors_for(tenant, search=search, include_archived=include_archived)
    page, sort_key, direction = paginate(
        request,
        queryset,
        allowed_sorts={"name": "name", "area": "area", "created": "created_at"},
        default_sort="name",
    )

    context = {
        "page_title": _("Sponsors"),
        "breadcrumb": [_("Sponsors")],
        "columns": [
            {"key": "name", "label": _("Sponsor"), "sortable": True},
            {"key": "id", "label": _("National ID / CPR"), "sortable": False},
            {"key": "phone", "label": _("Phone"), "sortable": False},
            {"key": "area", "label": _("Area"), "sortable": True},
            {"key": "status", "label": _("Status"), "sortable": False},
            {"key": "actions", "label": "", "sortable": False},
        ],
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "search": search,
        "include_archived": include_archived,
        "form": SponsorForm(tenant=tenant),
        "can_manage": has_permission(request, MANAGE_SPONSORS),
    }
    if request.htmx and request.htmx.target == "sponsors-table":
        return render(request, "manpower/_sponsors_table.html", context)
    return render(request, "manpower/sponsor_list.html", context)


@require_POST
def sponsor_create(request: HttpRequest) -> HttpResponse:
    _require_manpower(request)
    require_permission(request, MANAGE_SPONSORS)
    form = SponsorForm(request.POST, tenant=request.tenant)
    if form.is_valid():
        sponsor = services.create_sponsor(
            tenant=request.tenant, user=request.user, **form.cleaned_data
        )
        messages.success(request, _("%(name)s has been added.") % {"name": sponsor.name})
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("manpower:sponsor_list")


@require_POST
def sponsor_archive(request: HttpRequest, pk) -> HttpResponse:
    _require_manpower(request)
    require_permission(request, MANAGE_SPONSORS)
    sponsor = get_object_or_404(Sponsor.objects.filter(tenant=request.tenant), pk=pk)
    services.set_sponsor_active(sponsor, user=request.user, is_active=not sponsor.is_active)
    messages.success(request, _("Changes saved."))
    return redirect("manpower:sponsor_list")


# --- placements --------------------------------------------------------------


def placement_list(request: HttpRequest) -> HttpResponse:
    _require_manpower(request)
    tenant = request.tenant
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    page, sort_key, direction = paginate(
        request,
        services.placements_for(tenant, search=search, status=status),
        allowed_sorts={"reference": "reference", "created": "created_at"},
        default_sort="created",
    )

    context = {
        "page_title": _("Placements"),
        "breadcrumb": [_("Placements")],
        "columns": [
            {"key": "reference", "label": _("Ref"), "sortable": True},
            {"key": "worker", "label": _("Worker"), "sortable": False},
            {"key": "sponsor", "label": _("Sponsor"), "sortable": False},
            {
                "key": "route",
                "label": _("Route"),
                "sortable": False,
                "css": "hidden lg:table-cell",
            },
            {"key": "status", "label": _("Status"), "sortable": False},
            {"key": "billing", "label": _("Billing"), "sortable": False},
        ],
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "search": search,
        "status": status,
        "status_choices": Placement.Status.choices,
        "stats": services.placement_summary(tenant),
        "can_manage": has_permission(request, MANAGE_PLACEMENTS),
        "form": PlacementForm(tenant=tenant),
    }
    if request.htmx and request.htmx.target == "placements-table":
        return render(request, "manpower/_placements_table.html", context)
    return render(request, "manpower/placement_list.html", context)


def _get_placement(request: HttpRequest, pk) -> Placement:
    return get_object_or_404(
        Placement.objects.filter(tenant=request.tenant).select_related("sponsor", "worker"),
        pk=pk,
    )


def placement_detail(request: HttpRequest, pk) -> HttpResponse:
    _require_manpower(request)
    placement = _get_placement(request, pk)
    return render(
        request,
        "manpower/placement_detail.html",
        {
            "page_title": placement.reference,
            "breadcrumb": [_("Placements"), placement.reference],
            "placement": placement,
            "invoices": placement.invoices.prefetch_related("lines", "payments"),
            "agreement_form": PlacementAgreementForm(instance=placement, tenant=request.tenant),
            "pipeline_form": PlacementPipelineForm(instance=placement, tenant=request.tenant),
            "can_manage": has_permission(request, MANAGE_PLACEMENTS),
            "can_invoice": has_permission(request, MANAGE_INVOICES),
        },
    )


@require_POST
def placement_create(request: HttpRequest) -> HttpResponse:
    _require_manpower(request)
    require_permission(request, MANAGE_PLACEMENTS)
    form = PlacementForm(request.POST, tenant=request.tenant)
    if form.is_valid():
        data = dict(form.cleaned_data)
        placement = services.create_placement(
            tenant=request.tenant,
            user=request.user,
            sponsor=data.pop("sponsor"),
            worker=data.pop("worker"),
            **data,
        )
        messages.success(request, _("Placement %(ref)s opened.") % {"ref": placement.reference})
        return redirect("manpower:placement_detail", pk=placement.pk)
    messages.error(request, _("Please correct the errors and try again."))
    return redirect("manpower:placement_list")


@require_POST
def placement_update(request: HttpRequest, pk, section: str) -> HttpResponse:
    """Save one section of the placement (agreement wording or pipeline dates)."""
    _require_manpower(request)
    require_permission(request, MANAGE_PLACEMENTS)
    placement = _get_placement(request, pk)

    form_class = {
        "agreement": PlacementAgreementForm,
        "pipeline": PlacementPipelineForm,
    }.get(section)
    if form_class is None:
        raise Http404("unknown placement section")

    form = form_class(request.POST, instance=placement, tenant=request.tenant)
    if form.is_valid():
        services.update_placement(placement, user=request.user, **form.cleaned_data)
        messages.success(request, _("Changes saved."))
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("manpower:placement_detail", pk=placement.pk)


@require_POST
def placement_status(request: HttpRequest, pk) -> HttpResponse:
    _require_manpower(request)
    require_permission(request, MANAGE_PLACEMENTS)
    placement = _get_placement(request, pk)

    status = request.POST.get("status", "")
    if status not in Placement.Status.values:
        raise Http404("unknown status")

    services.set_placement_status(placement, user=request.user, status=status)
    messages.success(request, _("Placement updated."))
    return redirect("manpower:placement_detail", pk=placement.pk)


@require_POST
def placement_invoice(request: HttpRequest, pk) -> HttpResponse:
    """Raise a draft invoice for this placement, pre-filled from the price list."""
    _require_manpower(request)
    require_permission(request, MANAGE_INVOICES)
    placement = _get_placement(request, pk)

    invoice = billing_services.create_invoice(
        tenant=request.tenant,
        user=request.user,
        sponsor=placement.sponsor,
        placement=placement,
        services=list(Service.objects.filter(tenant=request.tenant, is_active=True)),
        payment_terms=placement.payment_terms,
    )
    messages.success(request, _("Draft invoice created. Check the lines, then issue it."))
    return redirect("billing:invoice_detail", pk=invoice.pk)


def placement_print(request: HttpRequest, pk) -> HttpResponse:
    """The signed agreement. Money is on the invoice, which prints separately."""
    _require_manpower(request)
    placement = _get_placement(request, pk)
    return render(request, "manpower/placement_print.html", {"placement": placement})


# --- setup -------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def setup(request: HttpRequest, section: str = "occupations") -> HttpResponse:
    """One page with a tab per lookup list."""
    _require_manpower(request)
    require_permission(request, MANAGE_MANPOWER_SETUP)

    if section not in SETUP_FORMS:
        raise Http404("unknown setup section")

    model, form_class, label = SETUP_FORMS[section]
    tenant = request.tenant

    editing_id = request.POST.get("id") or request.GET.get("edit")
    instance = (
        model.all_tenants.filter(tenant=tenant, pk=editing_id).first() if editing_id else None
    )

    if request.method == "POST":
        if request.POST.get("archive"):
            if instance is None:
                raise PermissionDenied(_("That record is not available."))
            instance.is_active = not instance.is_active
            instance.updated_by = request.user
            instance.save(update_fields=["is_active", "updated_by", "updated_at"])
            messages.success(request, _("Changes saved."))
            return redirect("manpower:setup_section", section=section)

        form = form_class(request.POST, instance=instance, tenant=tenant)
        if form.is_valid():
            record = form.save(commit=False)
            record.tenant = tenant
            if instance is None:
                record.created_by = request.user
            record.updated_by = request.user
            record.save()
            form.save_m2m()
            messages.success(request, _("Changes saved."))
            return redirect("manpower:setup_section", section=section)
        messages.error(request, _("Please correct the errors and try again."))
    else:
        form = form_class(instance=instance, tenant=tenant)

    rows = model.objects.filter(tenant=tenant).order_by("name")

    return render(
        request,
        "manpower/setup.html",
        {
            "page_title": _("Manpower setup"),
            "breadcrumb": [_("Manpower setup"), label],
            "section": section,
            "section_label": label,
            "sections": [(key, value[2]) for key, value in SETUP_FORMS.items()],
            "rows": rows,
            "form": form,
            "editing": instance,
        },
    )


def worker_cv(request: HttpRequest, pk) -> HttpResponse:
    """The worker's biodata sheet — what an agency sends a sponsor to choose from.

    Print-styled HTML for the same reason as the invoice: no PDF dependency, and
    RTL renders correctly because it is the browser doing the layout.
    """
    _require_manpower(request)
    worker = get_object_or_404(
        Worker.objects.filter(tenant=request.tenant).select_related(
            "nationality", "occupation", "agent"
        ),
        pk=pk,
    )
    return render(
        request,
        "manpower/worker_cv.html",
        {
            "worker": worker,
            "skills": worker.skills.all(),
            "languages": worker.languages.all(),
        },
    )
