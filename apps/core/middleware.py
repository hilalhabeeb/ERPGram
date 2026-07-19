"""Request middleware: login enforcement and tenant binding.

``TenantMiddleware`` implements both isolation layers per request:

* Layer 1 (application) — binds the active tenant into the ``contextvars`` store
  read by ``TenantScopedModel.objects``.
* Layer 2 (database) — opens a transaction and sets the ``app.tenant_id`` GUC so
  the Postgres RLS policies apply. ``set_config(..., is_local => true)`` is the
  parameter-safe equivalent of ``SET LOCAL app.tenant_id = '<uuid>'`` and, being
  transaction-local, is automatically cleared when the transaction ends.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve

from apps.core.tenant import reset_current_tenant_id, set_current_tenant_id

# View names reachable without authentication.
PUBLIC_VIEW_NAMES = frozenset(
    {
        "accounts:login",
        "accounts:logout",
        "accounts:password_reset",
        "accounts:password_reset_done",
        "accounts:password_reset_confirm",
        "accounts:password_reset_complete",
        "accounts:activate",
        "set_language",
    }
)

# URL namespaces that manage their own authentication.
PUBLIC_NAMESPACES = frozenset({"admin"})


class LoginRequiredMiddleware:
    """Require login for every view except an explicit public allowlist."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return self.get_response(request)

        try:
            match = resolve(request.path_info)
        except Resolver404:
            # Let Django raise its normal 404 rather than bouncing to login.
            return self.get_response(request)

        if match.view_name in PUBLIC_VIEW_NAMES or match.namespace in PUBLIC_NAMESPACES:
            return self.get_response(request)

        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)


class TenantMiddleware:
    """Bind the active tenant for the request (both isolation layers)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tenant = self._resolve_tenant(request)
        request.tenant = tenant

        if tenant is None:
            token = set_current_tenant_id(None)
            try:
                return self.get_response(request)
            finally:
                reset_current_tenant_id(token)

        token = set_current_tenant_id(str(tenant.id))
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Transaction-local; cleared automatically at COMMIT/ROLLBACK.
                    cursor.execute(
                        "SELECT set_config('app.tenant_id', %s, true)",
                        [str(tenant.id)],
                    )
                return self.get_response(request)
        finally:
            reset_current_tenant_id(token)

    @staticmethod
    def _resolve_tenant(request: HttpRequest):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        # Imported lazily so the app registry is fully populated.
        from apps.accounts.models import Membership

        memberships = Membership.objects.filter(user=user)
        session_key = settings.SESSION_TENANT_KEY
        session_tenant_id = request.session.get(session_key)

        if session_tenant_id:
            membership = (
                memberships.filter(tenant_id=session_tenant_id).select_related("tenant").first()
            )
            if membership is not None and membership.tenant.is_active:
                return membership.tenant

        membership = (
            memberships.filter(is_default=True, tenant__is_active=True)
            .select_related("tenant")
            .first()
            or memberships.filter(tenant__is_active=True).select_related("tenant").first()
        )
        if membership is not None:
            request.session[session_key] = str(membership.tenant_id)
            return membership.tenant

        return None
