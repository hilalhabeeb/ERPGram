"""Icon-rail navigation.

Central list so the shell, breadcrumb and active-state logic all agree.

The rail is a **collapsed 64px strip that expands on hover** (and on keyboard
focus) to show labels. It grew to ten entries as modules landed, and ten
unlabelled icons — several of them near-identical gears and sliders — is not
navigation anyone can learn. Entries are therefore grouped, and the group
headings only appear while expanded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from apps.core.domains import MANPOWER, applies_to
from apps.core.permissions import (
    MANAGE_BILLING_SETUP,
    MANAGE_INVOICES,
    MANAGE_MANPOWER_SETUP,
    MANAGE_MEMBERS,
    MANAGE_ORGANIZATION,
)


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    url_name: str
    # Codename from apps.core.permissions; None means every member may open it.
    requires: str | None = None
    # Domains this entry belongs to; None means every domain.
    domains: tuple[str, ...] | None = None
    # Heading this entry sits under while the rail is expanded.
    group: str = ""


@dataclass(frozen=True)
class NavGroup:
    label: str
    items: list[NavItem] = field(default_factory=list)


# icon= is passed by keyword so the icon-audit test (tests/test_icons.py) sees it.
PRIMARY_NAV: list[NavItem] = [
    NavItem("dashboard", _("Dashboard"), icon="layout-dashboard", url_name="ui:dashboard"),
    # --- manpower domain ---
    NavItem(
        "workers",
        _("Workers"),
        icon="users",
        url_name="manpower:worker_list",
        domains=(MANPOWER,),
        group=_("Operations"),
    ),
    NavItem(
        "sponsors",
        _("Sponsors"),
        icon="user-check",
        url_name="manpower:sponsor_list",
        domains=(MANPOWER,),
        group=_("Operations"),
    ),
    NavItem(
        "placements",
        _("Placements"),
        icon="briefcase",
        url_name="manpower:placement_list",
        domains=(MANPOWER,),
        group=_("Operations"),
    ),
    NavItem(
        "invoices",
        _("Invoices"),
        icon="file-text",
        url_name="billing:invoice_list",
        requires=MANAGE_INVOICES,
        domains=(MANPOWER,),
        group=_("Accounting"),
    ),
    # --- shared core ---
    NavItem(
        "companies",
        _("Companies"),
        icon="building",
        url_name="tenancy:company_list",
        group=_("Setup"),
    ),
    NavItem(
        "manpower_setup",
        _("Manpower setup"),
        icon="sliders",
        url_name="manpower:setup",
        requires=MANAGE_MANPOWER_SETUP,
        domains=(MANPOWER,),
        group=_("Setup"),
    ),
    NavItem(
        "billing_setup",
        _("Billing setup"),
        icon="settings-2",
        url_name="billing:setup",
        requires=MANAGE_BILLING_SETUP,
        domains=(MANPOWER,),
        group=_("Setup"),
    ),
    NavItem(
        "users",
        _("Users"),
        icon="user",
        url_name="ui:settings_users",
        requires=MANAGE_MEMBERS,
        group=_("Setup"),
    ),
    NavItem(
        "organization",
        _("Organisation"),
        icon="settings",
        url_name="ui:settings_organization",
        requires=MANAGE_ORGANIZATION,
        group=_("Setup"),
    ),
]


def nav_for(permissions, tenant_domain: str | None = None) -> list[NavItem]:
    """Rail entries this user can actually reach — never advertise a 403.

    Filtered on both axes: the tenant's industry decides what exists, the user's
    permissions decide what they may open.
    """
    held = frozenset(permissions or ())
    return [
        item
        for item in PRIMARY_NAV
        if applies_to(item.domains, tenant_domain)
        and (item.requires is None or item.requires in held)
    ]


def nav_groups(permissions, tenant_domain: str | None = None) -> list[NavGroup]:
    """The same entries, bucketed under their headings and in declared order."""
    groups: list[NavGroup] = []
    for item in nav_for(permissions, tenant_domain):
        label = str(item.group)
        if not groups or groups[-1].label != label:
            groups.append(NavGroup(label=label, items=[]))
        groups[-1].items.append(item)
    return groups


def active_nav_key(view_name: str | None, namespace: str | None) -> str | None:
    """Which rail entry should be highlighted for the current view.

    Exact match first; then fall back to the URL namespace so a nested page like
    /companies/<id>/branches/<id>/ still lights up "Companies". The ``ui``
    namespace is excluded from the fallback because it spans several rail
    entries (dashboard, users, organisation) and would match them all.
    """
    if not view_name:
        return None
    for item in PRIMARY_NAV:
        if item.url_name == view_name:
            return item.key
    if namespace and namespace != "ui":
        for item in PRIMARY_NAV:
            if item.url_name.split(":")[0] == namespace:
                return item.key
    return None
