"""Authorization: one place that decides what a user may do in a tenant.

``has_permission`` is the only function that should ever be consulted. Views
call ``require_permission``; templates read the ``user_permissions`` set put in
the context by ``apps.ui.context_processors.shell``.

Two rules the rest of the codebase depends on:

* A tenant **owner** implicitly holds every permission. Without this, an owner
  could edit roles until nobody — including themselves — could administer the
  tenant, and there would be no way back in through the product.
* A membership with **no role** holds nothing. Access is granted explicitly,
  never by default.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.utils.translation import gettext as _

from apps.accounts.models import Membership
from apps.core.permissions import codenames_for_domain

# Cached on the request: several template fragments and view branches ask the
# same question during one render, and this is a database round-trip.
_CACHE_ATTR = "_tenant_permissions_cache"


def permissions_for(user, tenant) -> frozenset[str]:
    """Every permission codename `user` holds in `tenant`."""
    if user is None or not user.is_authenticated or tenant is None:
        return frozenset()

    membership = Membership.objects.filter(user=user, tenant=tenant).select_related("role").first()
    if membership is None:
        return frozenset()

    # Everything is bounded by the tenant's industry: a manpower permission is
    # meaningless — and must not be grantable — in a tenant of another domain.
    catalogue = codenames_for_domain(getattr(tenant, "domain", None))

    if membership.is_owner:
        return catalogue
    if membership.role is None:
        return frozenset()
    # Intersect with the catalogue so a stale codename in the stored JSON can
    # never grant something this build does not define.
    return frozenset(membership.role.permissions or ()) & catalogue


def request_permissions(request: HttpRequest) -> frozenset[str]:
    """Permissions for the request's user in the request's active tenant."""
    cached = getattr(request, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    result = permissions_for(getattr(request, "user", None), getattr(request, "tenant", None))
    setattr(request, _CACHE_ATTR, result)
    return result


def has_permission(request: HttpRequest, codename: str) -> bool:
    return codename in request_permissions(request)


def require_permission(request: HttpRequest, codename: str) -> None:
    """Raise ``PermissionDenied`` unless the user holds `codename`."""
    if not has_permission(request, codename):
        raise PermissionDenied(_("You do not have permission to do that."))


def is_owner(request: HttpRequest) -> bool:
    """True when the user owns the active tenant (not a permission check)."""
    user = getattr(request, "user", None)
    tenant = getattr(request, "tenant", None)
    if user is None or not user.is_authenticated or tenant is None:
        return False
    return Membership.objects.filter(user=user, tenant=tenant, is_owner=True).exists()
