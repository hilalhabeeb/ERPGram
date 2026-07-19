"""Template context shared by the app shell on every authenticated page."""

from __future__ import annotations

from django.http import HttpRequest

from apps.accounts.services import memberships_for
from apps.ui.navigation import active_nav_key, nav_for


def shell(request: HttpRequest) -> dict:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav_items": [], "tenant_memberships": []}

    tenant = getattr(request, "tenant", None)
    memberships = memberships_for(user)
    current = next((m for m in memberships if tenant and m.tenant_id == tenant.id), None)

    match = getattr(request, "resolver_match", None)

    return {
        "nav_items": nav_for(is_owner=bool(current and current.is_owner)),
        "active_nav": active_nav_key(
            getattr(match, "view_name", None), getattr(match, "namespace", None)
        ),
        "current_tenant": tenant,
        "current_membership": current,
        "tenant_memberships": memberships,
    }
