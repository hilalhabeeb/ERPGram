"""UI-layer read helpers: dashboard stats and generic table pagination/sorting."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.tenancy.models import Branch, Company, Department


@dataclass(frozen=True)
class Stat:
    key: str
    label: str
    value: int
    icon: str


@dataclass(frozen=True)
class SettingsTab:
    key: str
    label: str
    url_name: str


def settings_tabs(*, is_owner: bool) -> list[SettingsTab]:
    """Tabs for the settings section; owner-only pages are omitted for members."""
    from django.utils.translation import gettext as _

    tabs = [SettingsTab("profile", _("Profile"), "ui:settings_profile")]
    if is_owner:
        tabs.append(SettingsTab("organization", _("Organisation"), "ui:settings_organization"))
    tabs.append(SettingsTab("users", _("Users"), "ui:settings_users"))
    return tabs


def dashboard_stats() -> list[Stat]:
    """Counts for the active tenant (managers are tenant-filtered)."""
    from django.utils.translation import gettext as _

    # icon= is passed by keyword so the icon-audit test can find these names.
    return [
        Stat("companies", _("Companies"), Company.objects.count(), icon="building"),
        Stat("branches", _("Branches"), Branch.objects.count(), icon="git-branch"),
        Stat("departments", _("Departments"), Department.objects.count(), icon="network"),
    ]


def paginate(
    request: HttpRequest,
    queryset: QuerySet,
    *,
    allowed_sorts: dict[str, str],
    default_sort: str,
    per_page: int = 10,
) -> tuple[Page, str, str]:
    """Apply request-driven sorting + pagination.

    ``allowed_sorts`` maps a public column key to an ORM field, guarding against
    arbitrary ``order_by`` injection. Returns ``(page, sort_key, direction)``.
    """
    sort_key = request.GET.get("sort", default_sort)
    if sort_key not in allowed_sorts:
        sort_key = default_sort
    direction = "desc" if request.GET.get("dir") == "desc" else "asc"
    field = allowed_sorts[sort_key]
    order = f"-{field}" if direction == "desc" else field

    queryset = queryset.order_by(order)
    paginator = Paginator(queryset, per_page)
    page = paginator.get_page(request.GET.get("page"))
    return page, sort_key, direction
