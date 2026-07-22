"""App-shell pages: dashboard, settings, and styled error handlers."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import InviteForm, OrganizationForm, ProfileForm, RoleForm
from apps.accounts.models import Membership, Role
from apps.accounts.permissions import has_permission, request_permissions, require_permission
from apps.accounts.services import (
    create_role,
    invite_member,
    roles_for,
    send_invitation_email,
    update_role,
)
from apps.core.domains import MANPOWER
from apps.core.permissions import (
    MANAGE_INVOICES,
    MANAGE_MEMBERS,
    MANAGE_ORGANIZATION,
    MANAGE_ROLES,
    grouped_permissions,
)
from apps.tenancy.services import update_organization
from apps.ui.services import dashboard_stats, paginate, settings_tabs


def _settings_context(request: HttpRequest, active: str) -> dict:
    """Shared chrome for every settings page: sub-nav tabs and action gating."""
    permissions = request_permissions(request)
    return {
        "active": active,
        "can_manage_organization": MANAGE_ORGANIZATION in permissions,
        "can_manage_members": MANAGE_MEMBERS in permissions,
        "can_manage_roles": MANAGE_ROLES in permissions,
        "tabs": settings_tabs(
            can_manage_organization=MANAGE_ORGANIZATION in permissions,
            can_manage_roles=MANAGE_ROLES in permissions,
        ),
    }


def dashboard(request: HttpRequest) -> HttpResponse:
    range_options = [
        {"value": "yearly", "label": _("Yearly")},
        {"value": "monthly", "label": _("Monthly")},
        {"value": "weekly", "label": _("Weekly")},
    ]

    # The dashboard follows the tenant's industry. A manpower agency has no
    # interest in a branch count; it wants to know who is placeable and what
    # paperwork is about to expire.
    context = {
        "page_title": _("Dashboard"),
        "breadcrumb": [],  # root crumb is rendered by the shell
        "range_options": range_options,
    }

    if getattr(request.tenant, "domain", None) == MANPOWER:
        from apps.billing import services as billing_services
        from apps.manpower import services as manpower_services

        # Grouped rather than one undifferentiated row: "18 available workers"
        # and "2 unpaid invoices" are different questions and read as noise when
        # shown side by side in identical cards.
        context.update(
            stat_groups=[
                {
                    "label": _("Workers"),
                    "stats": manpower_services.worker_summary(request.tenant),
                },
                {
                    "label": _("Placements"),
                    "stats": manpower_services.placement_summary(request.tenant),
                },
            ],
            money_stats=billing_services.billing_summary(request.tenant)
            if has_permission(request, MANAGE_INVOICES)
            else [],
            expiring=manpower_services.expiring_documents(request.tenant),
            recent_placements=manpower_services.placements_for(request.tenant)[:5],
            is_manpower=True,
        )
    else:
        context.update(stat_groups=[{"label": "", "stats": dashboard_stats()}])

    return render(request, "ui/dashboard.html", context)


@require_http_methods(["GET", "POST"])
def settings_profile(request: HttpRequest) -> HttpResponse:
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Your profile has been updated."))
        return redirect("ui:settings_profile")
    return render(
        request,
        "ui/settings/profile.html",
        {
            "page_title": _("Profile"),
            "breadcrumb": [_("Settings"), _("Profile")],
            "form": form,
            **_settings_context(request, "profile"),
        },
    )


@require_http_methods(["GET", "POST"])
def settings_organization(request: HttpRequest) -> HttpResponse:
    require_permission(request, MANAGE_ORGANIZATION)
    tenant = request.tenant
    fields = [
        "name",
        "timezone",
        "default_locale",
        "legal_name",
        "currency",
        "vat_number",
        "cr_number",
        "default_tax_rate",
        "phone",
        "email",
        "address",
    ]
    initial = {name: getattr(tenant, name) for name in fields}
    form = OrganizationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        update_organization(tenant, **form.cleaned_data)
        messages.success(request, _("Organisation settings saved."))
        return redirect("ui:settings_organization")
    return render(
        request,
        "ui/settings/organization.html",
        {
            "page_title": _("Organisation"),
            "breadcrumb": [_("Settings"), _("Organisation")],
            "form": form,
            **_settings_context(request, "organization"),
        },
    )


@require_http_methods(["GET", "POST"])
def settings_users(request: HttpRequest) -> HttpResponse:
    form = InviteForm(request.POST or None, tenant=request.tenant)
    if request.method == "POST":
        require_permission(request, MANAGE_MEMBERS)
        if form.is_valid():
            membership, created_user = invite_member(
                tenant=request.tenant,
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                invited_by=request.user,
                role=form.cleaned_data["role"],
            )
            if created_user:
                send_invitation_email(request, membership.user, request.tenant)
                messages.success(
                    request, _("Invitation sent to %(email)s.") % {"email": membership.user.email}
                )
            else:
                messages.info(
                    request,
                    _("%(email)s was added to this organisation.")
                    % {"email": membership.user.email},
                )
            return redirect("ui:settings_users")

    members = Membership.objects.filter(tenant=request.tenant).select_related("user", "role")
    page, sort_key, direction = paginate(
        request,
        members,
        allowed_sorts={
            "name": "user__full_name",
            "email": "user__email",
            "joined": "joined_at",
        },
        default_sort="name",
    )

    columns = [
        {"key": "name", "label": _("Name"), "sortable": True},
        {"key": "email", "label": _("Email"), "sortable": True},
        {"key": "role", "label": _("Role"), "sortable": False},
        {"key": "status", "label": _("Status"), "sortable": False},
        {"key": "joined", "label": _("Joined"), "sortable": True},
    ]

    context = {
        "page_title": _("Users"),
        "breadcrumb": [_("Settings"), _("Users")],
        "form": form,
        "columns": columns,
        "page_obj": page,
        "sort_key": sort_key,
        "direction": direction,
        "assignable_roles": roles_for(request.tenant),
        **_settings_context(request, "users"),
    }
    if request.htmx and request.htmx.target == "users-table":
        return render(request, "ui/settings/_users_table.html", context)
    return render(request, "ui/settings/users.html", context)


@require_http_methods(["GET", "POST"])
def settings_roles(request: HttpRequest) -> HttpResponse:
    """List and edit the tenant's roles."""
    require_permission(request, MANAGE_ROLES)
    tenant = request.tenant

    if request.method == "POST":
        role_id = request.POST.get("role_id")
        selected = request.POST.getlist("permissions")

        if role_id:
            role = get_object_or_404(Role.objects.filter(tenant=tenant), pk=role_id)
            if role.slug == "owner":
                # Owners hold every permission implicitly; letting this role be
                # weakened would imply a restriction the code does not honour.
                messages.error(request, _("The Owner role always has full access."))
                return redirect("ui:settings_roles")
            form = RoleForm(request.POST, instance=role)
            if form.is_valid():
                update_role(role, name=form.cleaned_data["name"], permissions=selected)
                messages.success(request, _("Role updated."))
                return redirect("ui:settings_roles")
        else:
            form = RoleForm(request.POST)
            if form.is_valid():
                create_role(tenant=tenant, name=form.cleaned_data["name"], permissions=selected)
                messages.success(request, _("Role created."))
                return redirect("ui:settings_roles")
        messages.error(request, _("Please correct the errors and try again."))
        return redirect("ui:settings_roles")

    roles = roles_for(tenant).annotate(member_count=Count("memberships"))
    return render(
        request,
        "ui/settings/roles.html",
        {
            "page_title": _("Roles"),
            "breadcrumb": [_("Settings"), _("Roles")],
            "roles": roles,
            "groups": grouped_permissions(),
            "form": RoleForm(),
            **_settings_context(request, "roles"),
        },
    )


@require_POST
def member_role_update(request: HttpRequest, membership_id) -> HttpResponse:
    """Change one member's role from the users table."""
    require_permission(request, MANAGE_MEMBERS)
    membership = get_object_or_404(
        Membership.objects.filter(tenant=request.tenant), pk=membership_id
    )
    if membership.is_owner:
        messages.error(request, _("Owners always have full access; their role cannot limit it."))
        return redirect("ui:settings_users")

    role_id = request.POST.get("role") or None
    role = Role.objects.filter(tenant=request.tenant, pk=role_id).first() if role_id else None
    membership.role = role
    membership.save(update_fields=["role"])
    messages.success(request, _("Role updated."))
    return redirect("ui:settings_users")


# --- error handlers ---------------------------------------------------------


def error_403(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def error_404(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def error_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)
