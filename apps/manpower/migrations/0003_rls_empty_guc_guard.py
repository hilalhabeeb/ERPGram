"""Re-apply the manpower RLS policies with the empty-string guard.

See apps/tenancy/migrations/0005 for why.
"""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("manpower", "0002_rls"),
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
