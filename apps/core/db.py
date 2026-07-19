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

# ``current_setting('app.tenant_id', true)`` uses missing_ok=true so that when
# the GUC is unset the expression is NULL and the row comparison yields NULL —
# i.e. no rows are visible. Fail-closed by default.
_ENABLE_SQL = """
ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy} ON "{table}";
CREATE POLICY {policy} ON "{table}"
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
"""

_DISABLE_SQL = """
DROP POLICY IF EXISTS {policy} ON "{table}";
ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;
"""


def enable_rls(table: str, policy: str = POLICY_NAME) -> list[migrations.RunSQL]:
    """Return migration operations that enable + force tenant RLS on ``table``."""
    return [
        migrations.RunSQL(
            sql=_ENABLE_SQL.format(table=table, policy=policy),
            reverse_sql=_DISABLE_SQL.format(table=table, policy=policy),
        )
    ]
