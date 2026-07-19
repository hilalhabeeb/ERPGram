"""Give every existing tenant the two system roles and assign them.

Before this migration, access was a single ``is_owner`` boolean. Owners keep
implicit full access (see apps.accounts.permissions), so the Owner role exists
mainly so the UI has something to display; the Member role is what actually
changes: it starts with no permissions, which matches the old behaviour where a
non-owner could only read.

Codenames are written literally rather than imported from
apps.core.permissions: a migration must keep describing the past even after the
catalogue changes.
"""

from django.db import migrations

OWNER_PERMISSIONS = [
    "tenancy.manage_structure",
    "tenancy.manage_organization",
    "accounts.manage_members",
    "accounts.manage_roles",
]

SYSTEM_ROLES = [
    ("owner", "Owner", OWNER_PERMISSIONS),
    ("member", "Member", []),
]


def create_roles(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    Role = apps.get_model("accounts", "Role")
    Membership = apps.get_model("accounts", "Membership")

    for tenant in Tenant.objects.all():
        roles = {}
        for slug, name, permissions in SYSTEM_ROLES:
            roles[slug], _created = Role.objects.get_or_create(
                tenant=tenant,
                slug=slug,
                defaults={"name": name, "permissions": permissions, "is_system": True},
            )

        Membership.objects.filter(tenant=tenant, is_owner=True, role__isnull=True).update(
            role=roles["owner"]
        )
        Membership.objects.filter(tenant=tenant, is_owner=False, role__isnull=True).update(
            role=roles["member"]
        )


def drop_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Membership = apps.get_model("accounts", "Membership")
    Membership.objects.update(role=None)
    Role.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_role_membership_role_role_uniq_role_tenant_slug"),
        ("tenancy", "0003_branch_is_active_department_is_active"),
    ]

    operations = [migrations.RunPython(create_roles, drop_roles)]
