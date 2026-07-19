"""Enable + force row-level security on every tenant-scoped table (layer 2)."""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_initial"),
    ]

    operations = [
        *enable_rls("tenancy_company"),
        *enable_rls("tenancy_branch"),
        *enable_rls("tenancy_department"),
    ]
