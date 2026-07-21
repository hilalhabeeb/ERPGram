"""Reusable migration helpers for tenant row-level-security (layer 2).

Future modules enable database-enforced isolation on a tenant-scoped table with
a single operation in their migration::

    from apps.core.db import enable_rls

    class Migration(migrations.Migration):
        operations = [*enable_rls("myapp_widget")]

Why ``FORCE``: the application connects as the role that owns these tables
(it runs the migrations). A table's owner is exempt from its own RLS policies
unless ``FORCE ROW LEVEL SECURITY`` is set — without it the policy would be a
no-op for exactly the role that matters, and the isolation tests would pass for
the wrong reason. See README ("Database role").
"""

from __future__ import annotations

from django.db import migrations

POLICY_NAME = "tenant_isolation"

# ``current_setting('app.tenant_id', true)`` uses missing_ok=true so an unbound
# request yields NULL and the comparison hides every row — fail-closed.
#
# The NULLIF matters: once the GUC has been SET LOCAL anywhere on a connection,
# Postgres reports it as the empty string rather than NULL for the rest of that
# session, and ''::uuid raises "invalid input syntax for type uuid". Without the
# guard, any unbound query on a reused (pooled) connection errors instead of
# returning nothing — a 500 rather than an empty list.
_ENABLE_SQL = """
ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy} ON "{table}";
CREATE POLICY {policy} ON "{table}"
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""

_DISABLE_SQL = """
DROP POLICY IF EXISTS {policy} ON "{table}";
ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;
"""


def bind_tenant(connection, tenant_id) -> None:
    """Set ``app.tenant_id`` on this connection for the current transaction.

    Pass an empty string to unbind.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            ["" if tenant_id is None else str(tenant_id)],
        )


def each_tenant(apps, schema_editor):
    """Yield every tenant id with that tenant bound on the connection.

    **Data migrations that touch tenant-scoped tables must use this.** RLS applies
    to migrations exactly as it does to requests: with no ``app.tenant_id`` bound,
    every SELECT returns nothing, so a migration reads zero rows, writes nothing,
    and reports success. A migration that moved placement charges into invoices
    did precisely that before this helper existed.

    Usage::

        def forwards(apps, schema_editor):
            for tenant_id in each_tenant(apps, schema_editor):
                Thing.objects.filter(tenant_id=tenant_id).update(...)
    """
    Tenant = apps.get_model("tenancy", "Tenant")
    connection = schema_editor.connection
    try:
        for tenant_id in Tenant.objects.values_list("id", flat=True):
            bind_tenant(connection, tenant_id)
            yield tenant_id
    finally:
        # Leave the connection unbound so later operations start clean.
        bind_tenant(connection, None)


def enable_rls(table: str, policy: str = POLICY_NAME) -> list[migrations.RunSQL]:
    """Return migration operations that enable + force tenant RLS on ``table``."""
    return [
        migrations.RunSQL(
            sql=_ENABLE_SQL.format(table=table, policy=policy),
            reverse_sql=_DISABLE_SQL.format(table=table, policy=policy),
        )
    ]
