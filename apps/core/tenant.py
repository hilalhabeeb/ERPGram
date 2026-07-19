"""Thread/async-safe storage for the request's active tenant.

The value is a tenant UUID (as ``str``) or ``None``. It is set by
``TenantMiddleware`` at the start of each request and read by
``TenantScopedModel``'s default manager. ``contextvars`` is used so the value
is isolated per thread *and* per asyncio task.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

_current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant_id(tenant_id: str | None) -> contextvars.Token:
    """Set the active tenant id, returning a token to restore the prior value."""
    return _current_tenant_id.set(str(tenant_id) if tenant_id is not None else None)


def get_current_tenant_id() -> str | None:
    """Return the active tenant id, or ``None`` when unset (e.g. anonymous)."""
    return _current_tenant_id.get()


def reset_current_tenant_id(token: contextvars.Token) -> None:
    """Restore the tenant id captured by an earlier ``set`` call."""
    _current_tenant_id.reset(token)


@contextmanager
def use_tenant(tenant_id: str | None) -> Iterator[None]:
    """Bind the active tenant at the application layer only (contextvar).

    Use this in unit tests that exercise the manager filtering without needing
    the database policy. For code that reads/writes tenant-scoped tables outside
    the request cycle (seed, jobs, admin actions) use ``activate_tenant`` so the
    database GUC is set too — otherwise FORCE ROW LEVEL SECURITY blocks the query.
    """
    token = set_current_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant_id(token)


@contextmanager
def activate_tenant(tenant_id: str) -> Iterator[None]:
    """Bind a tenant for both isolation layers within a transaction.

    Sets the application contextvar *and* the ``app.tenant_id`` Postgres GUC so
    that reads and writes against RLS-protected tables succeed for the current
    tenant. Mirrors what ``TenantMiddleware`` does per request; reuse it in the
    seed command, background jobs, and integration tests.
    """
    # Imported here to keep this module import-light at model-load time.
    from django.db import connection, transaction

    token = set_current_tenant_id(str(tenant_id))
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])
            yield
    finally:
        reset_current_tenant_id(token)
