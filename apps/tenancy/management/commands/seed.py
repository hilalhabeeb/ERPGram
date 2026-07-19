"""Seed two demo tenants with distinct data so tenant isolation is visible.

Idempotent: safe to run repeatedly. Prints the demo credentials at the end.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Membership
from apps.core.tenant import activate_tenant
from apps.tenancy.models import Branch, Company, Department, Tenant

User = get_user_model()

DEMO_PASSWORD = "demo-pass-123"

TENANTS = [
    {
        "slug": "acme",
        "name": "Acme Trading",
        "timezone": "Asia/Bahrain",
        "company": "Acme Trading W.L.L.",
        "branch": ("Manama HQ", "MNM"),
        "department": ("Sales", "SAL"),
        "owner": ("owner@acme.test", "Aisha Al-Sayed"),
        "members": [("sara@acme.test", "Sara Khan"), ("omar@acme.test", "Omar Farooq")],
    },
    {
        "slug": "globex",
        "name": "Globex LLC",
        "timezone": "Asia/Riyadh",
        "company": "Globex International LLC",
        "branch": ("Riyadh Center", "RUH"),
        "department": ("Operations", "OPS"),
        "owner": ("owner@globex.test", "John Rivera"),
        "members": [("lina@globex.test", "Lina Haddad"), ("yusuf@globex.test", "Yusuf Demir")],
    },
]


class Command(BaseCommand):
    help = "Create two demo tenants, each with an owner and two members."

    def handle(self, *args, **options) -> None:
        for spec in TENANTS:
            self._seed_tenant(spec)
        self.stdout.write(self.style.SUCCESS("\nSeed complete. Demo sign-ins:"))
        for spec in TENANTS:
            self.stdout.write(f"  {spec['name']}:")
            self.stdout.write(f"    owner  → {spec['owner'][0]}  /  {DEMO_PASSWORD}")
            for email, _name in spec["members"]:
                self.stdout.write(f"    member → {email}  /  {DEMO_PASSWORD}")

    @transaction.atomic
    def _seed_tenant(self, spec: dict) -> None:
        tenant, _ = Tenant.objects.get_or_create(
            slug=spec["slug"],
            defaults={"name": spec["name"], "timezone": spec["timezone"]},
        )

        owner = self._ensure_user(*spec["owner"])
        Membership.objects.get_or_create(
            user=owner, tenant=tenant, defaults={"is_owner": True, "is_default": True}
        )
        for email, name in spec["members"]:
            member = self._ensure_user(email, name)
            Membership.objects.get_or_create(
                user=member, tenant=tenant, defaults={"is_owner": False, "is_default": True}
            )

        # Tenant-scoped rows: bind the tenant at the DB layer (FORCE RLS).
        with activate_tenant(tenant.id):
            company, _ = Company.objects.get_or_create(
                tenant=tenant, name=spec["company"], defaults={"created_by": owner}
            )
            branch, _ = Branch.objects.get_or_create(
                tenant=tenant,
                company=company,
                name=spec["branch"][0],
                defaults={"code": spec["branch"][1], "created_by": owner},
            )
            Department.objects.get_or_create(
                tenant=tenant,
                branch=branch,
                name=spec["department"][0],
                defaults={"code": spec["department"][1], "created_by": owner},
            )

        self.stdout.write(self.style.SUCCESS(f"  seeded {tenant.name}"))

    def _ensure_user(self, email: str, full_name: str):
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email, password=DEMO_PASSWORD, full_name=full_name, is_active=True
            )
        return user
