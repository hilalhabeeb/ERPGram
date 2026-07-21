"""Row-level security on every billing table."""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        *enable_rls("billing_service"),
        *enable_rls("billing_termstemplate"),
        *enable_rls("billing_invoice"),
        *enable_rls("billing_invoiceline"),
        *enable_rls("billing_payment"),
    ]
