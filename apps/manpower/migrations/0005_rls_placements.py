"""Row-level security for the placement tables."""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("manpower", "0004_chargetype_placement_placementcharge_and_more"),
    ]

    operations = [
        *enable_rls("manpower_chargetype"),
        *enable_rls("manpower_placement"),
        *enable_rls("manpower_placementcharge"),
    ]
