"""Enable + force row-level security on every tenant-scoped manpower table.

Country and Language are deliberately absent: they are shared reference data
with no tenant column (see the module docstring in apps/manpower/models.py).
"""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("manpower", "0001_initial"),
    ]

    operations = [
        *enable_rls("manpower_occupation"),
        *enable_rls("manpower_skill"),
        *enable_rls("manpower_agent"),
        *enable_rls("manpower_accommodation"),
        *enable_rls("manpower_documenttype"),
        *enable_rls("manpower_sponsor"),
        *enable_rls("manpower_worker"),
        *enable_rls("manpower_workerdocument"),
    ]
