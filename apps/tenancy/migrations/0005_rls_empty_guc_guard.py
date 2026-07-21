"""Re-apply the tenancy RLS policies with the empty-string guard.

The original policies cast current_setting('app.tenant_id', true) straight to
uuid. Once that GUC has been SET LOCAL anywhere on a connection, Postgres
reports it as '' rather than NULL for the rest of the session, and ''::uuid
raises. On a pooled connection that turns an unbound query into a 500 instead
of an empty result. apps.core.db now wraps the value in NULLIF; this migration
rewrites the already-created policies to match.
"""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0004_tenant_domain"),
    ]

    operations = [
        *enable_rls("tenancy_company"),
        *enable_rls("tenancy_branch"),
        *enable_rls("tenancy_department"),
    ]
