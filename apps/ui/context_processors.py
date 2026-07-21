"""Template context shared by the app shell on every page."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest
from django.urls import translate_url
from django.utils.translation import get_language

from apps.accounts.permissions import request_permissions
from apps.accounts.services import memberships_for
from apps.ui.navigation import active_nav_key, nav_for


def language_links(request: HttpRequest) -> dict:
    """The current page's URL in every available language.

    Computed here, during the page render, because that is the only moment the
    translation is possible: ``translate_url`` has to ``resolve()`` the path, and
    an ``/ar/...`` path only resolves while Arabic is the active language.

    The language switcher posts to ``set_language``, which lives outside
    ``i18n_patterns``; with ``prefix_default_language=False`` the middleware
    forces English there, so by the time that view runs the Arabic path no longer
    resolves and Django's own translation silently returns it unchanged —
    redirecting the user straight back to the page they were trying to leave.
    Handing it an already-translated ``next`` avoids that entirely.
    """
    current = get_language()
    path = request.get_full_path()

    links = []
    for code, name in settings.LANGUAGES:
        try:
            url = translate_url(path, code)
        except Exception:  # noqa: BLE001 - a broken URL must not break the page
            url = path
        links.append({"code": code, "name": name, "url": url, "is_current": code == current})

    return {"language_links": links}


def shell(request: HttpRequest) -> dict:
    context = language_links(request)

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        # Anonymous pages (login, sign-up) still need the language switcher.
        return {**context, "nav_items": [], "tenant_memberships": []}

    tenant = getattr(request, "tenant", None)
    memberships = memberships_for(user)
    current = next((m for m in memberships if tenant and m.tenant_id == tenant.id), None)

    match = getattr(request, "resolver_match", None)
    permissions = request_permissions(request)

    return {
        **context,
        # Templates gate actions with `{% if "code" in user_permissions %}`.
        "user_permissions": permissions,
        "tenant_domain": getattr(tenant, "domain", None),
        "nav_items": nav_for(permissions, getattr(tenant, "domain", None)),
        "active_nav": active_nav_key(
            getattr(match, "view_name", None), getattr(match, "namespace", None)
        ),
        "current_tenant": tenant,
        "current_membership": current,
        "tenant_memberships": memberships,
    }
