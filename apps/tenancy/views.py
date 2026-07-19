"""Organisation-structure pages: companies -> branches -> departments.

Views orchestrate only: they resolve objects, check permission, and hand off to
``apps.tenancy.services``. Reads are open to any member of the tenant; every
mutation is owner-only.

Object lookups go through the tenant-filtered default manager, so a URL carrying
another tenant's UUID 404s rather than leaking anything.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.models import Membership
from apps.tenancy import services
from apps.tenancy.forms import BranchForm, CompanyForm, DepartmentForm
from apps.tenancy.models import Branch, Company, Department
from apps.ui.services import paginate


def _require_owner(request: HttpRequest) -> Membership:
    membership = Membership.objects.filter(
        user=request.user, tenant=request.tenant, is_owner=True
    ).first()
    if membership is None:
        raise PermissionDenied(_("Owner access is required to change the organisation structure."))
    return membership


def _is_owner(request: HttpRequest) -> bool:
    return Membership.objects.filter(
        user=request.user, tenant=request.tenant, is_owner=True
    ).exists()


def _get_company(request: HttpRequest, pk) -> Company:
    return get_object_or_404(Company.objects.filter(tenant=request.tenant), pk=pk)


def _get_branch(request: HttpRequest, company: Company, pk) -> Branch:
    return get_object_or_404(Branch.objects.filter(company=company), pk=pk)


def _show_archived(request: HttpRequest) -> bool:
    return request.GET.get("archived") == "1"


# --- companies ---------------------------------------------------------------


def company_list(request: HttpRequest) -> HttpResponse:
    include_archived = _show_archived(request)
    queryset = services.companies_for(request.tenant, include_archived=include_archived)

    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(name__icontains=search)

    page, sort_key, direction = paginate(
        request,
        queryset,
        allowed_sorts={"name": "name", "branches": "branch_count", "created": "created_at"},
        default_sort="name",
    )

    context = {
        "page_title": _("Companies"),
        "breadcrumb": [_("Companies")],
        "columns": [
            {"key": "name", "label": _("Name"), "sortable": True},
            {"key": "registration", "label": _("Registration no."), "sortable": False},
            {"key": "branches", "label": _("Branches"), "sortable": True},
            {"key": "status", "label": _("Status"), "sortable": False},
            {"key": "actions", "label": "", "sortable": False},
        ],
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "search": search,
        "include_archived": include_archived,
        "is_owner": _is_owner(request),
        "form": CompanyForm(),
    }
    if request.htmx and request.htmx.target == "companies-table":
        return render(request, "tenancy/_companies_table.html", context)
    return render(request, "tenancy/company_list.html", context)


@require_POST
def company_create(request: HttpRequest) -> HttpResponse:
    _require_owner(request)
    form = CompanyForm(request.POST)
    if form.is_valid():
        company = services.create_company(
            tenant=request.tenant, user=request.user, **form.cleaned_data
        )
        messages.success(request, _("%(name)s has been created.") % {"name": company.name})
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("tenancy:company_list")


@require_POST
def company_update(request: HttpRequest, pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    form = CompanyForm(request.POST)
    if form.is_valid():
        services.update_company(company, user=request.user, **form.cleaned_data)
        messages.success(request, _("Changes saved."))
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("tenancy:company_detail", pk=company.pk)


@require_POST
def company_archive(request: HttpRequest, pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    if company.is_active:
        services.archive_company(company, user=request.user)
        messages.success(
            request,
            _("%(name)s and everything under it were archived.") % {"name": company.name},
        )
    else:
        services.restore_company(company, user=request.user)
        messages.success(request, _("%(name)s was restored.") % {"name": company.name})
    return redirect("tenancy:company_list")


def company_detail(request: HttpRequest, pk) -> HttpResponse:
    company = _get_company(request, pk)
    include_archived = _show_archived(request)
    branches = services.branches_for(company, include_archived=include_archived)

    page, sort_key, direction = paginate(
        request,
        branches,
        allowed_sorts={"name": "name", "code": "code", "departments": "department_count"},
        default_sort="name",
    )

    context = {
        "page_title": company.name,
        "breadcrumb": [_("Companies"), company.name],
        "company": company,
        "columns": [
            {"key": "name", "label": _("Name"), "sortable": True},
            {"key": "code", "label": _("Code"), "sortable": True},
            {"key": "departments", "label": _("Departments"), "sortable": True},
            {"key": "status", "label": _("Status"), "sortable": False},
            {"key": "actions", "label": "", "sortable": False},
        ],
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "include_archived": include_archived,
        "is_owner": _is_owner(request),
        "form": BranchForm(),
        "company_form": CompanyForm(
            initial={
                "name": company.name,
                "legal_name": company.legal_name,
                "registration_no": company.registration_no,
            }
        ),
    }
    if request.htmx and request.htmx.target == "branches-table":
        return render(request, "tenancy/_branches_table.html", context)
    return render(request, "tenancy/company_detail.html", context)


# --- branches ----------------------------------------------------------------


@require_POST
def branch_create(request: HttpRequest, pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    form = BranchForm(request.POST)
    if form.is_valid():
        services.create_branch(company=company, user=request.user, **form.cleaned_data)
        messages.success(request, _("Branch created."))
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("tenancy:company_detail", pk=company.pk)


@require_POST
def branch_update(request: HttpRequest, pk, branch_pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    branch = _get_branch(request, company, branch_pk)
    form = BranchForm(request.POST)
    if form.is_valid():
        services.update_branch(branch, user=request.user, **form.cleaned_data)
        messages.success(request, _("Changes saved."))
    else:
        messages.error(request, _("Please correct the errors and try again."))
    return redirect("tenancy:branch_detail", pk=company.pk, branch_pk=branch.pk)


@require_POST
def branch_archive(request: HttpRequest, pk, branch_pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    branch = _get_branch(request, company, branch_pk)
    if branch.is_active:
        services.archive_branch(branch, user=request.user)
        messages.success(request, _("%(name)s was archived.") % {"name": branch.name})
    else:
        services.restore_branch(branch, user=request.user)
        messages.success(request, _("%(name)s was restored.") % {"name": branch.name})
    return redirect("tenancy:company_detail", pk=company.pk)


def branch_detail(request: HttpRequest, pk, branch_pk) -> HttpResponse:
    company = _get_company(request, pk)
    branch = _get_branch(request, company, branch_pk)
    include_archived = _show_archived(request)

    context = {
        "page_title": branch.name,
        "breadcrumb": [_("Companies"), company.name, branch.name],
        "company": company,
        "branch": branch,
        "rows": services.department_tree(branch, include_archived=include_archived),
        "include_archived": include_archived,
        "is_owner": _is_owner(request),
        "form": DepartmentForm(branch=branch),
        "branch_form": BranchForm(
            initial={"name": branch.name, "code": branch.code, "address": branch.address}
        ),
    }
    return render(request, "tenancy/branch_detail.html", context)


# --- departments -------------------------------------------------------------


@require_POST
def department_create(request: HttpRequest, pk, branch_pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    branch = _get_branch(request, company, branch_pk)
    form = DepartmentForm(request.POST, branch=branch)
    if form.is_valid():
        services.create_department(branch=branch, user=request.user, **form.cleaned_data)
        messages.success(request, _("Department created."))
    else:
        messages.error(request, form.errors.as_text() or _("Please correct the errors."))
    return redirect("tenancy:branch_detail", pk=company.pk, branch_pk=branch.pk)


@require_POST
def department_update(request: HttpRequest, pk, branch_pk, department_pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    branch = _get_branch(request, company, branch_pk)
    department = get_object_or_404(Department.objects.filter(branch=branch), pk=department_pk)

    form = DepartmentForm(request.POST, branch=branch, instance=department)
    if form.is_valid():
        services.update_department(department, user=request.user, **form.cleaned_data)
        messages.success(request, _("Changes saved."))
    else:
        messages.error(request, form.errors.as_text() or _("Please correct the errors."))
    return redirect("tenancy:branch_detail", pk=company.pk, branch_pk=branch.pk)


@require_POST
def department_archive(request: HttpRequest, pk, branch_pk, department_pk) -> HttpResponse:
    _require_owner(request)
    company = _get_company(request, pk)
    branch = _get_branch(request, company, branch_pk)
    department = get_object_or_404(Department.objects.filter(branch=branch), pk=department_pk)

    if department.is_active:
        services.archive_department(department, user=request.user)
        messages.success(request, _("%(name)s was archived.") % {"name": department.name})
    else:
        services.restore_department(department, user=request.user)
        messages.success(request, _("%(name)s was restored.") % {"name": department.name})
    return redirect("tenancy:branch_detail", pk=company.pk, branch_pk=branch.pk)
