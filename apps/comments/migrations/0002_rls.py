"""Row-level security on the comments table.

Without this the ORM manager still scopes reads, but a raw query or a pooled
connection with the wrong GUC could cross tenants. The comment thread carries an
agency's private notes, so it gets the same database-layer guarantee as every
other tenant-scoped table.
"""

from django.db import migrations

from apps.core.db import enable_rls


class Migration(migrations.Migration):
    dependencies = [
        ("comments", "0001_initial"),
    ]

    operations = [
        *enable_rls("comments_comment"),
    ]
