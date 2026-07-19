"""App-shell pages: dashboard, settings, and styled error handlers."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import InviteForm, OrganizationForm, ProfileForm
from apps.accounts.models import Membership
from apps.accounts.services import invite_member, send_invitation_email
from apps.tenancy.services import update_organization
from apps.ui.services import dashboard_stats, paginate, settings_tabs


def _owner_membership(request: HttpRequest) -> Membership | None:
    return Membership.objects.filter(
        user=request.user, tenant=request.tenant, is_owner=True
    ).first()


def _require_owner(request: HttpRequest) -> Membership:
    membership = _owner_membership(request)
    if membership is None:
        raise PermissionDenied(_("Owner access is required for this page."))
    return membership


def _settings_context(request: HttpRequest, active: str) -> dict:
    """Shared chrome for every settings page: breadcrumb trail and sub-nav tabs."""
    is_owner = _owner_membership(request) is not None
    return {
        "active": active,
        "is_owner": is_owner,
        "tabs": settings_tabs(is_owner=is_owner),
    }


def dashboard(request: HttpRequest) -> HttpResponse:
    range_options = [
        {"value": "yearly", "label": _("Yearly")},
        {"value": "monthly", "label": _("Monthly")},
        {"value": "weekly", "label": _("Weekly")},
    ]
    return render(
        request,
        "ui/dashboard.html",
        {
            "page_title": _("Dashboard"),
            "breadcrumb": [],  # root crumb is rendered by the shell
            "stats": dashboard_stats(),
            "range_options": range_options,
        },
    )


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
    _require_owner(request)
    tenant = request.tenant
    initial = {
        "name": tenant.name,
        "timezone": tenant.timezone,
        "default_locale": tenant.default_locale,
    }
    form = OrganizationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        update_organization(
            tenant,
            name=form.cleaned_data["name"],
            timezone=form.cleaned_data["timezone"],
            default_locale=form.cleaned_data["default_locale"],
        )
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
    form = InviteForm(request.POST or None)
    if request.method == "POST":
        _require_owner(request)
        if form.is_valid():
            membership, created_user = invite_member(
                tenant=request.tenant,
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                invited_by=request.user,
                is_owner=form.cleaned_data["is_owner"],
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

    members = Membership.objects.filter(tenant=request.tenant).select_related("user")
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
        **_settings_context(request, "users"),
    }
    if request.htmx and request.htmx.target == "users-table":
        return render(request, "ui/settings/_users_table.html", context)
    return render(request, "ui/settings/users.html", context)


# --- error handlers ---------------------------------------------------------


def error_403(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def error_404(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def error_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)
