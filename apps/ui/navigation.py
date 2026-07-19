"""Icon-rail navigation definition.

Central list so the shell, breadcrumb, and active-state logic all agree.
Business modules will append their own entries here in later steps.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    url_name: str
    owner_only: bool = False


# icon= is passed by keyword so the icon-audit test (tests/test_icons.py) sees it.
PRIMARY_NAV: list[NavItem] = [
    NavItem("dashboard", _("Dashboard"), icon="layout-dashboard", url_name="ui:dashboard"),
    NavItem("companies", _("Companies"), icon="building", url_name="tenancy:company_list"),
    NavItem("profile", _("Profile"), icon="user", url_name="ui:settings_profile"),
    NavItem(
        "organization",
        _("Organisation"),
        # "building" now belongs to Companies; settings uses the gear.
        icon="settings",
        url_name="ui:settings_organization",
        owner_only=True,
    ),
    NavItem("users", _("Users"), icon="users", url_name="ui:settings_users"),
]


def nav_for(*, is_owner: bool) -> list[NavItem]:
    """Rail entries this user can actually reach — never advertise a 403."""
    return [item for item in PRIMARY_NAV if not item.owner_only or is_owner]


def active_nav_key(view_name: str | None, namespace: str | None) -> str | None:
    """Which rail entry should be highlighted for the current view.

    Exact match first; then fall back to the URL namespace so a nested page like
    /companies/<id>/branches/<id>/ still lights up "Companies". The ``ui``
    namespace is excluded from the fallback because it spans several rail
    entries (dashboard, profile, settings) and would match them all.
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
